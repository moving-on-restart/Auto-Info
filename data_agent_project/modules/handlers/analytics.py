from app3.data_agent_project.modules.handlers.base import BaseHandler

class StatisticsHandler(BaseHandler):
    """处理：统计与分布类"""
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
    """处理：时空演变类"""
    def handle(self, query):
        system_prompt = """
        你是一个 Pandas 时间序列分析专家。任务是分析随时间/朝代的变化。
        【关键注意】:
        - ❌ 严禁直接对中文朝代字符串进行 sort_values。
        - ✅ 必须在代码中创建一个自定义的 mapping 字典来定义朝代顺序。
          例如: `order_map = {'唐':1, '宋':2, '元':3, '明':4, '清':5}`。
          注意：需要注意朝代的完整顺序，并根据数据集中的朝代进行调整，不局限于上述示例。
               有部分时代可能存在包含关系，比如用户问清代，时代中若存在清道光等，也需要包含在内。
        """
        code = self.generate_code(query, system_prompt)
        print(f"⏳ [Temporal Code]:\n{code}")
        exec_res = self.sandbox.execute(code, self.df)
        return self.format_result(exec_res), "建议使用：折线图 (Line Chart) 或 堆叠面积图 (Stacked Area) 展示趋势。"

class CorrelationHandler(BaseHandler):
    """处理：对比与关联类"""
    def handle(self, query):
        system_prompt = """
        你是一个 Pandas 数据挖掘专家。任务是发现变量间的关系或对比不同组别。
        - 如果涉及数值关系，计算 corr() 或准备 scatter plot 数据。
        - 如果是对比不同组（如不同皇帝的审美），使用 groupby + mean/std。
        """
        code = self.generate_code(query, system_prompt)
        print(f"🔗 [Correlation Code]:\n{code}")
        exec_res = self.sandbox.execute(code, self.df)
        return self.format_result(exec_res), "建议使用：散点图 (Scatter Plot) 或 分组柱状图 (Grouped Bar) 展示对比。"