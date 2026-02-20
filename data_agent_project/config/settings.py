import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 设置 Hugging Face 镜像
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# --- 本地 LLM 配置 ---
LLM_API_URL = "http://100.64.0.1:3025/v1/chat/completions"
LLM_TIMEOUT = 60
LLM_MAX_TOKENS = 4096

# --- 远程 API 配置 (AIHubMix) ---
# 请确保 .env 文件中有 AIHUBMIX_API_KEY
AIHUBMIX_KEY = os.getenv("AIHUBMIX_API_KEY")
AIHUBMIX_BASE_URL = "https://aihubmix.com/v1"
# 指定你想要调用的远程模型名称
REMOTE_MODEL_NAME = "claude-opus-4-5-think"
REMOTE_MODEL_MAX_TOKENS = 8192