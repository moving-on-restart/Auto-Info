# Pattern Analysis Experiment (S1 / S2 / S3)

本目录用于复现实验中的三组模式分析对比方法：

- `S1`：全量遍历法（逐行统计唯一值、类型推断、统计特征）
- `S2`：固定参数 Cochran 抽样法（`z=1.96`, `e0=0.05`, `p=0.5`）
- `S3`：自适应 Cochran 抽样法（在 S2 基础上引入微批次熵调节，`lambda=0.6`, `k=100`）

## 1. 输入

需要两个输入文件：

1. 数据文件：CSV
2. 字段类型标注文件：CSV 或 JSON

### 类型标注 CSV 最简格式

```csv
column,type
age,numeric
gender,category
created_at,datetime
comment,text
```

也支持中文表头（如 `字段`,`类型`）。

### 类型标注 JSON 格式

```json
{
  "age": "numeric",
  "gender": "category",
  "created_at": "datetime",
  "comment": "text"
}
```

## 2. 指标

- 效率：模式分析总耗时（秒）
- 精度：
  - `Type Accuracy`：字段类型识别准确率
  - `UVRE`（Unique Value Relative Error）：
    各字段唯一值估计数量相对全量真实唯一值的平均相对误差

每种方法默认重复执行 10 次，输出均值与标准差。

## 3. 运行

直接运行（使用脚本内置默认路径）：

```bash
python app3/exp/pattern_analysis/run_pattern_analysis_experiment.py
```

默认会使用：

- 数据 CSV：`app3/static/uploads/palace_museum_taoci_optimized.csv`
- 类型 CSV：`app3/exp/pattern_analysis/palace_museum_taoci_types.csv`

如需切换数据，可显式传参：

```bash
python app3/exp/pattern_analysis/run_pattern_analysis_experiment.py \
  --csv path/to/your_dataset.csv \
  --types path/to/your_field_types.csv
```

可选参数：

- `--repeats`：重复次数（默认 `10`）
- `--seed`：随机种子（默认 `42`）
- `--output`：输出根目录（默认写到本目录 `results/`）
- `--z`：Cochran `z`（默认 `1.96`）
- `--e0`：基础误差界限（默认 `0.05`）
- `--p`：方差估计（默认 `0.5`）
- `--lambda-penalty`：S3 复杂度惩罚系数（默认 `0.6`）
- `--micro-batch-size`：S3 微批次容量（默认 `100`）

## 4. 输出

每次运行会在 `results/pattern_experiment_YYYYMMDD_HHMMSS/` 下生成：

- `run_level_results.csv`：每次重复实验的指标
- `summary_by_method.csv`：按方法聚合后的均值/标准差（含 `elapsed_mean/std` 与 `runtime_seconds_mean/std`）
- `column_level_results.csv`：字段级预测与误差明细
- `experiment_meta.json`：实验配置、输入路径、字段对齐信息（含 `total_runtime_seconds` 与 `runtime_by_method_seconds`）

## 5. 备注

- `Type Accuracy` 仅在“有类型标注的字段”上评估。
- `UVRE` 在 CSV 的全部字段上评估。
- 若类型文件字段名与 CSV 不一致，程序会在 `experiment_meta.json` 中记录未对齐字段。


