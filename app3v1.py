import os
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from data_agent_project.analyze_data_with_chart import analyze_data_with_chart
from util.file_utils import process_uploaded_file

# [新增] 引入图片生成服务
from controller.infographic_service import InfographicService
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
# [新增] 图片生成目录
app.config['GENERATED_IMAGES_FOLDER'] = 'generated_images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
# [新增] 确保图片目录存在
os.makedirs(app.config['GENERATED_IMAGES_FOLDER'], exist_ok=True)

# [新增] 初始化图片服务实例
infographic_agent = InfographicService(output_dir=app.config['GENERATED_IMAGES_FOLDER'])

@app.route('/')
def index():
    return render_template('index.html')


# [新增] 路由：提供生成的图片访问
@app.route('/generated_images/<path:filename>')
def serve_generated_image(filename):
    return send_from_directory(app.config['GENERATED_IMAGES_FOLDER'], filename)


@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    # ... (保持原有的 upload_csv 代码不变) ...
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'error': 'No file part'}), 400
    file = request.files['file']
    result_data, error_msg = process_uploaded_file(file, app.config['UPLOAD_FOLDER'])
    if error_msg:
        return jsonify({'status': 'error', 'error': error_msg}), 400
    return jsonify({'status': 'success', **result_data})


@app.route('/analyze', methods=['POST'])
def analyze():
    # ... (保持原有的 analyze 代码不变) ...
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


# [修改] 生成信息图的路由
@app.route('/generate_infographic', methods=['POST'])
def generate_infographic():
    data = request.json
    description = data.get('description')
    query = data.get('query')
    analysis_result = data.get('analysis_result')
    chart_source = data.get('chart_source')  # [关键] 接收 Vega-Lite JSON
    print(f"DEBUG: 接收到的图表数据长度: {len(str(chart_source)) if chart_source else 0} 字符")

    # 简单校验
    if not all([description, query, analysis_result]):
         return jsonify({'status': 'error', 'error': 'Missing context data'}), 400

    try:
        # 调用 Service
        image_path = infographic_agent.generate(
            description=description,
            query=query,
            analysis_result=analysis_result,
            chart_json=chart_source # 传入图表代码
        )

        if image_path:
            filename = os.path.basename(image_path)
            image_url = f"/generated_images/{filename}"
            return jsonify({'status': 'success', 'image_url': image_url})
        else:
             return jsonify({'status': 'error', 'error': 'Image generation failed'}), 500

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True, port=5008)