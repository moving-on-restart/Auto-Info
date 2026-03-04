import logging
import json
import os
import copy
import time
import math
import concurrent.futures
import threading
import uuid
from collections import defaultdict
from itertools import combinations
from flask import current_app

# 导入您提供的分析控制器 (确保它位于 controller 目录下)
from app3.controller.generate_info_data_controller import generate_visualization_elements
# 导入原有的生图服务
from app3.services.gemini_image_service import GeminiLangChainService

logger = logging.getLogger(__name__)

# 初始化生图服务 (图片保存到 static/generated_assets 以便前端访问)
ASSETS_DIR = "static/generated_assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
image_service = GeminiLangChainService(output_dir=ASSETS_DIR)

FORCE_GRAPH_DEFAULT_SAMPLE_COUNT = 50
FORCE_GRAPH_MAX_SAMPLE_COUNT = 80
FORCE_GRAPH_MAX_WORKERS = 6
_LAYER_ORDER = ["bottom_layer", "middle_layer", "top_layer"]
_FORCE_LAYOUT_MODE = "force"
_SOM_LAYOUT_MODE = "som"
_APP3_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNS_JSON_DIR = os.path.join(_APP3_BASE_DIR, "static", "json")
_SOM_TEXT_MODEL_NAME = "shibing624/text2vec-base-chinese"
_SOM_TEXT_MODEL = None
_SOM_TEXT_MODEL_LOCK = threading.Lock()
_SOM_LAYER_ORDER_PRIORITY = {
    "bottom_layer": 1,
    "middle_layer": 2,
    "top_layer": 3,
    "title_layer": 4,
    "title_scheme": 4,
}

_FORCE_GRAPH_JOBS = {}
_FORCE_GRAPH_JOBS_LOCK = threading.Lock()
_FORCE_GRAPH_JOB_TTL_SECONDS = 30 * 60

os.makedirs(_RUNS_JSON_DIR, exist_ok=True)


def _normalize_layout_mode(layout_mode):
    mode = str(layout_mode or _FORCE_LAYOUT_MODE).strip().lower()
    return _SOM_LAYOUT_MODE if mode == _SOM_LAYOUT_MODE else _FORCE_LAYOUT_MODE


def _persist_sample_runs(raw_runs, layout_mode, target_count, query=None, job_id=None):
    if not isinstance(raw_runs, list) or not raw_runs:
        return None

    normalized_mode = _normalize_layout_mode(layout_mode)
    os.makedirs(_RUNS_JSON_DIR, exist_ok=True)

    timestamp_compact = time.strftime("%Y%m%d_%H%M%S")
    job_suffix = str(job_id).strip() if job_id else uuid.uuid4().hex[:8]
    filename = f"{normalized_mode}_runs_{int(target_count or len(raw_runs))}_{timestamp_compact}_{job_suffix}.json"
    absolute_path = os.path.join(_RUNS_JSON_DIR, filename)

    payload = {
        "layout_mode": normalized_mode,
        "target_count": int(target_count or len(raw_runs)),
        "actual_count": len(raw_runs),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "query": str(query or ""),
        "runs": raw_runs,
    }

    with open(absolute_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)

    return {
        "filename": filename,
        "absolute_path": absolute_path,
        "web_path": f"/static/json/{filename}",
    }


def _rgb_triplet_to_hex(color_triplet):
    """Convert [r, g, b] into #RRGGBB."""
    if not isinstance(color_triplet, (list, tuple)) or len(color_triplet) < 3:
        return None
    try:
        r = max(0, min(255, int(color_triplet[0])))
        g = max(0, min(255, int(color_triplet[1])))
        b = max(0, min(255, int(color_triplet[2])))
        return f"#{r:02X}{g:02X}{b:02X}"
    except (TypeError, ValueError):
        return None


def _build_palette_info_text(color_scheme_selection):
    """
    Support both:
    1) legacy string color scheme,
    2) structured palette object selected from extracted palettes.
    """
    if isinstance(color_scheme_selection, dict):
        source_label = color_scheme_selection.get("source_label", "未命名对象")
        option_label = color_scheme_selection.get("label", "调色板方案")
        palette = color_scheme_selection.get("palette") or []
        harmony_score = color_scheme_selection.get("harmony_score")
        harmony_text = f"{harmony_score:.3f}" if isinstance(harmony_score, (int, float)) else "N/A"

        hex_list = []
        for color in palette:
            hex_color = _rgb_triplet_to_hex(color)
            if hex_color:
                hex_list.append(hex_color)

        if hex_list:
            return f"来源对象: {source_label}; 方案: {option_label}; 色值: {', '.join(hex_list)}; 和谐度: {harmony_text}"
        return f"来源对象: {source_label}; 方案: {option_label}; 和谐度: {harmony_text}"

    return f"未提供提取调色板，按配色偏好“{color_scheme_selection}”生成。"


def _normalize_sample_count(sample_count):
    if sample_count is None:
        return FORCE_GRAPH_DEFAULT_SAMPLE_COUNT
    try:
        parsed = int(sample_count)
    except (TypeError, ValueError):
        return FORCE_GRAPH_DEFAULT_SAMPLE_COUNT
    return max(1, min(FORCE_GRAPH_MAX_SAMPLE_COUNT, parsed))


