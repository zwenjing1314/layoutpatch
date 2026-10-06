"""Synthetic checks for route-v2 page-conditioned localization metrics."""

from __future__ import annotations

import pytest

from layoutpatch.evaluation.localization import (
    doc_bootstrap_diff,
    mcnemar_exact,
    question_macro,
    rank_candidates,
    union_intersection_area,
    unit_metrics,
)
from layoutpatch.evaluation.region_metrics import recall_layout

PAGE = [100.0, 100.0]


def test_union_and_intersection_are_exact_and_deduplicated():
    assert union_intersection_area([[0, 0, 10, 10], [5, 0, 15, 10]]) == pytest.approx(150)
    assert union_intersection_area([[0, 0, 10, 10]] * 3, [[5, 5, 20, 20]]) == pytest.approx(25)
    assert union_intersection_area([[0, 0, 0, 10]]) == 0.0


def test_hits_random_oracle_and_size_on_one_unit():
    gold = [[0, 0, 10, 10]]
    ranked = [[0, 0, 100, 100], [0, 0, 10, 10], [50, 50, 60, 60]]
    m = unit_metrics(ranked, gold, PAGE)
    assert m["top1_iou"] == pytest.approx(0.01)
    assert m["hit1@0.5"] == 0.0 and m["oracle@0.5"] == 1.0
    assert m["random1@0.5"] == pytest.approx(1 / 3)
    assert m["cov@1"] == pytest.approx(1.0) and m["area_sum@1"] == pytest.approx(1.0)
    assert m["top1_area_frac"] == pytest.approx(1.0) and m["top1_to_gold_area"] == pytest.approx(100)
    assert m["gold_recall@3@0.5"] == 1.0


def test_dedup_coverage_differs_from_summed_area_for_overlapping_predictions():
    gold = [[0, 0, 10, 10]]
    ranked = [[0, 0, 10, 10], [0, 0, 10, 10]]
    m = unit_metrics(ranked, gold, PAGE)
    assert m["cov@3"] == pytest.approx(1.0)
    assert m["area_sum@3"] == pytest.approx(2.0)


def test_area_sum_matches_official_recall_layout_within_one_page():
    gold = [[10, 10, 30, 30], [40, 40, 60, 50]]
    ranked = [[0, 0, 20, 20], [35, 35, 70, 70], [10, 10, 30, 30]]
    indices = [("doc", 0, *box) for box in ranked]
    mapping = [{"page": 0, "bbox": box} for box in gold]
    for k in (1, 3):
        official = recall_layout(list(range(k)), indices, mapping)
        assert unit_metrics(ranked, gold, PAGE)[f"area_sum@{k}"] == pytest.approx(official)


def test_empty_candidates_score_zero_and_are_flagged():
    m = unit_metrics([], [[0, 0, 10, 10]], PAGE)
    assert m["empty"] == 1.0 and m["hit1@0.25"] == 0.0 and m["cov@5"] == 0.0
    with pytest.raises(ValueError):
        unit_metrics([[0, 0, 1, 1]], [], PAGE)


def test_ranking_ties_and_nonfinite_break_by_layout_id():
    assert rank_candidates([1.0, 1.0, float("-inf"), 2.0], [7, 3, 0, 9]) == [3, 1, 0, 2]


def test_question_macro_and_paired_statistics():
    rows = [
        {"query_id": "q1", "hit": 1.0},
        {"query_id": "q1", "hit": 0.0},
        {"query_id": "q2", "hit": 1.0},
    ]
    assert question_macro(rows, "hit") == {"q1": 0.5, "q2": 1.0}
    a = {"q1": 1.0, "q2": 1.0, "q3": 0.0, "q4": 1.0}
    b = {"q1": 0.0, "q2": 1.0, "q3": 0.0, "q4": 0.0}
    docs = {"q1": "d1", "q2": "d1", "q3": "d2", "q4": "d3"}
    boot = doc_bootstrap_diff(a, b, docs, iterations=500, seed=3)
    assert boot["mean_diff"] == pytest.approx(0.5)
    assert boot["ci95_low"] <= 0.5 <= boot["ci95_high"]
    assert boot["documents"] == 3
    test = mcnemar_exact(a, b)
    assert (test["a_only"], test["b_only"]) == (2.0, 0.0)
    assert test["p_value"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        doc_bootstrap_diff(a, {"q1": 0.0}, docs)
