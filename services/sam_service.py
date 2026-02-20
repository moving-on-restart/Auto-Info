import numpy as np
import torch
import cv2
import os
import pandas as pd
import matplotlib.pyplot as plt
import logging
from segment_anything import sam_model_registry, SamPredictor

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class SamService:
    def __init__(self, checkpoint_path, model_type="vit_b", device=None):
        """
        初始化 SAM 服务，加载模型权重
        """
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_type = model_type

        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"SAM 权重文件未找到: {checkpoint_path}")

        logging.info(f"正在加载 SAM 模型 ({self.device})，请稍候...")
        try:
            sam = sam_model_registry[self.model_type](checkpoint=checkpoint_path)
            sam.to(device=self.device)
            self.predictor = SamPredictor(sam)
            logging.info("✅ SAM 模型加载完成！")
        except Exception as e:
            logging.error(f"模型加载失败: {e}")
            raise e

    def segment_with_boxes(self, image_path, boxes):
        """
        核心功能：根据 Box 进行分割

        Args:
            image_path (str): 图片路径
            boxes (list): 格式 [[x1, y1, x2, y2], ...]

        Returns:
            list: 包含分割结果的字典列表 (segmentation, iou, area, box)
        """
        if not boxes:
            logging.warning("未提供 Box，跳过分割")
            return []

        # 1. 读取图片 (支持中文路径)
        try:
            img_array = np.fromfile(image_path, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("解码失败")
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        except Exception as e:
            logging.error(f"读取图片失败: {e}")
            return []

        # 2. 设置图像 (计算 Embedding)
        # logging.info("正在计算图像 Embedding...")
        self.predictor.set_image(image_rgb)

        # 3. 转换 Box 坐标
        input_boxes_tensor = torch.tensor(boxes, device=self.predictor.device)
        transformed_boxes = self.predictor.transform.apply_boxes_torch(
            input_boxes_tensor, image_rgb.shape[:2]
        )

        # 4. 推理
        try:
            masks, scores, logits = self.predictor.predict_torch(
                point_coords=None,
                point_labels=None,
                boxes=transformed_boxes,
                multimask_output=False,
            )
        except Exception as e:
            logging.error(f"推理过程出错: {e}")
            return []

        # 5. 格式化结果
        masks_np = masks.detach().cpu().numpy()  # shape: (N, 1, H, W)
        scores_np = scores.detach().cpu().numpy()

        results = []
        for i in range(len(masks_np)):
            mask_bool = masks_np[i][0]  # 取出 2D Mask
            results.append({
                "id": i,
                "segmentation": mask_bool,
                "iou": float(scores_np[i][0]),
                "input_box": boxes[i],
                "area": int(np.sum(mask_bool))
            })

        logging.info(f"分割完成，生成 {len(results)} 个 Mask")
        return results

    def save_results(self, results, output_csv="segmentation_data.csv", output_img="segmentation_vis.png",
                     original_image_path=None):
        """
        辅助功能：保存统计 CSV 和可视化图片
        """
        if not results:
            return

        # --- A. 保存 CSV ---
        data_list = []
        for res in results:
            # 计算实际 Mask 的边界
            y_idx, x_idx = np.where(res['segmentation'])
            if len(y_idx) > 0:
                actual_bbox = f"{np.min(x_idx)},{np.min(y_idx)},{np.max(x_idx)},{np.max(y_idx)}"
            else:
                actual_bbox = "None"

            p_box = res['input_box']
            data_list.append({
                "ID": res['id'],
                "提示词Box": f"[{p_box[0]},{p_box[1]},{p_box[2]},{p_box[3]}]",
                "Mask面积": res['area'],
                "实际Mask范围": actual_bbox,
                "置信度(IoU)": round(res['iou'], 4)
            })

        df = pd.DataFrame(data_list)
        df.to_csv(output_csv, index=False, encoding='utf_8_sig')
        logging.info(f"统计数据已保存: {output_csv}")

        # --- B. 保存可视化图片 (如果提供了原图路径) ---
        if original_image_path and os.path.exists(original_image_path):
            self._visualize(original_image_path, results, output_img)

    def _visualize(self, image_path, results, output_path):
        """内部绘图函数"""
        img_array = np.fromfile(image_path, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        plt.figure(figsize=(10, 10))
        plt.imshow(image)
        ax = plt.gca()

        for res in results:
            # 画 Mask
            mask = res['segmentation']
            color = np.concatenate([np.random.random(3), [0.6]])
            h, w = mask.shape[-2:]
            mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
            ax.imshow(mask_image)

            # 画 Box
            box = res['input_box']
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            ax.add_patch(plt.Rectangle((x0, y0), w, h, edgecolor='green', facecolor='none', lw=2))

        plt.axis('off')
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
        plt.close()  # 关闭图表释放内存
        logging.info(f"可视化图片已保存: {output_path}")


# ================= 使用示例 =================
if __name__ == "__main__":
    # 1. 配置
    CKPT = "sam_vit_b_01ec64.pth"  # 确保该文件在当前目录或提供绝对路径
    IMG_PATH = r"E:\研究生\myproject\image api\boat_2-3.png"

    # 2. 初始化服务 (只做一次)
    #  - 这是一个很重的操作，耗时约几秒
    sam_service = SamService(checkpoint_path=CKPT, model_type="vit_b")

    # 3. 模拟输入 (来自 GroundingDINO)
    dummy_boxes = [
        [197, 74, 675, 879]
    ]

    # 4. 执行分割
    seg_results = sam_service.segment_with_boxes(IMG_PATH, dummy_boxes)

    # 5. 保存结果
    if seg_results:
        sam_service.save_results(
            seg_results,
            output_csv="test_sam_data.csv",
            output_img="test_sam_vis.png",
            original_image_path=IMG_PATH
        )