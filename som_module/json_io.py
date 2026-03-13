# -*- coding: utf-8 -*-
"""
som_module/json_io.py
=====================
JSON 输入/输出处理：
  - 从文件或字典载入 runs 数据
  - 规范化不同来源的 JSON 格式
  - 将处理结果保存回文件

此模块是 SOM 子模块的"入口"，负责将原始 JSON 转换为
element_extractor 和 som_trainer 可直接使用的标准 raw_runs 列表。
"""

import json
import os
import time
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────────────────────

def _extract_single_run_payload(entry: dict) -> Optional[dict]:
    """
    从单条 entry 中提取 generated_scheme（含 element_pool）。

    支持以下几种常见格式：
      1. {"generated_scheme": {"element_pool": {...}}}   ← 标准格式
      2. {"plan": {"element_pool": {...}}}               ← 旧版格式
      3. {"element_pool": {...}}                         ← 扁平格式
    """
    if not isinstance(entry, dict):
        return None

    # 格式 1: 标准格式
    generated_scheme = entry.get("generated_scheme")
    if isinstance(generated_scheme, dict) and isinstance(generated_scheme.get("element_pool"), dict):
        return generated_scheme

    # 格式 2: 旧版 plan 字段
    plan_obj = entry.get("plan")
    if isinstance(plan_obj, dict) and isinstance(plan_obj.get("element_pool"), dict):
        return plan_obj

    # 格式 3: 扁平格式（element_pool 直接在顶层）
    if isinstance(entry.get("element_pool"), dict):
        return {
            "analysis_report": entry.get("analysis_report", {}),
            "element_pool": entry["element_pool"],
        }

    return None


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def load_runs_from_file(json_path: str) -> list:
    """
    从 JSON 文件加载 raw_runs 列表。

    文件可以是：
      - 保存的 som_runs_*.json（含 "runs" 字段的对象）
      - 直接的 list（每个元素为一次生成结果）
      - 单个 run 对象（自动包装成列表）

    Parameters
    ----------
    json_path : str
        JSON 文件绝对或相对路径。

    Returns
    -------
    list
        标准化后的 raw_runs 列表，每条包含：
        {"run_id": int, "timestamp": str, "generated_scheme": dict}

    Raises
    ------
    FileNotFoundError
        文件不存在时抛出。
    ValueError
        文件内容不符合预期格式时抛出。
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON 文件不存在: {json_path}")

    with open(json_path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)

    return normalize_runs_payload(payload)


def normalize_runs_payload(payload) -> list:
    """
    将任意格式的 payload（dict 或 list）规范化为标准 raw_runs 列表。

    Parameters
    ----------
    payload : dict | list
        原始数据。支持的顶层格式：
          - {"runs": [...]}         ← som_runs_*.json 文件格式
          - {"raw_runs": [...]}
          - {"data": [...]}
          - {"items": [...]}
          - {"results": [...]}
          - [...]                   ← 直接的列表
          - {...}                   ← 单个 run 对象

    Returns
    -------
    list
        标准 raw_runs，每条格式为：
        {"run_id": int, "timestamp": str, "generated_scheme": {...}}

    Raises
    ------
    ValueError
        无法识别格式或无有效 run 时抛出。
    """
    # 如果是 dict，尝试从常见字段中取出列表
    if isinstance(payload, dict):
        for key in ("runs", "raw_runs", "data", "items", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break
        else:
            # 可能是单个 run 对象
            payload = [payload]

    if not isinstance(payload, list):
        raise ValueError(
            "输入 JSON 必须是列表，或包含 runs/raw_runs/data 字段的对象。"
        )

    raw_runs = []
    for idx, entry in enumerate(payload, start=1):
        scheme = _extract_single_run_payload(entry)
        if not scheme:
            continue  # 跳过不含 element_pool 的条目

        run_id = entry.get("run_id") if isinstance(entry, dict) else None
        if run_id is None:
            run_id = idx

        timestamp = entry.get("timestamp") if isinstance(entry, dict) else None
        if not timestamp:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        raw_runs.append({
            "run_id": run_id,
            "timestamp": timestamp,
            "generated_scheme": scheme,
        })

    if not raw_runs:
        raise ValueError(
            "未找到有效的 run 数据。"
            "每条记录必须包含 generated_scheme.element_pool 或 element_pool 字段。"
        )

    return raw_runs


def save_runs_to_file(raw_runs: list, output_path: str, metadata: Optional[dict] = None) -> str:
    """
    将 raw_runs 保存到 JSON 文件。

    Parameters
    ----------
    raw_runs : list
        标准化后的 raw_runs 列表。
    output_path : str
        输出文件路径（不存在的目录会自动创建）。
    metadata : dict, optional
        附加到文件顶层的元数据（如 query、layout_mode 等）。

    Returns
    -------
    str
        实际写入的文件绝对路径。
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    payload = {
        "actual_count": len(raw_runs),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "runs": raw_runs,
    }
    if isinstance(metadata, dict):
        payload.update({k: v for k, v in metadata.items() if k != "runs"})

    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)

    return os.path.abspath(output_path)


def save_som_result(som_bundle: dict, output_path: str) -> str:
    """
    将 SOM 生成结果保存到 JSON 文件。

    Parameters
    ----------
    som_bundle : dict
        pipeline.build_som_from_runs() 返回的 bundle 字典。
    output_path : str
        输出文件路径。

    Returns
    -------
    str
        实际写入的文件绝对路径。
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # element sets 不可 JSON 序列化，确保已转换
    import copy
    bundle_copy = copy.deepcopy(som_bundle)

    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(bundle_copy, fp, ensure_ascii=False, indent=2, default=str)

    return os.path.abspath(output_path)


def print_runs_summary(raw_runs: list) -> None:
    """打印 raw_runs 的简要统计信息，便于快速检查输入数据。"""
    print(f"共 {len(raw_runs)} 条 run 数据")
    for i, run in enumerate(raw_runs[:3], start=1):
        scheme = run.get("generated_scheme", {})
        pool = scheme.get("element_pool", {})
        layer_counts = {layer: len(pool.get(layer, [])) for layer in ("bottom_layer", "middle_layer", "top_layer")}
        print(f"  run #{run.get('run_id', i)}: {layer_counts}")
    if len(raw_runs) > 3:
        print(f"  ... (共 {len(raw_runs)} 条，仅显示前 3 条)")
