# -*- coding: utf-8 -*-
"""
som_module/pipeline.py
======================
完整流水线协调器：JSON 输入 → 元素提取 → SOM 训练 → 结果输出。

对外暴露两个主入口：

  build_som_from_file(json_path)
      直接从 JSON 文件路径运行完整流水线，适合脚本调用和调试。

  build_som_from_runs(raw_runs)
      从已加载的 raw_runs 列表运行流水线，适合程序内部调用。

两个函数均返回与主代码 generate_som_bundle_from_runs() 相同格式的 bundle 字典，
因此可直接用于比较或替换主代码中的对应函数。
"""

from . import json_io, element_extractor, som_trainer


# ──────────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────────

def build_som_from_runs(raw_runs: list, use_hungarian: bool = True) -> dict:
    """
    从标准化的 raw_runs 列表运行完整 SOM 流水线。

    Parameters
    ----------
    raw_runs : list
        来自 json_io.normalize_runs_payload 或 json_io.load_runs_from_file 的列表。
    use_hungarian : bool
        True（默认）：使用匈牙利算法；False：使用贪心 BMU 分配（用于对比演示）。

    Returns
    -------
    dict
        SOM bundle，格式与主代码 generate_som_bundle_from_runs() 一致：
        {
            "target_count"  : int,
            "success_count" : int,
            "failed_count"  : int,
            "attempted_count": int,
            "max_attempts"  : int,
            "graph_data"    : {
                "nodes": list[dict],   # 每个节点: {x, y, u_value, elements:[...]}
                "links": list[dict],   # 跨层关联: {source, target, lift, co_occur}
            },
            "group_defaults": dict,    # {layer: {group_id: element_id}}
            "layout_mode"   : "som",
        }

    Raises
    ------
    ValueError
        raw_runs 为空或无法提取元素时抛出。
    RuntimeError
        依赖库缺失（networkx / minisom / scipy / numpy / sentence-transformers）时抛出。
    """
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("raw_runs 必须是非空列表")

    # ── 第一步：提取元素节点和关联规则 ──
    elements, run_ids, pagerank, degree_cent, links = \
        element_extractor.extract_elements_and_rules(raw_runs)

    if not elements:
        raise ValueError("无法从 runs 中提取到任何设计元素，请检查 JSON 格式。")

    # ── 第二步：训练 SOM ──
    som_nodes = som_trainer.train_som(elements, run_ids, pagerank, degree_cent,
                                      use_hungarian=use_hungarian)

    if not som_nodes:
        raise ValueError("SOM 训练未产生任何节点，请检查元素数量是否过少。")

    # ── 第三步：构建默认选项 ──
    group_defaults = element_extractor.build_group_defaults(elements)

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
        "layout_mode": "som",
    }


def build_comparison_from_runs(raw_runs: list) -> tuple:
    """
    同时构建两个 SOM bundle，用于可视化对比：

      - bundle_no_hungarian  : 贪心 BMU 分配（不使用匈牙利算法），可能产生节点碰撞
      - bundle_with_hungarian: 匈牙利算法最优分配（标准流程）

    两次训练使用相同的随机种子，因此 SOM 权重矩阵完全一致，
    仅分配算法不同，便于直接对比优化效果。

    Parameters
    ----------
    raw_runs : list
        来自 json_io.normalize_runs_payload 或 json_io.load_runs_from_file 的列表。

    Returns
    -------
    tuple
        (bundle_no_hungarian, bundle_with_hungarian)
    """
    bundle_no_hungarian   = build_som_from_runs(raw_runs, use_hungarian=False)
    bundle_with_hungarian = build_som_from_runs(raw_runs, use_hungarian=True)
    return bundle_no_hungarian, bundle_with_hungarian


def build_som_from_file(json_path: str) -> dict:
    """
    直接从 JSON 文件路径运行完整 SOM 流水线。

    Parameters
    ----------
    json_path : str
        包含 runs 数据的 JSON 文件路径。

    Returns
    -------
    dict
        与 build_som_from_runs() 相同格式的 SOM bundle。
    """
    raw_runs = json_io.load_runs_from_file(json_path)
    return build_som_from_runs(raw_runs)


def print_bundle_summary(bundle: dict) -> None:
    """
    打印 SOM bundle 的摘要信息，便于调试时快速查看结果。

    Parameters
    ----------
    bundle : dict
        build_som_from_runs() 或 build_som_from_file() 的返回值。
    """
    print("\n" + "=" * 60)
    print("  SOM Bundle 摘要")
    print("=" * 60)
    print(f"  Run 数量      : {bundle.get('success_count', 0)}")
    print(f"  布局模式      : {bundle.get('layout_mode', 'som')}")

    graph_data = bundle.get("graph_data", {})
    nodes = graph_data.get("nodes", [])
    links = graph_data.get("links", [])

    # 统计非空节点
    non_empty_nodes = [n for n in nodes if n.get("elements")]
    total_elements_assigned = sum(len(n["elements"]) for n in non_empty_nodes)

    print(f"  SOM 网格节点  : {len(nodes)} 个 (非空: {len(non_empty_nodes)} 个)")
    print(f"  已分配元素    : {total_elements_assigned} 个")
    print(f"  跨层关联链接  : {len(links)} 条")

    group_defaults = bundle.get("group_defaults", {})
    print("\n  各层默认选项:")
    for layer, groups in group_defaults.items():
        print(f"    [{layer}]")
        for gid, eid in groups.items():
            print(f"      {gid}: {eid}")

    if links:
        print(f"\n  Top 5 跨层关联 (by lift):")
        for link in links[:5]:
            print(
                f"    {link['source']} ↔ {link['target']}"
                f"  lift={link['lift']}  co_occur={link['co_occur']}"
            )
    print("=" * 60 + "\n")
