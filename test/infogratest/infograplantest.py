# -*- coding: utf-8 -*-
import json
import time
import sys

# 尝试导入您的模块
import app3.controller.generate_info_data_controller



def run_debug_session():
    # ==========================================
    # 1. 准备输入数据 (您提供的真实案例)
    # ==========================================
    user_query = "明代和清代的瓷器数量对比？"

    table_schema = """根据数据分析结果，我们可以得出以下结论：
总体对比：
明代瓷器总数为266件。
清代瓷器总数为625件。
清代的瓷器数量明显多于明代。

细分时代统计：
明代瓷器主要分布在不同的时期，其中清代乾隆时期的瓷器数量最多，为154件；其次是雍正时期的111件、康熙时期的107件。
明代瓷器数量最多的时期是明宣德，有50件。

数据结果总结：
从表格数据可以看出，清代瓷器的数量远超明代，整体趋势非常明确。这表明清代在瓷器制作方面投入了更多资源或需求更大。

可视化建议：
建议使用分组柱状图（Grouped Bar）来展示各个时代的瓷器数量，这样可以直观地比较每个时代在明代和清代之间的差异。"""

    table_description = "该数据集记录了1409件文物的信息，涵盖时代、分类、尺寸等多维度数据。可用于研究中国不同时期的陶瓷艺术风格演变、不同窑口的技术特点及历史分布等。"

    vegalite_code = json.dumps({
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"数量": 266, "朝代": "明代"}, {"数量": 625, "朝代": "清代"}]},
        "encoding": {
            "color": {"field": "朝代", "legend": None,
                      "scale": {"domain": ["明代", "清代"], "range": ["#e67c73", "#57bb8a"]}, "type": "nominal"},
            "tooltip": [{"field": "朝代", "title": "朝代", "type": "nominal"},
                        {"field": "数量", "title": "瓷器数量", "type": "quantitative"}],
            "x": {"axis": {"labelFontSize": 14, "titleFontSize": 14}, "field": "朝代", "sort": ["明代", "清代"],
                  "title": "朝代", "type": "nominal"},
            "y": {"axis": {"labelFontSize": 12, "titleFontSize": 14}, "field": "数量", "title": "瓷器数量",
                  "type": "quantitative"}
        },
        "height": 300,
        "layer": [{"mark": {"cornerRadiusTopLeft": 5, "cornerRadiusTopRight": 5, "type": "bar"}},
                  {"encoding": {"text": {"field": "数量", "type": "quantitative"}},
                   "mark": {"dy": -15, "fontSize": 16, "fontWeight": "bold", "type": "text"}}],
        "mark": {"cornerRadiusTopLeft": 5, "cornerRadiusTopRight": 5, "type": "bar"},
        "title": {"fontSize": 18, "text": "明代和清代瓷器数量对比"},
        "width": 300
    })

    # ==========================================
    # 2. 获取生成次数
    # ==========================================
    try:
        raw_input = input("\n请输入需要生成的次数 (默认为 1): ").strip()
        loop_count = int(raw_input) if raw_input.isdigit() else 1
    except KeyboardInterrupt:
        sys.exit(0)

    print(f"\n🚀 开始执行任务，共 {loop_count} 次调用...\n")

    # ==========================================
    # 3. 循环调用并打印完整结果
    # ==========================================
    for i in range(loop_count):
        print(f"[{i + 1}/{loop_count}] 正在调用 LLM 生成数据...", end="", flush=True)
        start_time = time.time()

        try:
            # 真实调用
            result = app3.controller.generate_info_data_controller.generate_visualization_elements(
                user_query, table_schema, table_description, vegalite_code
            )

            duration = time.time() - start_time
            print(f" 完成! (耗时 {duration:.2f}s)")

            print("-" * 60)
            if result:
                # === 核心修改：直接打印完整的 JSON 结果 ===
                print(f"📝 第 {i + 1} 次生成结果 (Full JSON):")
                print(json.dumps(result, indent=4, ensure_ascii=False))
            else:
                print("❌ 生成失败: 返回结果为 None")
            print("-" * 60 + "\n")

        except Exception as e:
            print(f"\n❌ 调用过程中发生异常: {e}\n")

    print("🏁 所有任务执行完毕。")


if __name__ == "__main__":
    run_debug_session()