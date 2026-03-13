#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
som_module/run_debug.py
=======================
独立调试脚本：无需启动 Flask 服务，直接从 JSON 文件生成 SOM 图并输出结果。

使用方式
--------
# 方式一：使用内置示例数据（sample_data/sample_runs.json）
  python run_debug.py

# 方式二：指定 JSON 文件路径
  python run_debug.py --input /path/to/your/runs.json

# 方式三：指定输入并保存结果
  python run_debug.py --input data.json --output result.json

# 方式四：仅输出摘要，不保存文件
  python run_debug.py --input data.json --no-save

命令行参数
----------
  --input   输入 JSON 文件路径（可以是绝对或相对路径）
  --output  输出 JSON 文件路径（默认: som_debug_output.json）
  --no-save 不保存输出文件，仅打印摘要

调试技巧
--------
1. 修改 config.py 中的参数后，重新运行此脚本即可看到效果
2. 设置 config.VERBOSE = True 可查看详细的训练过程
3. 修改 som_trainer.py 中的 _build_embeddings() 可实验不同的向量表示
4. 修改 som_trainer.py 中的 _assign_elements_to_nodes() 可测试不同的分配策略
"""

import argparse
import json
import os
import sys
import time

# 将 som_module 的父目录加入 sys.path（允许在任何位置直接运行此脚本）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from som_module import pipeline, json_io
from som_module import config as cfg


# ──────────────────────────────────────────────────────────────────────────────
# 示例数据（当未指定 --input 时使用）
# ──────────────────────────────────────────────────────────────────────────────

SAMPLE_DATA_PATH = os.path.join(_THIS_DIR, "sample_data", "sample_runs.json")

_BUILTIN_SAMPLE_RUNS = [
    {
        "run_id": 1,
        "timestamp": "2026-01-01 10:00:00",
        "generated_scheme": {
            "analysis_report": {"domain_detected": "历史文物", "intent_match": "Match"},
            "element_pool": {
                "bottom_layer": [
                    {
                        "id": "bg_style",
                        "name": "背景风格",
                        "options": [
                            {"value": "ink_wash", "label": "水墨宣纸", "desc": "仿古宣纸底纹，呈现东方雅韵"},
                            {"value": "museum_dark", "label": "博物馆深邃", "desc": "深灰背景模拟展厅灯光"},
                        ],
                    },
                    {
                        "id": "grid_style",
                        "name": "网格样式",
                        "options": [
                            {"value": "classic_frame", "label": "古典边框", "desc": "回纹装饰边框"},
                            {"value": "minimal", "label": "极简无框", "desc": "仅保留坐标轴"},
                        ],
                    },
                ],
                "middle_layer": [
                    {
                        "id": "chart_type",
                        "name": "图表形态",
                        "options": [
                            {"value": "standard_bar", "label": "标准柱状图", "desc": "经典双柱对比"},
                            {"value": "pictogram", "label": "象形图", "desc": "用瓷器剪影堆叠表示数量"},
                        ],
                    },
                    {
                        "id": "color_scheme",
                        "name": "配色方案",
                        "options": [
                            {"value": "qinghua_classic", "label": "青花经典", "desc": "钴蓝配釉里红"},
                            {"value": "dynasty_gold", "label": "皇家金璃", "desc": "明黄配帝王紫"},
                        ],
                    },
                ],
                "top_layer": [
                    {
                        "id": "highlight_insight",
                        "name": "核心洞察",
                        "options": [
                            {"value": "ratio_focus", "label": "强调倍数关系", "content": "清代数量是明代的2.35倍"},
                            {"value": "total_focus", "label": "强调总量悬殊", "content": "清代(625) 远超 明代(266)"},
                        ],
                    },
                    {
                        "id": "visual_assets",
                        "name": "装饰素材",
                        "options": [
                            {"category": "瓷器", "suggestion": "青花瓷瓶插画", "keywords": "Blue white porcelain vase"},
                        ],
                    },
                ],
            },
        },
    },
    {
        "run_id": 2,
        "timestamp": "2026-01-01 10:01:00",
        "generated_scheme": {
            "analysis_report": {"domain_detected": "历史文物", "intent_match": "Match"},
            "element_pool": {
                "bottom_layer": [
                    {
                        "id": "bg_style",
                        "name": "背景风格",
                        "options": [
                            {"value": "porcelain_white", "label": "瓷白素净", "desc": "纯净象牙白底"},
                            {"value": "ink_wash", "label": "水墨宣纸", "desc": "仿古宣纸底纹"},
                        ],
                    },
                    {
                        "id": "grid_style",
                        "name": "网格样式",
                        "options": [
                            {"value": "subtle_grid", "label": "淡雅辅助线", "desc": "浅色虚线网格"},
                            {"value": "minimal", "label": "极简无框", "desc": "最大化数据区域"},
                        ],
                    },
                ],
                "middle_layer": [
                    {
                        "id": "chart_type",
                        "name": "图表形态",
                        "options": [
                            {"value": "radial_compare", "label": "环形对比", "desc": "双环嵌套展示比例"},
                            {"value": "standard_bar", "label": "标准柱状图", "desc": "清晰直观对比"},
                        ],
                    },
                    {
                        "id": "color_scheme",
                        "name": "配色方案",
                        "options": [
                            {"value": "ink_gradient", "label": "墨色渐变", "desc": "从淡墨到浓墨的灰阶渐变"},
                            {"value": "qinghua_classic", "label": "青花经典", "desc": "钴蓝配釉里红"},
                        ],
                    },
                ],
                "top_layer": [
                    {
                        "id": "highlight_insight",
                        "name": "核心洞察",
                        "options": [
                            {"value": "ratio_focus", "label": "强调倍数关系", "content": "清代是明代的2.35倍"},
                            {"value": "pct_focus", "label": "强调占比格局", "content": "清代占比70.1%"},
                        ],
                    },
                    {
                        "id": "visual_assets",
                        "name": "装饰素材",
                        "options": [
                            {"category": "龙纹", "suggestion": "清代龙纹插画", "keywords": "Qing dynasty dragon pattern"},
                        ],
                    },
                ],
            },
        },
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _print_config() -> None:
    """打印当前生效的 SOM 配置参数。"""
    print("\n当前 SOM 配置 (来自 som_module/config.py):")
    print(f"  TEXT_MODEL_NAME         = {cfg.TEXT_MODEL_NAME}")
    print(f"  WEIGHT_NLP              = {cfg.WEIGHT_NLP}")
    print(f"  WEIGHT_CO_OCCURRENCE    = {cfg.WEIGHT_CO_OCCURRENCE}")
    print(f"  WEIGHT_CATEGORY         = {cfg.WEIGHT_CATEGORY}")
    print(f"  WEIGHT_LAYER            = {cfg.WEIGHT_LAYER}")
    print(f"  WEIGHT_GRAPH            = {cfg.WEIGHT_GRAPH}")
    print(f"  GRID_SIZE_PADDING       = {cfg.GRID_SIZE_PADDING}")
    print(f"  SOM_SIGMA               = {cfg.SOM_SIGMA}")
    print(f"  SOM_LEARNING_RATE       = {cfg.SOM_LEARNING_RATE}")
    print(f"  SOM_TOPOLOGY            = {cfg.SOM_TOPOLOGY}")
    print(f"  SOM_RANDOM_SEED         = {cfg.SOM_RANDOM_SEED}")
    print(f"  SOM_TRAINING_ITERATIONS = {cfg.SOM_TRAINING_ITERATIONS}")
    print(f"  SOM_INIT_METHOD         = {cfg.SOM_INIT_METHOD}")
    print(f"  LINK_MIN_LIFT           = {cfg.LINK_MIN_LIFT}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SOM 子模块调试脚本：从 JSON 输入生成自组织映射图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="输入 JSON 文件路径（默认使用内置示例数据）",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="som_debug_output.json",
        help="输出 JSON 文件路径（默认: som_debug_output.json）",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存输出文件，仅打印摘要",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  SOM 子模块调试脚本")
    print("=" * 60)

    # ── 1. 打印当前配置 ──
    _print_config()

    # ── 2. 加载输入数据 ──
    if args.input:
        input_path = os.path.abspath(args.input)
        print(f"从文件加载数据: {input_path}")
        try:
            raw_runs = json_io.load_runs_from_file(input_path)
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            sys.exit(1)
    elif os.path.exists(SAMPLE_DATA_PATH):
        print(f"使用 sample_data 目录中的示例数据: {SAMPLE_DATA_PATH}")
        try:
            raw_runs = json_io.load_runs_from_file(SAMPLE_DATA_PATH)
        except Exception as e:
            print(f"❌ 加载示例文件失败，回退到内置数据: {e}")
            raw_runs = json_io.normalize_runs_payload(_BUILTIN_SAMPLE_RUNS)
    else:
        print("未指定 --input，使用内置示例数据（2 条 runs）...")
        raw_runs = json_io.normalize_runs_payload(_BUILTIN_SAMPLE_RUNS)

    json_io.print_runs_summary(raw_runs)

    # ── 3. 运行 SOM 流水线 ──
    print("\n开始运行 SOM 流水线 ...")
    t0 = time.time()
    try:
        bundle = pipeline.build_som_from_runs(raw_runs)
    except Exception as e:
        print(f"\n❌ SOM 流水线执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    elapsed = time.time() - t0
    print(f"\n✅ SOM 流水线完成，耗时 {elapsed:.2f}s")

    # ── 4. 打印摘要 ──
    pipeline.print_bundle_summary(bundle)

    # ── 5. 保存结果 ──
    if not args.no_save:
        output_path = os.path.abspath(args.output)
        try:
            saved = json_io.save_som_result(bundle, output_path)
            print(f"结果已保存到: {saved}")
        except Exception as e:
            print(f"⚠️  保存失败: {e}")
    else:
        print("（已跳过保存，使用 --output 可指定输出路径）")


if __name__ == "__main__":
    main()
