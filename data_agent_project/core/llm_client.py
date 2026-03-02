import requests
from openai import OpenAI
# 确保这里导入了新增加的配置项
from app3.data_agent_project.config.settings import (
    LLM_API_URL,
    LLM_TIMEOUT,
    LLM_MAX_TOKENS,
    AIHUBMIX_KEY,
    AIHUBMIX_BASE_URL,
    REMOTE_MODEL_NAME,
    REMOTE_MODEL_MAX_TOKENS,
    DOUBAO_MODEL_NAME,
    DOUBAO_MODEL_MAX_TOKENS,
    DOUBAO_THINKING_TYPE,
)


class LLMClient:
    """统一的 LLM 调用接口"""

    # 初始化 OpenAI 客户端 (复用以提高效率)
    _client = None

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            cls._client = OpenAI(
                base_url=AIHUBMIX_BASE_URL,
                api_key=AIHUBMIX_KEY,
            )
        return cls._client

    @staticmethod
    def _safe_extract_content(completion):
        try:
            return completion.choices[0].message.content
        except Exception:
            return "Error"

    @staticmethod
    def call_local(messages, temperature=0.1, json_mode=False):
        """调用本地部署的模型"""
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": LLM_MAX_TOKENS
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            res = requests.post(LLM_API_URL, json=payload, timeout=LLM_TIMEOUT).json()
            return res['choices'][0]['message']['content']
        except Exception as e:
            print(f"❌ 本地 LLM 调用失败: {e}")
            return "{}" if json_mode else "Error"

    @staticmethod
    def call_api(messages, temperature=0.1, json_mode=False):
        """调用远程 API 模型 (AIHubMix)"""
        try:
            client = LLMClient._get_client()

            # --- 针对 Thinking 模型的特殊处理 ---
            # 错误显示: `temperature` may only be set to 1 when thinking is enabled.
            # 为了保持接口一致性，如果检测到是思考模型，强制内部使用 temperature=1
            current_temperature = temperature
            if "think" in REMOTE_MODEL_NAME or "reasoner" in REMOTE_MODEL_NAME:
                current_temperature = 1
            # ----------------------------------

            # 构造参数
            kwargs = {
                "model": REMOTE_MODEL_NAME,
                "messages": messages,
                "temperature": current_temperature,  # 使用处理后的温度
                # 以此类推，Thinking模型有时也不支持 max_tokens 限制思考过程，
                # 如果不报错可以保留，若后续报错可在此处移除 max_tokens
                "max_tokens": REMOTE_MODEL_MAX_TOKENS,
            }

            # 注意：部分 Thinking 模型可能不支持 json_object 模式，
            # 如果后续报 response_format 错误，需要在这里加判断跳过
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            completion = client.chat.completions.create(**kwargs)
            return LLMClient._safe_extract_content(completion)

        except Exception as e:
            print(f"❌ 远程 API 调用失败: {e}")
            # 打印详细错误以便调试
            if hasattr(e, 'body'):
                print(f"Details: {e.body}")
            return "{}" if json_mode else "Error"

    @staticmethod
    def call_doubao_seed_pro(messages, temperature=0.1, json_mode=False, thinking_type=None):
        """
        Call doubao-seed-2-0-pro through AIHubMix (OpenAI-compatible API).
        thinking_type: disabled | enabled | auto
        """
        try:
            client = LLMClient._get_client()

            resolved_thinking = (thinking_type or DOUBAO_THINKING_TYPE or "disabled").strip().lower()
            if resolved_thinking not in {"disabled", "enabled", "auto"}:
                resolved_thinking = "disabled"

            kwargs = {
                "model": DOUBAO_MODEL_NAME,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": DOUBAO_MODEL_MAX_TOKENS,
                "thinking": {"type": resolved_thinking},
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                completion = client.chat.completions.create(**kwargs)
            except TypeError:
                # Some SDK versions do not accept custom top-level fields like `thinking`.
                thinking_payload = kwargs.pop("thinking", None)
                if thinking_payload:
                    kwargs["extra_body"] = {"thinking": thinking_payload}
                completion = client.chat.completions.create(**kwargs)

            return LLMClient._safe_extract_content(completion)

        except Exception as e:
            print(f"Doubao API call failed: {e}")
            if hasattr(e, "body"):
                print(f"Details: {e.body}")
            return "{}" if json_mode else "Error"
