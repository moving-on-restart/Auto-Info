import os
from app3.controller.service_manager import get_infographic_agent
from app3.data_agent_project.analyze_data_with_chart import analyze_data_with_chart


def analyze_logic(filepath, description, query):
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError("CSV File not found")

    answer, chart_json = analyze_data_with_chart(filepath, description, query)
    return answer, chart_json


def generate_infographic_logic(description, query, analysis_result, chart_source):
    image_path = get_infographic_agent().generate(
        description=description,
        query=query,
        analysis_result=analysis_result,
        chart_json=chart_source
    )
    if image_path:
        # 返回相对路径
        filename = os.path.basename(image_path)
        return f"static/generated_images/{filename}"
    return None
