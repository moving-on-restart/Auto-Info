import json
from llm_client import LLMClient


def test_llm_calls():
    # 定义一个简单的测试消息
    test_messages = [
        {"role": "user", "content": "你好，请回复‘收到’二字。"}
    ]

    print("正在测试本地 LLM 调用...")
    local_res = LLMClient.call_local(test_messages)
    print(f"本地返回结果: {local_res}")
    print("-" * 30)

    print("正在测试远程 API 调用...")
    api_res = LLMClient.call_api(test_messages)
    print(f"API 返回结果: {api_res}")
    print("-" * 30)

    print("正在测试远程 API 调用...")
    api_res = LLMClient.call_doubao_seed_pro(test_messages)
    print(f"API 返回结果: {api_res}")
    print("-" * 30)

    # 测试 JSON 模式（如果你的模型支持）
    print("正在测试 API JSON 模式...")
    json_messages = [
        {"role": "user", "content": "请返回一个JSON，包含键名 'status'，值为 'ok'"}
    ]
    json_res = LLMClient.call_api(json_messages, json_mode=True)
    print(f"JSON 模式返回: {json_res}")


if __name__ == "__main__":
    test_llm_calls()