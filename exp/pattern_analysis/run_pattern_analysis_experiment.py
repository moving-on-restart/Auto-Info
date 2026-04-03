from __future__ import annotations

import argparse
import json
import math
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
APP3_DIR = SCRIPT_DIR.parent.parent
DEFAULT_INPUT_CSV = APP3_DIR / "static" / "uploads" / "palace_museum_taoci_optimized.csv"
DEFAULT_TYPES_CSV = SCRIPT_DIR / "palace_museum_taoci_types.csv"


TYPE_ALIASES = {
    "numeric": {
        "numeric",
        "number",
        "num",
        "int",
        "integer",
        "float",
        "double",
        "decimal",
        "quantitative",
        "continuous",
    },
    "datetime": {"datetime", "date", "time", "timestamp", "temporal"},
    "category": {"category", "categorical", "nominal", "enum", "label"},
    "text": {"text", "string", "str", "free text", "freetext"},
    "boolean": {"bool", "boolean"},
    "unknown": {"unknown", "na", "n/a", "none"},
}


BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "0", "1"}


@dataclass
class MethodConfig:
    z: float = 1.96
    e0: float = 0.05
    p: float = 0.5
    lambda_penalty: float = 0.6
    micro_batch_size: int = 100


def normalize_type_label(raw: Any) -> str:
    if raw is None:
        return "unknown"
    text = str(raw).strip().lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    if not text:
        return "unknown"
    for canonical, aliases in TYPE_ALIASES.items():
        if text in aliases:
            return canonical
    return text


def load_ground_truth_types(types_path: Path) -> Dict[str, str]:
    suffix = types_path.suffix.lower()
    if suffix == ".json":
        with types_path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return {str(k): normalize_type_label(v) for k, v in obj.items()}
        if isinstance(obj, list):
            mapping: Dict[str, str] = {}
            for row in obj:
                if not isinstance(row, dict):
                    continue
                field = (
                    row.get("field")
                    or row.get("column")
                    or row.get("name")
                    or row.get("column_name")
                )
                field_type = (
                    row.get("type")
                    or row.get("field_type")
                    or row.get("dtype")
                    or row.get("data_type")
                )
                if field is None or field_type is None:
                    continue
                mapping[str(field)] = normalize_type_label(field_type)
            return mapping
        raise ValueError("JSON 类型标注文件应为对象映射或对象列表。")

    df = pd.read_csv(types_path)
    if df.empty:
        return {}

    cols = list(df.columns)
    lower_to_original = {c.lower(): c for c in cols}

    def pick_col(candidates: List[str]) -> str | None:
        for c in candidates:
            if c in lower_to_original:
                return lower_to_original[c]
        return None

    field_col = pick_col(["field", "column", "name", "column_name", "字段", "列名"])
    type_col = pick_col(["type", "field_type", "dtype", "data_type", "类型", "字段类型"])

    if field_col is None or type_col is None:
        if len(cols) < 2:
            raise ValueError("类型文件至少需要两列（字段名与字段类型）。")
        field_col, type_col = cols[0], cols[1]

    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        field = row.get(field_col)
        field_type = row.get(type_col)
        if pd.isna(field) or pd.isna(field_type):
            continue
        field_name = str(field).strip()
        if not field_name:
            continue
        mapping[field_name] = normalize_type_label(field_type)
    return mapping


def sanitize_series(series: pd.Series) -> pd.Series:
    s = series.dropna()
    if s.empty:
        return s
    if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
        s = s.astype(str).str.strip()
        s = s[s != ""]
    return s


