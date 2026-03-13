# -*- coding: utf-8 -*-
"""
som_module/element_extractor.py
================================
从 raw_runs 列表中提取设计元素节点，并计算共现图的统计指标。

输入: raw_runs（由 json_io.normalize_runs_payload 生成的列表）
输出:
  elements     - dict，key 为全局 ID，value 为元素元数据
  run_ids      - list，所有 run 的 ID
  pagerank     - dict，元素节点的 PageRank 得分
  degree_cent  - dict，元素节点的度中心性
  links        - list，跨层提升度 > LINK_MIN_LIFT 的关联边
"""

import copy
from collections import defaultdict
from itertools import combinations

from . import config


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────────────────────

def _extract_option_uid_label_desc(option):
    """
    从单个 option 对象（dict 或 string）中提取 (uid, label, desc, payload)。

    uid   - 用于去重的唯一标识符（尽量取 value/style/category 等字段）
    label - 显示用的可读文本
    desc  - 描述文字
    payload - 原始 option 的完整拷贝（传递给前端展示用）
    """
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


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def extract_elements_and_rules(raw_runs: list):
    """
    从 raw_runs 列表中提取设计元素节点，并计算共现图统计指标。

    Parameters
    ----------
    raw_runs : list
        标准化的 run 列表（来自 json_io）。

    Returns
    -------
    elements : dict
        key = "{layer}::{group_id}::{uid}"
        value = {
            "id": str,
            "layer": str,        # bottom_layer / middle_layer / top_layer
            "category": str,     # group 的显示名称
            "group": str,        # 同 category
            "group_id": str,     # 来自 LLM 输出的 id 字段
            "label": str,
            "name": str,
            "desc": str,
            "count": int,        # 出现次数
            "val": int,          # 同 count（兼容旧接口）
            "runs": list[int],   # 出现过的 run_id 列表
            "option_payload": dict,
            "is_palette_node": bool,
        }
    run_ids : list
        所有 run 的 ID 列表（与 raw_runs 顺序一致）。
    pagerank : dict
        {element_id: float}，NetworkX PageRank 得分。
    degree_cent : dict
        {element_id: float}，NetworkX 度中心性。
    links : list
        跨层关联边，每条格式为：
        {"source": str, "target": str, "lift": float, "co_occur": int}
        仅保留 lift > config.LINK_MIN_LIFT 的边，按 lift 降序排列。

    Raises
    ------
    RuntimeError
        networkx 未安装时抛出。
    ValueError
        raw_runs 为空或所有 run 无效时抛出。
    """
    try:
        import networkx as nx
    except ImportError as exc:
        raise RuntimeError("networkx 未安装，请执行: pip install networkx") from exc

    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("raw_runs 必须是非空列表")

    elements: dict = {}
    run_ids: list = []
    run_to_elements: dict = defaultdict(list)

    # ── 第一遍：遍历所有 run，提取元素节点 ──
    for idx, run in enumerate(raw_runs, start=1):
        run_id = run.get("run_id") if isinstance(run, dict) else None
        if run_id is None:
            run_id = idx
        run_ids.append(run_id)

        pool = (
            run.get("generated_scheme", {}).get("element_pool", {})
            if isinstance(run, dict)
            else {}
        )
        if not isinstance(pool, dict):
            continue

        for layer_name, categories in pool.items():
            if not isinstance(categories, list):
                continue
            layer_text = str(layer_name or "").strip() or "top_layer"

            for cat in categories:
                if not isinstance(cat, dict):
                    continue

                group_id = str(
                    cat.get("id") or cat.get("name") or "unknown_group"
                ).strip() or "unknown_group"
                category_name = str(cat.get("name") or group_id).strip() or group_id
                options = cat.get("options") or []
                if not isinstance(options, list):
                    continue

                for option in options:
                    uid_text, label_text, desc_text, option_payload = \
                        _extract_option_uid_label_desc(option)

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
                            "option_payload": option_payload
                            if isinstance(option_payload, dict)
                            else {},
                            "is_palette_node": group_id == "color_scheme",
                        }

                    elements[global_id]["runs"].add(run_id)
                    elements[global_id]["count"] += 1
                    elements[global_id]["val"] += 1
                    run_to_elements[run_id].append(global_id)

    total_runs = len(run_ids)
    if total_runs == 0:
        raise ValueError("没有有效的 run 数据，无法提取元素。")

    # 将 runs set 转成 list（方便后续序列化）
    for value in elements.values():
        value["runs"] = list(value["runs"])

    # ── 第二遍：构建共现图 ──
    G = nx.Graph()
    for node_id in elements:
        G.add_node(node_id)

    for _, elem_ids in run_to_elements.items():
        for e1, e2 in combinations(elem_ids, 2):
            if G.has_edge(e1, e2):
                G[e1][e2]["weight"] += 1
            else:
                G.add_edge(e1, e2, weight=1)

    # ── 第三遍：计算图指标 ──
    if len(G.nodes) > 0 and len(G.edges) > 0:
        pagerank = nx.pagerank(G, weight="weight")
    else:
        pagerank = {}
    degree_cent = nx.degree_centrality(G) if len(G.nodes) > 0 else {}

    # ── 第四遍：计算跨层 Lift，生成 links ──
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
        # 仅保留跨层的强关联
        if layer1 != layer2 and lift > config.LINK_MIN_LIFT:
            links.append({
                "source": e1,
                "target": e2,
                "lift": round(float(lift), 3),
                "co_occur": co_occur,
            })

    links.sort(key=lambda item: (-float(item.get("lift", 0)), -int(item.get("co_occur", 0))))

    return elements, run_ids, pagerank, degree_cent, links


def build_group_defaults(elements: dict) -> dict:
    """
    为每个 layer 的每个 group_id 找出出现频率最高的默认元素 ID。

    Parameters
    ----------
    elements : dict
        extract_elements_and_rules 返回的 elements 字典。

    Returns
    -------
    dict
        格式: {layer: {group_id: element_id}}
    """
    temp = {layer: {} for layer in config.LAYER_ORDER}
    for elem in elements.values():
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

    return {
        layer: {gid: payload["id"] for gid, payload in groups.items()}
        for layer, groups in temp.items()
    }