def _cleanup_expired_force_graph_jobs():
    now_ts = time.time()
    expired_job_ids = []
    with _FORCE_GRAPH_JOBS_LOCK:
        for job_id, job in _FORCE_GRAPH_JOBS.items():
            updated_at = float(job.get("updated_at", job.get("created_at", now_ts)))
            if now_ts - updated_at > _FORCE_GRAPH_JOB_TTL_SECONDS:
                expired_job_ids.append(job_id)
        for job_id in expired_job_ids:
            _FORCE_GRAPH_JOBS.pop(job_id, None)


def _create_force_graph_job(sample_count, layout_mode=_FORCE_LAYOUT_MODE):
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    target_count = _normalize_sample_count(sample_count)
    normalized_mode = _normalize_layout_mode(layout_mode)
    job = {
        "job_id": job_id,
        "layout_mode": normalized_mode,
        "status": "queued",
        "message": "Queued",
        "progress": 0,
        "target_count": target_count,
        "attempted_count": 0,
        "max_attempts": max(target_count, target_count * 2),
        "success_count": 0,
        "failed_count": 0,
        "result": None,
        "error": None,
        "created_at": now_ts,
        "updated_at": now_ts,
    }
    with _FORCE_GRAPH_JOBS_LOCK:
        _FORCE_GRAPH_JOBS[job_id] = job
    return job_id


def _update_force_graph_job(job_id, **fields):
    with _FORCE_GRAPH_JOBS_LOCK:
        job = _FORCE_GRAPH_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = time.time()


def get_force_graph_job_status(job_id):
    _cleanup_expired_force_graph_jobs()
    with _FORCE_GRAPH_JOBS_LOCK:
        job = _FORCE_GRAPH_JOBS.get(job_id)
        if not job:
            return None
        return copy.deepcopy(job)


def _extract_option_label_desc(option):
    if isinstance(option, dict):
        label = (
            option.get("label")
            or option.get("suggestion")
            or option.get("name")
            or option.get("value")
        )
        desc = (
            option.get("desc")
            or option.get("description")
            or option.get("text")
            or option.get("content")
            or option.get("suggestion")
            or ""
        )
        label_text = str(label).strip() if label is not None else ""
        desc_text = str(desc).strip() if desc is not None else ""
        return label_text or None, desc_text

    if option is None:
        return None, ""

    label_text = str(option).strip()
    return label_text or None, ""


def _extract_features_from_pool(pool_data):
    features = set()
    node_metadata = {}

    if not isinstance(pool_data, dict):
        return features, node_metadata

    for layer_name in _LAYER_ORDER:
        items = pool_data.get(layer_name, [])
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            group_id = str(item.get("id") or item.get("name") or "unknown_group")
            group_name = str(item.get("name") or group_id)
            options = item.get("options") or []
            if not isinstance(options, list):
                continue

            for option in options:
                label, desc = _extract_option_label_desc(option)
                if not label:
                    continue

                node_id = f"{layer_name}::{group_id}::{label}"
                features.add(node_id)
                node_metadata[node_id] = {
                    "layer": layer_name,
                    "group_id": group_id,
                    "group": group_name,
                    "label": label,
                    "desc": desc,
                    "option_payload": copy.deepcopy(option) if isinstance(option, dict) else {"label": label},
                    "is_palette_node": group_id == "color_scheme",
                }

    return features, node_metadata


def _build_force_graph(raw_runs, min_node_freq=1):
    node_freq = defaultdict(int)
    edge_freq = defaultdict(int)
    global_metadata = {}

    for run in raw_runs:
        pool = run.get("generated_scheme", {}).get("element_pool", {})
        features, metadata = _extract_features_from_pool(pool)
        global_metadata.update(metadata)

        for node in features:
            node_freq[node] += 1

        for u, v in combinations(sorted(features), 2):
            edge_freq[(u, v)] += 1

    nodes = []
    valid_nodes = set()
    layer_rank = {layer: idx for idx, layer in enumerate(_LAYER_ORDER)}
    for node_id, freq in node_freq.items():
        if freq < min_node_freq:
            continue

        meta = global_metadata.get(node_id, {})
        valid_nodes.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "name": meta.get("label", node_id),
                "group": meta.get("group", "Unknown"),
                "group_id": meta.get("group_id", "unknown_group"),
                "layer": meta.get("layer", "top_layer"),
                "desc": meta.get("desc", ""),
                "val": freq,
                "option_payload": meta.get("option_payload", {}),
                "is_palette_node": bool(meta.get("is_palette_node", False)),
            }
        )

    nodes.sort(
        key=lambda n: (
            layer_rank.get(n.get("layer"), 99),
            n.get("group_id", ""),
            -int(n.get("val", 0)),
            n.get("name", ""),
        )
    )

    links = []
    for (u, v), co_occur in edge_freq.items():
        if u not in valid_nodes or v not in valid_nodes or co_occur <= 0:
            continue

        denom = node_freq[u] + node_freq[v] - co_occur
        jaccard = (co_occur / denom) if denom > 0 else 0.0
        layer_u = global_metadata.get(u, {}).get("layer")
        layer_v = global_metadata.get(v, {}).get("layer")
        is_intra = layer_u == layer_v

        links.append(
            {
                "source": u,
                "target": v,
                "weight": co_occur,
                "jaccard": round(jaccard, 4),
                "is_intra": is_intra,
            }
        )

    return {"nodes": nodes, "links": links}


