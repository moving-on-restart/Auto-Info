import os
import logging
from app3.controller.service_manager import (
    get_reference_gen_service,
    get_dino_service,
    get_sam_service,
)
from app3.services.textservice import transform_to_dino_prompt
from app3.services.palette import palette_service
from app3.services.palette_prompt_service import generate_palette_prompt_package
from app3.util.image_utils import mask_to_polygon

logger = logging.getLogger(__name__)


def generate_ref_image_logic(prompt, aspect_ratio):
    logger.info(f"Generating Reference: {prompt}")
    return get_reference_gen_service().generate(prompt, aspect_ratio=aspect_ratio)


def process_palette_pipeline_logic(image_path, text_prompt):
    """执行 检测 -> 分割 -> 调色板提取 的全流程"""
    if not image_path or not os.path.exists(image_path):
        raise ValueError("Invalid image path")

    # 1. Prompt 转换
    dino_prompt = transform_to_dino_prompt(text_prompt)

    # 2. Dino 检测
    dino_result = get_dino_service().detect_objects(image_path, dino_prompt)
    if not dino_result or dino_result.get('count', 0) == 0:
        return []  # 无结果

    boxes = [item['box_pixel'] for item in dino_result['results']]
    labels = [item['label'] for item in dino_result['results']]

    # 3. SAM 分割 (检查服务是否存在)
    sam_service = get_sam_service()
    if sam_service is None:
        raise RuntimeError("SAM service not initialized")

    seg_results = sam_service.segment_with_boxes(image_path, boxes)

    # 4. 调色板提取
    final_results = palette_service.process_sam_results(image_path, seg_results)

    # 5. 格式化前端数据
    frontend_data = []
    for item in final_results:
        original_id = item['id']
        mask = None
        if 0 <= original_id < len(seg_results):
            mask = seg_results[original_id].get('segmentation')

        polygons = mask_to_polygon(mask) if mask is not None else []

        current_label = labels[original_id] if 0 <= original_id < len(labels) else 'object'

        frontend_data.append({
            'id': original_id,
            'label': current_label,
            'polygons': polygons,
            'palette': item.get('palette'),
            'harmony_score': item.get('harmony_score')
        })

    return frontend_data


def generate_palette_prompt_logic(description, query, analysis_result=None, chart_source=None):
    return generate_palette_prompt_package(
        description=description or "",
        query=query or "",
        analysis_result=analysis_result,
        chart_source=chart_source if isinstance(chart_source, dict) else None,
    )
