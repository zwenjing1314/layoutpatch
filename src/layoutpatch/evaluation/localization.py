"""Route-v2 page-conditioned localization metrics (definition: PAPER_SPEC section 8.1).

Unit = (query, gold page). A method ranks that page's fixed parsed candidates; all
boxes share the page frame. Questions are macro-averaged over their units, then over
questions. Empty candidate lists score zero and are counted, never dropped. The legacy
summed Area@K (``recall_layout``) is reported separately under its own name.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.layout.correspondence import intersection_area

IOU_THRESHOLDS = (0.25, 0.5, 0.7)
TOP_K = (1, 3, 5)


def _area(box: Sequence[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _cover(boxes: Sequence[Sequence[float]], xs: list[float], ys: list[float]) -> list[list[bool]]:
    grid = [[False] * (len(ys) - 1) for _ in range(len(xs) - 1)]
    for box in boxes:
        for i in range(len(xs) - 1):
            if box[0] <= xs[i] and xs[i + 1] <= box[2]:
                for j in range(len(ys) - 1):
                    if box[1] <= ys[j] and ys[j + 1] <= box[3]:
                        grid[i][j] = True
    return grid


def union_intersection_area(
    left: Sequence[Sequence[float]], right: Sequence[Sequence[float]] | None = None
) -> float:
    """Exact area of union(left) (∩ union(right) when given) by coordinate compression."""
    boxes = [b for b in left if _area(b) > 0] + [b for b in (right or []) if _area(b) > 0]
    if not boxes:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    ys = sorted({v for b in boxes for v in (b[1], b[3])})
    first = _cover([b for b in left if _area(b) > 0], xs, ys)
    second = _cover([b for b in right if _area(b) > 0], xs, ys) if right is not None else None
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if first[i][j] and (second is None or second[i][j]):
                total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return total


def rank_candidates(scores: Sequence[float], layout_ids: Sequence[int]) -> list[int]:
    """Positions sorted by score desc; ties and non-finite scores break by layout_id asc."""
    keyed = [
        (s if math.isfinite(s) else -math.inf, lid, i)
        for i, (s, lid) in enumerate(zip(scores, layout_ids, strict=True))
    ]
    return [i for _, _, i in sorted(keyed, key=lambda t: (-t[0], t[1]))]


def unit_metrics(
    ranked_boxes: Sequence[Sequence[float]],
    gold_boxes: Sequence[Sequence[float]],
    page_size: Sequence[float],
) -> dict[str, float]:
    """All route-v2 unit metrics; ``ranked_boxes`` is the full ranked candidate list."""
    if not gold_boxes:
        raise ValueError("a unit needs at least one gold box")
    n = len(ranked_boxes)
    best = [max(bbox_iou(c, g) for g in gold_boxes) for c in ranked_boxes]
    gold_union = union_intersection_area(gold_boxes)
    page_area = float(page_size[0]) * float(page_size[1])
    out: dict[str, float] = {"empty": float(n == 0), "candidates": float(n)}
    out["top1_iou"] = best[0] if n else 0.0
    out["oracle_iou"] = max(best, default=0.0)
    for t in IOU_THRESHOLDS:
        tag = f"{t:.2f}".rstrip("0").rstrip(".")
        out[f"hit1@{tag}"] = float(n > 0 and best[0] >= t)
        out[f"random1@{tag}"] = sum(b >= t for b in best) / n if n else 0.0
        out[f"oracle@{tag}"] = float(any(b >= t for b in best))
    for k in TOP_K:
        top = list(ranked_boxes[:k])
        covered = union_intersection_area(top, gold_boxes)
        out[f"cov@{k}"] = covered / gold_union if gold_union > 0 else 0.0
        summed = sum(intersection_area(list(p), list(g)) for p in top for g in gold_boxes)
        gold_sum = sum(_area(g) for g in gold_boxes)
        out[f"area_sum@{k}"] = summed / gold_sum if gold_sum > 0 else 0.0
        out[f"gold_recall@{k}@0.5"] = _greedy_recall(top, gold_boxes, 0.5)
    out["top1_area_frac"] = _area(ranked_boxes[0]) / page_area if n and page_area > 0 else 0.0
    out["top1_to_gold_area"] = _area(ranked_boxes[0]) / gold_union if n and gold_union > 0 else 0.0
    return out


def _greedy_recall(pred: Sequence[Sequence[float]], gold: Sequence[Sequence[float]], t: float) -> float:
    pairs = sorted(
        ((bbox_iou(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gold)),
        key=lambda x: (-x[0], x[1], x[2]),
    )
    used_p, used_g = set(), set()
    for iou, i, j in pairs:
        if iou < t:
            break
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
    return len(used_g) / len(gold)


def question_macro(unit_rows: Sequence[Mapping[str, object]], key: str) -> dict[str, float]:
    """Mean of ``key`` per query over its units; rows need ``query_id`` and ``key``."""
    grouped: dict[str, list[float]] = {}
    for row in unit_rows:
        grouped.setdefault(str(row["query_id"]), []).append(float(row[key]))  # type: ignore[arg-type]
    return {q: sum(v) / len(v) for q, v in grouped.items()}


def doc_bootstrap_diff(
    a: Mapping[str, float],
    b: Mapping[str, float],
    doc_of: Mapping[str, str],
    *,
    iterations: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    """Paired mean(a-b) over queries with a 95% CI from resampling whole documents."""
    if set(a) != set(b):
        raise ValueError("paired comparison needs identical query sets")
    by_doc: dict[str, list[float]] = {}
    for q in sorted(a):
        by_doc.setdefault(doc_of[q], []).append(a[q] - b[q])
    docs = sorted(by_doc)
    rng = random.Random(seed)
    stats = []
    for _ in range(iterations):
        diffs = [d for doc in (rng.choice(docs) for _ in docs) for d in by_doc[doc]]
        stats.append(sum(diffs) / len(diffs))
    stats.sort()
    mean = sum(a[q] - b[q] for q in a) / len(a)
    return {
        "mean_diff": mean,
        "ci95_low": stats[int(0.025 * iterations)],
        "ci95_high": stats[min(iterations - 1, int(0.975 * iterations))],
        "documents": float(len(docs)),
        "queries": float(len(a)),
    }


def mcnemar_exact(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, float]:
    """Two-sided exact McNemar on binary outcomes keyed by unit (auxiliary; ignores clustering)."""
    if set(a) != set(b):
        raise ValueError("paired comparison needs identical query sets")
    a_only = sum(1 for q in a if a[q] >= 0.5 > b[q])
    b_only = sum(1 for q in a if b[q] >= 0.5 > a[q])
    n = a_only + b_only
    tail = sum(math.comb(n, i) for i in range(min(a_only, b_only) + 1)) / 2**n if n else 1.0
    return {"a_only": float(a_only), "b_only": float(b_only), "p_value": min(1.0, 2 * tail)}
