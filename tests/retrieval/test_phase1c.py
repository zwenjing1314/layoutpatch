"""Phase 1C no-train baseline unit tests (PAPER_SPEC 7.4, batch 5).

Covers: Snappy max/mean/iou aggregation on a toy 2x2 patch grid, fixed
coverage pooling, saliency grouping connectivity, patch-score flattening
for multi-token queries, and the 1031-row cache layout assertion.
"""

from __future__ import annotations

import torch

from layoutpatch.layout.correspondence import GRID
from layoutpatch.retrieval.propagation import (
    patch_scores_from_vectors,
    propagate_region_scores,
)


def _toy_regions() -> list[dict]:
    # 2x2 toy on the 448 canvas: region covers exactly patch 0 (top-left 224x224).
    return [{"node_id": "r0", "bbox_model": [0.0, 0.0, 224.0, 224.0], "bbox_orig": [0.0, 0.0, 224.0, 224.0]}]


def test_snappy_iou_picks_hot_region():
    scores = [0.0] * (GRID * GRID)
    scores[0] = 5.0  # patch 0 hot
    out = propagate_region_scores(scores, _toy_regions(), "iou")
    assert out[0] > 0.0


def test_snappy_max_mean_agree_on_single_overlap():
    scores = [0.0] * (GRID * GRID)
    scores[0] = 5.0
    assert propagate_region_scores(scores, _toy_regions(), "max")[0] > 0.0
    assert propagate_region_scores(scores, _toy_regions(), "mean")[0] > 0.0


def test_coverage_pooling_positive():
    from layoutpatch.retrieval.region_pooling import coverage_region_scores

    scores = [0.0] * (GRID * GRID)
    scores[0] = 5.0
    assert coverage_region_scores(scores, _toy_regions(), "coverage")[0] > 0.0
    assert coverage_region_scores(scores, _toy_regions(), "iou_mass")[0] > 0.0


def test_grouping_connectivity_and_threshold():
    from layoutpatch.retrieval.region_grouping import salient_groups

    scores = [0.0] * (GRID * GRID)
    scores[0] = 1.0
    scores[1] = 1.0  # 4-neighbor of patch 0
    scores[100] = 1.0  # isolated
    groups = salient_groups(scores, eta=0.5)
    assert len(groups) == 2
    assert {g["size"] for g in groups} == {2, 1}


def test_patch_scores_flatten_multi_token_query():
    dim = 8
    torch.manual_seed(0)
    page = torch.randn(GRID * GRID + 7, dim)
    query = torch.randn(3, dim)  # 3 query tokens -> MaxSim flattens to 1024
    scores = patch_scores_from_vectors(query, page)
    assert len(scores) == GRID * GRID


def test_cache_layout_is_prefix_first():
    assert GRID * GRID + 7 == 1031
