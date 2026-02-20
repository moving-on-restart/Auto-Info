import pandas as pd
from app3.data_agent_project.core.llm_client import LLMClient
from app3.data_agent_project.core.schema_analyzer import SchemaAnalyzer
from app3.data_agent_project.core.sandbox import CodeSandbox, VegaSandbox # 导入新的 VegaSandbox
from app3.data_agent_project.modules.router import TaskRouter
from app3.data_agent_project.modules.handlers.analytics import StatisticsHandler, TemporalHandler, CorrelationHandler
from app3.data_agent_project.modules.handlers.rag import KnowledgeRetrievalHandler



class UniversalAgent:
    def __init__(self, csv_path, table_description):
        print(f"📂 加载数据: {csv_path}")
        self.df = pd.read_csv(csv_path)
        self.analyzer = SchemaAnalyzer(self.df)
        self.schema = self.analyzer.analyze()
        self.sandbox = CodeSandbox()
        self.vega_sandbox = VegaSandbox()  # 初始化 VegaSandbox
        self.router = TaskRouter()
        self.table_description = table_description  # 新增变量存储表格描述

        # 初始化各领域的 Handler
        self.handlers = {
            "STATISTICS": StatisticsHandler(self.df, self.schema, self.sandbox,self.table_description),
            "TEMPORAL": TemporalHandler(self.df, self.schema, self.sandbox,self.table_description),
            "CORRELATION": CorrelationHandler(self.df, self.schema, self.sandbox,self.table_description),
            "KNOWLEDGE": KnowledgeRetrievalHandler(self.df, self.schema, self.sandbox,self.table_description)
        }
        print("✅ 系统初始化完成。")

    def solve(self, query):
        print(f"\n💬 用户: {query}")

        # 1. 意图识别
        category, reason = self.router.route(query)
        print(f"🧭 任务分类: [{category}] ({reason})")

        # 2. 路由分发与执行
        handler = self.handlers.get(category)
        if not handler:
            return "无法识别的任务类型。"

        fact_data, viz_advice = handler.handle(query)

        # 3. 最终自然语言生成
        final_response = self._generate_response(query, category, fact_data, viz_advice)
        # 4. 生成可视化图表 (新增步骤)
        print("📊 正在生成可视化图表...")
        vega_json = self._generate_visualization(query, category, fact_data, viz_advice)

        return final_response, vega_json

    def _generate_response(self, query, category, fact_data, viz_advice):
        prompt = f"""
        你是一位专业的数据分析师。

        【当前任务模式】: {category}
        【用户问题】: {query}

        【数据分析结果】:
        {fact_data}

        【可视化建议】:
        {viz_advice}

        请根据分析结果回答用户问题。
        1. 必须基于提供的数据结果说话，不要编造。
        2. 如果结果中包含 DataFrame 表格，请用简洁的语言总结其中的规律。
        3. 在回答的最后，简要提及可视化建议。
        """
        return LLMClient.call_local([{"role": "user", "content": prompt}], temperature=0.5)

    def _generate_visualization(self, query, category, fact_data, viz_advice):
        """生成 Vega-Lite 可视化代码并校验"""

        system_prompt = f"""
        你是一个数据可视化专家，擅长编写 Vega-Lite (JSON) 规范。

        【任务】
        根据用户问题、数据分析结果和可视化建议，生成一个完整的 Vega-Lite JSON 配置。

        【输入信息】
        - 用户问题: "{query}"
        - 任务类型: {category}
        - 数据表结构: 
        {self.schema}
        - 表格描述: {self.table_description}
        - 实际数据/分析结果: 
        {fact_data}
        - 可视化建议: 根据数据选择合适的图表类型（如柱状图、折线图、散点图等）

        【要求】
        1. **数据内嵌**: 请将分析结果中的关键数据提取出来，直接硬编码在 Vega-Lite 的 `data.values` 字段中。不要使用 url 加载数据。
        2. **完整性**: 输出必须是合法的 JSON，包含 `$schema`, `data`, `mark`, `encoding` 等字段。
        3. **格式**: 仅输出 JSON 字符串，不要包含 markdown 标记（如 ```json ... ```）。
        4. **交互**: 如果合适，可以添加简单的 tooltip。
        """

        # 调用远程 Thinking 模型 (claude-opus-4-5-think via AIHubMix)
        # 注意：这里我们使用 call_api 调用远程模型
        raw_response = LLMClient.call_api(
            [{"role": "user", "content": system_prompt}],
            temperature=1.0,  # Thinking 模型通常推荐较高温度或特定设置
            json_mode=True
        )

        # 清理可能存在的 Markdown 标记
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()

        # 调用 VegaSandbox 进行校验
        validation = self.vega_sandbox.validate(clean_json)

        if validation["success"]:
            print("✅ Vega-Lite 代码生成并校验成功。")
            return validation["spec"]
        else:
            print(f"❌ Vega-Lite 校验失败: {validation['error']}")
            # 可以选择重试或返回空，这里返回 None 表示失败
            return None