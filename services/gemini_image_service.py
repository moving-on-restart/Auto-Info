# -*- coding: utf-8 -*-
import os
import base64
import time
import logging
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

from app3.config import AppConfig

# LangChain 核心组件
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class GeminiLangChainService:
    def __init__(self, output_dir="generated_images", model_name="gemini-3-pro-image-preview"):
        """
        初始化服务
        :param output_dir: 图片保存目录
        :param model_name: 模型名称，默认使用 gemini-3-pro-image-preview，
                           也可传入 'gpt-image-1.5' 切换回旧逻辑
        """
        load_dotenv()
        config = AppConfig.from_env()
        self.api_key = config.aihubmix_api_key
        self.base_url = config.aihubmix_base_url
        self.output_dir = output_dir
        self.model_name = model_name or config.image_model_name

        if not self.api_key:
            logging.warning("⚠️ 未检测到 AIHUBMIX_API_KEY")

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # 创建 Runnable
        self.chain = RunnableLambda(self._core_generator_logic)

    def _map_aspect_ratio_to_size(self, aspect_ratio):
        """仅供旧版 gpt-image-1.5 模型使用：将比例映射为分辨率"""
        if not aspect_ratio:
            return "auto"
        ratio = aspect_ratio.replace(":", "-")
        if "3-4" in ratio or "9-16" in ratio:
            return "1024x1536"
        elif "4-3" in ratio or "16-9" in ratio:
            return "1536x1024"
        elif "1-1" in ratio:
            return "1024x1024"
        else:
            return "auto"

    def _save_image_from_bytes(self, image_data, aspect_ratio):
        """通用工具方法：保存二进制图片数据到文件"""
        try:
            image = Image.open(BytesIO(image_data))
            timestamp = int(time.time())
            # 文件名带上模型前缀以区分
            model_prefix = self.model_name.replace("-", "_")
            filename = f"{model_prefix}_{timestamp}_{aspect_ratio.replace(':', '-')}.png"
            full_path = os.path.join(self.output_dir, filename)
            image.save(full_path)
            logging.info(f"✅ 图片已保存: {full_path}")
            return full_path
        except Exception as e:
            logging.error(f"❌ 保存图片失败: {e}")
            return None

    def _generate_with_gemini_preview(self, client, prompt, aspect_ratio):
        """
        策略 A: 使用 Gemini-3-Pro-Image-Preview (基于 Chat Completion)
        参考: imagetest.py
        """
        logging.info(f"🎨 生图请求 (Gemini Chat) | Model: {self.model_name} | Ratio: {aspect_ratio}")

        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": f"aspect_ratio={aspect_ratio}"},
                    {"role": "user", "content": [{"type": "text", "text": prompt}]},
                ],
                modalities=["text", "image"]
            )

            image_saved_path = None
            text_content = ""

            # 解析特殊的 multi_mod_content 结构
            try:
                # 注意：OpenAI SDK 标准对象可能不包含 multi_mod_content，
                # 但 Python 动态属性允许访问如果 API 返回了该字段。
                # 如果报错，可能需要检查 response.model_extra 或类似属性，
                # 这里严格按照 imagetest.py 的写法。
                parts = response.choices[0].message.multi_mod_content

                if parts:
                    for part in parts:
                        if "text" in part:
                            text_content += part["text"]
                        if "inline_data" in part:
                            # 提取 Base64
                            b64_data = part["inline_data"]["data"]
                            image_data = base64.b64decode(b64_data)
                            image_saved_path = self._save_image_from_bytes(image_data, aspect_ratio)
                else:
                    logging.warning("⚠️ 响应中未包含 multi_mod_content")
                    text_content = "No multimodal content returned."

            except AttributeError:
                # 兼容性处理：如果 SDK 版本不同，结构可能不同，尝试标准 content
                logging.warning("⚠️ 无法读取 multi_mod_content，尝试读取标准 content")
                text_content = response.choices[0].message.content

            if not text_content:
                text_content = f"Image generated with {self.model_name}"

            return image_saved_path, text_content

        except Exception as e:
            raise e

    def _generate_with_legacy_gpt(self, client, prompt, aspect_ratio):
        """
        策略 B: 使用 gpt-image-1.5 (基于 Image Generate API)
        旧版逻辑
        """
        size_param = self._map_aspect_ratio_to_size(aspect_ratio)
        logging.info(f"🎨 生图请求 (Legacy GPT) | Model: {self.model_name} | Size: {size_param}")

        response = client.images.generate(
            model=self.model_name,
            prompt=prompt,
            n=1,
            size=size_param,
            quality="auto"
        )

        image_saved_path = None
        if response.data and len(response.data) > 0:
            image_obj = response.data[0]
            b64_json = getattr(image_obj, 'b64_json', None)
            image_url = getattr(image_obj, 'url', None)

            image_data = None
            if b64_json:
                image_data = base64.b64decode(b64_json)
            elif image_url:
                logging.info(f"🔗 下载 URL: {image_url}")
                img_resp = requests.get(image_url)
                if img_resp.status_code == 200:
                    image_data = img_resp.content

            if image_data:
                image_saved_path = self._save_image_from_bytes(image_data, aspect_ratio)

        return image_saved_path, f"Image generated with {self.model_name} (Size: {size_param})"

    def _core_generator_logic(self, input_data):
        """
        核心生成逻辑：根据 model_name 分发请求
        """
        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        # 1. 解析输入
        if isinstance(input_data, str):
            prompt = input_data
            aspect_ratio = "1:1"
        elif isinstance(input_data, dict):
            prompt = input_data.get("prompt")
            aspect_ratio = input_data.get("aspect_ratio", "1:1")
        else:
            prompt = input_data.content if hasattr(input_data, "content") else str(input_data)
            aspect_ratio = "1:1"

        try:
            # 2. 路由分发
            if "gemini" in self.model_name.lower() or "preview" in self.model_name.lower():
                # 使用新版 Chat 接口
                image_path, text_output = self._generate_with_gemini_preview(client, prompt, aspect_ratio)
            else:
                # 默认回退到 Image 接口 (适用于 gpt-image-1.5)
                image_path, text_output = self._generate_with_legacy_gpt(client, prompt, aspect_ratio)

            # 3. 返回 LangChain 格式
            return AIMessage(
                content=text_output,
                additional_kwargs={"image_path": image_path}
            )

        except Exception as e:
            import traceback
            logging.error(f"❌ 生图服务严重错误: {e}")
            logging.error(traceback.format_exc())
            return AIMessage(content=f"Error: {str(e)}")

    def get_chain(self):
        return self.chain

    def generate(self, prompt, aspect_ratio="1:1"):
        """
        外部调用的便捷方法
        """
        result_message = self.chain.invoke({
            "prompt": prompt,
            "aspect_ratio": aspect_ratio
        })
        path = result_message.additional_kwargs.get("image_path")
        return path

    def set_model(self, model_name):
        """
        运行时切换模型
        """
        logging.info(f"🔄 切换生图模型: {self.model_name} -> {model_name}")
        self.model_name = model_name


