import logging
from app3.data_agent_project.core.llm_client import LLMClient  # 保持你原有的 import

logger = logging.getLogger(__name__)


def generate_description(meta_data, schema_info=None):
    """
    :param meta_data: 基础元数据
    :param schema_info: SchemaAnalyzer 生成的详细字段统计信息 (str)
    """
    columns = meta_data.get('columns', [])
    row_count = meta_data.get('rows', 0)

    try:
        # 1. 构造 Prompt
        system_instruction = (
            "你是一个专业的数据分析助手。请根据提供的数据集元数据和字段统计信息，"
            "用精炼的中文生成一段数据集描述（100字以内）。"
            "描述应包含：数据主题、核心字段的业务含义（如时间范围、数值分布特征等）以及可能的分析方向。"
        )

        # 如果有 Schema 分析结果，则优先使用，否则降级使用 columns
        if schema_info:
            data_context = f"详细字段统计与样本:\n{schema_info}"
        else:
            data_context = f"所有列名: {', '.join(columns)}"

        user_content = (
            f"数据总行数: {row_count}\n"
            f"{data_context}\n\n"
            "请生成该数据集的描述："
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        # 2. 调用本地 LLM
        logger.info("Calling local LLM for description generation...")
        description = LLMClient.call_local(messages, temperature=0.3)

        if not description or description.strip() == "Error":
            return _generate_fallback(columns, row_count)

        return description.strip()

    except Exception as e:
        logger.error(f"Description generation failed: {e}")
        return _generate_fallback(columns, row_count)


def _generate_fallback(columns, row_count):
    col_str = ", ".join(columns[:5])
    if len(columns) > 5: col_str += "..."
    return f"这是一个包含 {row_count} 行数据的表格，主要字段包括：{col_str}。"