def _build_group_defaults(nodes):
    temp = {layer: {} for layer in _LAYER_ORDER}

    for node in nodes:
        layer = node.get("layer")
        group_id = node.get("group_id")
        node_id = node.get("id")
        score = int(node.get("val", 0))
        if layer not in temp or not group_id or not node_id:
            continue

        existing = temp[layer].get(group_id)
        if existing is None or score > existing["score"]:
            temp[layer][group_id] = {"id": node_id, "score": score}

    return {layer: {gid: payload["id"] for gid, payload in groups.items()} for layer, groups in temp.items()}


def _extract_option_uid_label_desc(option):
    if isinstance(option, dict):
        uid = (
            option.get("value")
            or option.get("style")
            or option.get("category")
            or option.get("keywords")
            or option.get("label")
            or option.get("suggestion")
            or option.get("name")
        )
        label = (
            option.get("label")
            or option.get("suggestion")
            or option.get("value")
            or option.get("style")
            or option.get("category")
            or option.get("keywords")
            or option.get("name")
        )
        desc = (
            option.get("desc")
            or option.get("description")
            or option.get("text")
            or option.get("content")
            or option.get("suggestion")
            or ""
        )
        uid_text = str(uid).strip() if uid is not None else ""
        label_text = str(label).strip() if label is not None else ""
        desc_text = str(desc).strip() if desc is not None else ""
        payload = copy.deepcopy(option)
        if not uid_text:
            uid_text = label_text
        return uid_text, label_text, desc_text, payload

    if option is None:
        return "", "", "", {}

    text = str(option).strip()
    return text, text, "", {"label": text}


def _extract_elements_and_rules_for_som(raw_runs):
    try:
        import networkx as nx
    except Exception as import_error:
        raise RuntimeError("networkx is required for SOM mode.") from import_error

    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("raw_runs must be a non-empty list")

    elements = {}
    run_ids = []
    run_to_elements = defaultdict(list)

    for idx, run in enumerate(raw_runs, start=1):
        run_id = run.get("run_id") if isinstance(run, dict) else None
        if run_id is None:
            run_id = idx
        run_ids.append(run_id)

        pool = run.get("generated_scheme", {}).get("element_pool", {}) if isinstance(run, dict) else {}
        if not isinstance(pool, dict):
            continue

        for layer_name, categories in pool.items():
            if not isinstance(categories, list):
                continue
            layer_text = str(layer_name or "").strip() or "top_layer"

            for cat in categories:
                if not isinstance(cat, dict):
                    continue

                group_id = str(cat.get("id") or cat.get("name") or "unknown_group").strip() or "unknown_group"
                category_name = str(cat.get("name") or group_id).strip() or group_id
                options = cat.get("options") or []
                if not isinstance(options, list):
                    continue

                for option in options:
                    uid_text, label_text, desc_text, option_payload = _extract_option_uid_label_desc(option)
                    if not uid_text and not label_text:
                        continue
                    if not uid_text:
                        uid_text = label_text
                    if not label_text:
                        label_text = uid_text

                    global_id = f"{layer_text}::{group_id}::{uid_text}"

                    if global_id not in elements:
                        elements[global_id] = {
                            "id": global_id,
                            "layer": layer_text,
                            "category": category_name,
                            "group": category_name,
                            "group_id": group_id,
                            "label": label_text,
                            "name": label_text,
                            "desc": desc_text,
                            "count": 0,
                            "val": 0,
                            "runs": set(),
                            "option_payload": option_payload if isinstance(option_payload, dict) else {},
                            "is_palette_node": group_id == "color_scheme",
                        }

                    elements[global_id]["runs"].add(run_id)
                    elements[global_id]["count"] += 1
                    elements[global_id]["val"] += 1
                    run_to_elements[run_id].append(global_id)

    total_runs = len(run_ids)
    if total_runs == 0:
        raise ValueError("No valid runs were provided for SOM generation.")

    for value in elements.values():
        value["runs"] = list(value["runs"])

    G = nx.Graph()
    for node_id in elements:
        G.add_node(node_id)

    for _, elem_ids in run_to_elements.items():
        for e1, e2 in combinations(elem_ids, 2):
            if G.has_edge(e1, e2):
                G[e1][e2]["weight"] += 1
            else:
                G.add_edge(e1, e2, weight=1)

    if len(G.nodes) > 0 and len(G.edges) > 0:
        pagerank = nx.pagerank(G, weight="weight")
    else:
        pagerank = {}
    degree_cent = nx.degree_centrality(G) if len(G.nodes) > 0 else {}

    links = []
    for e1, e2 in G.edges():
        co_occur = int(G[e1][e2]["weight"])
        p_a = elements[e1]["count"] / total_runs if total_runs > 0 else 0
        p_b = elements[e2]["count"] / total_runs if total_runs > 0 else 0
        p_ab = co_occur / total_runs if total_runs > 0 else 0
        denom = p_a * p_b
        if denom <= 0:
            continue
        lift = p_ab / denom
        layer1 = elements[e1]["layer"]
        layer2 = elements[e2]["layer"]
        if layer1 != layer2 and lift > 1.2:
            links.append(
                {
                    "source": e1,
                    "target": e2,
                    "lift": round(float(lift), 3),
                    "co_occur": co_occur,
                }
            )

    links.sort(key=lambda item: (-float(item.get("lift", 0)), -int(item.get("co_occur", 0))))
    return elements, run_ids, pagerank, degree_cent, links


