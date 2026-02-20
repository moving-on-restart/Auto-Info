
##v3使用
import json
import logging
from app3.services.gemini_image_service import GeminiLangChainService


class InfographicService:
    def __init__(self, output_dir="generated_images"):
        self.image_engine = GeminiLangChainService(output_dir=output_dir)

    def generate(self, description, query, analysis_result, chart_json):
        """
        直接使用完整的 chart_json 生成 Prompt
        """

        # 1. 安全校验与序列化
        if not chart_json:
            chart_code_str = "（未提供图表数据）"
        else:
            try:
                # 直接将字典转为 JSON 字符串，保留所有数据细节
                chart_code_str = json.dumps(chart_json, indent=2, ensure_ascii=False)
            except Exception as e:
                logging.error(f"JSON serialization failed: {e}")
                chart_code_str = "（图表数据解析失败）"

        # 2. 构建 Prompt
        # 既然数据完整，我们明确告诉 AI 请根据这些数据点来绘图
        prompt = f"""
        请扮演一位专业的数据可视化设计师。你需要根据以下数据分析结果和原本的图表代码，设计一张精美、现代化的数据信息图 (Infographic)。

        ### 1. 任务背景
        - **数据来源**: {description}
        - **用户问题**: {query}
        - **核心结论**: {analysis_result}

        ### 2. 参考图表数据 (Vega-Lite Source Code)
        以下是完整的图表定义代码，包含了具体的数据值 (values)。请仔细阅读这些数据，确保生成的信息图在趋势和数值上与此保持一致。

        ```json
        {chart_code_str}
        ```

        ### 3. 设计要求
        - **视觉风格**: 采用扁平化或伪 3D 的商业智能 (BI) 仪表盘风格，背景整洁（推荐深色或科技蓝白）。
        - **精准还原**: 请基于代码中的 `values` 数据绘制主要的视觉元素（如柱子的高度、线条的走向），不要凭空捏造数据趋势。
        - **排版**: 将“核心结论”放在显眼位置，辅以对应的图标。
        """

        # 3. 生成图片
        image_path = self.image_engine.generate(prompt=prompt, aspect_ratio="3:4")

        return image_path