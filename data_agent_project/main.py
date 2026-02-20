import os
import json
from agent.universal_agent import UniversalAgent

if __name__ == "__main__":
    # 请替换为你的实际文件路径
    csv_file = r"E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"
    table_description = "该表格记录了故宫博物院的瓷器藏品信息，包括年代、类别等字段。"

    if os.path.exists(csv_file):
        agent = UniversalAgent(csv_file, table_description)

        print("--- 测试开始 ---")

        # 场景: 趋势 (Temporal)
        query = "故宫藏品中，明代和清代的瓷器数量分别是多少？"

        # 接收两个返回值：文本回复 和 图表JSON
        response, chart_json = agent.solve(query)

        print(f"🤖 回答:\n{response}")

        if chart_json:
            print("\n📈 [Vega-Lite 图表代码]:")
            print(json.dumps(chart_json, indent=2, ensure_ascii=False))
            # 提示：你可以将此 JSON 粘贴到 https://vega.github.io/editor/ 进行查看
        else:
            print("\n⚠️ 未生成有效图表。")

    else:
        print("❌ 找不到 CSV 文件，请检查路径。")