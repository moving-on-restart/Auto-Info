import json
from app3.data_agent_project.core.llm_client import LLMClient

class TaskRouter:
    """根据用户问题，将任务分发给特定处理器"""

    def route(self, query):
        prompt = f"""
        你是一个数据分析任务分发员。请分析用户问题，将其归入以下 4 类之一。

        【类别定义】
        1. STATISTICS (统计与分布): 关注"多少个"、"占比"、"Top N"、"平均值"、"最大/最小"。
        2. TEMPORAL (时空演变): 关注随"时间"、"朝代"的变化趋势。
        3. CORRELATION (对比与关联): 关注两个属性之间的关系或不同群组的属性对比。
        4. KNOWLEDGE (知识与检索): 关注具体名词解释、模糊搜索、推荐、文本挖掘。
        
        

        【用户问题】: "{query}"

        请输出 JSON:
        {{
            "category": "CATEGORY_NAME",
            "reason": "简短理由"
        }}
        """
        raw = LLMClient.call_local([{"role": "user", "content": prompt}], json_mode=True)
        try:
            clean_json = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            return data.get("category", "KNOWLEDGE"), data.get("reason", "")
        except:
            return "KNOWLEDGE", "Fallback"