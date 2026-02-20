Auto-Info: 智能数据可视化与信息图生成系统
Auto-Info 是一个基于 Flask 的 Web 应用程序，旨在通过用户上传的数据自动进行分析，并结合 AI 大模型（如 Gemini）、计算机视觉模型（SAM, DINO）自动生成精美、现代化的数据信息图 (Infographics) 和可视化图表。

🌟 核心功能
📊 数据上传与智能分析

支持上传 CSV 文件进行解析。

根据用户查询 (Query) 和数据描述自动生成数据分析结论和图表配置。

🎨 智能信息图生成

基于数据的 Prompt 生成：将 Vega-Lite 图表 JSON 数据转换为 AI 绘图提示词，精准还原数据趋势。

分步生成引擎：支持从“规划 (Plan)” -> “素材生成 (Asset)” -> “最终排版合成 (Final Composite)” 的完整流水线。

随机生成模式：提供快速的信息图随机探索生成。

🖼️ 视觉处理与配色分析

AI 图像生成：集成 Gemini 图像模型 (gemini-3-pro-image-preview) 生成参考图及最终海报。

色板 (Palette) 处理：基于用户上传或生成的参考图片，结合 DINO (目标检测) 和 SAM (Segment Anything Model，图像分割) 提取画面色板与视觉元素。

🛠️ 技术栈
后端框架: Python 3, Flask

AI 与大模型:

Gemini (文本到图像生成, LangChain 集成)

RAG 模型 (paraphrase-multilingual-MiniLM-L12-v2)

计算机视觉:

SAM (Segment Anything Model)

DINO (目标检测 API)

可视化规范: Vega-Lite (用于图表 JSON 渲染)

⚙️ 环境配置
项目使用 .env 文件进行环境配置。请在项目根目录下创建一个 .env 文件，并参考以下配置项进行修改：

代码段

# Flask 基础配置
APP3_UPLOAD_FOLDER=static/uploads
APP3_GENERATED_IMAGES_FOLDER=static/generated_images
APP3_MAX_CONTENT_LENGTH=16777216  # 默认 16MB

# API 服务配置
AIHUBMIX_API_KEY=你的_AIHUBMIX_API_KEY
AIHUBMIX_BASE_URL=https://aihubmix.com/v1
APP3_IMAGE_MODEL=gemini-3-pro-image-preview

# 视觉与大模型本地/服务路径
APP3_DINO_API_URL=http://100.64.0.1:3045/predict
APP3_SAM_CHECKPOINT=E:\研究生\myproject\sam_model\sam_vit_b_01ec64.pth
APP3_RAG_MODEL_PATH=E:\研究生\myproject\app3\static\model\paraphrase-multilingual-MiniLM-L12-v2
🚀 快速启动
克隆项目并安装依赖
建议使用虚拟环境：

Bash

pip install -r requirements.txt
(注: 确保安装了 Flask, python-dotenv, flask-cors 等相关依赖)

配置环境变量
根据上一节的内容，配置 .env 文件，并确保对应的模型权重文件（如 SAM 检查点）和 RAG 模型位于指定路径。

运行应用
启动主 Flask 服务：

Bash

python app3v4.py
服务将默认运行在 http://0.0.0.0:5008。

📡 主要 API 接口
系统提供了丰富的 RESTful API 接口供前端调用：

数据与分析
GET / : 渲染前端主页 (indexv4.html)。

POST /upload_csv : 上传 CSV 文件并进行初步处理。

POST /analyze : 提交数据文件路径、描述和问题，返回分析结论及图表 JSON 配置。

信息图生成 (Infographic)
POST /infographic/plan : 依据分析结论和图表数据，规划信息图的整体结构和素材池。

POST /infographic/generate_asset : 生成单一视觉素材元素。

POST /infographic/generate_final : 根据用户选择的图表和数据，最终合成数据信息图海报。

POST /infographic/generate_random : 随机生成信息图探索方案。

视觉与图像处理 (Vision & Palette)
POST /generate_ref_image : 通过文本 Prompt 生成风格参考图。

POST /upload_ref_image : 上传本地参考图至服务器。

POST /generate_palette_prompt : 结合图表数据提取 Prompt，用于色板生成。

POST /process_palette_pipeline : 核心视觉管道，对图像进行检测、分割并返回画面色彩元素结果。