def _l2_normalize_rows(matrix):
    try:
        import numpy as np
    except Exception as import_error:
        raise RuntimeError("numpy is required for SOM mode.") from import_error

    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)


def _get_som_text_model():
    global _SOM_TEXT_MODEL
    if _SOM_TEXT_MODEL is not None:
        return _SOM_TEXT_MODEL

    with _SOM_TEXT_MODEL_LOCK:
        if _SOM_TEXT_MODEL is not None:
            return _SOM_TEXT_MODEL
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as import_error:
            raise RuntimeError("sentence-transformers is required for SOM mode.") from import_error
        _SOM_TEXT_MODEL = SentenceTransformer(_SOM_TEXT_MODEL_NAME)
        return _SOM_TEXT_MODEL


def _train_advanced_som(elements, run_ids, pagerank, degree_cent):
    try:
        import numpy as np
        from minisom import MiniSom
        from scipy.spatial.distance import cdist
        from scipy.optimize import linear_sum_assignment
    except Exception as import_error:
        raise RuntimeError("SOM mode requires minisom, scipy, and numpy.") from import_error

    element_list = list(elements.values())
    if not element_list:
        return []

    model = _get_som_text_model()
    texts = [f"{e.get('category', '')} {e.get('label', '')} {e.get('desc', '')}".strip() for e in element_list]
    nlp_vectors = np.array(model.encode(texts))
    nlp_vectors = _l2_normalize_rows(nlp_vectors)

    run_sets = [set(e.get("runs", [])) for e in element_list]
    co_vectors = np.array(
        [[1.0 if run_id in run_set else 0.0 for run_id in run_ids] for run_set in run_sets],
        dtype=float,
    )
    co_vectors = _l2_normalize_rows(co_vectors)

    layers = sorted({str(e.get("layer") or "top_layer") for e in element_list}, key=lambda x: (_SOM_LAYER_ORDER_PRIORITY.get(x, 99), x))
    layer_vectors = np.array([[1.0 if e.get("layer") == layer else 0.0 for layer in layers] for e in element_list], dtype=float)

    categories = sorted({str(e.get("category") or "unknown") for e in element_list})
    category_vectors = np.array(
        [[1.0 if e.get("category") == category else 0.0 for category in categories] for e in element_list],
        dtype=float,
    )

    pr_vec = np.array([float(pagerank.get(e.get("id"), 0.0)) for e in element_list]).reshape(-1, 1)
    deg_vec = np.array([float(degree_cent.get(e.get("id"), 0.0)) for e in element_list]).reshape(-1, 1)
    graph_vectors = np.hstack([pr_vec, deg_vec])
    graph_vectors = graph_vectors / (np.linalg.norm(graph_vectors, axis=0, keepdims=True) + 1e-9)

    combined_vectors = np.hstack(
        [
            0.35 * nlp_vectors,
            0.25 * co_vectors,
            0.20 * category_vectors,
            0.10 * layer_vectors,
            0.10 * graph_vectors,
        ]
    )

    num_elements = len(element_list)
    grid_size = int(math.ceil(math.sqrt(num_elements))) + 5
    num_grids = grid_size * grid_size

    som = MiniSom(
        grid_size,
        grid_size,
        combined_vectors.shape[1],
        sigma=1.2,
        learning_rate=0.5,
        topology="hexagonal",
        random_seed=42,
    )

    try:
        som.pca_weights_init(combined_vectors)
    except Exception:
        som.random_weights_init(combined_vectors)
    som.train_batch(combined_vectors, 5000)

    u_matrix = som.distance_map()
    som_nodes = [
        {"x": x, "y": y, "u_value": float(u_matrix[x][y]), "elements": []}
        for x in range(grid_size)
        for y in range(grid_size)
    ]

    grid_weights = som.get_weights().reshape(num_grids, -1)
    distances = cdist(combined_vectors, grid_weights, metric="cosine")
    row_ind, col_ind = linear_sum_assignment(distances)

    for elem_idx, grid_idx in zip(row_ind, col_ind):
        som_nodes[int(grid_idx)]["elements"].append(element_list[int(elem_idx)])

    return som_nodes


def _build_group_defaults_from_elements(elements_dict):
    temp = {layer: {} for layer in _LAYER_ORDER}
    for elem in elements_dict.values():
        layer = elem.get("layer")
        if layer not in temp:
            continue
        group_id = elem.get("group_id")
        node_id = elem.get("id")
        score = int(elem.get("count", 0))
        if not group_id or not node_id:
            continue
        existing = temp[layer].get(group_id)
        if existing is None or score > existing["score"]:
            temp[layer][group_id] = {"id": node_id, "score": score}
    return {layer: {gid: payload["id"] for gid, payload in groups.items()} for layer, groups in temp.items()}


