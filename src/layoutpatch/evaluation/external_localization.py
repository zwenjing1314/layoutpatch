"""冻结 SciEGQA 外部定位评测的聚合、配对统计与保存预测复核。"""
from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence

from layoutpatch.evaluation.localization import (
    doc_bootstrap_diff,
    mcnemar_exact,
    question_macro,
    unit_metrics,
)
from layoutpatch.retrieval.route_v2_exp1 import macro_summary

METADATA_KEYS = {
    "query_id",
    "doc_id",
    "page_id",
    "unit_id",
    "role",
    "method",
    "candidate_count",
    "page_overlap_excluded",
    "ranked_layout_ids",
    "ranked_scores",
}


def gold_boxes_from_relative(boxes: Sequence[Sequence[float]], page_size: Sequence[float]) -> list[list[float]]:
    """将 SciEGQA 的 0–1000 xyxy 框映射到已审计渲染页坐标。"""
    width, height = map(float, page_size)
    if width <= 0 or height <= 0 or not boxes:
        raise ValueError("gold page needs positive size and at least one box")
    result = []
    for box in boxes:
        if len(box) != 4:
            raise ValueError("gold box must be xyxy")
        x1, y1, x2, y2 = map(float, box)
        if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
            raise ValueError("relative gold box must be within 0-1000")
        result.append([x1 * width / 1000, y1 * height / 1000, x2 * width / 1000, y2 * height / 1000])
    return result


def summarize_rows(rows: list[dict]) -> dict:
    """复用 v2-loc-1 的题内 unit 均值、题间宏平均及 M>=2 子集。"""
    if not rows:
        raise ValueError("cannot summarize empty predictions")
    keys = [key for key in rows[0] if key not in METADATA_KEYS]
    if not keys or any(set(row) != set(rows[0]) for row in rows):
        raise ValueError("prediction metric schema mismatch")
    out = {
        "all": macro_summary(rows, keys),
        "M_ge_2": macro_summary([row for row in rows if row["candidate_count"] >= 2], keys),
        "empty_units": sum(row["candidate_count"] == 0 for row in rows),
        "page_overlap_excluded_eval_units": sum(row["page_overlap_excluded"] for row in rows),
    }
    out["area_quantiles_unit"] = {}
    probabilities = (0, 0.05, 0.25, 0.5, 0.75, 0.95, 1)
    labels = ("min", "p05", "p25", "p50", "p75", "p95", "max")
    for key in ("top1_area_frac", "top1_to_gold_area"):
        values = sorted(float(row[key]) for row in rows)
        quantiles = []
        for probability in probabilities:
            position = probability * (len(values) - 1)
            low, high = math.floor(position), math.ceil(position)
            fraction = position - low
            quantiles.append(values[low] * (1 - fraction) + values[high] * fraction)
        out["area_quantiles_unit"][key] = dict(zip(labels, quantiles, strict=True))
    return out


def aggregate_seed_summaries(summaries: Mapping[str, dict], label: str, seeds: Sequence[int]) -> dict:
    """对训练方法的三个 seed 汇总均值与样本标准差。"""
    if len(seeds) != 3:
        raise ValueError("external evaluation requires three seeds")
    result = {}
    for subset in ("all", "M_ge_2"):
        selected = [summaries[f"{label}_seed_{seed}"][subset] for seed in seeds]
        denominator = {(row["questions"], row["units"]) for row in selected}
        if len(denominator) != 1:
            raise ValueError("seed subset denominator mismatch")
        keys = set(selected[0]["metrics"])
        if any(set(row["metrics"]) != keys for row in selected):
            raise ValueError("seed metric schema mismatch")
        questions, units = next(iter(denominator))
        result[subset] = {
            "questions": questions,
            "units": units,
            "metrics": {key: statistics.mean(row["metrics"][key] for row in selected) for key in sorted(keys)},
            "std": {key: statistics.stdev(row["metrics"][key] for row in selected) for key in sorted(keys)},
        }
    return result


def averaged_question_scores(methods: Mapping[str, list[dict]], label: str, seeds: Sequence[int]) -> dict[str, float]:
    values = [question_macro(methods[f"{label}_seed_{seed}"], "hit1@0.5") for seed in seeds]
    if not values or any(set(value) != set(values[0]) for value in values):
        raise ValueError("seed question denominator mismatch")
    return {query_id: statistics.mean(value[query_id] for value in values) for query_id in sorted(values[0])}


