from flask import Flask, jsonify, request, render_template
import pandas as pd
import json
import itertools
import os

app = Flask(__name__)

# 配置文件路径 (确保这两个文件和 app.py 在同一级目录)
CSV_PATH = 'generation_statistics.csv'
JSON_PATH = 'data.json'


# --- 新增：页面访问路由 ---
@app.route('/')
def index():
    """当用户访问 http://127.0.0.1:5000 时，渲染并返回前端页面"""
    return render_template('index.html')


# --- 原有的 API 接口保持不变 ---
@app.route('/api/graph-data', methods=['GET'])
def get_graph_data():
    """读取 CSV 和 JSON，进行统计算法处理，返回 D3.js 所需的网络图数据结构"""
    if not os.path.exists(CSV_PATH) or not os.path.exists(JSON_PATH):
        return jsonify({"error": "数据文件不存在，请检查路径"}), 404

    # 1. 处理 CSV 生成 Nodes
    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=['选项/值 (Option/Value)'])

    nodes_dict = {}
    for _, row in df.iterrows():
        name = str(row['选项/值 (Option/Value)']).strip()
        count = int(row['数量 (Count)'])
        category = str(row['层级/类别 (Category)']).strip()

        radius = max(8, count * 4)  # 缩放半径

        if name not in nodes_dict:
            nodes_dict[name] = {
                "id": name,
                "group": category,
                "radius": radius,
                "value": count
            }

    nodes = list(nodes_dict.values())

    # 2. 处理 JSON 提取共现关系生成 Links
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)

    selected_elements = []
    element_pool = plan_data.get('element_pool', {})

    for layer in ['bottom_layer', 'middle_layer', 'top_layer']:
        for item in element_pool.get(layer, []):
            if 'options' in item:
                opt = item['options'][0]
                if isinstance(opt, dict) and 'label' in opt:
                    selected_elements.append(opt['label'])
                elif isinstance(opt, str):
                    selected_elements.append(opt)

    for asset in element_pool.get('visual_assets', []):
        if 'suggestion' in asset:
            selected_elements.append(asset['suggestion'])

    links_dict = {}
    for pair in itertools.combinations(selected_elements, 2):
        source, target = sorted(pair)
        if source in nodes_dict and target in nodes_dict:
            edge_key = f"{source}---{target}"
            if edge_key not in links_dict:
                links_dict[edge_key] = {"source": source, "target": target, "value": 1}
            else:
                links_dict[edge_key]["value"] += 1

    links = list(links_dict.values())

    return jsonify({
        "nodes": nodes,
        "links": links
    })


@app.route('/api/generate-infographic', methods=['POST'])
def generate_infographic():
    """接收前端发送的组装配方，触发后续生成流程"""
    data = request.json
    selected_nodes = data.get('selectedNodes', [])

    if not selected_nodes:
        return jsonify({"status": "error", "message": "未收到任何节点"}), 400

    print(f"✅ 后端接收到生成请求，配方包含: {selected_nodes}")

    return jsonify({
        "status": "success",
        "message": "配方已提交，正在生成信息图...",
        "received_items": len(selected_nodes)
    })


if __name__ == '__main__':
    # 启动后端服务
    app.run(debug=True, port=5000)