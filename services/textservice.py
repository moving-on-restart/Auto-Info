import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

from app3.config import AppConfig

# ================= 初始化配置 =================
# 1. 加载环境变量
load_dotenv()

# 2. 配置日志 (后端服务推荐用 logging 而不是 print)
logger = logging.getLogger(__name__)

# 3. 初始化全局 Client (避免每次调用函数都重新建立连接)
config = AppConfig.from_env()
_api_key = config.aihubmix_api_key
_base_url = config.aihubmix_base_url

client = None

if _api_key:
    try:
        client = OpenAI(api_key=_api_key, base_url=_base_url)
        logger.info("✅ GPT Service initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize OpenAI client: {e}")
else:
    logger.warning("⚠️ AIHUBMIX_API_KEY not found. GPT service will be disabled.")


# ================= 核心服务函数 =================
def transform_to_dino_prompt(user_text: str) -> str:
    """
    后端服务函数：将自然语言转换为 GroundingDINO 格式

    Args:
        user_text (str): 用户输入的原始描述 (如 "找一下红色的杯子")

    Returns:
        str: 转换后的 Prompt (如 "red cup")。如果服务不可用或出错，返回原字符串。
    """
    # 1. 快速检查：如果客户端未初始化或输入为空，直接返回原始内容
    if not client or not user_text:
        return user_text

    # 2. 定义 System Prompt
    system_instruction = (
        "你是一个专为 GroundingDINO 目标检测模型服务的 Prompt 转换专家。\n"
        "你的任务是将用户的自然语言描述转换为模型所需的标准格式：'object1 . object2'。\n\n"
        "### 严格执行以下要求：\n"
        "1. **实体提取与语义判断**：\n"
        "   - 分析文本语义，提取所有视觉实体。\n"
        "   - **智能决策实体数量**：\n"
        "     * **修饰关系**（Adjective + Noun）：保持为一个整体（例如：“红色的跑车” -> 'red sports car'）。\n"
        "     * **包含/动作关系**（Noun + Verb + Noun）：通常拆分为独立实体（例如：“人拿着杯子” -> 'person . cup'）。\n"
        "     * **并列关系**：必须拆分（例如：“猫和狗” -> 'cat . dog'）。\n"
        "2. **英译**：将提取出的所有实体准确翻译为英文。\n"
        "3. **格式化**：使用 ' . ' （空格+点+空格）作为分隔符连接实体。\n"
        "4. **清洗**：移除所有无关词汇（如“检测”、“找到”、“请”、“图片中的”等）。\n"
        "5. **输出**：仅输出最终的格式化字符串，严禁包含任何解释。"
    )

    try:
        # 3. 发起请求
        logger.info(f"Processing prompt: {user_text}")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text}
            ],
            temperature=0.1,  # 低温以保证格式稳定
            max_tokens=100  # 限制 Token 消耗
        )

        # 4. 解析结果
        result = response.choices[0].message.content.strip()

        # 5. 格式清洗 (GroundingDINO 对末尾句号敏感)
        if result.endswith(".") and not result.endswith(" ."):
            result = result.rstrip(".")

        logger.info(f"Converted: '{user_text}' -> '{result}'")
        return result

    except Exception as e:
        # 6. 兜底策略：如果 GPT 挂了，记录错误并返回原始文本，保证主流程不崩
        logger.error(f"GPT API Error: {e}")
        return user_text