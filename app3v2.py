import os
import logging
import time
import numpy as np
import cv2
from flask import Flask, render_template, request, jsonify, send_from_directory

# --- App 3 导入 (数据与信息图) ---
from data_agent_project.analyze_data_with_chart import analyze_data_with_chart
from util.file_utils import process_uploaded_file
from controller.infographic_service import InfographicService

# --- App 2 导入 (视觉与调色板) ---
from services.gemini_image_service import GeminiLangChainService
from services.textservice import transform_to_dino_prompt
from services.Grounding_service import DinoService
from services.sam_service import SamService
from services.palette import palette_service

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['GENERATED_IMAGES_FOLDER'] = 'static/generated_images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_IMAGES_FOLDER'], exist_ok=True)

# ================= 服务初始化 (SERVICE INITIALIZATION) =================

# 1. 数据信息图服务 (来自 App 3)
infographic_agent = InfographicService(output_dir=app.config['GENERATED_IMAGES_FOLDER'])

# 2. 参考图像生成服务 (来自 App 2)
# 注意：这里共用 static/generated_images 目录
reference_gen_service = GeminiLangChainService(output_dir=app.config['GENERATED_IMAGES_FOLDER'])

# 3. 视觉模型 (Dino & SAM)
dino_service = DinoService(api_url="http://100.64.0.1:3045/predict")
SAM_CHECKPOINT_PATH = r"E:\研究生\myproject\sam_model\sam_vit_b_01ec64.pth"  # 请确保此路径正确

try:
    if os.path.exists(SAM_CHECKPOINT_PATH):
        sam_service = SamService(checkpoint_path=SAM_CHECKPOINT_PATH, model_type="vit_b")
        logger.info("SAM Service 启动成功")
    else:
        logger.warning(f"SAM 权重文件未找到: {SAM_CHECKPOINT_PATH}")
        sam_service = None
except Exception as e:
    logger.error(f"SAM 初始化失败: {e}")
    sam_service = None


# ================= 工具函数 (UTILITIES) =================

def save_uploaded_image(file, upload_dir):
    filename = f"{int(time.time())}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    # 返回相对路径供前端使用
    return filepath


def mask_to_polygon(binary_mask):
    """将二进制 mask 转换为多边形点集以进行 SVG 渲染"""
    try:
        if binary_mask is None: return []
        if hasattr(binary_mask, 'cpu'): binary_mask = binary_mask.cpu().detach().numpy()
        binary_mask = np.array(binary_mask)
        if binary_mask.ndim > 2: binary_mask = np.squeeze(binary_mask)

        mask_uint8 = (binary_mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        polygons = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 30: continue
            epsilon = 0.002 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            points = approx.reshape(-1, 2).tolist()
            if len(points) > 2: polygons.append(points)
        return polygons
    except Exception:
        return []


# ================= 路由定义 (ROUTES) =================

@app.route('/')
def index():
    return render_template('indexv2.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    # 如果未自动处理，则手动提供静态文件服务
    return send_from_directory('static', filename)


# --- A部分: 数据流水线 (来自 App 3) ---

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'error': 'No file part'}), 400
    file = request.files['file']
    result_data, error_msg = process_uploaded_file(file, app.config['UPLOAD_FOLDER'])
    if error_msg:
        return jsonify({'status': 'error', 'error': error_msg}), 400
    return jsonify({'status': 'success', **result_data})


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    filepath = data.get('filepath')
    description = data.get('description')
    query = data.get('query')

    if not filepath or not os.path.exists(filepath):
        return jsonify({'status': 'error', 'error': 'File not found'})

    try:
        answer, chart_json = analyze_data_with_chart(filepath, description, query)
        return jsonify({
            'status': 'success',
            'answer': answer,
            'chart': chart_json
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/generate_infographic', methods=['POST'])
def generate_infographic():
    data = request.json
    description = data.get('description')
    query = data.get('query')
    analysis_result = data.get('analysis_result')
    chart_source = data.get('chart_source')

    if not all([description, query, analysis_result]):
        return jsonify({'status': 'error', 'error': 'Missing context data'}), 400

    try:
        image_path = infographic_agent.generate(
            description=description,
            query=query,
            analysis_result=analysis_result,
            chart_json=chart_source
        )
        if image_path:
            # 确保返回前端的是相对于 static 的路径
            filename = os.path.basename(image_path)
            return jsonify({'status': 'success', 'image_url': f"static/generated_images/{filename}"})
        else:
            return jsonify({'status': 'error', 'error': 'Image generation failed'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


# --- B部分: 颜色/参考图流水线 (来自 App 2) ---

@app.route('/generate_ref_image', methods=['POST'])
def generate_ref_image():
    """步骤 4 选项 A: AI 生成参考图像"""
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        aspect_ratio = data.get('aspect_ratio', '1:1')

        if not prompt: return jsonify({'error': 'Prompt is required'}), 400

        logger.info(f"Generating Reference: {prompt}")
        image_path = reference_gen_service.generate(prompt, aspect_ratio=aspect_ratio)

        if image_path:
            return jsonify({'status': 'success', 'image_path': image_path})
        else:
            return jsonify({'error': 'Image generation failed'}), 500
    except Exception as e:
        logger.error(f"Gen Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/upload_ref_image', methods=['POST'])
def upload_ref_image():
    """步骤 4 选项 B: 上传参考图像"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        image_path = save_uploaded_image(file, app.config['UPLOAD_FOLDER'])
        return jsonify({'status': 'success', 'image_path': image_path})
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/process_palette_pipeline', methods=['POST'])
def process_palette_pipeline():
    """步骤 5 & 6: 检测对象 -> 分割 -> 提取调色板"""
    try:
        data = request.get_json()
        image_path = data.get('image_path')
        text_prompt = data.get('text_prompt')

        if not image_path or not os.path.exists(image_path):
            return jsonify({'error': 'Invalid image path'}), 400

        # 1. Prompt 转换
        dino_prompt = transform_to_dino_prompt(text_prompt)

        # 2. Dino 检测
        dino_result = dino_service.detect_objects(image_path, dino_prompt)
        if not dino_result or dino_result.get('count', 0) == 0:
            return jsonify({'status': 'no_objects', 'results': []})

        boxes = [item['box_pixel'] for item in dino_result['results']]
        labels = [item['label'] for item in dino_result['results']]

        # 3. SAM 分割
        seg_results = sam_service.segment_with_boxes(image_path, boxes)

        # 4. 调色板提取
        final_results = palette_service.process_sam_results(image_path, seg_results)

        frontend_data = []
        for item in final_results:
            original_id = item['id']
            mask = None
            if 0 <= original_id < len(seg_results):
                mask = seg_results[original_id].get('segmentation')

            polygons = mask_to_polygon(mask) if mask is not None else []

            current_label = 'object'
            if 0 <= original_id < len(labels):
                current_label = labels[original_id]

            frontend_data.append({
                'id': original_id,
                'label': current_label,
                'polygons': polygons,
                'palette': item.get('palette'),
                'harmony_score': item.get('harmony_score')
            })

        return jsonify({'status': 'success', 'results': frontend_data})

    except Exception as e:
        logger.error(f"Palette Pipeline Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5008)