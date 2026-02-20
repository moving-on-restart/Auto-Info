import logging
import json
import os
from flask import current_app

# 导入您提供的分析控制器 (确保它位于 controller 目录下)
from app3.controller.generate_info_data_controller import generate_visualization_elements
# 导入原有的生图服务
from app3.services.gemini_image_service import GeminiLangChainService

logger = logging.getLogger(__name__)

# 初始化生图服务 (图片保存到 static/generated_assets 以便前端访问)
ASSETS_DIR = "static/generated_assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
image_service = GeminiLangChainService(output_dir=ASSETS_DIR)


def _rgb_triplet_to_hex(color_triplet):
    """Convert [r, g, b] into #RRGGBB."""
    if not isinstance(color_triplet, (list, tuple)) or len(color_triplet) < 3:
        return None
    try:
        r = max(0, min(255, int(color_triplet[0])))
        g = max(0, min(255, int(color_triplet[1])))
        b = max(0, min(255, int(color_triplet[2])))
        return f"#{r:02X}{g:02X}{b:02X}"
    except (TypeError, ValueError):
        return None


def _build_palette_info_text(color_scheme_selection):
    """
    Support both:
    1) legacy string color scheme,
    2) structured palette object selected from extracted palettes.
    """
    if isinstance(color_scheme_selection, dict):
        source_label = color_scheme_selection.get("source_label", "未命名对象")
        option_label = color_scheme_selection.get("label", "调色板方案")
        palette = color_scheme_selection.get("palette") or []
        harmony_score = color_scheme_selection.get("harmony_score")
        harmony_text = f"{harmony_score:.3f}" if isinstance(harmony_score, (int, float)) else "N/A"

        hex_list = []
        for color in palette:
            hex_color = _rgb_triplet_to_hex(color)
            if hex_color:
                hex_list.append(hex_color)

        if hex_list:
            return f"来源对象: {source_label}; 方案: {option_label}; 色值: {', '.join(hex_list)}; 和谐度: {harmony_text}"
        return f"来源对象: {source_label}; 方案: {option_label}; 和谐度: {harmony_text}"

    return f"未提供提取调色板，按配色偏好“{color_scheme_selection}”生成。"


def get_infographic_plan(description, query, analysis_result, chart_json):
    """
    第一步：调用 LLM 分析数据，生成视觉元素池 (JSON)
    """
    try:
        chart_str = json.dumps(chart_json, ensure_ascii=False)
        if len(chart_str) > 2000:
            chart_str = chart_str[:2000] + "...(truncated)"

        plan_json = generate_visualization_elements(
            user_query=query,
            table_schema=analysis_result,
            table_description=description,
            vegalite_code=chart_str
        )

        return plan_json
    except Exception as e:
        logger.error(f"Plan Gen Error: {e}")
        return {"error": str(e), "element_pool": {}}


def generate_single_asset(keywords, style_desc):
    """
    中间步骤：用户点击生成某个具体的视觉素材 (如图标、插画)
    """
    try:
        prompt = f"""
        请设计一个高质量的视觉素材元素,我想将其用在信息图设计中。
        主题内容：{keywords}
        设计风格：{style_desc} 
        要求：请输出一个干净、独立的元素主体，不要有多余的背景杂物。
        """
        image_path = image_service.generate(prompt=prompt, aspect_ratio="1:1")

        if image_path:
            web_path = image_path.replace("\\", "/")
            if "static/" in web_path:
                web_path = web_path.split("static/")[-1]
                web_path = f"/static/{web_path}"
            return web_path
        return None
    except Exception as e:
        logger.error(f"Asset Gen Error: {e}")
        raise e


