import requests
import cv2
import numpy as np
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DinoService:
    def __init__(self, api_url="http://100.64.0.1:3045/predict"):
        self.api_url = api_url

    def detect_objects(self, image_path, prompt, box_threshold=0.35, text_threshold=0.25):
        """
        调用 GroundingDINO 接口进行目标检测

        Args:
            image_path (str): 图片的本地路径
            prompt (str): 检测提示词
            box_threshold (float): 框置信度阈值
            text_threshold (float): 文本置信度阈值

        Returns:
            dict: 接口返回的完整 JSON 数据，如果失败则返回 None
        """
        if not os.path.exists(image_path):
            logging.error(f"文件不存在: {image_path}")
            return None

        try:
            # 使用 with open 自动管理文件关闭
            with open(image_path, 'rb') as f:
                files = {'image': f}
                data = {
                    'prompt': prompt,
                    'box_threshold': box_threshold,
                    'text_threshold': text_threshold
                }

                logging.info(f"发送请求到 {self.api_url} | Prompt: {prompt}")
                response = requests.post(self.api_url, files=files, data=data)

            if response.status_code == 200:
                result = response.json()
                logging.info(f"✅ 请求成功，检测到 {result.get('count', 0)} 个物体")
                return result
            else:
                logging.error(f"❌ 请求失败 (Code {response.status_code}): {response.text}")
                return None

        except Exception as e:
            logging.error(f"❌ 运行错误: {e}")
            return None

    @staticmethod
    def visualize_and_save(image_path, detection_results, output_path="result_vis.jpg"):
        """
        可视化检测结果并保存图片（支持中文路径）

        Args:
            image_path (str): 原图路径
            detection_results (dict): detect_objects 返回的结果
            output_path (str): 结果保存路径
        """
        if not detection_results or 'results' not in detection_results:
            logging.warning("没有检测结果可供可视化")
            return

        try:
            # 1. 读取图片 (支持中文路径的黑科技)
            img_array = np.fromfile(image_path, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                logging.error("无法解码图片，请检查文件是否损坏")
                return

            # 2. 绘制框和标签
            for item in detection_results['results']:
                label = item['label']
                score = item['score']
                box = item['box_pixel']  # [x1, y1, x2, y2]

                # 确保坐标是整数
                x1, y1, x2, y2 = map(int, box)

                # 画矩形框
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # 画标签背景和文字
                text = f"{label} {score:.2f}"
                cv2.putText(img, text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # 3. 保存图片 (支持中文路径的保存方式)
            # 使用 cv2.imencode 将图片编码为内存流，然后用 tofile 写入文件
            is_success, buffer = cv2.imencode(".jpg", img)
            if is_success:
                buffer.tofile(output_path)
                logging.info(f"可视化结果已保存: {output_path}")
            else:
                logging.error("图片编码失败，无法保存")

        except Exception as e:
            logging.error(f"可视化过程出错: {e}")


# ================= 使用示例 =================
if __name__ == "__main__":
    # 1. 配置参数
    IMAGE_FILE = r"E:\研究生\myproject\image api\boat_2-3.png"
    PROMPT_TEXT = "boat"

    # 2. 初始化服务
    dino_service = DinoService(api_url="http://100.64.0.1:3045/predict")

    # 3. 获取数据 (这步返回纯数据，非常适合传给 SAM)
    results = dino_service.detect_objects(IMAGE_FILE, PROMPT_TEXT)

    # 4. 如果需要看图，再调用可视化 (这一步是可选的)
    if results:
        # 打印一下数据看看
        print("检测到的框数据:", [res['box_pixel'] for res in results['results']])

        # 保存可视化图片
        dino_service.visualize_and_save(IMAGE_FILE, results, "result_test_output.jpg")