def calculate_normalized_entropy(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    counts = series.value_counts(normalize=True)
    if len(counts) <= 1:
        return 0.0
    entropy = float(-(counts * np.log2(counts)).sum())
    n = len(series)
    if n <= 1:
        return 0.0
    return float(entropy / np.log2(n))



def safe_to_datetime(series: pd.Series) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        return pd.to_datetime(series, errors="coerce")

def infer_column_type(series: pd.Series) -> str:
    clean = sanitize_series(series)
    if clean.empty:
        return "unknown"

    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"

    as_text = clean.astype(str).str.strip()
    if as_text.empty:
        return "unknown"

    lower = as_text.str.lower()
    bool_ratio = float(lower.isin(BOOL_TOKENS).mean())
    if bool_ratio >= 0.95:
        return "boolean"

    numeric_like = pd.to_numeric(as_text, errors="coerce")
    if float(numeric_like.notna().mean()) >= 0.95:
        return "numeric"

    datetime_like = safe_to_datetime(as_text)
    if float(datetime_like.notna().mean()) >= 0.90:
        return "datetime"

    n_unique = int(as_text.nunique(dropna=True))
    unique_ratio = float(n_unique / max(len(as_text), 1))
    entropy = calculate_normalized_entropy(as_text)

    if n_unique < 20 or unique_ratio <= 0.2 or entropy < 0.6:
        return "category"
    return "text"


def compute_statistics(series: pd.Series, inferred_type: str) -> Dict[str, Any]:
    clean = sanitize_series(series)
    if clean.empty:
        return {"count": 0}

    if inferred_type == "numeric":
        numeric_series = pd.to_numeric(clean, errors="coerce").dropna()
        if numeric_series.empty:
            return {"count": 0}
        return {
            "count": int(len(numeric_series)),
            "min": float(numeric_series.min()),
            "max": float(numeric_series.max()),
            "mean": float(numeric_series.mean()),
            "std": float(numeric_series.std(ddof=0)),
        }

    if inferred_type == "datetime":
        datetime_series = safe_to_datetime(clean).dropna()
        if datetime_series.empty:
            return {"count": 0}
        return {
            "count": int(len(datetime_series)),
            "start": datetime_series.min().isoformat(),
            "end": datetime_series.max().isoformat(),
        }

    as_text = clean.astype(str)
    top_values = as_text.value_counts().head(5)
    return {
        "count": int(len(as_text)),
        "entropy": float(calculate_normalized_entropy(as_text)),
        "top_values": {str(k): int(v) for k, v in top_values.items()},
    }


def cochran_sample_size(population_size: int, z: float, e: float, p: float) -> int:
    if population_size <= 0:
        return 0
    n0 = (z**2 * p * (1.0 - p)) / (e**2)
    n = n0 / (1.0 + (n0 - 1.0) / population_size)
    return int(min(population_size, max(1, math.ceil(n))))


def sample_series_without_replacement(series: pd.Series, n: int, rng: np.random.Generator) -> pd.Series:
    if n <= 0:
        return series.iloc[:0]
    if n >= len(series):
        return series
    sampled_indices = rng.choice(series.index.to_numpy(), size=n, replace=False)
    return series.loc[sampled_indices]


def estimate_unique_count(sample_series: pd.Series, population_size: int) -> int:
    if population_size <= 0:
        return 0
    clean = sanitize_series(sample_series)
    if clean.empty:
        return 0
    observed_unique = int(clean.nunique(dropna=True))
    n_sample = len(clean)
    if n_sample >= population_size:
        return observed_unique
    estimate = int(round(observed_unique * (population_size / n_sample)))
    return int(max(observed_unique, min(population_size, estimate)))


def analyze_s1_full_traversal(df: pd.DataFrame) -> Tuple[Dict[str, Dict[str, Any]], float]:
    start = time.perf_counter()
    results: Dict[str, Dict[str, Any]] = {}
    for col in df.columns:
        clean = sanitize_series(df[col])
        inferred = infer_column_type(df[col])
        unique_exact = int(clean.nunique(dropna=True))
        stats = compute_statistics(df[col], inferred)
        results[col] = {
            "inferred_type": inferred,
            "estimated_unique": unique_exact,
            "sample_size": int(len(clean)),
            "stats": stats,
        }
    elapsed = time.perf_counter() - start
    return results, elapsed


def analyze_s2_fixed_cochran(
    df: pd.DataFrame,
    config: MethodConfig,
    rng: np.random.Generator,
) -> Tuple[Dict[str, Dict[str, Any]], float]:
    start = time.perf_counter()
    n_rows = len(df)
    sample_n = cochran_sample_size(n_rows, config.z, config.e0, config.p)

    if sample_n >= n_rows:
        sampled_df = df
    else:
        sampled_idx = rng.choice(df.index.to_numpy(), size=sample_n, replace=False)
        sampled_df = df.loc[sampled_idx]

    results: Dict[str, Dict[str, Any]] = {}
    for col in df.columns:
        population_series = sanitize_series(df[col])
        sample_series = sanitize_series(sampled_df[col])

        inferred = infer_column_type(sample_series)
        estimated_unique = estimate_unique_count(sample_series, population_size=len(population_series))
        stats = compute_statistics(sample_series, inferred)

        results[col] = {
            "inferred_type": inferred,
            "estimated_unique": estimated_unique,
            "sample_size": int(len(sample_series)),
            "stats": stats,
        }

    elapsed = time.perf_counter() - start
    return results, elapsed


def analyze_s3_adaptive_cochran(
    df: pd.DataFrame,
    config: MethodConfig,
    rng: np.random.Generator,
) -> Tuple[Dict[str, Dict[str, Any]], float]:
    start = time.perf_counter()
    results: Dict[str, Dict[str, Any]] = {}

    for col in df.columns:
        population_series = sanitize_series(df[col])
        population_size = len(population_series)

        if population_size == 0:
            results[col] = {
                "inferred_type": "unknown",
                "estimated_unique": 0,
                "sample_size": 0,
                "stats": {"count": 0},
            }
            continue

        micro_n = min(config.micro_batch_size, population_size)
        micro_batch = sample_series_without_replacement(population_series, micro_n, rng)
        h_norm_hat = calculate_normalized_entropy(micro_batch.astype(str))

        e_prime = config.e0 * (1.0 - config.lambda_penalty * h_norm_hat)
        e_prime = max(e_prime, 0.01)

        adaptive_n = cochran_sample_size(population_size, config.z, e_prime, config.p)
        sampled_series = sample_series_without_replacement(population_series, adaptive_n, rng)

        inferred = infer_column_type(sampled_series)
        estimated_unique = estimate_unique_count(sampled_series, population_size=population_size)
        stats = compute_statistics(sampled_series, inferred)

        results[col] = {
            "inferred_type": inferred,
            "estimated_unique": estimated_unique,
            "sample_size": int(len(sampled_series)),
            "stats": stats,
        }

    elapsed = time.perf_counter() - start
    return results, elapsed


def compute_actual_unique_counts(df: pd.DataFrame) -> Dict[str, int]:
    return {col: int(sanitize_series(df[col]).nunique(dropna=True)) for col in df.columns}


def align_ground_truth_columns(df: pd.DataFrame, gt_types: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    df_lower = {col.lower(): col for col in df.columns}
    aligned: Dict[str, str] = {}
    missing: List[str] = []
    for raw_col, raw_type in gt_types.items():
        candidate = str(raw_col).strip()
        if candidate in df.columns:
            aligned[candidate] = normalize_type_label(raw_type)
            continue
        mapped = df_lower.get(candidate.lower())
        if mapped is not None:
            aligned[mapped] = normalize_type_label(raw_type)
        else:
            missing.append(candidate)
    return aligned, missing


def evaluate_type_accuracy(result_by_col: Dict[str, Dict[str, Any]], gt_types: Dict[str, str]) -> float:
    if not gt_types:
        return 0.0
    correct = 0
    for col, gt_type in gt_types.items():
        pred_type = normalize_type_label(result_by_col[col]["inferred_type"])
        if pred_type == gt_type:
            correct += 1
    return float(correct / len(gt_types))


def evaluate_uvre(
    result_by_col: Dict[str, Dict[str, Any]],
    actual_unique: Dict[str, int],
) -> float:
    errors: List[float] = []
    for col, true_unique in actual_unique.items():
        est_unique = int(result_by_col[col]["estimated_unique"])
        if true_unique <= 0:
            rel_error = 0.0 if est_unique <= 0 else 1.0
        else:
            rel_error = abs(est_unique - true_unique) / true_unique
        errors.append(float(rel_error))
    return float(np.mean(errors)) if errors else 0.0


def summarize_sample_sizes(result_by_col: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    sizes = np.array([int(v["sample_size"]) for v in result_by_col.values()], dtype=float)
    if sizes.size == 0:
        return {
            "sample_size_mean": 0.0,
            "sample_size_std": 0.0,
            "sample_size_min": 0.0,
            "sample_size_max": 0.0,
        }
    return {
        "sample_size_mean": float(np.mean(sizes)),
        "sample_size_std": float(np.std(sizes)),
        "sample_size_min": float(np.min(sizes)),
        "sample_size_max": float(np.max(sizes)),
    }


def run_experiment(
    df: pd.DataFrame,
    gt_types: Dict[str, str],
    repeats: int,
    seed: int,
    config: MethodConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    methods = ["S1", "S2", "S3"]
    actual_unique = compute_actual_unique_counts(df)

    run_records: List[Dict[str, Any]] = []
    column_records: List[Dict[str, Any]] = []

    for method_index, method in enumerate(methods):
        for run_id in range(1, repeats + 1):
            run_seed = int(seed + method_index * 10000 + run_id)
            rng = np.random.default_rng(run_seed)

            if method == "S1":
                result_by_col, elapsed = analyze_s1_full_traversal(df)
            elif method == "S2":
                result_by_col, elapsed = analyze_s2_fixed_cochran(df, config, rng)
            else:
                result_by_col, elapsed = analyze_s3_adaptive_cochran(df, config, rng)

            type_accuracy = evaluate_type_accuracy(result_by_col, gt_types)
            uvre = evaluate_uvre(result_by_col, actual_unique)
            size_summary = summarize_sample_sizes(result_by_col)

            run_records.append(
                {
                    "method": method,
                    "run_id": run_id,
                    "seed": run_seed,
                    "elapsed_seconds": float(elapsed),
                    "type_accuracy": float(type_accuracy),
                    "uvre": float(uvre),
                    "evaluated_type_fields": int(len(gt_types)),
                    **size_summary,
                }
            )

            for col in df.columns:
                true_unique = int(actual_unique[col])
                est_unique = int(result_by_col[col]["estimated_unique"])
                if true_unique <= 0:
                    rel_error = 0.0 if est_unique <= 0 else 1.0
                else:
                    rel_error = abs(est_unique - true_unique) / true_unique

                column_records.append(
                    {
                        "method": method,
                        "run_id": run_id,
                        "column": col,
                        "gt_type": gt_types.get(col, ""),
                        "pred_type": normalize_type_label(result_by_col[col]["inferred_type"]),
                        "type_correct": int(
                            gt_types.get(col, "__na__")
                            == normalize_type_label(result_by_col[col]["inferred_type"])
                        ),
                        "sample_size": int(result_by_col[col]["sample_size"]),
                        "true_unique": true_unique,
                        "estimated_unique": est_unique,
                        "relative_error": float(rel_error),
                    }
                )

    run_df = pd.DataFrame(run_records)
    column_df = pd.DataFrame(column_records)

    summary_df = (
        run_df.groupby("method", as_index=False)
        .agg(
            elapsed_mean=("elapsed_seconds", "mean"),
            elapsed_std=("elapsed_seconds", "std"),
            type_accuracy_mean=("type_accuracy", "mean"),
            type_accuracy_std=("type_accuracy", "std"),
            uvre_mean=("uvre", "mean"),
            uvre_std=("uvre", "std"),
            sample_size_mean=("sample_size_mean", "mean"),
            sample_size_std=("sample_size_std", "mean"),
        )
        .fillna(0.0)
    )

    summary_df["runtime_seconds_mean"] = summary_df["elapsed_mean"]
    summary_df["runtime_seconds_std"] = summary_df["elapsed_std"]

    return run_df, summary_df, column_df


def build_output_dir(base_output_dir: Path | None) -> Path:
    if base_output_dir is None:
        base_output_dir = Path(__file__).resolve().parent / "results"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_output = base_output_dir / f"pattern_experiment_{timestamp}"
    final_output.mkdir(parents=True, exist_ok=True)
    return final_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="模式分析方法对比实验：S1 全量遍历，S2 固定参数 Cochran 抽样，S3 自适应 Cochran 抽样。",
    )
    parser.add_argument("--csv", type=str, default=str(DEFAULT_INPUT_CSV), help=f"输入 CSV 文件路径。默认: {DEFAULT_INPUT_CSV}")
    parser.add_argument("--types", type=str, default=str(DEFAULT_TYPES_CSV), help=f"字段类型标注文件（CSV 或 JSON）。默认: {DEFAULT_TYPES_CSV}")
    parser.add_argument("--repeats", type=int, default=10, help="每组实验重复次数。默认 10。")
    parser.add_argument("--seed", type=int, default=42, help="随机种子。默认 42。")
    parser.add_argument("--output", type=str, default=None, help="输出目录。默认写入当前目录下 results。")
    parser.add_argument("--z", type=float, default=1.96, help="Cochran 置信水平 z。默认 1.96。")
    parser.add_argument("--e0", type=float, default=0.05, help="Cochran 基础误差界限 e0。默认 0.05。")
    parser.add_argument("--p", type=float, default=0.5, help="Cochran 方差估计 p。默认 0.5。")
    parser.add_argument(
        "--lambda-penalty",
        type=float,
        default=0.6,
        help="S3 复杂度惩罚系数 lambda。默认 0.6。",
    )
    parser.add_argument(
        "--micro-batch-size",
        type=int,
        default=100,
        help="S3 微批次容量 k。默认 100。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    experiment_start = time.perf_counter()

    csv_path = Path(args.csv)
    types_path = Path(args.types)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")
    if not types_path.exists():
        raise FileNotFoundError(f"类型标注文件不存在: {types_path}")

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty:
        raise ValueError("输入 CSV 为空。")

    raw_gt_types = load_ground_truth_types(types_path)
    aligned_gt_types, missing_gt_cols = align_ground_truth_columns(df, raw_gt_types)
    if not aligned_gt_types:
        raise ValueError("字段类型标注与 CSV 字段无法对齐，请检查字段名。")

    config = MethodConfig(
        z=float(args.z),
        e0=float(args.e0),
        p=float(args.p),
        lambda_penalty=float(args.lambda_penalty),
        micro_batch_size=int(args.micro_batch_size),
    )

    output_dir = build_output_dir(Path(args.output) if args.output else None)

    run_df, summary_df, column_df = run_experiment(
        df=df,
        gt_types=aligned_gt_types,
        repeats=int(args.repeats),
        seed=int(args.seed),
        config=config,
    )

    total_runtime_seconds = time.perf_counter() - experiment_start
    runtime_by_method = {
        row["method"]: {
            "mean": float(row["elapsed_mean"]),
            "std": float(row["elapsed_std"]),
        }
        for _, row in summary_df.iterrows()
    }

    run_csv = output_dir / "run_level_results.csv"
    summary_csv = output_dir / "summary_by_method.csv"
    column_csv = output_dir / "column_level_results.csv"
    meta_json = output_dir / "experiment_meta.json"

    run_df.to_csv(run_csv, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    column_df.to_csv(column_csv, index=False, encoding="utf-8-sig")

    df_no_gt = [c for c in df.columns if c not in aligned_gt_types]
    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_csv": str(csv_path.resolve()),
        "input_types": str(types_path.resolve()),
        "total_rows": int(len(df)),
        "total_columns": int(len(df.columns)),
        "repeats": int(args.repeats),
        "total_runtime_seconds": float(total_runtime_seconds),
        "runtime_by_method_seconds": runtime_by_method,
        "config": {
            "z": config.z,
            "e0": config.e0,
            "p": config.p,
            "lambda_penalty": config.lambda_penalty,
            "micro_batch_size": config.micro_batch_size,
        },
        "evaluation": {
            "type_accuracy_fields": len(aligned_gt_types),
            "type_accuracy_missing_type_labels": df_no_gt,
            "ground_truth_not_in_csv": missing_gt_cols,
        },
        "outputs": {
            "run_level_results": str(run_csv.resolve()),
            "summary_by_method": str(summary_csv.resolve()),
            "column_level_results": str(column_csv.resolve()),
        },
    }
    with meta_json.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("实验完成。")
    print(f"总运行时间: {total_runtime_seconds:.3f} 秒")
    print("各方法平均耗时(秒):")
    for _, row in summary_df.iterrows():
        print(f"  {row['method']}: {row['elapsed_mean']:.4f} ± {row['elapsed_std']:.4f}")
    print(f"结果目录: {output_dir}")
    print(f"- run-level: {run_csv.name}")
    print(f"- summary:   {summary_csv.name}")
    print(f"- column:    {column_csv.name}")


if __name__ == "__main__":
    main()
