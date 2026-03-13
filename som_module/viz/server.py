# -*- coding: utf-8 -*-
"""
som_module/viz/server.py
========================
轻量级 Flask 可视化服务器。

运行后在浏览器中打开 http://localhost:<port>/ 即可查看交互式 SOM 图。

支持三种使用方式：

  1. 从 run_debug.py 自动启动（推荐）：
       python run_debug.py --input runs.json --viz

  2. 直接向 server 传入 bundle：
       from som_module.viz.server import launch
       launch(bundle)               # 阻塞，在浏览器中打开

  3. 命令行直接运行（接受 JSON 文件）：
       python -m som_module.viz.server --input som_result.json
       python -m som_module.viz.server --input runs.json --from-runs
"""

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

# ── 确保父目录在 sys.path ──
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_DIR = os.path.dirname(_MODULE_DIR)
for _p in (_PROJECT_DIR, _MODULE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from flask import Flask, jsonify, render_template, request
except ImportError as exc:
    raise RuntimeError("Flask 未安装，请执行: pip install flask") from exc

_TEMPLATES_DIR = os.path.join(_THIS_DIR, "templates")

app = Flask(__name__, template_folder=_TEMPLATES_DIR)
app.config["JSON_ENSURE_ASCII"] = False

# 全局存储当前 SOM bundle（在 launch() 中注入）
_current_bundle: dict = {}


@app.route("/")
def index():
    """主页：渲染 SOM 可视化页面。"""
    return render_template("som_viewer.html")


@app.route("/api/som_data")
def som_data():
    """返回当前 SOM bundle 的 JSON 数据。"""
    return jsonify(_current_bundle)


@app.route("/api/reload", methods=["POST"])
def reload_bundle():
    """
    热重载接口：前端或外部脚本可 POST 新的 bundle JSON 触发刷新。
    Body: {"bundle": {...}}  或  直接 POST bundle 本身
    """
    global _current_bundle
    try:
        data = request.get_json(force=True, silent=True) or {}
        if "bundle" in data:
            _current_bundle = data["bundle"]
        else:
            _current_bundle = data
        return jsonify({"status": "ok", "node_count": len(_current_bundle.get("graph_data", {}).get("nodes", []))})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


def _open_browser(port: int) -> None:
    """延迟 800ms 后打开浏览器（给 Flask 启动时间）。"""
    import time
    time.sleep(0.8)
    webbrowser.open(f"http://localhost:{port}/")


def launch(
    bundle: dict,
    port: int = 7860,
    open_browser: bool = True,
    block: bool = True,
) -> None:
    """
    注入 SOM bundle 并启动可视化服务器。

    Parameters
    ----------
    bundle : dict
        pipeline.build_som_from_runs() 返回的 bundle 字典。
    port : int
        监听端口，默认 7860。
    open_browser : bool
        是否自动打开浏览器，默认 True。
    block : bool
        是否阻塞当前线程（True：前台运行；False：后台线程运行）。
    """
    global _current_bundle
    _current_bundle = bundle

    print(f"\n[SOM Viewer] 服务器启动中 → http://localhost:{port}/")
    print("[SOM Viewer] 按 Ctrl+C 停止服务器\n")

    if open_browser:
        t = threading.Thread(target=_open_browser, args=(port,), daemon=True)
        t.start()

    if block:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    else:
        server_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
            daemon=True,
        )
        server_thread.start()
        return server_thread


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="SOM 可视化服务器：从 JSON 文件启动交互式浏览器视图"
    )
    parser.add_argument("--input", "-i", required=True, help="输入 JSON 文件路径")
    parser.add_argument(
        "--from-runs",
        action="store_true",
        help="输入文件是 raw runs JSON（而非 SOM bundle）；自动先运行流水线",
    )
    parser.add_argument("--port", "-p", type=int, default=7860, help="服务端口（默认 7860）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    if args.from_runs:
        from som_module import pipeline, json_io
        print(f"从 runs 文件构建 SOM: {input_path}")
        raw_runs = json_io.load_runs_from_file(input_path)
        bundle = pipeline.build_som_from_runs(raw_runs)
    else:
        with open(input_path, "r", encoding="utf-8") as fp:
            bundle = json.load(fp)

    launch(bundle, port=args.port, open_browser=not args.no_browser, block=True)


if __name__ == "__main__":
    _cli()
