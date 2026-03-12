import pandas as pd
import numpy as np


class SchemaAnalyzer:
    """
    基于微批次信息熵调节的自适应 Cochran 增强版 Schema 分析器
    """

    def __init__(self, df, confidence_level=1.96, base_error_margin=0.05, lambda_penalty=0.5):
        self.df = df
        self.total_rows = len(df)
        self.Z = confidence_level         # 95% 置信度下为 1.96
        self.e0 = base_error_margin       # 基础误差容忍度 (5%)
        self.lambda_penalty = lambda_penalty  # 复杂度惩罚系数 λ

    def _calculate_normalized_entropy(self, series):
        """计算归一化信息熵"""
        counts = series.value_counts(normalize=True)
        if len(counts) <= 1:
            return 0.0
        # 计算香农熵
        entropy = -sum(counts * np.log2(counts))
        # 归一化 (除以样本总数 n 的 log2，防止极值)
        n = len(series)
        normalized_entropy = entropy / np.log2(n) if n > 1 else 0.0
        return normalized_entropy

    def _get_adaptive_sample_for_column(self, col_name):
        """针对特定列，基于微批次信息熵调节计算动态样本量并抽样"""
        series = self.df[col_name].dropna()
        valid_rows = len(series)

        if valid_rows == 0:
            return series

        # 1. 抽取微批次 (Micro-batch) 作为探针，上限100条
        micro_batch_size = min(100, valid_rows)
        micro_batch = series.sample(n=micro_batch_size, random_state=42)

        # 2. 计算局部归一化信息熵 (先验复杂度)
        h_norm_hat = self._calculate_normalized_entropy(micro_batch)

        # 3. 动态误差界限惩罚机制: e' = e0 * (1 - λ * H_norm_hat)
        e_prime = self.e0 * (1 - self.lambda_penalty * h_norm_hat)
        # 设定一个极小值保底，防止 e_prime 过小导致除零或样本量爆炸
        e_prime = max(e_prime, 0.01)

        # 4. 计算改进后的目标样本量 n0*
        p = 0.5
        n0_star = (self.Z ** 2 * p * (1 - p)) / (e_prime ** 2)

        # 5. 有限总体校正计算实际样本量 n
        n = int(n0_star / (1 + (n0_star - 1) / valid_rows))

        # 6. 如果有效数据量大于计算出的动态样本量，则执行随机抽样
        if valid_rows > n:
            return series.sample(n=n, random_state=42)
        return series

    def analyze(self):
        info = []
        for col in self.df.columns:
            dtype = self.df[col].dtype

            # 【核心改进】: 针对当前列进行动态自适应抽样
            sampled_series = self._get_adaptive_sample_for_column(col)

            if sampled_series.empty:
                info.append(f"- {col} [Unknown] (All missing values)")
                continue

            col_type = "Text"
            stats = ""
            sample = []

            # === 数值型处理 ===
            if pd.api.types.is_numeric_dtype(dtype):
                col_type = "Numeric"
                # 数值型的最值依然使用全量数据（Pandas底层C级别运算，开销极低）
                min_val, max_val = self.df[col].min(), self.df[col].max()
                stats = f"(Min: {min_val:.2f}, Max: {max_val:.2f})"
                sample = sampled_series.head(3).tolist()

            # === 时间型处理 ===
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_type = "Time"
                min_time, max_time = self.df[col].min(), self.df[col].max()
                stats = f"(Start: {min_time.date() if pd.notnull(min_time) else 'N/A'}, End: {max_time.date() if pd.notnull(max_time) else 'N/A'})"
                sample = [str(x) for x in sampled_series.head(3).tolist()]

            # === 文本/分类型处理 ===
            else:
                # 在动态算出的精细样本上进行操作，大幅降低内存开销
                unique_vals = sampled_series.unique()
                n_unique_sample = len(unique_vals)

                # 计算最终样本的信息熵判定是否为类别 (Category)
                norm_entropy = self._calculate_normalized_entropy(sampled_series)

                # 如果熵小于 0.6 或 样本中唯一值数量极少，则判定为 Category
                if norm_entropy < 0.6 or n_unique_sample < 10:
                    col_type = "Category"
                    # 估算全表唯一值数量 (用 Pandas 高效的 nunique)
                    total_unique = self.df[col].nunique()
                    stats = f"(Entropy: {norm_entropy:.2f}, {total_unique} unique classes)"
                    sample = [str(x) for x in unique_vals[:8]]
                else:
                    col_type = "Free Text"
                    stats = f"(High diversity, Entropy: {norm_entropy:.2f})"
                    sample = [str(x) for x in unique_vals[:3]]

            info.append(f"- {col} [{col_type}] {stats}: {sample}")

        return "\n".join(info)