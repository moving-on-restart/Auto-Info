import os
import logging

import cv2
import numpy as np

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
    """Detect -> segment -> palette extraction pipeline."""
    if not image_path or not os.path.exists(image_path):
        raise ValueError("Invalid image path")

    dino_prompt = transform_to_dino_prompt(text_prompt)

    dino_result = get_dino_service().detect_objects(image_path, dino_prompt)
    if not dino_result or dino_result.get("count", 0) == 0:
        return []

    boxes = [item["box_pixel"] for item in dino_result["results"]]
    labels = [item["label"] for item in dino_result["results"]]

    sam_service = get_sam_service()
    if sam_service is None:
        raise RuntimeError("SAM service not initialized")

    seg_results = sam_service.segment_with_boxes(image_path, boxes)
    final_results = palette_service.process_sam_results(image_path, seg_results)

    frontend_data = []
    for item in final_results:
        original_id = item["id"]
        mask = None
        if 0 <= original_id < len(seg_results):
            mask = seg_results[original_id].get("segmentation")

        polygons = mask_to_polygon(mask) if mask is not None else []
        current_label = labels[original_id] if 0 <= original_id < len(labels) else "object"

        frontend_data.append(
            {
                "id": original_id,
                "label": current_label,
                "polygons": polygons,
                "palette": item.get("palette"),
                "harmony_score": item.get("harmony_score"),
            }
        )

    return frontend_data


def generate_palette_prompt_logic(description, query, analysis_result=None, chart_source=None):
    return generate_palette_prompt_package(
        description=description or "",
        query=query or "",
        analysis_result=analysis_result,
        chart_source=chart_source if isinstance(chart_source, dict) else None,
    )


def process_full_image_palette_logic(image_path):
    """Extract palette directly from full image (no object-region prompt)."""
    if not image_path or not os.path.exists(image_path):
        raise ValueError("Invalid image path")

    image_cv = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image_cv is None:
        raise ValueError(f"Failed to read image: {image_path}")

    image_rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
    pixels = image_rgb.reshape(-1, 3)
    if len(pixels) < 50:
        return []

    result = palette_service.selector.extract_harmonious_palette_from_pixels(
        pixels,
        target_colors=5,
        method="exhaustive",
    )
    if not result:
        return []

    return [
        {
            "id": 0,
            "label": "full_image",
            "polygons": [],
            "palette": result.get("palette"),
            "harmony_score": result.get("harmony_score"),
        }
    ]


def _resolve_local_image_path(image_path):
    if not image_path:
        return image_path

    if os.path.exists(image_path):
        return image_path

    normalized = image_path.replace("/", os.sep).replace("\\", os.sep)
    if os.path.exists(normalized):
        return normalized

    if image_path.startswith("/static/"):
        candidate = os.path.join(os.getcwd(), image_path.lstrip("/"))
        if os.path.exists(candidate):
            return candidate

    return image_path


def generate_palette_from_color_node_logic(
    description,
    query,
    node_label,
    node_desc,
    user_region_prompt=None,
    reuse_image=False,
    current_image_path=None,
    analysis_result=None,
    chart_source=None,
    aspect_ratio="1:1",
):
    prompt_package = generate_palette_prompt_package(
        description=description or "",
        query=query or "",
        analysis_result=analysis_result,
        chart_source=chart_source if isinstance(chart_source, dict) else None,
    )

    stage4 = prompt_package.get("stage4", {}) if isinstance(prompt_package, dict) else {}
    base_prompt = (stage4.get("reference_prompt") or "").strip()
    node_label_text = (node_label or "").strip()
    node_desc_text = (node_desc or "").strip()

    node_constraint_parts = []
    if node_label_text:
        node_constraint_parts.append(f"指定配色方案名称: {node_label_text}")
    if node_desc_text:
        node_constraint_parts.append(f"指定配色描述: {node_desc_text}")
    node_constraint = "; ".join(node_constraint_parts) if node_constraint_parts else "指定配色方案作为主导约束"

    composed_prompt = "\n".join(
        [
            base_prompt,
            f"{node_constraint}。请强化该配色方案的主色、辅助色与对比关系。",
            "请生成一个清晰、可理解的单一物体或真实场景图像，用于体现整体色调氛围。",
            "禁止出现调色板色条、色卡、图表、UI块、文字和水印。",
        ]
    ).strip()

    resolved_existing_path = _resolve_local_image_path(current_image_path) if current_image_path else None
    use_existing_image = bool(reuse_image and resolved_existing_path and os.path.exists(resolved_existing_path))

    if use_existing_image:
        image_path = current_image_path
        resolved_path = resolved_existing_path
    else:
        image_path = generate_ref_image_logic(composed_prompt, aspect_ratio or "1:1")
        resolved_path = _resolve_local_image_path(image_path)

    region_prompt = str(user_region_prompt or "").strip()
    extracted_results = []
    full_image_mode = False

    if resolved_path and os.path.exists(resolved_path):
        try:
            if region_prompt:
                extracted_results = process_palette_pipeline_logic(resolved_path, region_prompt)
            else:
                extracted_results = process_full_image_palette_logic(resolved_path)
                full_image_mode = True
        except Exception as e:
            logger.warning(f"Palette pipeline from color node failed: {e}")

    return {
        "image_path": image_path,
        "used_existing_image": use_existing_image,
        "region_prompt": region_prompt,
        "full_image_mode": full_image_mode,
        "composed_prompt": composed_prompt,
        "results": extracted_results,
        "prompt_package": prompt_package,
    }
