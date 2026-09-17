"""Dynamic saliency grouping (PAPER_SPEC 7.4 baseline 4, batch 5, EXP-006).

What (beginner): instead of scoring the fixed official boxes, we let HOT patches
vote. Patches with score >= eta become "salient"; 4-neighbor connected salient
patches form groups; each group's bounding box is a predicted box. The pick is the
group whose box best overlaps... no: at test time we have no gold, so the pick is
the group with the highest mean patch score. Gold is used ONLY for scoring.
Threshold eta grid: P25/P50/P75 of the page's patch-score distribution (recorded).

NOT called RegionRAG reproduction (rule): RegionRAG trains region supervision and
crops group boxes for generation input; we do neither (no training, no crop, boxes
only scored, P_fused untouched).
"""

from __future__ import annotations

from layoutpatch.retrieval.propagation import patch_boxes


def salient_groups(patch_scores: list[float], eta: float, grid: int = 32) -> list[dict]:
    hot = {i for i, s in enumerate(patch_scores) if s >= eta}
    seen: set[int] = set()
    groups: list[dict] = []
    for seed in sorted(hot):
        if seed in seen:
            continue
        stack = [seed]
        comp: set[int] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.add(cur)
            r, c = divmod(cur, grid)
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < grid and 0 <= nc < grid:
                    nxt = nr * grid + nc
                    if nxt in hot and nxt not in seen:
                        stack.append(nxt)
        boxes = patch_boxes(grid)
        xs1 = [boxes[i][0] for i in comp]
        ys1 = [boxes[i][1] for i in comp]
        xs2 = [boxes[i][2] for i in comp]
        ys2 = [boxes[i][3] for i in comp]
        mean_s = sum(patch_scores[i] for i in comp) / len(comp)
        groups.append({"bbox_model": [min(xs1), min(ys1), max(xs2), max(ys2)], "mean_score": mean_s, "size": len(comp)})
    groups.sort(key=lambda g: g["mean_score"], reverse=True)
    return groups
