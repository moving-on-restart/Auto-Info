# services/palette.py
import numpy as np
import cv2
from app3.util.cielab_improve_kmeans import MoonSpencerHarmonySelector

class PaletteService:
    def __init__(self):
        self.selector = MoonSpencerHarmonySelector()

    def _extract_colors_from_mask(self, image, mask, target_colors=5):
        """内部辅助方法：从掩码区域提取颜色
        注意：image 参数必须是 BGR 格式 (OpenCV 默认格式)
        """
        # 统一在此处将 BGR 转为 RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # 提取掩码区域的非零像素
        region_pixels = image_rgb[mask]

        # 过滤无效区域
        if len(region_pixels) < 50:
            return None

        try:
            result = self.selector.extract_harmonious_palette_from_pixels(
                region_pixels,
                target_colors=target_colors,
                method='exhaustive'
            )
            return result
        except Exception as e:
            print(f"Color extraction internal error: {e}")
            return None

    def process_sam_results(self, image_path, sam_results):
        """
        【新增】专门处理 SAM 分割结果
        """
        # 1. 读取图片 (BGR格式)
        image_cv = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image_cv is None:
            raise ValueError(f"无法读取图片: {image_path}")

        # 【修复】：这里不需要手动转 RGB，因为 _extract_colors_from_mask 内部会处理
        # image_rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB) <--- 删除这一行

        processed_palettes = []

        for idx, res in enumerate(sam_results):
            mask = res['segmentation']  # bool array
            bbox = res['input_box']     # [x1, y1, x2, y2]

            # 直接传入 image_cv (BGR)
            color_result = self._extract_colors_from_mask(image_cv, mask)

            if color_result:
                processed_palettes.append({
                    'id': idx,
                    'label_name': res.get('label', 'target'),
                    'bbox': [int(x) for x in bbox],
                    'area': int(res['area']),
                    'palette': color_result['palette'],
                    'harmony_score': color_result['harmony_score'],
                    # 'segmentation_mask': mask.tolist()
                })

        return processed_palettes

    def process_region_palettes(self, image_path, segments_info, segmentation_map_list):
        """处理整个图片的所有分割区域，生成调色板"""
        image_cv = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image_cv is None:
            raise ValueError(f"Could not read image from {image_path}")

        segmentation_map = np.array(segmentation_map_list)
        region_palettes = []

        for segment in segments_info:
            segment_id = segment['id']
            if segmentation_map.size == 0:
                continue

            mask = (segmentation_map == segment_id)

            # 这里传入的是 BGR，逻辑是正确的
            region_colors = self._extract_colors_from_mask(image_cv, mask)

            if region_colors:
                region_palettes.append({
                    'segment_id': segment_id,
                    'label_name': segment['label_name'],
                    'area': segment['area'],
                    'palette': region_colors['palette'],
                    'harmony_score': region_colors['harmony_score'],
                    'bbox': segment.get('bbox', [])
                })

        return region_palettes

# 创建实例
palette_service = PaletteService()