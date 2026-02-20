import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    # Flask
    upload_folder: str = "static/uploads"
    generated_images_folder: str = "static/generated_images"
    max_content_length: int = 16 * 1024 * 1024

    # External services
    aihubmix_api_key: Optional[str] = None
    aihubmix_base_url: str = "https://aihubmix.com/v1"
    image_model_name: str = "gemini-3-pro-image-preview"
    dino_api_url: str = "http://100.64.0.1:3045/predict"

    # Model paths
    sam_checkpoint_path: str = r"E:\研究生\myproject\sam_model\sam_vit_b_01ec64.pth"
    rag_model_path: str = r"E:\研究生\myproject\app3\static\model\paraphrase-multilingual-MiniLM-L12-v2"

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()

        return cls(
            upload_folder=os.getenv("APP3_UPLOAD_FOLDER", cls.upload_folder),
            generated_images_folder=os.getenv("APP3_GENERATED_IMAGES_FOLDER", cls.generated_images_folder),
            max_content_length=int(os.getenv("APP3_MAX_CONTENT_LENGTH", str(cls.max_content_length))),
            aihubmix_api_key=os.getenv("AIHUBMIX_API_KEY"),
            aihubmix_base_url=os.getenv("AIHUBMIX_BASE_URL", cls.aihubmix_base_url),
            image_model_name=os.getenv("APP3_IMAGE_MODEL", cls.image_model_name),
            dino_api_url=os.getenv("APP3_DINO_API_URL", cls.dino_api_url),
            sam_checkpoint_path=os.getenv("APP3_SAM_CHECKPOINT", cls.sam_checkpoint_path),
            rag_model_path=os.getenv("APP3_RAG_MODEL_PATH", cls.rag_model_path),
        )