def _extract_single_run_payload(entry):
    if not isinstance(entry, dict):
        return None

    generated_scheme = entry.get("generated_scheme")
    if isinstance(generated_scheme, dict) and isinstance(generated_scheme.get("element_pool"), dict):
        return generated_scheme

    plan_obj = entry.get("plan")
    if isinstance(plan_obj, dict) and isinstance(plan_obj.get("element_pool"), dict):
        return plan_obj

    if isinstance(entry.get("element_pool"), dict):
        return {
            "analysis_report": entry.get("analysis_report", {}),
            "element_pool": entry.get("element_pool"),
        }

    return None


def normalize_uploaded_runs_payload(payload):
    if isinstance(payload, dict):
        for key in ("runs", "raw_runs", "data", "items", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break
        else:
            payload = [payload]

    if not isinstance(payload, list):
        raise ValueError("Uploaded JSON must be a list or an object containing a list in runs/raw_runs/data.")

    raw_runs = []
    for idx, entry in enumerate(payload, start=1):
        scheme = _extract_single_run_payload(entry)
        if not scheme:
            continue

        run_id = entry.get("run_id") if isinstance(entry, dict) else None
        if run_id is None:
            run_id = idx
        timestamp = entry.get("timestamp") if isinstance(entry, dict) else None
        if not timestamp:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        raw_runs.append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "generated_scheme": scheme,
            }
        )

    if not raw_runs:
        raise ValueError("No valid runs found. Each run must include generated_scheme.element_pool or element_pool.")

    return raw_runs


def generate_force_graph_bundle_from_runs(raw_runs):
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("raw_runs must be a non-empty list")

    graph_data = _build_force_graph(raw_runs, min_node_freq=1)
    if not graph_data.get("nodes"):
        raise ValueError("No force-graph nodes could be built from uploaded runs.")
    group_defaults = _build_group_defaults(graph_data.get("nodes", []))

    return {
        "target_count": len(raw_runs),
        "success_count": len(raw_runs),
        "failed_count": 0,
        "attempted_count": len(raw_runs),
        "max_attempts": len(raw_runs),
        "graph_data": graph_data,
        "group_defaults": group_defaults,
        "layout_mode": _FORCE_LAYOUT_MODE,
    }


def generate_som_bundle_from_runs(raw_runs):
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("raw_runs must be a non-empty list")

    elements, run_ids, pagerank, degree_cent, links = _extract_elements_and_rules_for_som(raw_runs)
    if not elements:
        raise ValueError("No SOM elements could be built from uploaded runs.")

    som_nodes = _train_advanced_som(elements, run_ids, pagerank, degree_cent)
    if not som_nodes:
        raise ValueError("SOM training produced no nodes.")

    group_defaults = _build_group_defaults_from_elements(elements)

    return {
        "target_count": len(raw_runs),
        "success_count": len(raw_runs),
        "failed_count": 0,
        "attempted_count": len(raw_runs),
        "max_attempts": len(raw_runs),
        "graph_data": {
            "nodes": som_nodes,
            "links": links,
        },
        "group_defaults": group_defaults,
        "layout_mode": _SOM_LAYOUT_MODE,
    }


def _generate_single_plan_worker(description, query, analysis_result, chart_str):
    try:
        plan_json = generate_visualization_elements(
            user_query=query,
            table_schema=analysis_result,
            table_description=description,
            vegalite_code=chart_str,
        )
        if isinstance(plan_json, dict) and isinstance(plan_json.get("element_pool"), dict):
            return plan_json
        return None
    except Exception as e:
        logger.warning(f"Force graph single plan generation failed: {e}")
        return None


