import pandas as pd
import numpy as np
import requests
import json
import traceback
import io
import contextlib
import re
import os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# 1. 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ==================== 配置区域 ====================
LLM_API_URL = "http://100.64.0.1:3025/v1/chat/completions"


# ==================== 基础工具层 (Infrastructure) ====================

class LLMClient:
    """统一的 LLM 调用接口"""

    @staticmethod
    def call(messages, temperature=0.1, json_mode=False):
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048  # 增加 token 以支持长代码生成
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            res = requests.post(LLM_API_URL, json=payload, timeout=60).json()
            return res['choices'][0]['message']['content']
        except Exception as e:
            print(f"❌ LLM 调用失败: {e}")
            return "{}" if json_mode else "Error"


class SchemaAnalyzer:
    """增强版 Schema 分析：提取列名、类型以及关键的唯一值"""

    def __init__(self, df):
        self.df = df

    def analyze(self):
        info = []
        for col in self.df.columns:
            dtype = self.df[col].dtype
            # 获取非空唯一值样本
            unique_vals = self.df[col].dropna().astype(str).unique()
            n_unique = len(unique_vals)
            sample = unique_vals[:5].tolist()

            col_type = "Text"
            if pd.api.types.is_numeric_dtype(dtype):
                col_type = "Numeric"
                stats = f"(Min: {self.df[col].min()}, Max: {self.df[col].max()})"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_type = "Time"
                stats = ""
            else:
                # 对于文本列，如果是少量的分类（如朝代），全部列出有助于排序
                if n_unique < 20:
                    sample = unique_vals.tolist()
                    stats = f"(Category, {n_unique} unique values)"
                else:
                    stats = f"(Text, {n_unique} unique values)"

            info.append(f"- {col} [{col_type}] {stats}: {sample}")
        return "\n".join(info)


class CodeSandbox:
    """执行 Python 代码并捕获输出"""

    def execute(self, code, df):
        # 预加载常用库
        local_vars = {"df": df, "pd": pd, "np": np, "result": None}
        output_buffer = io.StringIO()

        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(code, {}, local_vars)

            result_var = local_vars.get("result")
            console_output = output_buffer.getvalue()

            return {
                "success": True,
                "result_var": result_var,
                "console_output": console_output,
                "error": None
            }
        except Exception:
            return {
                "success": False,
                "result_var": None,
                "console_output": output_buffer.getvalue(),
                "error": traceback.format_exc()
            }


# ==================== 1. 意图路由层 (Router) ====================

class TaskRouter:
    """
    根据用户问题，将任务分发给四个特定处理器之一。
    """

    def route(self, query):
        prompt = f"""
        你是一个数据分析任务分发员。请分析用户问题，将其归入以下 4 类之一。

        【类别定义】
        1. STATISTICS (统计与分布): 关注"多少个"、"占比"、"Top N"、"平均值"、"最大/最小"。
           - 关键词: 数量, 分布, 排名, 占比, 统计, 结构.
        2. TEMPORAL (时空演变): 关注随"时间"、"朝代"的变化趋势。
           - 关键词: 趋势, 变化, 演变, 发展, 从...到..., 兴起.
        3. CORRELATION (对比与关联): 关注两个属性之间的关系或不同群组的属性对比。
           - 关键词: 关系, 相关性, 比例, 对比, 区别, 偏好, 规律.
        4. KNOWLEDGE (知识与检索): 关注具体名词解释、模糊搜索、推荐、文本挖掘。
           - 关键词: 查找, 推荐, 描述, 什么是, 介绍, 搜索.

        【用户问题】: "{query}"

        请输出 JSON:
        {{
            "category": "CATEGORY_NAME",
            "reason": "简短理由"
        }}
        """
        raw = LLMClient.call([{"role": "user", "content": prompt}], json_mode=True)
        try:
            # 清理潜在的 Markdown 标记
            clean_json = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            return data.get("category", "KNOWLEDGE"), data.get("reason", "")
        except:
            return "KNOWLEDGE", "Fallback"


# ==================== 2. 处理器抽象层 (Handlers) ====================

