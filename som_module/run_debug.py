#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
som_module/run_debug.py
=======================
PyCharm 直接运行调试脚本。

★ 使用方式：在下方「调试配置区」修改参数，然后直接点击 PyCharm 的运行按钮即可。
"""

import os
import sys
import time
import traceback

# ── 路径修正（PyCharm 从任意目录运行均可） ──────────────────────────────────
_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from som_module import pipeline, json_io
from som_module import config as cfg

# ==============================================================================
#  ★★★ 调试配置区 —— 在这里修改所有参数，然后直接运行 ★★★
# ==============================================================================

# ── 输入数据 ──────────────────────────────────────────────────────────────────
# 填写 runs JSON 文件的路径（绝对路径或相对于本文件的路径）。
# 留空 ("") 则自动使用 sample_data/sample_runs.json；
# 若 sample_data 也不存在则使用脚本内内置的 2 条最小样本。
INPUT_JSON_PATH = ""
# 示例：
# INPUT_JSON_PATH = r"C:\projects\Auto-Info\static\json\som_runs_100_20260301_120000.json"
# INPUT_JSON_PATH = os.path.join(_THIS_DIR, "sample_data", "sample_runs.json")

# ── 输出结果 ──────────────────────────────────────────────────────────────────
# SOM bundle 结果保存路径，留空 ("") 则不保存。
OUTPUT_JSON_PATH = os.path.join(_THIS_DIR, "som_debug_output.json")
# OUTPUT_JSON_PATH = ""   # 不保存

# ── 可视化 ────────────────────────────────────────────────────────────────────
# True  → 运行完成后自动在浏览器中打开交互式 SOM 可视化页面（会阻塞终端）
# False → 仅打印摘要，不启动浏览器
OPEN_VIZ = True

# 可视化服务器端口（如果 7860 被占用请改成其他端口，如 8080）
VIZ_PORT = 7860

# ==============================================================================
#  ★★★ SOM 算法参数（直接在此覆盖 config.py 的默认值）★★★
#  修改后保存文件，重新运行即可看到效果。
#  若不想覆盖，将整段注释掉即可恢复 config.py 的默认值。
# ==============================================================================

# cfg.TEXT_MODEL_NAME         = "shibing624/text2vec-base-chinese"
# cfg.WEIGHT_NLP              = 0.35   # NLP 语义权重
# cfg.WEIGHT_CO_OCCURRENCE    = 0.25   # 共现权重
# cfg.WEIGHT_CATEGORY         = 0.20   # 类别 one-hot 权重
# cfg.WEIGHT_LAYER            = 0.10   # 层级 one-hot 权重
# cfg.WEIGHT_GRAPH            = 0.10   # 图结构权重
# cfg.GRID_SIZE_PADDING       = 5      # 网格边长 = ceil(sqrt(元素数)) + padding
# cfg.SOM_SIGMA               = 1.2    # 邻域半径
# cfg.SOM_LEARNING_RATE       = 0.5    # 学习率
# cfg.SOM_TOPOLOGY            = "hexagonal"   # "hexagonal" 或 "rectangular"
# cfg.SOM_RANDOM_SEED         = 42     # 随机种子，None 则每次不同
# cfg.SOM_TRAINING_ITERATIONS = 5000   # 训练迭代次数
# cfg.SOM_INIT_METHOD         = "pca"  # "pca" 或 "random"
# cfg.LINK_MIN_LIFT           = 1.2    # 跨层链接的最小提升度阈值
# cfg.VERBOSE                 = True   # 打印训练进度

# ==============================================================================
#  内置最小样本（当 INPUT_JSON_PATH 为空且 sample_data 不存在时使用）
# ==============================================================================

_SAMPLE_DATA_PATH = os.path.join(_THIS_DIR, "sample_data", "sample_runs.json")

_BUILTIN_RUNS = [
    {
        "run_id": 1, "timestamp": "2026-01-01 10:00:00",
        "generated_scheme": {
            "analysis_report": {"domain_detected": "历史文物", "intent_match": "Match"},
            "element_pool": {
                "bottom_layer": [
                    {"id": "bg_style", "name": "背景风格", "options": [
                        {"value": "ink_wash",    "label": "水墨宣纸",  "desc": "仿古宣纸底纹，呈现东方雅韵"},
                        {"value": "museum_dark", "label": "博物馆深邃", "desc": "深灰背景模拟展厅灯光"},
                    ]},
                    {"id": "grid_style", "name": "网格样式", "options": [
                        {"value": "classic_frame", "label": "古典边框", "desc": "回纹装饰边框"},
                        {"value": "minimal",       "label": "极简无框", "desc": "仅保留坐标轴"},
                    ]},
                ],
                "middle_layer": [
                    {"id": "chart_type", "name": "图表形态", "options": [
                        {"value": "standard_bar", "label": "标准柱状图", "desc": "经典双柱对比"},
                        {"value": "pictogram",    "label": "象形图",    "desc": "用瓷器剪影堆叠表示数量"},
                    ]},
                    {"id": "color_scheme", "name": "配色方案", "options": [
                        {"value": "qinghua_classic", "label": "青花经典", "desc": "钴蓝配釉里红"},
                        {"value": "dynasty_gold",    "label": "皇家金璃", "desc": "明黄配帝王紫"},
                    ]},
                ],
                "top_layer": [
                    {"id": "highlight_insight", "name": "核心洞察", "options": [
                        {"value": "ratio_focus", "label": "强调倍数关系", "content": "清代数量是明代的2.35倍"},
                        {"value": "total_focus", "label": "强调总量悬殊", "content": "清代(625) 远超 明代(266)"},
                    ]},
                    {"id": "visual_assets", "name": "装饰素材", "options": [
                        {"category": "瓷器", "suggestion": "青花瓷瓶插画", "keywords": "Blue white porcelain vase"},
                    ]},
                ],
            },
        },
    },
    {
        "run_id": 2, "timestamp": "2026-01-01 10:01:00",
        "generated_scheme": {
            "analysis_report": {"domain_detected": "历史文物", "intent_match": "Match"},
            "element_pool": {
                "bottom_layer": [
                    {"id": "bg_style", "name": "背景风格", "options": [
                        {"value": "porcelain_white", "label": "瓷白素净", "desc": "纯净象牙白底"},
                        {"value": "ink_wash",        "label": "水墨宣纸", "desc": "仿古宣纸底纹"},
                    ]},
                    {"id": "grid_style", "name": "网格样式", "options": [
                        {"value": "subtle_grid", "label": "淡雅辅助线", "desc": "浅色虚线网格"},
                        {"value": "minimal",     "label": "极简无框",   "desc": "最大化数据区域"},
                    ]},
                ],
                "middle_layer": [
                    {"id": "chart_type", "name": "图表形态", "options": [
                        {"value": "radial_compare", "label": "环形对比",   "desc": "双环嵌套展示比例"},
                        {"value": "standard_bar",   "label": "标准柱状图", "desc": "清晰直观对比"},
                    ]},
                    {"id": "color_scheme", "name": "配色方案", "options": [
                        {"value": "ink_gradient",    "label": "墨色渐变", "desc": "从淡墨到浓墨的灰阶渐变"},
                        {"value": "qinghua_classic", "label": "青花经典", "desc": "钴蓝配釉里红"},
                    ]},
                ],
                "top_layer": [
                    {"id": "highlight_insight", "name": "核心洞察", "options": [
                        {"value": "ratio_focus", "label": "强调倍数关系", "content": "清代是明代的2.35倍"},
                        {"value": "pct_focus",   "label": "强调占比格局", "content": "清代占比70.1%"},
                    ]},
                    {"id": "visual_assets", "name": "装饰素材", "options": [
                        {"category": "龙纹", "suggestion": "清代龙纹插画", "keywords": "Qing dynasty dragon pattern"},
                    ]},
                ],
            },
        },
    },
]


# ==============================================================================
#  以下为执行逻辑，一般不需要修改
# ==============================================================================

def _print_config():
    print("\n当前 SOM 配置:")
    print(f"  TEXT_MODEL_NAME         = {cfg.TEXT_MODEL_NAME}")
    print(f"  WEIGHT_NLP / CO / CAT / LAYER / GRAPH = "
          f"{cfg.WEIGHT_NLP} / {cfg.WEIGHT_CO_OCCURRENCE} / "
          f"{cfg.WEIGHT_CATEGORY} / {cfg.WEIGHT_LAYER} / {cfg.WEIGHT_GRAPH}")
    print(f"  GRID_SIZE_PADDING       = {cfg.GRID_SIZE_PADDING}")
    print(f"  SOM sigma={cfg.SOM_SIGMA}  lr={cfg.SOM_LEARNING_RATE}  "
          f"topology={cfg.SOM_TOPOLOGY}  seed={cfg.SOM_RANDOM_SEED}")
    print(f"  SOM_TRAINING_ITERATIONS = {cfg.SOM_TRAINING_ITERATIONS}  "
          f"init={cfg.SOM_INIT_METHOD}")
    print(f"  LINK_MIN_LIFT           = {cfg.LINK_MIN_LIFT}")
    print()


def main():
    print("=" * 60)
    print("  SOM 调试脚本")
    print("=" * 60)
    _print_config()

    # ── 1. 加载数据 ──
    if INPUT_JSON_PATH:
        path = os.path.abspath(INPUT_JSON_PATH)
        print(f"输入文件: {path}")
        try:
            raw_runs = json_io.load_runs_from_file(path)
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            sys.exit(1)
    elif os.path.exists(_SAMPLE_DATA_PATH):
        print(f"使用示例数据: {_SAMPLE_DATA_PATH}")
        try:
            raw_runs = json_io.load_runs_from_file(_SAMPLE_DATA_PATH)
        except Exception as e:
            print(f"加载示例文件失败，使用内置数据: {e}")
            raw_runs = json_io.normalize_runs_payload(_BUILTIN_RUNS)
    else:
        print("使用内置最小样本（2 条 runs）")
        raw_runs = json_io.normalize_runs_payload(_BUILTIN_RUNS)

    json_io.print_runs_summary(raw_runs)

    # ── 2. 运行流水线 ──
    print("\n开始 SOM 流水线 ...")
    t0 = time.time()
    try:
        bundle = pipeline.build_som_from_runs(raw_runs)
    except Exception as e:
        print(f"\n❌ 流水线失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    print(f"\n✅ 完成，耗时 {time.time() - t0:.2f}s")

    # ── 3. 打印摘要 ──
    pipeline.print_bundle_summary(bundle)

    # ── 4. 保存结果 ──
    if OUTPUT_JSON_PATH:
        try:
            saved = json_io.save_som_result(bundle, os.path.abspath(OUTPUT_JSON_PATH))
            print(f"结果已保存: {saved}")
        except Exception as e:
            print(f"⚠️  保存失败: {e}")

    # ── 5. 可视化 ──
    if OPEN_VIZ:
        print(f"\n启动可视化服务器 → http://localhost:{VIZ_PORT}/")
        print("（关闭终端或按 Ctrl+C 可停止服务器）\n")
        try:
            from som_module.viz.server import launch
            launch(bundle, port=VIZ_PORT, open_browser=True, block=True)
        except ImportError:
            print("❌ 未找到 Flask，请执行: pip install flask")
        except KeyboardInterrupt:
            print("\n已停止。")


if __name__ == "__main__":
    main()