def generate_final_composite(user_selections, chart_json, description, query, analysis_result):
    """
    最后一步：根据用户选择的所有参数 + 数据分析上下文，合成最终 Prompt
    """
    try:
        # 1. 动态解析所有层级的用户选择
        bottom_layer = user_selections.get('bottom_layer', {})
        middle_layer = user_selections.get('middle_layer', {})
        # [修复]: 使用 .copy() 防止 pop 操作修改原始的 user_selections 数据
        top_layer = user_selections.get('top_layer', {}).copy()

        # 单独提取并移除 visual_assets，因为要单独处理
        visual_assets_obj = top_layer.pop('visual_assets', None)
        color_scheme_selection = middle_layer.get('color_scheme', '商务专业')
        palette_info_text = _build_palette_info_text(color_scheme_selection)

        # 构建基础样式 Prompt
        design_preferences = f"""
        - **背景风格 (Background)**: {bottom_layer.get('bg_style', '现代简约')}
        - **坐标轴风格 (Axis)**: {bottom_layer.get('axis_style', '清晰易读')}
        - **图表类型 (Chart Type)**: {middle_layer.get('chart_type', '柱状/折线图')}
        - **调色板信息 (Palette Info)**: {palette_info_text}
        """

        # 动态构建顶层叙事（标题、洞察、注释等）的 Prompt
        narrative_preferences = ""
        if top_layer:
            narrative_preferences = "### 4. 叙事与文案排版要求 (Narrative & Typography)\n请根据以下要求设计文字内容：\n"
            # 建立一个友好的中文映射，方便 LLM 理解
            key_mapping = {
                'title_style': '标题文案风格 (Title Style)',
                'highlight_insight': '核心洞察的呈现方式 (Highlight Insight)',
                'annotation_text': '数据注释风格 (Annotation Text)'
            }
            for key, val in top_layer.items():
                # [核心修改]: 如果 key 不在映射表中，自动将英文 key 的下划线替换为空格并首字母大写
                # 例如 'font_family' 会自动变成 'Font Family'
                label = key_mapping.get(key, key.replace('_', ' ').title())
                narrative_preferences += f"- **{label}**: 采用“{val}”的表达方式。\n"

        # 处理 Asset 文本提示词 (适配字典格式)
        asset_prompt_section = ""
        if visual_assets_obj and isinstance(visual_assets_obj, dict):
            # 提取中英文关键词
            keywords = visual_assets_obj.get('keywords', '')
            suggestion = visual_assets_obj.get('suggestion', keywords)
            category = visual_assets_obj.get('category', '视觉元素')

            asset_prompt_section = f"""
            ### 5. 核心插图要求 (Visual Asset)
            请将以下指定的插画/图标概念自然地融入到信息图的设计中，作为背景点缀或核心装饰：
            - **元素类别**: {category}
            - **画面内容**: "{suggestion}" (概念参考: {keywords})
            请确保该元素的风格与整体配色协调统一。
            """

        # 2. 准备数据字符串
        chart_code_str = json.dumps(chart_json, ensure_ascii=False)
        if len(chart_code_str) > 5000:
            chart_code_str = chart_code_str[:5000] + "...(truncated)"

        # 3. 构建新的 Master Prompt
        prompt = f"""
        请扮演一位专业的数据可视化设计师。你需要根据以下数据分析结果、图表代码以及用户的定制要求，设计一张精美、具有艺术感的数据信息图 (Infographic)。

        ### 1. 任务背景
        - **数据来源**: {description}
        - **用户问题**: {query}
        - **核心结论**: {analysis_result}

        ### 2. 参考图表数据 (Vega-Lite Source Code)
        请严格参考以下代码中的 `values` 数据，确保生成的信息图在数值比例上真实准确。
        ```json
        {chart_code_str}
        ```

        ### 3. 全局设计风格要求
        {design_preferences}

        {narrative_preferences}

        {asset_prompt_section}

        ### 6. 输出要求
        请生成一张完整的 3:4 竖版数据海报。构图需主次分明，标题、洞察文案、图表和插画完美融合。
        """
        print("--- Final Prompt Generated ---")
        print(prompt)

        # 4. 调用 Gemini 生图 (生成 3:4 竖版海报)
        final_image_path = image_service.generate(prompt=prompt, aspect_ratio="3:4")

        if final_image_path:
            web_path = final_image_path.replace("\\", "/")
            if "static/" in web_path:
                web_path = web_path.split("static/")[-1]
                web_path = f"/static/{web_path}"
            return web_path
        return None

    except Exception as e:
        logger.error(f"Final Gen Error: {e}")
        raise e
