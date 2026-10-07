"""只用合成预测验证EXP-015基线兼容性拒绝条件。"""
import copy
import importlib.util
from pathlib import Path

import pytest

from layoutpatch.evaluation.localization import unit_metrics

spec = importlib.util.spec_from_file_location("exp15_verify", Path(__file__).resolve().parents[2] / "scripts/verify_route_v2_exp2.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def fixture():
    u = {"unit_id": "q#p0", "query_id": "q", "doc_id": "doc", "page": 0, "role": "source_dev",
         "gold_boxes": [[0, 0, 10, 10]], "page_size": [100, 100]}
    cs = {("doc", 0): {1: {"bbox": [0, 0, 10, 10]}, 2: {"bbox": [50, 50, 60, 60]}}}
    metrics = unit_metrics([cs["doc", 0][i]["bbox"] for i in [1, 2]], u["gold_boxes"], u["page_size"])
    rows = [{"unit_id": "q#p0", "query_id": "q", "doc_id": "doc", "role": "source_dev", "method": m,
             "ranked_layout_ids": [1, 2], "ranked_scores": [1., 1.], **metrics}
            for m in ("A", "B", "C_seed_0", "C_seed_1", "C_seed_2")]
    return rows, [u], cs


def test_saved_predictions_require_same_candidates_units_and_tie_rule():
    rows, units, cs = fixture()
    assert len(verify.check_predictions(rows, units, cs)) == 5
    for field, value in (("query_id", "wrong"), ("ranked_layout_ids", [1, 3]), ("ranked_layout_ids", [2, 1]), ("hit1@0.5", 0.)):
        broken = copy.deepcopy(rows)
        broken[0][field] = value
        with pytest.raises(ValueError):
            verify.check_predictions(broken, units, cs)
    with pytest.raises(ValueError):
        verify.check_predictions(rows[:-1], units, cs)


def test_budget_mismatch_stops():
    baseline = {k: 1 for k in verify.SHARED}
    config = {**baseline, "trainable_parameters": 273410, "C_trainable_parameters": 66176}
    verify.check_budget(config, baseline)
    config["max_epochs"] = 31
    with pytest.raises(ValueError, match="max_epochs"):
        verify.check_budget(config, baseline)