def _sample_runs_for_graph_generation(
    description,
    query,
    analysis_result,
    chart_json,
    sample_count,
    progress_callback=None,
    mode_label="force-graph",
    layout_mode=_FORCE_LAYOUT_MODE,
    job_id=None,
):
    target_count = _normalize_sample_count(sample_count)
    if not query:
        raise ValueError("Query is required for graph planning.")

    chart_str = json.dumps(chart_json, ensure_ascii=False) if isinstance(chart_json, dict) else "{}"
    if len(chart_str) > 4000:
        chart_str = chart_str[:4000] + "...(truncated)"

    worker_count = min(FORCE_GRAPH_MAX_WORKERS, target_count)
    raw_runs = []
    failed_count = 0
    attempts = 0
    max_attempts = max(target_count, target_count * 2)
    completed_attempts = 0

    if callable(progress_callback):
        progress_callback(
            {
                "stage": "sampling",
                "progress": 2,
                "message": f"Starting {mode_label} scheme sampling...",
                "attempted_count": completed_attempts,
                "max_attempts": max_attempts,
                "success_count": len(raw_runs),
                "failed_count": failed_count,
                "target_count": target_count,
            }
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        while len(raw_runs) < target_count and attempts < max_attempts:
            remaining = target_count - len(raw_runs)
            budget = max_attempts - attempts
            batch_size = min(worker_count, remaining, budget)
            if batch_size <= 0:
                break

            futures = [
                executor.submit(
                    _generate_single_plan_worker,
                    description,
                    query,
                    analysis_result,
                    chart_str,
                )
                for _ in range(batch_size)
            ]
            attempts += batch_size

            for future in concurrent.futures.as_completed(futures):
                completed_attempts += 1
                plan_json = future.result()
                if plan_json is None:
                    failed_count += 1
                else:
                    raw_runs.append(
                        {
                            "run_id": len(raw_runs) + 1,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "generated_scheme": plan_json,
                        }
                    )

                if callable(progress_callback):
                    ratio = min(1.0, completed_attempts / max_attempts) if max_attempts > 0 else 1.0
                    progress_callback(
                        {
                            "stage": "sampling",
                            "progress": min(90, int(2 + ratio * 86)),
                            "message": f"Sampling plans... success {len(raw_runs)}/{target_count}, failed {failed_count}",
                            "attempted_count": completed_attempts,
                            "max_attempts": max_attempts,
                            "success_count": len(raw_runs),
                            "failed_count": failed_count,
                            "target_count": target_count,
                        }
                    )

                if len(raw_runs) >= target_count:
                    break

    if not raw_runs:
        raise RuntimeError(f"All {mode_label} plan generations failed.")

    saved_runs_json = None
    try:
        saved_runs_json = _persist_sample_runs(
            raw_runs=raw_runs,
            layout_mode=layout_mode,
            target_count=target_count,
            query=query,
            job_id=job_id,
        )
    except Exception as e:
        logger.warning(f"Failed to persist sampled runs JSON: {e}")

    return {
        "target_count": target_count,
        "raw_runs": raw_runs,
        "failed_count": failed_count,
        "completed_attempts": completed_attempts,
        "max_attempts": max_attempts,
        "saved_runs_json": saved_runs_json,
    }


def generate_force_graph_bundle(
    description,
    query,
    analysis_result,
    chart_json,
    sample_count=FORCE_GRAPH_DEFAULT_SAMPLE_COUNT,
    progress_callback=None,
    job_id=None,
):
    sample_result = _sample_runs_for_graph_generation(
        description=description,
        query=query,
        analysis_result=analysis_result,
        chart_json=chart_json,
        sample_count=sample_count,
        progress_callback=progress_callback,
        mode_label="force-graph",
        layout_mode=_FORCE_LAYOUT_MODE,
        job_id=job_id,
    )

    raw_runs = sample_result["raw_runs"]
    target_count = sample_result["target_count"]
    failed_count = sample_result["failed_count"]
    completed_attempts = sample_result["completed_attempts"]
    max_attempts = sample_result["max_attempts"]
    saved_runs_json = sample_result.get("saved_runs_json")

    if callable(progress_callback):
        progress_callback(
            {
                "stage": "building_graph",
                "progress": 94,
                "message": "Building force graph structure...",
                "attempted_count": completed_attempts,
                "max_attempts": max_attempts,
                "success_count": len(raw_runs),
                "failed_count": failed_count,
                "target_count": target_count,
            }
        )

    graph_data = _build_force_graph(raw_runs, min_node_freq=1)
    group_defaults = _build_group_defaults(graph_data.get("nodes", []))

    bundle = {
        "target_count": target_count,
        "success_count": len(raw_runs),
        "failed_count": failed_count,
        "attempted_count": completed_attempts,
        "max_attempts": max_attempts,
        "graph_data": graph_data,
        "group_defaults": group_defaults,
        "layout_mode": _FORCE_LAYOUT_MODE,
        "saved_runs_json": saved_runs_json,
    }

    if callable(progress_callback):
        progress_callback(
            {
                "stage": "completed",
                "progress": 100,
                "message": "Force graph generation completed.",
                "attempted_count": completed_attempts,
                "max_attempts": max_attempts,
                "success_count": len(raw_runs),
                "failed_count": failed_count,
                "target_count": target_count,
            }
        )

    return bundle


def generate_som_bundle(
    description,
    query,
    analysis_result,
    chart_json,
    sample_count=FORCE_GRAPH_DEFAULT_SAMPLE_COUNT,
    progress_callback=None,
    job_id=None,
):
    sample_result = _sample_runs_for_graph_generation(
        description=description,
        query=query,
        analysis_result=analysis_result,
        chart_json=chart_json,
        sample_count=sample_count,
        progress_callback=progress_callback,
        mode_label="som-graph",
        layout_mode=_SOM_LAYOUT_MODE,
        job_id=job_id,
    )

    raw_runs = sample_result["raw_runs"]
    target_count = sample_result["target_count"]
    failed_count = sample_result["failed_count"]
    completed_attempts = sample_result["completed_attempts"]
    max_attempts = sample_result["max_attempts"]
    saved_runs_json = sample_result.get("saved_runs_json")

    if callable(progress_callback):
        progress_callback(
            {
                "stage": "building_graph",
                "progress": 94,
                "message": "Building SOM graph structure...",
                "attempted_count": completed_attempts,
                "max_attempts": max_attempts,
                "success_count": len(raw_runs),
                "failed_count": failed_count,
                "target_count": target_count,
            }
        )

    elements, run_ids, pagerank, degree_cent, links = _extract_elements_and_rules_for_som(raw_runs)
    if not elements:
        raise RuntimeError("No SOM elements could be built from sampled runs.")

    som_nodes = _train_advanced_som(elements, run_ids, pagerank, degree_cent)
    if not som_nodes:
        raise RuntimeError("SOM training produced no nodes.")
    group_defaults = _build_group_defaults_from_elements(elements)

    bundle = {
        "target_count": target_count,
        "success_count": len(raw_runs),
        "failed_count": failed_count,
        "attempted_count": completed_attempts,
        "max_attempts": max_attempts,
        "graph_data": {
            "nodes": som_nodes,
            "links": links,
        },
        "group_defaults": group_defaults,
        "layout_mode": _SOM_LAYOUT_MODE,
        "saved_runs_json": saved_runs_json,
    }

    if callable(progress_callback):
        progress_callback(
            {
                "stage": "completed",
                "progress": 100,
                "message": "SOM graph generation completed.",
                "attempted_count": completed_attempts,
                "max_attempts": max_attempts,
                "success_count": len(raw_runs),
                "failed_count": failed_count,
                "target_count": target_count,
            }
        )

    return bundle


def _run_force_graph_job(job_id, description, query, analysis_result, chart_json, sample_count, layout_mode):
    normalized_mode = _normalize_layout_mode(layout_mode)

    def on_progress(payload):
        _update_force_graph_job(
            job_id,
            status="running",
            progress=int(payload.get("progress", 0)),
            message=payload.get("message", "Running"),
            attempted_count=int(payload.get("attempted_count", 0)),
            max_attempts=int(payload.get("max_attempts", 0)),
            success_count=int(payload.get("success_count", 0)),
            failed_count=int(payload.get("failed_count", 0)),
            target_count=int(payload.get("target_count", _normalize_sample_count(sample_count))),
        )

    try:
        start_msg = "SOM graph job started" if normalized_mode == _SOM_LAYOUT_MODE else "Force graph job started"
        _update_force_graph_job(job_id, status="running", progress=1, message=start_msg, layout_mode=normalized_mode)

        if normalized_mode == _SOM_LAYOUT_MODE:
            bundle = generate_som_bundle(
                description=description,
                query=query,
                analysis_result=analysis_result,
                chart_json=chart_json,
                sample_count=sample_count,
                progress_callback=on_progress,
                job_id=job_id,
            )
        else:
            bundle = generate_force_graph_bundle(
                description=description,
                query=query,
                analysis_result=analysis_result,
                chart_json=chart_json,
                sample_count=sample_count,
                progress_callback=on_progress,
                job_id=job_id,
            )

        _update_force_graph_job(
            job_id,
            status="completed",
            progress=100,
            message="Completed",
            result=bundle,
            error=None,
            layout_mode=normalized_mode,
            attempted_count=int(bundle.get("attempted_count", 0)),
            max_attempts=int(bundle.get("max_attempts", 0)),
            success_count=int(bundle.get("success_count", 0)),
            failed_count=int(bundle.get("failed_count", 0)),
            target_count=int(bundle.get("target_count", _normalize_sample_count(sample_count))),
        )
    except Exception as e:
        _update_force_graph_job(
            job_id,
            status="failed",
            progress=100,
            message="Failed",
            layout_mode=normalized_mode,
            error=str(e),
        )
        logger.error(f"Graph async job failed ({normalized_mode}): {e}")


def start_force_graph_job(
    description,
    query,
    analysis_result,
    chart_json,
    sample_count=FORCE_GRAPH_DEFAULT_SAMPLE_COUNT,
    layout_mode=_FORCE_LAYOUT_MODE,
):
    _cleanup_expired_force_graph_jobs()
    normalized_mode = _normalize_layout_mode(layout_mode)
    job_id = _create_force_graph_job(sample_count, layout_mode=normalized_mode)
    worker = threading.Thread(
        target=_run_force_graph_job,
        args=(job_id, description, query, analysis_result, chart_json, sample_count, normalized_mode),
        daemon=True,
    )
    worker.start()
    return job_id


def get_infographic_plan(description, query, analysis_result, chart_json):
    """
    第一步：调用 LLM 分析数据，生成视觉元素池 (JSON)
    """
    try:
        chart_str = json.dumps(chart_json, ensure_ascii=False)
        if len(chart_str) > 2000:
            chart_str = chart_str[:2000] + "...(truncated)"

        plan_json = generate_visualization_elements(
            user_query=query,
            table_schema=analysis_result,
            table_description=description,
            vegalite_code=chart_str
        )

        return plan_json
    except Exception as e:
        logger.error(f"Plan Gen Error: {e}")
        return {"error": str(e), "element_pool": {}}


def generate_single_asset(keywords, style_desc):
    """
    中间步骤：用户点击生成某个具体的视觉素材 (如图标、插画)
    """
    try:
        prompt = f"""
        请设计一个高质量的视觉素材元素,我想将其用在信息图设计中。
        主题内容：{keywords}
        设计风格：{style_desc} 
        要求：请输出一个干净、独立的元素主体，不要有多余的背景杂物。
        """
        image_path = image_service.generate(prompt=prompt, aspect_ratio="1:1")

        if image_path:
            web_path = image_path.replace("\\", "/")
            if "static/" in web_path:
                web_path = web_path.split("static/")[-1]
                web_path = f"/static/{web_path}"
            return web_path
        return None
    except Exception as e:
        logger.error(f"Asset Gen Error: {e}")
        raise e


def generate_final_composite(user_selections, chart_json, description, query, analysis_result):
    """
    最后一步：根据用户选择的所有参数 + 数据分析上下文，合成最终 Prompt
    """
    try:
        # 1. 动态解析所有层级的用户选择
        bottom_layer = user_selections.get('bottom_layer', {})
        middle_layer = user_selections.get('middle_layer', {})
        # [修复]: 使用 .copy() 防止 pop 操作修改原始的 user_selections 数据
        top_layer = user_selections.get('top_layer', {}).copy()

        # 单独提取并移除 visual_assets，因为要单独处理
        visual_assets_obj = top_layer.pop('visual_assets', None)
        color_scheme_selection = middle_layer.get('color_scheme', '商务专业')
        palette_info_text = _build_palette_info_text(color_scheme_selection)

        # 构建基础样式 Prompt
        design_preferences = f"""
        - **背景风格 (Background)**: {bottom_layer.get('bg_style', '现代简约')}
        - **坐标轴风格 (Axis)**: {bottom_layer.get('axis_style', '清晰易读')}
        - **图表类型 (Chart Type)**: {middle_layer.get('chart_type', '柱状/折线图')}
        - **调色板信息 (Palette Info)**: {palette_info_text}
        """

        # 动态构建顶层叙事（标题、洞察、注释等）的 Prompt
        narrative_preferences = ""
        if top_layer:
            narrative_preferences = "### 4. 叙事与文案排版要求 (Narrative & Typography)\n请根据以下要求设计文字内容：\n"
            # 建立一个友好的中文映射，方便 LLM 理解
            key_mapping = {
                'title_style': '标题文案风格 (Title Style)',
                'highlight_insight': '核心洞察的呈现方式 (Highlight Insight)',
                'annotation_text': '数据注释风格 (Annotation Text)'
            }
            for key, val in top_layer.items():
                # [核心修改]: 如果 key 不在映射表中，自动将英文 key 的下划线替换为空格并首字母大写
                # 例如 'font_family' 会自动变成 'Font Family'
                label = key_mapping.get(key, key.replace('_', ' ').title())
                narrative_preferences += f"- **{label}**: 采用“{val}”的表达方式。\n"

        # 处理 Asset 文本提示词 (适配字典格式)
        asset_prompt_section = ""
        if visual_assets_obj and isinstance(visual_assets_obj, dict):
            # 提取中英文关键词
            keywords = visual_assets_obj.get('keywords', '')
            suggestion = visual_assets_obj.get('suggestion', keywords)
            category = visual_assets_obj.get('category', '视觉元素')

            asset_prompt_section = f"""
            ### 5. 核心插图要求 (Visual Asset)
            请将以下指定的插画/图标概念自然地融入到信息图的设计中，作为背景点缀或核心装饰：
            - **元素类别**: {category}
            - **画面内容**: "{suggestion}" (概念参考: {keywords})
            请确保该元素的风格与整体配色协调统一。
            """

        # 2. 准备数据字符串
        chart_code_str = json.dumps(chart_json, ensure_ascii=False)
        if len(chart_code_str) > 5000:
            chart_code_str = chart_code_str[:5000] + "...(truncated)"

        # 3. 构建新的 Master Prompt
        prompt = f"""
        请扮演一位专业的数据可视化设计师。你需要根据以下数据分析结果、图表代码以及用户的定制要求，设计一张精美、具有艺术感的数据信息图 (Infographic)。

        ### 1. 任务背景
        - **数据来源**: {description}
        - **用户问题**: {query}
        - **核心结论**: {analysis_result}

        ### 2. 参考图表数据 (Vega-Lite Source Code)
        请严格参考以下代码中的 `values` 数据，确保生成的信息图在数值比例上真实准确。
        ```json
        {chart_code_str}
        ```

        ### 3. 全局设计风格要求
        {design_preferences}

        {narrative_preferences}

        {asset_prompt_section}

        ### 6. 输出要求
        请生成一张完整的 3:4 竖版数据海报。构图需主次分明，标题、洞察文案、图表和插画完美融合。
        """
        print("--- Final Prompt Generated ---")
        print(prompt)

        # 4. 调用 Gemini 生图 (生成 3:4 竖版海报)
        final_image_path = image_service.generate(prompt=prompt, aspect_ratio="3:4")

        if final_image_path:
            web_path = final_image_path.replace("\\", "/")
            if "static/" in web_path:
                web_path = web_path.split("static/")[-1]
                web_path = f"/static/{web_path}"
            return web_path
        return None

    except Exception as e:
        logger.error(f"Final Gen Error: {e}")
        raise e
