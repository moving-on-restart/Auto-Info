from app3.util.file_utils import process_uploaded_file
from app3.services import description_service
from app3.data_agent_project.core.schema_analyzer import SchemaAnalyzer  # 导入新工具


def handle_csv_upload(file, upload_folder):
    # 1. 处理文件
    result_data, error_msg = process_uploaded_file(file, upload_folder)

    if error_msg:
        return None, error_msg

    # 2. 提取 DF 并进行 Schema 分析
    df = result_data.pop('_df', None)  # 取出并从 result_data 中移除，防止 JSON 序列化错误

    schema_analysis_text = ""
    if df is not None:
        try:
            analyzer = SchemaAnalyzer(df)
            schema_analysis_text = analyzer.analyze()
            print(schema_analysis_text)
        except Exception as e:
            print(f"Schema analysis failed: {e}")

    # 3. 调用 Service 生成描述 (传入 schema_analysis_text)
    auto_desc = description_service.generate_description(result_data['meta'], schema_analysis_text)

    result_data['description'] = auto_desc

    return result_data, None