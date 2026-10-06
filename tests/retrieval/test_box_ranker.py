"""Unit tests for the confirmed Phase 2-R scorer. No training run."""

from __future__ import annotations

import pytest
import torch

from layoutpatch.layout.correspondence import GRID
from layoutpatch.retrieval.rerank.box_ranker import (
    FEATURE_DIM,
    TRAIN_K,
    BoxRanker,
    area_at_k,
    build_features,
    early_stop_hit,
    page_pair_loss,
    rank_all,
    text_similarity,
)


def _box(area_bbox: list[float]) -> dict:
    return {"bbox": area_bbox, "bbox_model": [0.0, 0.0, 14.0, 14.0], "text_vec": [1.0, 0.0]}


def test_feature_dim_and_empty_text_is_zero():
    patches = [0.0] * (GRID * GRID)
    patches[0] = 3.0
    boxes = [_box([0.0, 0.0, 10.0, 10.0])]
    boxes[0]["text_vec"] = None
    feats = build_features(patches, boxes, page_w=100.0, page_h=100.0, query_vec=[1.0, 0.0])
    assert feats.shape == (1, FEATURE_DIM)
    assert float(feats[0, 5]) == 0.0
    assert text_similarity(None, [1.0]) == 0.0


def test_loss_uses_page_pair_not_coverage_label():
    ranker = BoxRanker()
    pos = torch.tensor([[1.0, 10.0, 0.1, 0.2, 0.2, 0.0], [0.0, 1.0, 0.01, 0.1, 0.1, 0.0]])
    neg = torch.tensor([[0.0, 9.0, 0.1, 0.5, 0.5, 0.0]])
    loss = page_pair_loss(ranker, pos, pos[:, 1], neg, neg[:, 1], k=TRAIN_K)
    assert loss is not None
    assert loss.ndim == 0
    assert page_pair_loss(ranker, pos[:0], pos[:0, 1], neg[:0], neg[:0, 1]) is None


def test_rank_all_does_not_truncate_to_k():
    ranker = BoxRanker()
    feats = torch.zeros((6, FEATURE_DIM))
    order = rank_all(ranker, feats)
    assert len(order) == 6
    assert set(order) == set(range(6))


def test_area_at_k_calls_official_recall_layout():
    # layout_indices rows are (doc, page, x1, y1, x2, y2); gold bbox is [x1, y1, x2, y2].
    indices = [(0, 1, 0.0, 0.0, 10.0, 10.0), (0, 1, 20.0, 20.0, 30.0, 30.0)]
    gold = [{"page": 1, "bbox": [0.0, 0.0, 10.0, 10.0]}]
    assert area_at_k(indices, gold, [0.1, 5.0], k=1) == 0.0
    assert area_at_k(indices, gold, [5.0, 0.1], k=1) == 1.0


def test_legacy_load_pool_rejects_test_eval(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "train_phase2r.py"
    spec = importlib.util.spec_from_file_location("train_phase2r_guard", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    forbidden = tmp_path / "test_eval_ids.jsonl"
    monkeypatch.setattr(mod, "TEST_EVAL", forbidden)
    # The legacy loader must reject this path before trying to open it.
    with pytest.raises(RuntimeError, match="test_eval scores are forbidden"):
        mod.load_pool(forbidden)
    allowed = tmp_path / "train_fit_ids.jsonl"
    allowed.write_text(
        '{"domain": "ArxivQA", "line_index": 7}\n'
        '{"domain": "DUDE", "line_index": 8}\n',
        encoding="utf-8",
    )
    assert mod.load_pool(allowed) == {7}


def test_page_pair_loss_rejects_coverage_label():
    features = torch.zeros((1, FEATURE_DIM))
    areas = torch.ones(1)
    with pytest.raises(TypeError, match="y_c"):
        page_pair_loss(BoxRanker(), features, areas, features, areas, y_c=0.3)


def test_early_stop_is_page_score_only():
    assert early_stop_hit(1.0, 0.0)
    assert not early_stop_hit(0.0, 0.0)
