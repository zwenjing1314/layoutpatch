"""Phase 1C no-train baselines (PAPER_SPEC 7.4, batch 5, EXP-006).

What (beginner):
- We do NOT train. We reuse FROZEN ColPali vectors (1031x128 per page: 1024 image
  patches + 7 prefix tokens) and ask: can rule-based region scoring pick the right
  box without learning?
- Three files, three ideas:
  - propagation.py: Snappy-style patch->region propagation. Patch scores come from
    a real query-vs-page MaxSim over cached ColPali vectors; region score =
    IoU-weighted pooling of patch scores (max/mean/iou three aggregations).
  - region_pooling.py: fixed IoU/coverage aggregation. Same patch scores, but the
    region score normalizes differently (coverage-weighted vs IoU-weighted).
  - region_grouping.py: dynamic saliency grouping. Take high-scoring patches
    (threshold eta + P25/P50/P75 sensitivity), group 4-neighbor connected patches,
    draw the bounding box of each group as a predicted box. NOT called RegionRAG.
- Measured on TWO sets (same frozen inputs, k=5, IoU>=0.5):
  - 1343 matched A (page-hit, gold box exists): Top-1 box-pick accuracy.
  - 45 B (page-hit, gold box missing): dissolution rate (expected ~0, negative result).

Hard constraints respected: 0 extra vision encodes (cache only), MaxSim interface
kept (query-side MaxSim over cached page vectors), query-independent page vectors.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch.nn.functional import normalize

from layoutpatch.layout.correspondence import GRID, MODEL_SIZE, clamp_bbox, scale_bbox_to_model
from layoutpatch.paths import artifacts_dir


def page_file(page_id: str) -> Path:
    return artifacts_dir() / "colpali" / "mmdocir_evaluation" / "vidore_colpali" / f"{page_id}.pt"


def load_page_vectors(page_id: str) -> torch.Tensor:
    payload = torch.load(page_file(page_id), map_location="cpu", weights_only=True)
    emb = payload["embedding"].float()
    return normalize(emb, dim=-1)


def load_query_vectors(run_dir: Path, query_text: str) -> torch.Tensor:
    raise NotImplementedError("query vectors are encoded per-document in run_phase1c.py")


def patch_scores_from_vectors(query_vecs: torch.Tensor, page_vecs: torch.Tensor) -> list[float]:
    """s_patch(j) = max_i Q_i . P_j over cached vectors (image patches only, skip 7 prefix)."""
    # cache layout is [7 prefix, 1024 patches] (prefix-first); asserted by callers.
    if page_vecs.shape[0] == GRID * GRID + 7:
        image_vecs = page_vecs[7:]
    elif page_vecs.shape[0] == GRID * GRID:
        image_vecs = page_vecs
    else:
        raise ValueError(f"unexpected page cache shape {tuple(page_vecs.shape)}")
    sims = query_vecs.float() @ image_vecs.T
    flat = sims.reshape(-1, image_vecs.shape[0]).amax(dim=0)
    scores = flat.tolist()
    assert len(scores) == GRID * GRID, f"patch score len {len(scores)} != 1024"
    return scores


def region_candidates(page_id: str, nodes_by_page: dict, page_size: list[float]) -> list[dict]:
    out = []
    for cand in nodes_by_page.get(page_id, []):
        scaled = clamp_bbox(scale_bbox_to_model([float(v) for v in cand["bbox"]], page_size))
        out.append({"node_id": cand["node_id"], "bbox_model": scaled, "bbox_orig": [float(v) for v in cand["bbox"]]})
    return out


def patch_boxes(grid: int = GRID, model_size: int = MODEL_SIZE) -> list[list[float]]:
    cell = model_size / grid
    boxes = []
    for idx in range(grid * grid):
        row, col = divmod(idx, grid)
        boxes.append([col * cell, row * cell, (col + 1) * cell, (row + 1) * cell])
    return boxes


def propagate_region_scores(
    patch_scores: list[float],
    regions: list[dict],
    aggregation: str = "iou",
) -> list[float]:
    """Snappy-style: region score from IoU-weighted patch scores.

    - max: max over overlapping patches of IoU*score (strong local evidence).
    - mean: mean over overlapping patches of IoU*score (robust to box size).
    - iou: sum(IoU*score)/sum(IoU) (Snappy rel(q,r) proper, size-normalized).
    """
    boxes = patch_boxes()
    scores = []
    for reg in regions:
        weights = []
        for idx, pb in enumerate(boxes):
            inter = _inter_area(pb, reg["bbox_model"])
            union = _area(pb) + _area(reg["bbox_model"]) - inter
            iou = inter / union if union > 0 else 0.0
            if iou > 0:
                weights.append((iou, patch_scores[idx]))
        if not weights:
            scores.append(float("-inf"))
            continue
        if aggregation == "max":
            scores.append(max(w * s for w, s in weights))
        elif aggregation == "mean":
            scores.append(sum(w * s for w, s in weights) / len(weights))
        elif aggregation == "iou":
            scores.append(sum(w * s for w, s in weights) / sum(w for w, _ in weights))
        else:
            raise ValueError(f"unknown aggregation {aggregation}")
    return scores


def _area(b: list[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter_area(a: list[float], b: list[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def top1_pick(scores: list[float]) -> int:
    best = max(range(len(scores)), key=lambda i: scores[i])
    return best
