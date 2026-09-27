"""Phase 2-R linear box scorer. Confirmed design, not a training license.

Features, in this order only:
  0 frozen ColPali patch score pooled with fixed:iou_mass
  1 box area
  2 box area / page area
  3 center x / page width
  4 center y / page height
  5 frozen BAAI/bge-m3 query-box dot product (0 if text is empty)

K=4 is training-only. Scoring always ranks every candidate on the given page.
Evaluation gold boxes and coverage y(c) are not inputs.
"""

from __future__ import annotations

import torch
from torch import nn

from layoutpatch.evaluation.region_metrics import recall_layout
from layoutpatch.retrieval.region_pooling import coverage_region_scores

FEATURE_DIM = 6
TRAIN_K = 4
BATCH_SIZE = 32
EARLY_STOP_ROUNDS = 2


def geometry(bbox: list[float], page_w: float, page_h: float) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    page_area = page_w * page_h
    rel = area / page_area if page_area > 0 else 0.0
    cx = ((x1 + x2) / 2.0) / page_w if page_w > 0 else 0.0
    cy = ((y1 + y2) / 2.0) / page_h if page_h > 0 else 0.0
    return area, rel, cx, cy


def text_similarity(query_vec: list[float] | None, box_vec: list[float] | None) -> float:
    if not query_vec or not box_vec:
        return 0.0
    return float(sum(a * b for a, b in zip(query_vec, box_vec, strict=True)))


def build_features(
    patch_scores: list[float],
    boxes: list[dict],
    page_w: float,
    page_h: float,
    query_vec: list[float] | None,
) -> torch.Tensor:
    """One row per candidate. Empty text stays, similarity is 0. No gold columns."""
    regions = [{"bbox_model": box["bbox_model"]} for box in boxes]
    pooled = coverage_region_scores(patch_scores, regions, "iou_mass") if boxes else []
    rows = []
    for box, patch_score in zip(boxes, pooled, strict=True):
        area, rel, cx, cy = geometry(box["bbox"], page_w, page_h)
        sim = text_similarity(query_vec, box.get("text_vec"))
        score = 0.0 if patch_score == float("-inf") else float(patch_score)
        rows.append([score, area, rel, cx, cy, sim])
    if not rows:
        return torch.zeros((0, FEATURE_DIM))
    return torch.tensor(rows, dtype=torch.float32)


class BoxRanker(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.linear = nn.Linear(FEATURE_DIM, 1)

    def score(self, features: torch.Tensor) -> torch.Tensor:
        if features.numel() == 0:
            return features.new_zeros((0,))
        return self.linear(features).squeeze(-1)


def page_pair_loss(
    ranker: BoxRanker,
    pos_features: torch.Tensor,
    pos_areas: torch.Tensor,
    neg_features: torch.Tensor,
    neg_areas: torch.Tensor,
    k: int = TRAIN_K,
) -> torch.Tensor | None:
    """Page-level weak supervision. Area only selects TopK boxes, it is not y(c)."""
    if pos_features.numel() == 0 and neg_features.numel() == 0:
        return None
    pos = _topk_area_scores(ranker, pos_features, pos_areas, k)
    neg = _topk_area_scores(ranker, neg_features, neg_areas, k)
    if pos.numel() == 0 or neg.numel() == 0:
        return None
    joined = torch.cat([pos, neg])
    log_z = torch.logsumexp(joined, dim=0)
    log_pos = torch.logsumexp(pos, dim=0)
    return -(log_pos - log_z)


def _topk_area_scores(ranker: BoxRanker, features: torch.Tensor, areas: torch.Tensor, k: int) -> torch.Tensor:
    if features.numel() == 0:
        return features.new_zeros((0,))
    n = min(k, features.shape[0])
    chosen = torch.topk(areas, k=n, largest=True).indices
    chosen = torch.sort(chosen).values  # stable tie-break by index
    return ranker.score(features.index_select(0, chosen))


def rank_all(ranker: BoxRanker, features: torch.Tensor) -> list[int]:
    """Inference order for every candidate on the gold page. K is not applied."""
    if features.numel() == 0:
        return []
    scores = ranker.score(features).detach()
    order = sorted(range(scores.shape[0]), key=lambda i: (-float(scores[i]), i))
    return order


def early_stop_hit(pos_score: float, neg_score: float) -> bool:
    return pos_score > neg_score


def area_at_k(layout_indices, layout_mapping, scores: list[float], k: int) -> float:
    """Official recall_layout on one gold page. Does not define a new metric."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    return float(recall_layout(order[:k], layout_indices, layout_mapping))
