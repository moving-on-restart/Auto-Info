import os  # 新增: 用于路径判断
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from app3.data_agent_project.modules.handlers.base import BaseHandler
from app3.config import AppConfig


class KnowledgeRetrievalHandler(BaseHandler):
    """处理：知识与检索类 (RAG) - 增强版(支持本地模型缓存)"""

    def __init__(self, df, schema_str, sandbox, table_description):
        super().__init__(df, schema_str, sandbox, table_description)
        self.model = None
        self.doc_embeddings = None
        self.documents = None
        # 定义模型名称和本地保存路径
        self.model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        self.local_model_path = AppConfig.from_env().rag_model_path

        self._init_rag()

    def _init_rag(self):
        print("📥 [RAG] 初始化向量模型..")
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

        # --- 修改开始: 模型加载与保存逻辑 ---
        if os.path.exists(self.local_model_path):
            print(f"📂 [RAG] 检测到本地缓存模型，正在从路径加载: {self.local_model_path}")
            # 直接加载本地文件夹，速度极快且无需联网
            self.model = SentenceTransformer(self.local_model_path)
        else:
            print(f"⬇️ [RAG] 本地未找到模型，正在从 HuggingFace 下载: {self.model_name}")
            print("⏳ [RAG] 请稍候，下载过程将显示在下方进度条(首次运行需要)...")

            # SentenceTransformer 默认会在下载时显示 tqdm 进度条
            # 这里的 cache_folder 仅用于临时缓存，我们稍后会显式 save 到 clean 的目录
            self.model = SentenceTransformer(self.model_name)

            print(f"💾 [RAG] 下载完成，正在保存模型到本地目录: {self.local_model_path}")
            # 创建目录并保存模型文件，下次运行时即可离线加载
            os.makedirs(os.path.dirname(self.local_model_path), exist_ok=True)
            self.model.save(self.local_model_path)
            print("✅ [RAG] 模型保存完毕。")
        # --- 修改结束 ---

        # 构建文档字符串：将每一行转为 "列名:值 | 列名:值" 的格式
        self.documents = self.df.apply(
            lambda x: " | ".join(
                [f"{k}:{v}" for k, v in x.items() if pd.notna(v) and isinstance(v, (str, int, float))]
            ),
            axis=1,
        ).tolist()

        # 预计算所有文档的 Embedding
        print(f"📘 [RAG] 正在计算 {len(self.documents)} 条数据的向量特征...")
        self.doc_embeddings = self.model.encode(self.documents, show_progress_bar=True)  # 开启 embedding 进度条
        print("✅ [RAG] 向量数据库构建完成。")

    def handle(self, query):
        print(f"📳 [RAG] 正在处理: {query}")

        # --- Step 1: 智能筛选(Pre-RAG Filtering) ---
        print("⚙️ [RAG] 正在判断是否需要预筛选数据..")

        # 定义筛选专用的 System Prompt
        filter_system_prompt = """
        你是一个数据分析助手。用户的意图是进行 知识检索。
        请分析用户的查询，判断是否包含明确的数据筛选条件（例如：特定的分类、标签、时代、作者、器型等）。

        1. 如果包含筛选条件：请编写 Pandas 代码对 `df` 进行筛选，并将结果 DataFrame 赋值给 `result`。
           - 务必使用 `str.contains` 进行模糊匹配以提高召回率 (例如 `na=False`)。
           - 例如：用户问“斗彩代表作”，代码应类似 `result = df[df['分类'].astype(str).str.contains('斗彩', na=False)]`。
        2. 如果不包含明确筛选条件（或者是询问通用定义、无关内容）：请直接赋值 `result = df`。

        请严格遵守输出要求，只输出包裹在 markdown 中的 Python 代码。
        """

        # 调用父类的代码生成方法
        filter_code = self.generate_code(query, filter_system_prompt)

        # 在沙箱中执行筛选
        exec_res = self.sandbox.execute(filter_code, self.df)

        target_df = self.df
        if exec_res["success"] and isinstance(exec_res["result_var"], pd.DataFrame):
            target_df = exec_res["result_var"]
            if target_df.empty:
                print("⚠️ [RAG] 筛选后数据为空，将尝试使用全量数据进行检索..")
                target_df = self.df
            elif len(target_df) < len(self.df):
                print(f"✅ [RAG] 筛选生效，将在 {len(target_df)} 条相关记录中进行检索")
        else:
            print(f"⚠️ [RAG] 筛选代码执行失败，使用全量数据。错误: {exec_res.get('error')}")

        # --- Step 2: 向量检索(Vector Search) ---
        print("📳 [RAG] 开始向量匹配..")
        query_vec = self.model.encode([query])

        # 映射机制：我们需要获得 target_df 在原始 self.df 中的位置，以索引对应的 embeddings
        subset_indices = self.df.index.get_indexer(target_df.index)
        subset_indices = subset_indices[subset_indices != -1]

        if len(subset_indices) == 0:
            return "未找到相关数据。", "无数据可视化。"

        # 提取对应的 Embeddings 子集
        target_embeddings = self.doc_embeddings[subset_indices]

        # 计算相似度
        sims = cosine_similarity(query_vec, target_embeddings)[0]

        # 获取 Top N
        top_k = min(5, len(sims))
        top_local_indices = np.argsort(sims)[-top_k:][::-1]

        results = []
        for local_idx in top_local_indices:
            score = sims[local_idx]
            if score > 0.25:  # 相似度阈值
                item = target_df.iloc[local_idx].to_dict()
                clean_item = {k: v for k, v in item.items() if pd.notna(v)}
                results.append(f"【相关度 {score:.2f}】 {clean_item}")

        if not results:
            return "在筛选后的数据中未找到相关性足够高的文档记录。", "无数据可视化。"

        return "\n\n".join(results), "建议使用：图文卡片(Infographic Card) 或 词云 (Word Cloud)。"
