import logging
import os
import sys

from flask import Flask, jsonify, render_template, request, send_from_directory

from app3.config import AppConfig
from app3.logging_config import configure_logging
##git提交测试
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from util.file_utils import save_uploaded_image
from controller import data_logic
from controller import generate_random_logic
from controller import infographic_logic
from controller import upload_logic
from controller import vision_logic

configure_logging()
logger = logging.getLogger(__name__)

config = AppConfig.from_env()

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = config.upload_folder
app.config["GENERATED_IMAGES_FOLDER"] = config.generated_images_folder
app.config["MAX_CONTENT_LENGTH"] = config.max_content_length

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["GENERATED_IMAGES_FOLDER"], exist_ok=True)


def create_app():
    """App factory for future extensibility."""
    return app


@app.route("/")
def index():
    return render_template("indexv4.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"status": "error", "error": "No file part"}), 400

    file = request.files["file"]
    result_data, error_msg = upload_logic.handle_csv_upload(file, app.config["UPLOAD_FOLDER"])
    if error_msg:
        return jsonify({"status": "error", "error": error_msg}), 400

    return jsonify({"status": "success", **result_data})


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.json or {}
        answer, chart_json = data_logic.analyze_logic(
            data.get("filepath"),
            data.get("description"),
            data.get("query"),
        )
        return jsonify({"status": "success", "answer": answer, "chart": chart_json})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/infographic/generate_random", methods=["POST"])
@app.route("/infographic/generate_random_three", methods=["POST"])
def generate_random_infographics():
    data = request.json or {}
    try:
        results, error_msg = generate_random_logic.generate_random_logic(data)
        if error_msg:
            return jsonify({"status": "error", "error": error_msg}), 400
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        logger.error(f"Random Generation Error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/infographic/plan", methods=["POST"])
def get_infographic_plan():
    data = request.json or {}
    try:
        plan = infographic_logic.get_infographic_plan(
            data.get("description"),
            data.get("query"),
            data.get("analysis_result"),
            data.get("chart_source"),
        )
        if plan and "element_pool" in plan:
            return jsonify({"status": "success", "plan": plan})
        return jsonify({"status": "error", "error": "Failed to generate plan structure"}), 500
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/infographic/generate_asset", methods=["POST"])
def generate_asset():
    data = request.json or {}
    try:
        image_url = infographic_logic.generate_single_asset(
            keywords=data.get("keywords"),
            style_desc=data.get("style"),
        )
        if image_url:
            return jsonify({"status": "success", "asset_url": image_url})
        return jsonify({"status": "error", "error": "Asset generation failed"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/infographic/generate_final", methods=["POST"])
def generate_final_poster():
    data = request.json or {}
    print("Received data for final infographic generation:", data)
    try:
        final_url = infographic_logic.generate_final_composite(
            user_selections=data.get("selections"),
            chart_json=data.get("chart_source"),
            description=data.get("description", "No description"),
            query=data.get("query", "No query"),
            analysis_result=data.get("analysis_result", "No insights"),
        )
        if final_url:
            return jsonify({"status": "success", "image_url": final_url})
        return jsonify({"status": "error", "error": "Final generation failed"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/generate_ref_image", methods=["POST"])
def generate_ref_image():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt")
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        image_path = vision_logic.generate_ref_image_logic(prompt, data.get("aspect_ratio", "1:1"))
        if image_path:
            return jsonify({"status": "success", "image_path": image_path})
        return jsonify({"error": "Image generation failed"}), 500
    except Exception as e:
        logger.error(f"Gen Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/generate_palette_prompt", methods=["POST"])
def generate_palette_prompt():
    try:
        data = request.get_json() or {}
        result = vision_logic.generate_palette_prompt_logic(
            description=data.get("description"),
            query=data.get("query"),
            analysis_result=data.get("analysis_result"),
            chart_source=data.get("chart_source"),
        )
        return jsonify({"status": "success", "prompt_package": result})
    except Exception as e:
        logger.error(f"Palette Prompt Error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/upload_ref_image", methods=["POST"])
def upload_ref_image():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        image_path = save_uploaded_image(file, app.config["UPLOAD_FOLDER"])
        return jsonify({"status": "success", "image_path": image_path})
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/process_palette_pipeline", methods=["POST"])
def process_palette_pipeline():
    try:
        data = request.get_json() or {}
        image_path = data.get("image_path")
        text_prompt = data.get("text_prompt")

        results = vision_logic.process_palette_pipeline_logic(image_path, text_prompt)
        if not results:
            return jsonify({"status": "no_objects", "results": []})

        return jsonify({"status": "success", "results": results})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Palette Pipeline Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5008)