class BaseHandler:
    def __init__(self, df, schema_str, sandbox):
        self.df = df
        self.schema_str = schema_str
        self.sandbox = sandbox

    def generate_code(self, query, system_prompt):
        """通用代码生成逻辑 - 修复版"""
        full_prompt = f"""
        {system_prompt}

        【数据 Schema】:
        {self.schema_str}

        【用户问题】: "{query}"

        【输出要求】:
        1. 仅输出 Python 代码，不要包含任何解释文字。
        2. 代码必须包裹在 markdown 代码块中 (```python ... ```)。
        3. 使用 `df` 变量作为输入。
        4. 将最终分析结果（DataFrame或数值）赋值给变量 `result`。
        """
        raw_response = LLMClient.call([{"role": "user", "content": full_prompt}])

        # --- 修复核心：使用正则提取代码块内容，丢弃解释性文字 ---
        # 优先匹配 ```python 代码 ```
        pattern_py = r"```python\s*(.*?)\s*```"
        match = re.search(pattern_py, raw_response, re.DOTALL | re.IGNORECASE)

        if match:
            code = match.group(1)
        else:
            # 如果没有 python 标签，尝试匹配通用代码块 ``` 代码 ```
            pattern_generic = r"```\s*(.*?)\s*```"
            match_generic = re.search(pattern_generic, raw_response, re.DOTALL)
            if match_generic:
                code = match_generic.group(1)
            else:
                # 兜底：如果完全没有 markdown 标记，则假设全部是代码（风险较高，但作为最后的尝试）
                code = raw_response

        return code.strip()

    def format_result(self, exec_res):
        # ... (保持原样) ...
        """通用结果格式化"""
        if not exec_res['success']:
            return f"❌ 代码执行出错:\n{exec_res['error']}"

        res = exec_res['result_var']
        output = []
        if exec_res['console_output']:
            output.append(f"控制台输出:\n{exec_res['console_output']}")

        if isinstance(res, pd.DataFrame):
            output.append(f"数据结果 (前10行):\n{res.head(10).to_markdown()}")
        elif isinstance(res, pd.Series):
            output.append(f"数据结果:\n{res.to_markdown()}")
        else:
            output.append(f"计算结果: {res}")

        return "\n\n".join(output)


# ==================== 3. 专用处理器实现 ====================

class StatisticsHandler(BaseHandler):
    """处理：统计与分布类 (Statistics & Distribution)"""

    def handle(self, query):
        system_prompt = """
        你是一个 Pandas 统计分析专家。任务是进行数据聚合、计数和排名。
        - 常用操作: groupby, value_counts, pivot_table, sort_values.
        - 如果是请求“占比”，请计算百分比。
        - 确保处理 NaN 值。
        """
        code = self.generate_code(query, system_prompt)
        print(f"📊 [Statistics Code]:\n{code}")
        exec_res = self.sandbox.execute(code, self.df)
        return self.format_result(exec_res), "建议使用：柱状图 (Bar Chart) 或 饼图 (Pie Chart) 展示分布。"


class TemporalHandler(BaseHandler):
    """处理：时空演变类 (Temporal Evolution)"""

    def handle(self, query):
        system_prompt = """
        你是一个 Pandas 时间序列分析专家。任务是分析随时间/朝代的变化。

        【关键注意】:
        - 数据集中的时间列可能不是标准日期（例如是“明”、“清”、“唐”等字符串）。
        - ❌ 严禁直接对中文朝代字符串进行 sort_values，这只会按拼音排序。
        - ✅ 必须在代码中创建一个自定义的 mapping 字典来定义朝代顺序。
          例如: `order_map = {'唐':1, '宋':2, '元':3, '明':4, '清':5}` (根据 Schema 中的实际值调整)。
          然后使用 `pd.Categorical` 或 `map` 进行排序。
        """
        code = self.generate_code(query, system_prompt)
        print(f"⏳ [Temporal Code]:\n{code}")
        exec_res = self.sandbox.execute(code, self.df)
        return self.format_result(exec_res), "建议使用：折线图 (Line Chart) 或 堆叠面积图 (Stacked Area) 展示趋势。"


class CorrelationHandler(BaseHandler):
    """处理：对比与关联类 (Comparison & Correlation)"""

    def handle(self, query):
        system_prompt = """
        你是一个 Pandas 数据挖掘专家。任务是发现变量间的关系或对比不同组别。
        - 如果涉及数值关系，计算 corr() 或准备 scatter plot 数据。
        - 如果是对比不同组（如不同皇帝的审美），使用 groupby + mean/std。
        - 如果是寻找比例规律，请计算两列的商。
        """
        code = self.generate_code(query, system_prompt)
        print(f"🔗 [Correlation Code]:\n{code}")
        exec_res = self.sandbox.execute(code, self.df)
        return self.format_result(exec_res), "建议使用：散点图 (Scatter Plot) 或 分组柱状图 (Grouped Bar) 展示对比。"


