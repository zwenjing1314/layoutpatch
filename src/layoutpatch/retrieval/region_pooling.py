"""Fixed IoU/coverage region aggregation (PAPER_SPEC 7.4 baseline 3, batch 5, EXP-006).

What (beginner): same frozen patch scores as propagation.py, but the region score
normalizes by COVERAGE (how much of the region is covered by hot patches) instead
of IoU-mass. Intuition: a huge gold-missing box gets diluted under iou-weighting;
coverage-weighting asks "what fraction of this box is hot", which favors tight boxes.
No training, no new vision encodes.
"""

from __future__ import annotations

from layoutpatch.retrieval.propagation import _area, _inter_area, patch_boxes


def coverage_region_scores(
    patch_scores: list[float],
    regions: list[dict],
    mode: str = "coverage",
) -> list[float]:
    boxes = patch_boxes()
    scores: list[float] = []
    for reg in regions:
        terms = []
        reg_area = _area(reg["bbox_model"])
        for idx, pb in enumerate(boxes):
            inter = _inter_area(pb, reg["bbox_model"])
            if inter <= 0:
                continue
            if mode == "coverage":
                w = inter / reg_area if reg_area > 0 else 0.0
            elif mode == "iou_mass":
                union = _area(pb) + reg_area - inter
                w = inter / union if union > 0 else 0.0
            else:
                raise ValueError(f"unknown mode {mode}")
            terms.append((w, patch_scores[idx]))
        if not terms:
            scores.append(float("-inf"))
            continue
        scores.append(sum(w * s for w, s in terms))
    return scores
