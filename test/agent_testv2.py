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
from openai import OpenAI
from dotenv import load_dotenv

# 1. 设置环境变量
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ==================== 配置区域 ====================
LOCAL_API_URL = "http://100.64.0.1:3025/v1/chat/completions"
LOCAL_API_KEY = "none"
LOCAL_MODEL_NAME = "default"
load_dotenv()

# 请确保 Key 是正确的，并且账户有余额
AIHUBMIX_KEY = os.getenv("AIHUBMIX_API_KEY")  # 替换为你的真实 Key
AIHUBMIX_BASE_URL = "https://aihubmix.com/v1"


# ==================== 基础工具层 ====================

class LocalLLMClient:
    """本地模型客户端 (保持不变)"""

    def __init__(self, api_url, api_key, model_name):
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name

    def call(self, messages, temperature=0.1, json_mode=False):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            res = requests.post(self.api_url, headers=headers, json=payload, timeout=30).json()
            return res['choices'][0]['message']['content']
        except Exception as e:
            print(f"❌ Local LLM Error: {e}")
            return "{}" if json_mode else "Error"


class AIHubMixClient:
    """
    [修复版] 专家模型客户端
    使用标准的 chat.completions 接口，兼容性最强
    """

    def __init__(self, api_key, base_url):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model_name = "gpt-5.1-codex-max"  # 或者是服务商提供的映射名，如 "gpt-4-turbo"

    def call(self, messages):
        # 1. 深度思维注入：通过 Prompt 模拟 reasoning 参数
        # 我们在 system prompt 后面追加一段强制指令
        system_instruction = messages[0]['content']
        enhanced_instruction = f"""
        {system_instruction}

        【Thinking Process Requirements】:
        1. Think strictly step-by-step before writing code.
        2. Verify library dependencies (e.g. use standard libraries first).
        3. Ensure Chinese characters are handled correctly in charts/sorting.
        4. Output ONLY the Python code block wrapped in Markdown.
        """
        messages[0]['content'] = enhanced_instruction

        try:
            # 2. 使用标准接口调用 (最稳妥的方式)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,  # 代码生成需要低温度
                max_tokens=4096,  # 给足 Token
                stream=True
            )

            # 3. 流式接收与拼接
            content_pieces = []
            print("⚡ [Expert AI] Coding...", end="", flush=True)

            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    content_pieces.append(content)
                    # 可选：打印进度点
                    # print(".", end="", flush=True)

            print(" Done.")
            return "".join(content_pieces)

        except Exception as e:
            print(f"\n❌ AIHUBMIX API Error: {e}")
            # 如果是 401，通常是 Key 错误或余额不足，也可能是模型名称不对
            if "401" in str(e):
                print("💡 提示: 请检查 API Key 是否正确，或该模型是否有权限访问。")
            return "# Error generating code"


class SchemaAnalyzer:
    """Schema 分析器 (保持不变)"""

    def __init__(self, df):
        self.df = df

    def analyze(self):
        info = []
        for col in self.df.columns:
            dtype = self.df[col].dtype
            unique_vals = self.df[col].dropna().astype(str).unique()
            n_unique = len(unique_vals)
            col_type = "Numeric" if pd.api.types.is_numeric_dtype(dtype) else "Text"
            sample = unique_vals[:5].tolist()
            info.append(f"- {col} [{col_type}] (Unique: {n_unique}): {sample}")
        return "\n".join(info)


class CodeSandbox:
    """代码沙箱 (保持不变)"""

    def execute(self, code, df):
        local_vars = {"df": df, "pd": pd, "np": np, "result": None}
        output_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(code, {}, local_vars)
            return {
                "success": True,
                "result_var": local_vars.get("result"),
                "console": output_buffer.getvalue(),
                "error": None
            }
        except Exception:
            return {
                "success": False,
                "result_var": None,
                "console": output_buffer.getvalue(),
                "error": traceback.format_exc()
            }


# ==================== 2. 处理器层 ====================

class BaseHandler:
    def __init__(self, df, schema_str, sandbox, code_llm):
        self.df = df
        self.schema_str = schema_str
        self.sandbox = sandbox
        self.code_llm = code_llm

    def generate_code(self, query, system_prompt):
        # 这里的 messages 结构是标准的 Chat 格式
        full_msg = [
            {"role": "system", "content": system_prompt},
            {"role": "user",
             "content": f"Schema:\n{self.schema_str}\n\nTask: {query}\n\nConstraint: Write Python code. Assign final dataframe or value to variable 'result'. Use to_string() for output."}
        ]
        code_raw = self.code_llm.call(full_msg)

        # 清洗 Markdown 标记
        code = re.sub(r"^```python", "", code_raw, flags=re.MULTILINE)
        code = re.sub(r"^```", "", code, flags=re.MULTILINE)
        return code.strip()

    def format_result(self, exec_res):
        if not exec_res['success']:
            return f"⚠️ Code Execution Error:\n{exec_res['error']}"

        output_parts = []
        res = exec_res['result_var']
        if isinstance(res, pd.DataFrame):
            # 使用 to_string 避免依赖
            output_parts.append(f"【Data Table】:\n{res.to_string()}")
        elif isinstance(res, pd.Series):
            output_parts.append(f"【Data Series】:\n{res.to_string()}")
        elif res is not None:
            output_parts.append(f"【Result】: {res}")

        if exec_res['console']:
            output_parts.append(f"【Console】:\n{exec_res['console']}")

        return "\n\n".join(output_parts) if output_parts else "No Output"


