import re
import pandas as pd
from app3.data_agent_project.core.llm_client import LLMClient

class BaseHandler:
    def __init__(self, df, schema_str, sandbox,table_description):
        self.df = df
        self.schema_str = schema_str
        self.sandbox = sandbox
        self.table_description = table_description

    def generate_code(self, query, system_prompt):
        print("schema_str:", self.schema_str)

        """通用代码生成逻辑"""
        full_prompt = f"""
        {system_prompt}

        【数据 Schema】:
        {self.schema_str}
        【数据介绍】:
        {self.table_description}

        【用户问题】: "{query}"

        【输出要求】:
        1. 仅输出 Python 代码，不要包含任何解释文字。
        2. 代码必须包裹在 markdown 代码块中 (```python ... ```)。
        3. 使用 `df` 变量作为输入。
        4. 将最终分析结果（DataFrame或数值）赋值给变量 `result`。
        """
        raw_response = LLMClient.call_api([{"role": "user", "content": full_prompt}])

        pattern_py = r"```python\s*(.*?)\s*```"
        match = re.search(pattern_py, raw_response, re.DOTALL | re.IGNORECASE)

        if match:
            code = match.group(1)
        else:
            pattern_generic = r"```\s*(.*?)\s*```"
            match_generic = re.search(pattern_generic, raw_response, re.DOTALL)
            code = match_generic.group(1) if match_generic else raw_response

        code = code.strip()

        # 【新增优化】：健壮性增强
        # 无论 LLM 是否写了 import，我们在代码头部强制拼接常用库
        # 这样可以防止 "NameError: name 'pd' is not defined"
        robust_imports = [
            "import pandas as pd",
            "import numpy as np",
            "import re"
        ]

        # 简单的去重判断，防止重复 import (可选)
        final_code_lines = []
        for imp in robust_imports:
            if imp not in code:
                final_code_lines.append(imp)

        final_code_lines.append(code)

        return "\n".join(final_code_lines)

    def format_result(self, exec_res):
        print("exec_res:", exec_res)
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