# -*- coding: utf-8 -*-
import json
import re

# 假设这是你项目中的实际路径，请确保环境中有此模块
try:
    from app3.data_agent_project.core.llm_client import LLMClient
except ImportError:
    # 仅用于无环境时的占位
    class LLMClient:
        @staticmethod
        def call_local(messages, temperature, json_mode):
            return "{}"


def extract_json(text):
    """
    从字符串中提取 JSON 内容，去除 Markdown 标记。
    """
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        return match.group(1).strip()
    return text.strip()


def generate_visualization_elements(user_query, table_schema, table_description, vegalite_code):
    """
    调用 LLM 分析用户意图和当前图表，生成通用的信息图可视化元素池。
    """

    # ==========================================
    # 1. 定义通用化 (Universal) System Prompt
    # ==========================================
    system_prompt = """
你是一位世界顶级的数据可视化专家与信息图架构师 (Universal Infographic Architect)。
你的任务是根据用户的数据查询和业务场景，拆解出构建信息图所需的“可选项元素池”。

### 核心任务：
1. **场景识别**：分析用户查询隐含的业务领域（如：金融、医疗、电商、历史、体育、IT等）。
2. **意图校验**：检查当前的 Vega-Lite 图表是否准确反映了用户意图。
3. **元素生成**：基于“三层视觉模型”生成设计方案。

### 三层视觉模型指导：

1. **底层元素 (Bottom Layer - 氛围与容器)**:
   - **背景风格**: 根据场景推荐（如金融深色、医疗白色、历史纹理）。
   - **坐标轴**: 决定网格的密度与样式。

2. **中层元素 (Middle Layer - 数据表达)**:
   - **图表变体**: 推荐适合数据的增强形式（如象形图、面积图）。
   - **配色方案**: 语义色（涨跌/冷暖）或 美学色（品牌/渐变）。

3. **顶层元素 (Top Layer - 叙事与修饰)**:
   - **洞察高亮 (Highlights)**: 提取关键数字（最大值、增长率等）。
   - **注解文案 (Annotations)**: 客观陈述或业务洞察。
   - **视觉素材 (Visual Assets)**: **(关键修改)** 这是顶层的装饰性元素。根据查询实体推荐图标或插画关键词（如查询“特斯拉”推荐“电动车Icon”）。

---

### 输出格式规范 (Strict JSON):
请直接输出 JSON，不要包含 Markdown 格式之外的废话。格式如下：

{
    "analysis_report": {
        "domain_detected": "识别到的领域",
        "intent_match": "Match / Mismatch",
        "data_correction_suggestion": "修正建议或留空"
    },
    "element_pool": {
        "bottom_layer": [
            { 
                "id": "bg_style", 
                "name": "背景风格", 
                "options": [
                    {"value": "style_1", "label": "风格1名称", "desc": "描述..."},
                    {"value": "style_2", "label": "风格2名称", "desc": "描述..."}
                ]
            },
            { "id": "axis_style", "name": "网格样式", "options": ["标准网格", "极简无框"] }
        ],
        "middle_layer": [
            { 
                "id": "chart_type", 
                "name": "图表形态", 
                "options": [
                    {"value": "standard", "label": "标准图表", "desc": "描述..."},
                    {"value": "creative", "label": "创意变体", "desc": "描述..."}
                ]
            },
            { 
                "id": "color_scheme", 
                "name": "配色方案", 
                "options": [
                    {"value": "semantic", "label": "语义配色", "desc": "描述..."},
                    {"value": "aesthetic", "label": "美学配色", "desc": "描述..."}
                ]
            }
        ],
        "top_layer": [
            { 
                "id": "highlight_insight", 
                "name": "核心洞察", 
                "options": [
                    {"value": "metric_1", "label": "总量/均值洞察", "content": "内容文本..."},
                    {"value": "metric_2", "label": "趋势洞察", "content": "内容文本..."}
                ]
            },
            { 
                "id": "annotation_text", 
                "name": "注解风格", 
                "options": [
                    {"style": "direct", "label": "直白数据", "text": "内容文本..."},
                    {"style": "story", "label": "故事讲述", "text": "内容文本..."}
                ]
            },
            {
                "id": "visual_assets",
                "name": "装饰素材",
                "options": [
                    { "category": "实体1", "suggestion": "推荐图标", "keywords": "Search Keyword" },
                    { "category": "实体2", "suggestion": "推荐插画", "keywords": "Search Keyword" }
                ]
            }
        ]
    }
}
"""

    # ==========================================
    # 2. 构建 User Input
    # ==========================================
    user_input_content = f"""
请分析以下输入并生成信息图元素池：

[User Query]: {user_query}
[Table Schema]: {table_schema}
[Table Description]: {table_description}
[Current Vega-Lite]: {vegalite_code}
"""

    # ==========================================
    # 3. 调用 LLM
    # ==========================================
    print(f"正在分析意图并生成通用视觉元素 (User Query: {user_query})...")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input_content}
    ]

    try:
        response_str = LLMClient.call_api(messages, temperature=0.4, json_mode=True)
        cleaned_json = extract_json(response_str)
        result = json.loads(cleaned_json)
        return result

    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        return None
    except Exception as e:
        print(f"LLM 调用错误: {e}")
        return None


# ==========================================
# 测试代码块
# ==========================================
if __name__ == "__main__":
    print("=== 测试场景: 金融/股票 ===")
    res = generate_visualization_elements(
        user_query="过去一年英伟达与特斯拉的股价波动趋势",
        table_schema="- Date [Date], - Ticker [Text], - Close_Price [Numeric]",
        table_description="纳斯达克股票历史数据",
        vegalite_code="{...mark: line...}"
    )

    if res:
        print(f"领域识别: {res.get('analysis_report', {}).get('domain_detected')}")

        # 打印 Top Layer 中的各个元素 ID，确认 visual_assets 是否在其中
        top_layer = res.get('element_pool', {}).get('top_layer', [])
        print("\nTop Layer 包含的组件:")
        for item in top_layer:
            print(f"- [ID: {item.get('id')}] {item.get('name')}")
            # 单独展示 visual_assets 的内容
            if item.get('id') == 'visual_assets':
                print(f"  -> 素材建议: {item.get('options')}")