class AnalysisHandler(BaseHandler):
    def handle(self, query, category):
        prompts = {
            "STATISTICS": "Analyze data distribution. Use value_counts, groupby.",
            "TEMPORAL": "Analyze trends over time. IMPORTANT: Map Chinese dynasties (唐,宋,元,明,清) to numbers for sorting.",
            "CORRELATION": "Analyze relationships between variables."
        }
        sys_prompt = prompts.get(category, "Analyze the data.")

        code = self.generate_code(query, sys_prompt)
        print(f"💻 [Generated Code]:\n{code}")

        exec_res = self.sandbox.execute(code, self.df)
        fact_data = self.format_result(exec_res)
        return fact_data, "Chart suggestion based on data."


class KnowledgeRetrievalHandler(BaseHandler):
    """RAG 不需要远程模型，保持本地"""

    def __init__(self, df, schema_str, sandbox, code_llm=None):
        super().__init__(df, schema_str, sandbox, code_llm)
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.docs = df.apply(lambda x: " ".join([f"{k}:{v}" for k, v in x.items() if pd.notna(v)]), axis=1).tolist()
        self.embs = self.model.encode(self.docs, show_progress_bar=False)

    def handle(self, query):
        print(f"🔍 [RAG] Searching: {query}")
        q_vec = self.model.encode([query])
        sims = cosine_similarity(q_vec, self.embs)[0]
        top_idx = np.argsort(sims)[-3:][::-1]
        res = [f"Item: {self.df.iloc[i].to_dict()}" for i in top_idx if sims[i] > 0.25]
        return "\n".join(res) if res else "No match found.", "Card View"


# ==================== 3. 总控系统 ====================

class TaskRouter:
    def __init__(self, llm_client):
        self.llm = llm_client

    def route(self, query):
        prompt = f"""
        Classify query into: STATISTICS, TEMPORAL, CORRELATION, KNOWLEDGE.
        Query: "{query}"
        JSON Output: {{"category": "...", "reason": "..."}}
        """
        try:
            raw = self.llm.call([{"role": "user", "content": prompt}], json_mode=True)
            data = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group())
            return data.get("category", "KNOWLEDGE"), data.get("reason", "")
        except:
            return "KNOWLEDGE", "Fallback"


class UniversalAgent:
    def __init__(self, csv_path):
        print(f"📂 Loading: {csv_path}")
        self.df = pd.read_csv(csv_path)
        self.schema = SchemaAnalyzer(self.df).analyze()
        self.sandbox = CodeSandbox()

        print("🔌 Initializing LLMs...")
        self.local_llm = LocalLLMClient(LOCAL_API_URL, LOCAL_API_KEY, LOCAL_MODEL_NAME)
        # 实例化修复后的 Client
        self.expert_llm = AIHubMixClient(AIHUBMIX_KEY, AIHUBMIX_BASE_URL)

        self.router = TaskRouter(self.local_llm)
        self.handlers = {
            "STATISTICS": AnalysisHandler(self.df, self.schema, self.sandbox, self.expert_llm),
            "TEMPORAL": AnalysisHandler(self.df, self.schema, self.sandbox, self.expert_llm),
            "CORRELATION": AnalysisHandler(self.df, self.schema, self.sandbox, self.expert_llm),
            "KNOWLEDGE": KnowledgeRetrievalHandler(self.df, self.schema, self.sandbox)
        }
        print("✅ Ready.")

    def solve(self, query):
        print(f"\n💬 User: {query}")
        try:
            cat, reason = self.router.route(query)
            print(f"🧭 Route: {cat}")
        except:
            cat = "KNOWLEDGE"

        try:
            handler = self.handlers.get(cat, self.handlers["STATISTICS"])
            if cat == "KNOWLEDGE":
                data, viz = handler.handle(query)
            else:
                data, viz = handler.handle(query, cat)
        except Exception as e:
            traceback.print_exc()
            data = f"Error: {str(e)}"
            viz = "None"

        return self._summarize(query, data, viz)

    def _summarize(self, query, data, viz):
        prompt = f"Question: {query}\nData: {data}\nAnswer nicely."
        return self.local_llm.call([{"role": "user", "content": prompt}])


if __name__ == "__main__":
    csv_file = "E:\研究生\myproject\spider\csv_full\palace_museum_taoci_optimized.csv"
    if os.path.exists(csv_file):
        agent = UniversalAgent(csv_file)
        print(agent.solve("从唐代到清代，陶瓷文物的高度是如何变化的？"))
    else:
        print("❌ CSV Not Found")