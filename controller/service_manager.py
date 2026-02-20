import os
import logging
from typing import Optional

from app3.config import AppConfig
from app3.controller.infographic_controller_v3 import InfographicService
from app3.services.gemini_image_service import GeminiLangChainService
from app3.services.Grounding_service import DinoService
from app3.services.sam_service import SamService

logger = logging.getLogger(__name__)

_config = AppConfig.from_env()

_infographic_agent = None
_reference_gen_service = None
_dino_service = None
_sam_service = None


def _ensure_output_dir() -> None:
    os.makedirs(_config.generated_images_folder, exist_ok=True)


def get_infographic_agent() -> InfographicService:
    global _infographic_agent
    if _infographic_agent is None:
        _ensure_output_dir()
        _infographic_agent = InfographicService(output_dir=_config.generated_images_folder)
    return _infographic_agent


def get_reference_gen_service() -> GeminiLangChainService:
    global _reference_gen_service
    if _reference_gen_service is None:
        _ensure_output_dir()
        _reference_gen_service = GeminiLangChainService(
            output_dir=_config.generated_images_folder,
            model_name=_config.image_model_name,
        )
    return _reference_gen_service


def get_dino_service() -> DinoService:
    global _dino_service
    if _dino_service is None:
        _dino_service = DinoService(api_url=_config.dino_api_url)
    return _dino_service


def get_sam_service() -> Optional[SamService]:
    global _sam_service
    if _sam_service is None:
        if os.path.exists(_config.sam_checkpoint_path):
            try:
                _sam_service = SamService(checkpoint_path=_config.sam_checkpoint_path, model_type="vit_b")
                logger.info("SAM Service 启动成功")
            except Exception as e:
                logger.error(f"SAM 初始化失败: {e}")
                _sam_service = None
        else:
            logger.warning(f"SAM 权重文件未找到: {_config.sam_checkpoint_path}")
            _sam_service = None
    return _sam_service
