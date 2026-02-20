import os
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
import time
import os
import pandas as pd
import numpy as np
from werkzeug.utils import secure_filename
import time

def process_uploaded_file(file_obj, upload_folder):
    """
    增加返回 df 对象的逻辑，用于后续深度分析
    """
    if not file_obj or file_obj.filename == '':
        return None, "No selected file"

    try:
        filename = secure_filename(file_obj.filename)
        filepath = os.path.join(upload_folder, filename)
        file_obj.save(filepath)

        # 1. 尝试多种编码读取
        df = None
        read_errors = []
        encodings_to_try = ['utf-8', 'gbk', 'gb18030', 'latin1']

        for encoding in encodings_to_try:
            try:
                df = pd.read_csv(filepath, encoding=encoding)
                break
            except Exception as e:
                read_errors.append(f"{encoding}: {str(e)}")

        if df is None:
            return None, f"无法读取文件，编码尝试失败: {read_errors}"

        # 2. 清洗数据
        df_clean = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        columns = list(df_clean.columns)
        row_count = len(df_clean)
        preview = df_clean.head(5).to_dict(orient='records')

        result_data = {
            'filepath': filepath,
            'filename': filename,
            'meta': {
                'columns': columns,
                'rows': row_count,
                'preview': preview
            },
            # [新增] 临时将 DF 对象传出去，Control层用完记得删除，否则 jsonify 会报错
            '_df': df
        }
        return result_data, None

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, str(e)
# ... save_uploaded_image 保持不变

def save_uploaded_image(file, upload_dir):
    filename = f"{int(time.time())}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    return filepath