class KnowledgeRetrievalHandler(BaseHandler):
    """处理：知识与检索类 (Knowledge & Retrieval) - 使用 RAG"""

    def __init__(self, df, schema_str, sandbox):
        super().__init__(df, schema_str, sandbox)
        self.model = None
        self.doc_embeddings = None
        self.documents = None
        self._init_rag()

    def _init_rag(self):
        print("🧠 [RAG] 初始化向量模型...")
        # 实际生产中可持久化保存，避免每次重算
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.documents = self.df.apply(
            lambda x: " | ".join(
                [f"{k}:{v}" for k, v in x.items() if pd.notna(v) and isinstance(v, (str, int, float))]),
            axis=1
        ).tolist()
        self.doc_embeddings = self.model.encode(self.documents, show_progress_bar=False)

    def handle(self, query):
        print(f"🔍 [RAG] 正在检索: {query}")
        query_vec = self.model.encode([query])
        sims = cosine_similarity(query_vec, self.doc_embeddings)[0]

        # 取 Top 5
        top_indices = np.argsort(sims)[-5:][::-1]
        results = []
        for idx in top_indices:
            if sims[idx] > 0.25:  # 相似度阈值
                item = self.df.iloc[idx].to_dict()
                # 简化显示，去掉空值
                clean_item = {k: v for k, v in item.items() if pd.notna(v)}
                results.append(f"【相关度 {sims[idx]:.2f}】: {clean_item}")

        if not results:
            return "未找到相关性高的文物记录。", "无数据可视化。"

        return "\n\n".join(results), "建议使用：图文卡片 (Infographic Card) 或 词云 (Word Cloud)。"


# ==================== 4. 总控系统 (The System) ====================

class UniversalAgent:
    def __init__(self, csv_path):
        print(f"📂 加载数据: {csv_path}")
        self.df = pd.read_csv(csv_path)
        self.analyzer = SchemaAnalyzer(self.df)
        self.schema = self.analyzer.analyze()
        self.sandbox = CodeSandbox()

        # 初始化组件
        self.router = TaskRouter()

        # 初始化各领域的 Handler
        self.handlers = {
            "STATISTICS": StatisticsHandler(self.df, self.schema, self.sandbox),
            "TEMPORAL": TemporalHandler(self.df, self.schema, self.sandbox),
            "CORRELATION": CorrelationHandler(self.df, self.schema, self.sandbox),
            "KNOWLEDGE": KnowledgeRetrievalHandler(self.df, self.schema, self.sandbox)
        }
        print("✅ 系统初始化完成。")

    def solve(self, query):
        print(f"\n💬 用户: {query}")

        # 1. 意图识别
        category, reason = self.router.route(query)
        print(f"🧭 任务分类: [{category}] ({reason})")

        # 2. 路由分发与执行
        handler = self.handlers.get(category)
        fact_data, viz_advice = handler.handle(query)

        # 3. 最终自然语言生成
        final_response = self._generate_response(query, category, fact_data, viz_advice)
        return final_response

    def _generate_response(self, query, category, fact_data, viz_advice):
        prompt = f"""
        你是一位专业的博物馆数据分析师。

        【当前任务模式】: {category}
        【用户问题】: {query}

        【数据分析结果】:
        {fact_data}

        【可视化建议】:
        {viz_advice}

        请根据分析结果回答用户问题。
        1. 必须基于提供的数据结果说话，不要编造。
        2. 如果结果中包含 DataFrame 表格，请用简洁的语言总结其中的规律（例如："从数据中可以看到，清代数量远超明代..."）。
        3. 在回答的最后，简要提及可视化建议。
        """
        return LLMClient.call([{"role": "user", "content": prompt}], temperature=0.5)


# ==================== 测试运行 ====================
if __name__ == "__main__":
    # 请替换为你的实际文件路径
    # 建议数据包含列：'文物名称', '时代', '分类', '高', '口径', '足径', '描述'
    csv_file = "E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"

    # 仅在文件存在时运行
    if os.path.exists(csv_file):
        agent = UniversalAgent(csv_file)

        # 场景 1: 统计 (Statistics)
        # response = agent.solve("故宫藏品中，明代和清代的瓷器数量分别是多少？")
        # print(f"🤖 回答:\n{response}")

        # 场景 2: 趋势 (Temporal) - 复杂逻辑：需要识别朝代顺序
        response = agent.solve("从唐代到清代，陶瓷文物的高度是如何变化的？")
        print(f"🤖 回答:\n{response}")

        # 场景 3: 关联 (Correlation) - 复杂逻辑：两列计算
        # response = agent.solve("宋代碗的口径和足径有什么特定的比例规律吗？")
        # print(f"🤖 回答:\n{response}")

        # 场景 4: 检索 (Knowledge) - 语义搜索
        # response = agent.solve("能否推荐一个以红色为主的文物？")
        # print(f"🤖 回答:\n{response}")
    else:
        print("❌ 找不到 CSV 文件，请检查路径。")