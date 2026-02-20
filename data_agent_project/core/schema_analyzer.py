import pandas as pd

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
                if n_unique < 100:
                    sample = unique_vals.tolist()
                    stats = f"(Category, {n_unique} unique values)"
                else:
                    stats = f"(Text, {n_unique} unique values)"

            info.append(f"- {col} [{col_type}] {stats}: {sample}")
        return "\n".join(info)