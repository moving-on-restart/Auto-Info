import requests
import json

# 指向你的 SSH 隧道地址
SERVER_URL = "http://100.64.0.1:3025/v1/chat/completions"


def call_llm_server(messages, temperature=0.7):
    """通用的底层调用函数"""
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024
    }

    try:
        response = requests.post(SERVER_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            cost = result['time_cost']
            print(f"✅ [耗时 {cost}s]")
            return content
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 连接错误: {e}")
        return None


# ================== 场景 A: 知识问答 (你的RAG部分) ==================
def scenario_museum_expert(user_query, retrieved_context=""):
    """
    场景：故宫陶瓷专家
    功能：结合检索到的 RAG 上下文回答问题
    """
    # 在本地构建 Prompt，你可以随时修改这里，不需要重启服务器
    system_prompt = "你是一个故宫博物院的陶瓷专家。请基于给定的上下文，用专业且优雅的语言回答用户的问题。"

    full_prompt = f"【已知上下文】：\n{retrieved_context}\n\n【用户问题】：{user_query}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_prompt}
    ]

    print(f"\n🏺 [场景: 陶瓷专家] 提问: {user_query}")
    response = call_llm_server(messages, temperature=0.5)  # 知识类需要低随机性
    print(f"回复: {response}")


# ================== 场景 B: 数据分析 (你的Pandas部分) ==================
def scenario_data_analyst(user_query, df_columns):
    """
    场景：Python 代码生成器
    功能：生成 Pandas 代码来统计数据
    """
    system_prompt = f"""你是一个 Python 数据分析助手。
    你拥有一个 DataFrame `df`，列包含: {df_columns}。
    请只输出 Python 代码，不要解释。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]

    print(f"\n📊 [场景: 代码生成] 需求: {user_query}")
    response = call_llm_server(messages, temperature=0.1)  # 代码生成需要极低随机性
    print(f"生成的代码:\n{response}")


# ================== 场景 C: 美学优化 (你的调色板部分) ==================
def scenario_aesthetic_designer(chart_json):
    """
    场景：美学设计师
    功能：优化图表配色
    """
    system_prompt = "你是一个精通中国传统美色的设计师。请接收 JSON 配置，将其中的颜色代码修改为故宫风格的配色（如：#E0E0E0 -> #F0F8FF）。只返回修改后的 JSON。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": str(chart_json)}
    ]

    print(f"\n🎨 [场景: 美学优化] 正在优化配色...")
    response = call_llm_server(messages, temperature=0.8)  # 创意类需要高随机性
    print(f"优化结果: {response[:100]}...")


# ================== 主程序 ==================
if __name__ == "__main__":
    # 1. 测试陶瓷专家
    scenario_museum_expert(
        user_query="素三彩有什么特点？",
        retrieved_context="素三彩是康熙时期的低温彩釉瓷器，以黄绿紫为主色。"
    )

    # 2. 测试代码生成
    scenario_data_analyst(
        user_query="统计清代不同分类的数量",
        df_columns="['时代', '分类', '文物名称']"
    )

    # 3. 测试美学优化
    scenario_aesthetic_designer({"title": "分布图", "color": ["red", "blue"]})