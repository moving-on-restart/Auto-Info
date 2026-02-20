import os
import sys

# # 获取当前文件所在的目录 (即 data_agent_project 的绝对路径)
# current_dir = os.path.dirname(os.path.abspath(__file__))
#
# # 将这个目录加入到 python 的搜索路径中
# if current_dir not in sys.path:
#     sys.path.append(current_dir)
import json
import traceback
from app3.data_agent_project.agent.universal_agent import UniversalAgent
def analyze_data_with_chart(csv_file, table_description, query):
    """
    封装的数据分析函数：加载数据、执行分析并返回结果与图表。

    Args:
        csv_file (str): CSV 文件的绝对路径或相对路径。
        table_description (str): 对表格内容的自然语言描述（帮助 AI 理解数据语义）。
        query (str): 用户的具体问题。

    Returns:
        tuple: (response_text, chart_json)
            - response_text (str): AI 的文本回答。
            - chart_json (dict or None): Vega-Lite 图表配置字典；如果无需绘图或出错，则为 None。
    """
    # 1. 基础校验
    if not os.path.exists(csv_file):
        return f"❌ 错误：找不到文件，请检查路径 -> {csv_file}", None

    try:
        # 2. 初始化 Agent
        # 注意：UniversalAgent 初始化会读取 CSV 并分析 Schema，
        # 如果是在高并发场景下使用，建议将 agent 实例作为参数传入，避免重复加载文件。
        agent = UniversalAgent(csv_file, table_description)

        # 3. 执行任务
        # 假设 agent.solve(query) 已经按照之前的修改返回 (text, json) 元组
        print(f"🔄 正在处理问题: {query}")
        response, chart_json = agent.solve(query)

        return response, chart_json

    except Exception as e:
        # 捕获运行时的所有异常，确保主程序不崩溃
        error_info = f"❌ 处理过程中发生异常: {str(e)}"
        print(traceback.format_exc()) # 打印详细堆栈供调试
        return error_info, None

# --- 调用示例 (Entry Point) ---
if __name__ == "__main__":
    # 1. 定义输入
    my_csv_path = r"E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"
    my_description = "故宫博物院的瓷器藏品信息。"
    my_question = "明代和清代的瓷器数量对比？"

    # 2. 调用函数
    print("--- 开始调用封装函数 ---")
    answer, chart = analyze_data_with_chart(my_csv_path, my_description, my_question)

    # 3. 处理输出
    print(f"\n🤖 [AI 回答]:\n{answer}")

    if chart:
        print("\n📈 [可视化图表 (Vega-Lite JSON)]:")
        # 将 JSON 对象格式化为字符串打印，方便查看或复制
        print(json.dumps(chart, indent=2, ensure_ascii=False))
        print("\n💡 提示: 你可以将上面的 JSON 代码复制到 https://vega.github.io/editor/ 查看渲染效果。")
    else:
        print("\n⚠️ 本次回答未生成图表 (或生成失败)。")