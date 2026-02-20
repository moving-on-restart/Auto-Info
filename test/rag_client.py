import pandas as pd
import numpy as np
import requests
import json
import time
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ================= 配置区域 =================
# 您的 Flask API 地址
LLM_API_URL = "http://100.64.0.1:3025/v1/chat/completions"
# 数据文件路径
DATA_PATH = "E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"
# 嵌入模型 (推荐使用中文能力强的模型，首次运行会自动下载)
EMBEDDING_MODEL_NAME = "shibing624/text2vec-base-chinese"


# ===========================================

class KnowledgeBase:
    def __init__(self, csv_path):
        print("正在加载知识库数据...")
        self.df = pd.read_csv(csv_path)
        # 数据清洗：填充空描述，组合标题和描述以丰富语义
        self.df['full_text'] = self.df['文物名称'] + "：" + self.df['文字描述'].fillna("暂无详细描述")

        print(f"正在加载嵌入模型: {EMBEDDING_MODEL_NAME} ...")
        self.encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)

        # 预计算向量索引（如果数据量大，建议保存为 .npy 文件以加速下次启动）
        print("正在构建向量索引 (这可能需要几分钟)...")
        self.vectors = self.encoder.encode(self.df['full_text'].tolist(), show_progress_bar=True)
        print(f"索引构建完成，共 {len(self.df)} 条数据。")

    def search(self, query, top_k=3):
        """
        语义检索：找到与问题最相关的 top_k 条文物记录
        """
        query_vec = self.encoder.encode([query])
        # 计算余弦相似度
        scores = cosine_similarity(query_vec, self.vectors).flatten()
        # 获取分数最高的 top_k 个索引
        top_indices = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            row = self.df.iloc[idx]
            results.append({
                "score": float(scores[idx]),
                "name": row['文物名称'],
                "era": row['时代'],
                "content": row['文字描述']
            })
        return results


def query_llm(messages, max_tokens=2048):
    """
    调用您的本地 Qwen API
    """
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens
    }

    try:
        response = requests.post(LLM_API_URL, json=payload)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"API 调用错误: {e}"


def generate_rag_prompt(query, context_items):
    """
    构建 RAG 提示词
    """
    context_str = "\n".join([
        f"--- 文物[{i + 1}]: {item['name']} ({item['era']}) ---\n描述: {item['content']}"
        for i, item in enumerate(context_items)
    ])

    system_prompt = f"""你是一位故宫博物院的资深陶瓷研究员。请基于以下检索到的【馆藏档案】，回答用户的问题。

【馆藏档案】：
{context_str}

【回答要求】：
1. 必须基于档案内容回答，如果档案中没有相关信息，请诚实说明。
2. 语言风格要专业、雅致，符合故宫美学。
3. 结合文物的时代背景进行简要的艺术点评。
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]


# ================= 主程序入口 =================
if __name__ == "__main__":
    # 1. 初始化知识库
    kb = KnowledgeBase(DATA_PATH)

    print("\n✅ RAG 系统已启动！请输入关于故宫陶瓷的问题 (输入 'exit' 退出)")

    while True:
        user_query = input("\n📝 您的提问: ").strip()
        if user_query.lower() in ['exit', 'quit']:
            break

        if not user_query:
            continue

        # 2. 检索阶段 (Retrieve)
        print("🔍 正在检索相关文物...")
        t0 = time.time()
        results = kb.search(user_query, top_k=3)
        print(f"   检索耗时: {time.time() - t0:.2f}s")

        # (可选) 打印检索到的文物名称供调试
        print(f"   参考文物: {[r['name'] for r in results]}")

        # 3. 生成阶段 (Generate)
        messages = generate_rag_prompt(user_query, results)

        print("🤖 正在思考...")
        answer = query_llm(messages)

        print("\n" + "=" * 40)
        print(f"💡 智能回答:\n{answer}")
        print("=" * 40)