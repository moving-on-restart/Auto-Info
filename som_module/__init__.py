# -*- coding: utf-8 -*-
"""
som_module
==========
从 JSON 输入到交互式自组织映射图（SOM）的独立子模块。

模块结构
--------
  config.py           所有可调节超参数（权重、SOM 参数、模型名称等）
  json_io.py          JSON 输入/输出（加载文件、规范化格式、保存结果）
  element_extractor.py 从 runs 数据提取设计元素节点及共现关系
  som_trainer.py      SOM 训练算法（多模态嵌入 + MiniSom + 匈牙利分配）
  pipeline.py         完整流水线协调器（一行代码完成全流程）
  run_debug.py        独立调试脚本（可直接命令行运行）

快速开始
--------
  # 从 JSON 文件生成 SOM bundle
  from som_module import pipeline
  bundle = pipeline.build_som_from_file("path/to/runs.json")
  pipeline.print_bundle_summary(bundle)

  # 或者使用 pipeline 的详细步骤
  from som_module import json_io, element_extractor, som_trainer
  raw_runs = json_io.load_runs_from_file("runs.json")
  elements, run_ids, pr, dc, links = element_extractor.extract_elements_and_rules(raw_runs)
  nodes = som_trainer.train_som(elements, run_ids, pr, dc)

调试
----
  # 命令行直接运行（使用内置示例数据）
  python -m som_module.run_debug

  # 指定输入文件
  python -m som_module.run_debug --input your_runs.json --output result.json
"""

from . import config
from . import json_io
from . import element_extractor
from . import som_trainer
from . import pipeline

# 最常用的公开入口
from .pipeline import build_som_from_file, build_som_from_runs, print_bundle_summary
from .json_io import load_runs_from_file, normalize_runs_payload, save_som_result

__all__ = [
    # 子模块
    "config",
    "json_io",
    "element_extractor",
    "som_trainer",
    "pipeline",
    # 快捷函数
    "build_som_from_file",
    "build_som_from_runs",
    "print_bundle_summary",
    "load_runs_from_file",
    "normalize_runs_payload",
    "save_som_result",
]
