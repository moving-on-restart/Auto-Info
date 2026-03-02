from flask import Flask, render_template
import json
from itertools import combinations
from collections import defaultdict

app = Flask(__name__)


class GraphProcessor:
    def __init__(self, min_node_freq=1):
        self.min_node_freq = min_node_freq

    def _extract_features(self, pool_data):
        features = set()
        node_metadata = {}
        layer_order = ["bottom_layer", "middle_layer", "top_layer"]

        for layer_name in layer_order:
            items = pool_data.get(layer_name, [])
            if not isinstance(items, list): continue
            for item in items:
                category = item.get("name", item.get("id", "Unknown"))
                for opt in item.get("options", []):
                    label = opt.get("label") or opt.get("suggestion") or opt.get("value")
                    if not label: continue
                    node_id = f"{category}::{label}"
                    features.add(node_id)
                    node_metadata[node_id] = {
                        "layer": layer_name,
                        "group": category,
                        "label": label,
                        "desc": opt.get("desc", opt.get("text", opt.get("content", "")))
                    }
        return features, node_metadata

    def process(self, raw_data):
        node_freq = defaultdict(int)
        edge_freq = defaultdict(int)
        global_metadata = {}

        for run in raw_data:
            pool = run.get("generated_scheme", {}).get("element_pool", {})
            features, metadata = self._extract_features(pool)
            global_metadata.update(metadata)

            for node in features: node_freq[node] += 1
            # 仅在同一个 run 中出现的节点才计入共现，建立严谨的拓扑关系
            for u, v in combinations(features, 2):
                edge = tuple(sorted([u, v]))
                edge_freq[edge] += 1

        nodes = []
        valid_nodes = set()
        for node_id, freq in node_freq.items():
            if freq >= self.min_node_freq:
                valid_nodes.add(node_id)
                nodes.append({
                    "id": node_id, "name": global_metadata[node_id]["label"],
                    "group": global_metadata[node_id]["group"],
                    "layer": global_metadata[node_id]["layer"],
                    "desc": global_metadata[node_id]["desc"], "val": freq
                })

        links = []
        for (u, v), co_occur in edge_freq.items():
            # 绝对执行：如果不曾出现在同一个 JSON 中 (co_occur == 0)，则彻底阻断连线
            if u in valid_nodes and v in valid_nodes and co_occur > 0:
                jaccard = co_occur / (node_freq[u] + node_freq[v] - co_occur)

                # 算法核心：识别是同层聚类引力，还是跨层关联引力
                layer_u = global_metadata[u]["layer"]
                layer_v = global_metadata[v]["layer"]
                is_intra = (layer_u == layer_v)

                links.append({
                    "source": u, "target": v,
                    "weight": co_occur,
                    "jaccard": round(jaccard, 3),
                    "is_intra": is_intra  # 关键特征：用于前端区分隐形弹簧与显式连线
                })

        return {"nodes": nodes, "links": links}


@app.route('/')
def index():
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception as e:
        return f"<h1 style='color:red;'>读取数据失败: {e}</h1>"

    processor = GraphProcessor(min_node_freq=1)
    graph_data = processor.process(raw_data)

    return render_template('index1.html', graph_data=graph_data)


if __name__ == '__main__':
    app.run(debug=True, port=5000)