if __name__ == "__main__":
    # 默认初始化为 gemini-3-pro-image-preview
    service = GeminiLangChainService(output_dir="my_images")

    print(f"--- 测试调用 ({service.model_name}) ---")
    test_prompt = "阶段一：统计特征提取与语义分析】输入流：图表数值序列、查询文本。核心模块：统计特征提取（分布、趋势 r_trend、波动 v_score、极端值、稀疏度、衰减评分）；语义特征提取（规则匹配与 LLM 双通道）；语义锚点构建（主题、关系、实体、焦点）。输出流向：多维信息特征。【阶段二：情感向量映射与色彩属性合成】输入流：多维信息特征。核心模块：三维情感向量映射 E=(v, a, t)（效价、唤醒度、色温）；五维色彩属性合成 C_attr（色相范围、饱和度、明度、对比度、色温倾向）。输出流向：视觉场景引导参数。【阶段三：参考图像生成与目标区域分割】输入流：视觉场景引导参数。核心模块：场景提示词构造；文本到图像生成；目标像素提取（GroundingDINO+SAM 区域模式或全图模式）。输出流向：目标像素集合。【阶段四：基于 Moon-Spencer 理论的和谐调色板优化】输入流：目标像素集合。核心模块：感知色彩空间聚类（CIELAB + K-Means）；组合寻优搜索；Moon-Spencer 和谐度量（M=O/C）。输出：最优色彩组合。//上述为图参考结构,但不要选择所有文字加入。能否参考示例图片生成合适论文附图，注意图片简洁，我将图片用在学术论文中,使用中文"

    # 1. 测试新模型 (Gemini 3 Pro)
    img_path = service.generate(test_prompt, aspect_ratio="16:9")
    print(f"Gemini 结果路径: {img_path}")

    # 2. (可选) 动态切换回旧模型测试
    # print("\n--- 切换回 gpt-image-1.5 测试 ---")
    # service.set_model("gpt-image-1.5")
    # img_path_old = service.generate(test_prompt, aspect_ratio="16:9")
    # print(f"GPT 结果路径: {img_path_old}")