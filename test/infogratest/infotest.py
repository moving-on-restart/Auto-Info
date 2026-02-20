import pandas as pd
import json
import os
import sys

# 假设当前脚本与你提供的模块在同一目录，或者已在 PYTHONPATH 中
# 根据提供的文件名导入模块
from app3.data_agent_project.core.schema_analyzer import SchemaAnalyzer
from app3.services.description_service import generate_description
from app3.data_agent_project.analyze_data_with_chart import analyze_data_with_chart
import infoio


def main():
    # ==========================================
    # 1. 定义输入变量
    # ==========================================
    my_csv_path = r"E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"
    my_question = "从唐代到清代，瓶类文物的高度是如何变化的？"

    print(f"--- 开始处理 ---")
    print(f"文件路径: {my_csv_path}")
    print(f"用户问题: {my_question}\n")

    # ==========================================
    # 2. 模拟 upload_logic 的逻辑生成 Description 和 Schema
    #    (对应 prompt: 调用者些变量调用upload_logic与decription_service生成table_description...调用schemaanalyzer生成table_schema)
    # ==========================================

    # 2.1 读取文件 (模拟 process_uploaded_file)
    if not os.path.exists(my_csv_path):
        print(f"错误: 文件不存在 -> {my_csv_path}")
        return

    df = pd.read_csv(my_csv_path)
    print("✅ 数据加载成功")

    # 2.2 生成 Schema (SchemaAnalyzer)
    # 逻辑源自 upload_logic.py 的 Step 2
    print("⏳ 正在进行 Schema 分析...")
    analyzer = SchemaAnalyzer(df)
    table_schema = analyzer.analyze()
    print("✅ Table Schema 生成完毕")
    # print(table_schema) # 调试用

    # 2.3 生成 Description (description_service)
    # 逻辑源自 upload_logic.py 的 Step 3
    print("⏳ 正在生成数据集描述...")
    meta_data = {
        'columns': df.columns.tolist(),
        'rows': len(df)
    }
    table_description = generate_description(meta_data, table_schema)
    print(f"✅ Table Description 生成完毕: {table_description}\n")

    # ==========================================
    # 3. 生成分析结果与图表代码
    #    (对应 prompt: 再用analyze生成，vegalite_code)
    # ==========================================
    print("⏳ 正在调用 analyze_data_with_chart 进行数据分析...")

    # 注意：analyze_data_with_chart 返回的是 (answer_text, chart_json_dict)
    answer, chart_json = analyze_data_with_chart(my_csv_path, table_description, my_question)

    if chart_json:
        vegalite_code = json.dumps(chart_json, ensure_ascii=False)
        print("✅ Vega-Lite 代码生成成功")
    else:
        vegalite_code = "{}"
        print("⚠️ 未生成图表，将使用空 JSON")

    print(f"🤖 AI 回答: {answer}\n")

    # ==========================================
    # 4. 生成信息图结构
    #    (对应 prompt: 最后调用infoio生成信息图结构)
    # ==========================================
    print("⏳ 正在调用 infoio 生成信息图可视化元素...")

    infographic_structure = infoio.generate_visualization_elements(
        user_query=my_question,
        table_schema=table_schema,  # 来自步骤 2.2
        table_description=table_description,  # 来自步骤 2.3
        vegalite_code=vegalite_code  # 来自步骤 3
    )

    # ==========================================
    # 5. 输出最终结果
    # ==========================================
    print("\n" + "=" * 30)
    print("   最终生成的 JSON 结构")
    print("=" * 30)

    if infographic_structure:
        print(json.dumps(infographic_structure, indent=2, ensure_ascii=False))
    else:
        print("❌ 生成失败 (infoio 返回为空)")


if __name__ == "__main__":
    main()