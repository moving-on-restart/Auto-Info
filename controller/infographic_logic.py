import logging
import json
import os
import copy
import time
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

_FORCE_GRAPH_JOBS = {}
_FORCE_GRAPH_JOBS_LOCK = threading.Lock()
_FORCE_GRAPH_JOB_TTL_SECONDS = 30 * 60


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


def _create_force_graph_job(sample_count):
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    target_count = _normalize_sample_count(sample_count)
    job = {
        "job_id": job_id,
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


def generate_force_graph_bundle(
    description,
    query,
    analysis_result,
    chart_json,
    sample_count=FORCE_GRAPH_DEFAULT_SAMPLE_COUNT,
    progress_callback=None,
):
    target_count = _normalize_sample_count(sample_count)
    if not query:
        raise ValueError("Query is required for force-graph planning.")

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
                "message": "Starting force-graph scheme sampling...",
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
        raise RuntimeError("All force-graph plan generations failed.")

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


def _run_force_graph_job(job_id, description, query, analysis_result, chart_json, sample_count):
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
        _update_force_graph_job(job_id, status="running", progress=1, message="Force graph job started")
        bundle = generate_force_graph_bundle(
            description=description,
            query=query,
            analysis_result=analysis_result,
            chart_json=chart_json,
            sample_count=sample_count,
            progress_callback=on_progress,
        )
        _update_force_graph_job(
            job_id,
            status="completed",
            progress=100,
            message="Completed",
            result=bundle,
            error=None,
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
            error=str(e),
        )
        logger.error(f"Force graph async job failed: {e}")


def start_force_graph_job(description, query, analysis_result, chart_json, sample_count=FORCE_GRAPH_DEFAULT_SAMPLE_COUNT):
    _cleanup_expired_force_graph_jobs()
    job_id = _create_force_graph_job(sample_count)
    worker = threading.Thread(
        target=_run_force_graph_job,
        args=(job_id, description, query, analysis_result, chart_json, sample_count),
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
