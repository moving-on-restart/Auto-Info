import os
import logging
import time
from flask import Flask, render_template, request, jsonify, send_from_directory

# --- 导入工具和逻辑 ---
from util.file_utils import process_uploaded_file,save_uploaded_image # 假设你保留了原有的 util

# --- 导入剥离出的业务逻辑 ---
from controller import upload_logic
from controller import data_logic
from controller import vision_logic


# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['GENERATED_IMAGES_FOLDER'] = 'static/generated_images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_IMAGES_FOLDER'], exist_ok=True)


# ================= 路由定义 (ROUTES) =================

@app.route('/')
def index():
    return render_template('indexv3.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


# --- App 3: 数据分析 ---

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'error': 'No file part'}), 400
    file = request.files['file']

    # [修改]：调用新的 controller 逻辑
    result_data, error_msg = upload_logic.handle_csv_upload(file, app.config['UPLOAD_FOLDER'])

    if error_msg:
        return jsonify({'status': 'error', 'error': error_msg}), 400

    # result_data 现在包含了 'description' 字段
    return jsonify({'status': 'success', **result_data})


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        # 调用逻辑层
        answer, chart_json = data_logic.analyze_logic(
            data.get('filepath'),
            data.get('description'),
            data.get('query')
        )
        return jsonify({'status': 'success', 'answer': answer, 'chart': chart_json})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/generate_infographic', methods=['POST'])
def generate_infographic():
    data = request.json
    if not all([data.get('description'), data.get('query'), data.get('analysis_result')]):
        return jsonify({'status': 'error', 'error': 'Missing context data'}), 400

    try:
        # 调用逻辑层
        image_url = data_logic.generate_infographic_logic(
            data.get('description'),
            data.get('query'),
            data.get('analysis_result'),
            data.get('chart_source')
        )
        if image_url:
            return jsonify({'status': 'success', 'image_url': image_url})
        else:
            return jsonify({'status': 'error', 'error': 'Image generation failed'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


# --- App 2: 视觉与调色板 ---

@app.route('/generate_ref_image', methods=['POST'])
def generate_ref_image():
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        if not prompt: return jsonify({'error': 'Prompt is required'}), 400

        # 调用逻辑层
        image_path = vision_logic.generate_ref_image_logic(prompt, data.get('aspect_ratio', '1:1'))

        if image_path:
            return jsonify({'status': 'success', 'image_path': image_path})
        return jsonify({'error': 'Image generation failed'}), 500
    except Exception as e:
        logger.error(f"Gen Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/upload_ref_image', methods=['POST'])
def upload_ref_image():
    try:
        if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '': return jsonify({'error': 'No selected file'}), 400

        # 文件保存逻辑简单，保留在app或util中均可
        image_path = save_uploaded_image(file, app.config['UPLOAD_FOLDER'])
        return jsonify({'status': 'success', 'image_path': image_path})
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/process_palette_pipeline', methods=['POST'])
def process_palette_pipeline():
    """步骤 5 & 6: 核心视觉处理流水线"""
    try:
        data = request.get_json()
        image_path = data.get('image_path')
        text_prompt = data.get('text_prompt')

        # 核心逻辑移交给 logic 层，app.py 不再关心 dino/sam 的具体调用
        results = vision_logic.process_palette_pipeline_logic(image_path, text_prompt)

        if not results:
            return jsonify({'status': 'no_objects', 'results': []})

        return jsonify({'status': 'success', 'results': results})

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Palette Pipeline Error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5008)