# -*- coding: utf-8 -*-
import json
import time
import sys
import csv
from collections import Counter, defaultdict

# 尝试导入您的模块
try:
    import app3.controller.generate_info_data_controller
except ImportError:
    pass  # 占位，确保环境依赖与您实际一致


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
明代瓷器数量最多的时期是明宣德，有50件。"""

    table_description = "该数据集记录了1409件文物的信息，涵盖时代、分类、尺寸等多维度数据。"

    vegalite_code = json.dumps({
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"数量": 266, "朝代": "明代"}, {"数量": 625, "朝代": "清代"}]},
        "mark": "bar"
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
    # 统计与存储数据结构初始化
    # ==========================================
    valid_runs = 0
    domain_counter = Counter()
    element_stats = defaultdict(lambda: defaultdict(Counter))

    # 新增：用于存储每一次完整生成的原始结果
    all_raw_results = []

    # ==========================================
    # 3. 循环调用并记录结果
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

            if result:
                valid_runs += 1

                # --- 新增：保存单次生成的完整结果，并打上序号 ---
                result_with_id = {
                    "run_id": i + 1,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "generated_scheme": result
                }
                all_raw_results.append(result_with_id)

                # --- 收集统计数据 ---
                domain = result.get('analysis_report', {}).get('domain_detected', 'Unknown')
                domain_counter[domain] += 1

                pool = result.get('element_pool', {})
                for layer_name in ['bottom_layer', 'middle_layer', 'top_layer']:
                    for item in pool.get(layer_name, []):
                        item_id = item.get('id', 'unknown_id')
                        options = item.get('options', [])

                        for opt in options:
                            if isinstance(opt, dict):
                                key = opt.get('label') or opt.get('value') or opt.get('category') or opt.get(
                                    'keywords') or str(opt)
                            else:
                                key = str(opt)

                            element_stats[layer_name][item_id][key] += 1

                print(f"✅ 第 {i + 1} 次生成成功并已录入。")
            else:
                print("❌ 生成失败: 返回结果为 None")

        except Exception as e:
            print(f"\n❌ 调用过程中发生异常: {e}\n")

    # ==========================================
    # 4. 打印统计结果并导出文件
    # ==========================================
    print("\n" + "=" * 60)
    print(f"📊 任务执行完毕 (总次数: {loop_count}, 成功: {valid_runs})")
    print("=" * 60)

    if valid_runs == 0:
        print("没有成功的生成记录，无法保存文件。")
        return

    # --- 导出 1: 统计结果 CSV (用于人工快速观察频率) ---
    csv_filename = "generation_statistics.csv"
    csv_headers = ["层级/类别 (Category)", "组件 ID (Element ID)", "选项/值 (Option/Value)", "数量 (Count)",
                   "频率 (Frequency)"]
    csv_data = []

    for domain, count in domain_counter.most_common():
        freq = (count / valid_runs) * 100
        csv_data.append(["领域识别 (Domain Detected)", "-", domain, count, f"{freq:.1f}%"])

    layer_display_names = {'bottom_layer': '底层', 'middle_layer': '中层', 'top_layer': '顶层'}
    for layer_name in ['bottom_layer', 'middle_layer', 'top_layer']:
        layer_data = element_stats.get(layer_name, {})
        for item_id, options_counter in layer_data.items():
            for opt_key, count in options_counter.most_common():
                freq = (count / valid_runs) * 100
                csv_data.append([layer_display_names[layer_name], item_id, opt_key, count, f"{freq:.1f}%"])

    try:
        with open(csv_filename, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers)
            writer.writerows(csv_data)
        print(f"💾 频率统计已保存至: {csv_filename}")
    except Exception as e:
        print(f"❌ 保存 CSV 失败: {e}")

    # --- 导出 2: 完整原始方案 JSON (用于后续算法分析) ---
    json_filename = "raw_schemes_output.json"
    try:
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(all_raw_results, f, ensure_ascii=False, indent=4)
        print(f"📦 所有单次生成的完整方案已保存至: {json_filename}")
    except Exception as e:
        print(f"❌ 保存 JSON 失败: {e}")

    print("\n请检查项目目录获取输出文件。")


if __name__ == "__main__":
    run_debug_session()