def joint_document_statistics(
    reference: Mapping[str, float],
    comparisons: Mapping[str, Mapping[str, float]],
    doc_of: Mapping[str, str],
    *,
    primary: Sequence[str],
    iterations: int = 2000,
    seed: int = 0,
    family_alpha: float = 0.05,
) -> dict:
    """用共同文档重采样计算全部外部比较，主比较另给 Bonferroni 区间。"""
    if not reference or iterations != 2000 or seed != 0:
        raise ValueError("frozen external bootstrap is 2000 iterations with seed 0")
    if len(primary) != 3 or set(primary) - set(comparisons):
        raise ValueError("three prespecified primary comparisons required")
    if set(doc_of) != set(reference) or any(set(value) != set(reference) for value in comparisons.values()):
        raise ValueError("paired question/document denominator mismatch")
    by_doc: dict[str, list[str]] = {}
    for query_id in sorted(reference):
        by_doc.setdefault(doc_of[query_id], []).append(query_id)
    docs = sorted(by_doc)
    rng = random.Random(seed)
    samples = {name: [] for name in comparisons}
    for _ in range(iterations):
        questions = [query_id for doc_id in (rng.choice(docs) for _ in docs) for query_id in by_doc[doc_id]]
        for name, baseline in comparisons.items():
            samples[name].append(sum(reference[q] - baseline[q] for q in questions) / len(questions))
    corrected_tail = family_alpha / (2 * len(primary))
    result = {}
    for name, baseline in comparisons.items():
        values = sorted(samples[name])
        raw = doc_bootstrap_diff(reference, baseline, doc_of, iterations=iterations, seed=seed)
        if raw["ci95_low"] != values[int(0.025 * iterations)] or raw["ci95_high"] != values[int(0.975 * iterations)]:
            raise ValueError("joint bootstrap differs from existing protocol")
        value = {**raw, "comparison_role": "primary" if name in primary else "secondary"}
        if name in primary:
            value.update({
                "bonferroni_ci_low": values[int(corrected_tail * iterations)],
                "bonferroni_ci_high": values[min(iterations - 1, int((1 - corrected_tail) * iterations))],
                "adjusted_positive": values[int(corrected_tail * iterations)] > 0,
                "adjusted_negative": values[min(iterations - 1, int((1 - corrected_tail) * iterations))] < 0,
            })
        result[name] = value
    return result


def compute_analytical_results(methods: Mapping[str, list[dict]], units: Sequence[dict], config: Mapping) -> dict:
    """从逐 unit 预测唯一地重算汇总、配对区间和辅助 McNemar。"""
    seeds = config["seeds"]
    expected = {"A", "B", *(f"{name}_seed_{seed}" for name in config["trained_methods"] for seed in seeds)}
    if set(methods) != expected:
        raise ValueError("saved method set mismatch")
    expected_units = {unit["unit_id"] for unit in units}
    if any({row["unit_id"] for row in rows} != expected_units or len(rows) != len(expected_units) for rows in methods.values()):
        raise ValueError("saved unit denominator mismatch")
    summaries = {name: summarize_rows(rows) for name, rows in methods.items()}
    seed_aggregates = {
        name: aggregate_seed_summaries(summaries, name, seeds)
        for name in config["trained_methods"]
    }
    reference = averaged_question_scores(methods, "D-no-text", seeds)
    comparisons = {
        "D-no-text-A": question_macro(methods["A"], "hit1@0.5"),
        "D-no-text-B": question_macro(methods["B"], "hit1@0.5"),
        "D-no-text-C-wide": averaged_question_scores(methods, "C-wide", seeds),
        "D-no-text-D": averaged_question_scores(methods, "D", seeds),
        "D-no-text-C": averaged_question_scores(methods, "C", seeds),
    }
    doc_of = {unit["query_id"]: unit["doc_id"] for unit in units}
    paired = joint_document_statistics(
        reference,
        comparisons,
        doc_of,
        primary=config["statistics"]["primary_comparisons"],
        iterations=config["statistics"]["bootstrap"]["iterations"],
        seed=config["statistics"]["bootstrap"]["seed"],
        family_alpha=config["statistics"]["multiple_comparisons"]["family_alpha"],
    )
    mcnemar = {}
    for comparison in comparisons:
        baseline_label = comparison.removeprefix("D-no-text-")
        mcnemar[comparison] = {}
        for seed in seeds:
            left = {row["unit_id"]: row["hit1@0.5"] for row in methods[f"D-no-text_seed_{seed}"]}
            baseline_method = baseline_label if baseline_label in {"A", "B"} else f"{baseline_label}_seed_{seed}"
            right = {row["unit_id"]: row["hit1@0.5"] for row in methods[baseline_method]}
            mcnemar[comparison][str(seed)] = mcnemar_exact(left, right)
    return {
        "schema": "route-v2-external-eval-v1",
        "role": "external_test_given_correct_page",
        "methods": summaries,
        "seed_aggregates": seed_aggregates,
        "paired": paired,
        "multiple_comparisons": config["statistics"]["multiple_comparisons"],
        "mcnemar_each_seed": mcnemar,
        "mcnemar_note": "unit-level auxiliary ignores within-document dependence",
        "external_minimum_difference": None,
    }


def validate_prediction_metrics(row: Mapping, ranked_boxes: Sequence[Sequence[float]], gold_boxes: Sequence[Sequence[float]], page_size: Sequence[float]) -> None:
    """从保存排名重新计算一个 unit 的全部 v2-loc-1 指标。"""
    expected = unit_metrics(ranked_boxes, gold_boxes, page_size)
    for key, value in expected.items():
        if key not in row or not math.isclose(float(row[key]), value, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"saved unit metric mismatch: {row['unit_id']} {key}")
