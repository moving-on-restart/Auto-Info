import io
import contextlib
import traceback
import pandas as pd
import numpy as np
import json
import sys
class CodeSandbox:
    """执行 Python 代码并捕获输出"""

    def __init__(self):
        pass

    def execute(self, code, df):
        """
        执行 LLM 生成的 Python 代码，并返回执行结果。
        """
        # 1. 捕获标准输出 (Print Capture)
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output

        # 2. 预注入上下文 (Pre-injected Context)
        # 这里直接把 pd, np, df 塞进去，这样即使 LLM 忘记写 import 也能跑
        execution_context = {
            "pd": pd,
            "numpy": np,
            "np": np,
            "df": df,
            "result": None  # 占位符
        }

        success = False
        error_msg = None
        result_var = None

        try:
            # =========================================================
            # 【核心修复】使用同一个字典作为 globals 和 locals
            # 这样 import 的库和定义的函数都在同一个命名空间，互通无阻
            # =========================================================
            exec(code, execution_context)

            success = True
            result_var = execution_context.get('result')  # 获取代码中赋值的 result 变量

        except Exception as e:
            # 捕获详细堆栈信息，或者仅捕获错误消息
            import traceback
            error_msg = traceback.format_exc()
        finally:
            # 恢复标准输出
            sys.stdout = old_stdout

        console_output = redirected_output.getvalue()

        return {
            "success": success,
            "result_var": result_var,
            "console_output": console_output,
            "error": error_msg
        }

class VegaSandbox:
    """Vega-Lite 代码校验沙箱"""

    def validate(self, json_code):
        """校验 JSON 格式及 Vega-Lite 基本结构"""
        try:
            # 1. 尝试解析 JSON
            spec = json.loads(json_code)

            # 2. 基本字段检查
            if not isinstance(spec, dict):
                return {"success": False, "error": "Output is not a JSON object"}

            # 检查是否有 data 和 mark/layer/encoding 核心字段
            # 注意：Vega-Lite 规范比较灵活，这里做基础检查
            has_data = "data" in spec
            has_mark = "mark" in spec or "layer" in spec or "concat" in spec or "hconcat" in spec or "vconcat" in spec

            if not has_data:
                return {"success": False, "error": "Missing 'data' field in Vega-Lite spec"}

            if not has_mark:
                return {"success": False, "error": "Missing visual encoding (mark/layer/concat) in Vega-Lite spec"}

            return {"success": True, "spec": spec}

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON format: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unknown validation error: {str(e)}"}