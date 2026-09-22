"""EXP-007 official-caliber recomputation (read-only, no re-encode).

Frozen inputs only:
  - EXP-001 page Top-K (runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet)
  - EXP-006 Top-1 picks per method (artifacts/baselines/mmdocir_1c/phase1c_picks.json)
  - processed gold/candidates (data/processed/mmdocir_evaluation/{region_labels,nodes}.parquet)

What this does:
  1. Verbatim-port MMDocIR/metric_eval.py: calculate_overlap_score + recall_layout.
  2. L1 page recall from frozen EXP-001 hits (document scope, metric_eval top_k_indices).
  3. L2 oracle Area Recall over ALL same-gold-page MinerU candidates (NOT Top-K constrained).
  4. L3 actual Area Recall for each frozen 1C method using its recorded Top-1 pick.
  5. union-clipped sensitivity alongside the verbatim official number (never mixed).

Bans: no vision re-encode, no training, no fusion/ subpackage, no train_fusion.py,
no evaluation-gold supervision. Old IoU numbers are copied as auxiliary only.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import polars as pl

# ---------------------------------------------------------------------------
# Verbatim port of C:/Users/WenJing/Documents/WorkTransfer/MMDocIR/metric_eval.py
# (calculate_overlap_score + recall_layout + top_k_indices semantics)
# ---------------------------------------------------------------------------


def top_k_indices(scores, k):  # noqa: ANN001, ANN202 - verbatim official semantics
    indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    if k <= len(scores):
        return [index for index, score in indexed_scores[:k]]
    return [index for index, score in indexed_scores]


def calculate_overlap_score(bbox1, bbox2):  # noqa: ANN001, ANN202 - verbatim official
    top1, left1, bottom1, right1 = bbox1
    top2, left2, bottom2, right2 = bbox2
    inter_top = max(top1, top2)
    inter_left = max(left1, left2)
    inter_bottom = min(bottom1, bottom2)
    inter_right = min(right1, right2)
    if inter_top < inter_bottom and inter_left < inter_right:
        return (inter_bottom - inter_top) * (inter_right - inter_left)
    return 0.0


def recall_layout(layout_topk, layout_indices, layout_mapping):  # noqa: ANN001, ANN202
    recall_area = 0
    for layout_id in layout_topk:
        _, page_id, x1, y1, x2, y2 = layout_indices[layout_id]
        for gt_layout in layout_mapping:
            if page_id == gt_layout["page"]:
                recall_area += calculate_overlap_score([x1, y1, x2, y2], gt_layout["bbox"])
    gt_area = 0
    for gt_layout in layout_mapping:
        top, left, bottom, right = gt_layout["bbox"]
        gt_area += (bottom - top) * (right - left)
    if gt_area == 0:
        return 0.0
    return recall_area / gt_area


def _ab(bbox):
    if isinstance(bbox, str):
        bbox = json.loads(bbox)
    return [float(v) for v in bbox]


def _union_area(rects):
    if not rects:
        return 0.0
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    total = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx = (xs[i] + xs[i + 1]) / 2.0
            cy = (ys[j] + ys[j + 1]) / 2.0
            for r in rects:
                if r[0] <= cx < r[2] and r[1] <= cy < r[3]:
                    total += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
                    break
    return total


def main() -> None:
    started = time.monotonic()
    root = Path(".")
    processed = root / "data" / "processed" / "mmdocir_evaluation"
    run_dir = root / "runs" / "retrieval" / "mmdocir_colpali" / "20260916_134144"
    picks_path = root / "artifacts" / "baselines" / "mmdocir_1c" / "phase1c_picks.json"
    out_dir = root / "artifacts" / "baselines" / "mmdocir_1c_official"
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = pl.read_parquet(processed / "region_labels.parquet").to_dicts()
    nodes = pl.read_parquet(processed / "nodes.parquet").to_dicts()
    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    picks_doc = json.loads(picks_path.read_text(encoding="utf-8"))
    picks = picks_doc["picks"]
    methods = picks_doc["meta"]["methods"]

    gold_by_q: dict[str, list[dict]] = defaultdict(list)
    for row in labels:
        gold_by_q[row["query_id"]].append({"page": row["page_id"], "bbox": _ab(row["bbox"])})

    node_box: dict[str, list[float]] = {}
    by_page: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    for row in nodes:
        box = _ab(row["bbox"])
        node_box[row["node_id"]] = box
        by_page[row["page_id"]].append((row["node_id"], box))

    # ---- L1: frozen EXP-001 page Top-K recall (document scope, official top_k order)
    hits_by_q: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
    for hit in hits:
        hits_by_q[hit["query_id"]].append((int(hit["rank"]), str(hit["page_id"]), float(hit["score"])))
    page_rank: dict[str, list[str]] = {}
    for qid, rows in hits_by_q.items():
        rows.sort(key=lambda r: (-r[2], r[0]))
        page_rank[qid] = [p for _, p, _ in rows]
    l1 = {}
    for k in (1, 5, 10):
        hit = 0
        for qid, golds in gold_by_q.items():
            gold_pages = {g["page"] for g in golds}
            if set(page_rank.get(qid, [])[:k]) & gold_pages:
                hit += 1
        l1[f"page_recall@{k}"] = round(hit / len(gold_by_q), 4)

    # ---- L2: oracle over ALL same-gold-page candidates (verbatim official + union-clipped)
    def oracle(qid: str, k: int) -> tuple[float, float]:
        golds = gold_by_q[qid]
        gt = sum((g["bbox"][2] - g["bbox"][0]) * (g["bbox"][3] - g["bbox"][1]) for g in golds)
        if gt <= 0:
            return (0.0, 0.0)
        seen: dict[str, list[float]] = {}
        for gold in golds:
            for nid, box in by_page.get(gold["page"], []):
                seen[nid] = box
        scored = [
            (sum(calculate_overlap_score(box, g["bbox"]) for g in golds) / gt, nid, box)
            for nid, box in seen.items()
        ]
        scored.sort(key=lambda r: (-r[0], r[1]))
        top = scored[:k]
        official = sum(s for s, _, _ in top)
        union = 0.0
        for gold in golds:
            clips = []
            for _, _, box in top:
                x1 = max(box[0], gold["bbox"][0])
                y1 = max(box[1], gold["bbox"][1])
                x2 = min(box[2], gold["bbox"][2])
                y2 = min(box[3], gold["bbox"][3])
                if x2 > x1 and y2 > y1:
                    clips.append([x1, y1, x2, y2])
            union += _union_area(clips)
        return (official, union / gt)

    l2_official: dict[str, float] = {}
    l2_union: dict[str, float] = {}
    for k in (1, 5, 10):
        off = [oracle(q, k)[0] for q in gold_by_q]
        uni = [oracle(q, k)[1] for q in gold_by_q]
        l2_official[f"oracle_area_recall@{k}_official"] = round(sum(off) / len(off), 4)
        l2_union[f"oracle_area_recall@{k}_union_clipped"] = round(sum(uni) / len(uni), 4)

    # ---- L2 aligned: same denominator as L3 (frozen EVAL1388 picks set), for a fair gap.
    # Picks are only defined for page-hit queries (1343 matched-A + strict 45 B); L2-full
    # stays the headline ceiling, L2-eval1388 is the gap-comparison denominator.
    eval_qids = sorted(picks)
    l2_eval1388_official: dict[str, float] = {}
    l2_eval1388_union: dict[str, float] = {}
    for k in (1, 5, 10):
        off = [oracle(q, k)[0] for q in eval_qids]
        uni = [oracle(q, k)[1] for q in eval_qids]
        l2_eval1388_official[f"oracle_area_recall@{k}_official"] = round(sum(off) / len(off), 4)
        l2_eval1388_union[f"oracle_area_recall@{k}_union_clipped"] = round(sum(uni) / len(uni), 4)

    # ---- L3: frozen 1C Top-1 picks scored with verbatim recall_layout
    # rebuild per-query candidate list deterministically (stable order by node_id)
    cand_list: dict[str, list[tuple[str, list[float]]]] = defaultdict(list)
    for qid, golds in gold_by_q.items():
        seen: dict[str, list[float]] = {}
        for gold in golds:
            for nid, box in by_page.get(gold["page"], []):
                seen[nid] = box
        cand_list[qid] = sorted(seen.items(), key=lambda r: r[0])

    l3_official: dict[str, dict] = {}
    l3_union: dict[str, dict] = {}
    for method in methods[:5]:  # fixed-candidate methods only; group boxes are self-drawn (None)
        off_vals: list[float] = []
        uni_vals: list[float] = []
        ge05 = 0
        for qid in eval_qids:
            golds = gold_by_q[qid]
            gt = sum((g["bbox"][2] - g["bbox"][0]) * (g["bbox"][3] - g["bbox"][1]) for g in golds)
            nid = picks[qid][method]
            if nid is None or gt <= 0:
                off_vals.append(0.0)
                uni_vals.append(0.0)
                continue
            box = node_box[nid]
            # page_id must be the node's own page; rebuild properly:
            pos = {n: i for i, (n, _) in enumerate(cand_list[qid])}
            node_page = next(p for p, rows in by_page.items() for n, _ in rows if n == nid)
            official = recall_layout(
                [pos[nid]],
                [(n, node_page if n == nid else "__other__", *b) for n, b in cand_list[qid]],
                golds,
            )
            union = 0.0
            for gold in golds:
                x1 = max(box[0], gold["bbox"][0])
                y1 = max(box[1], gold["bbox"][1])
                x2 = min(box[2], gold["bbox"][2])
                y2 = min(box[3], gold["bbox"][3])
                if x2 > x1 and y2 > y1:
                    union += (x2 - x1) * (y2 - y1)
            union /= gt
            off_vals.append(official)
            uni_vals.append(union)
            if official >= 0.5:
                ge05 += 1
        denom_eval = len(eval_qids)
        denom_full = len(gold_by_q)
        l3_official[method] = {
            "mean_eval1388_official@1": round(sum(off_vals) / denom_eval, 4),
            "mean_full1658_official@1": round(sum(off_vals) / denom_full, 4),
            "ge05_eval1388": ge05,
        }
        l3_union[method] = {
            "mean_eval1388_union@1": round(sum(uni_vals) / denom_eval, 4),
            "mean_full1658_union@1": round(sum(uni_vals) / denom_full, 4),
        }

    # ---- old IoU numbers copied as auxiliary (do NOT recompute, do NOT judge)
    old_1c = json.loads((root / "artifacts" / "baselines" / "mmdocir_1c" / "phase1c.json").read_text(encoding="utf-8"))
    old_1b = json.loads((root / "artifacts" / "diagnosis" / "mmdocir_evaluation" / "crosstab.json").read_text(encoding="utf-8"))

    result = {
        "meta": {
            "exp_id": "EXP-007",
            "date": "2026-09-19",
            "scope": "recompute-only; frozen EXP-001 pages + frozen EXP-006 picks; no re-encode; no training",
            "official_source": "C:/Users/WenJing/Documents/WorkTransfer/MMDocIR/metric_eval.py:calculate_overlap_score+recall_layout+top_k_indices (verbatim port)",
            "frozen_inputs": {
                "pages": "runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet",
                "picks": "artifacts/baselines/mmdocir_1c/phase1c_picks.json",
                "gold": "data/processed/mmdocir_evaluation/region_labels.parquet (1658 queries, 2638 rows)",
                "candidates": "data/processed/mmdocir_evaluation/nodes.parquet (170338 rows)",
            },
            "query_sets": {
                "full": 1658,
                "eval_picks": len(eval_qids),
                "note": "L2 over FULL1658; L3 Top-1 over frozen EVAL1388 picks, also reported with FULL1658 denominator",
            },
            "overlap_caveat": "official allows overlap double-count (can exceed 1); union-clipped reported separately, never mixed",
            "decision": "recompute-only; NO gate change; thresholds stay unfrozen; a1fbcc2 stays working proposal",
        },
        "L1_page_recall_frozen_EXP001": l1,
        "L2_oracle_full1658": {"official_verbatim": l2_official, "union_clipped_sensitivity": l2_union},
        "L2_oracle_eval1388_aligned": {"official_verbatim": l2_eval1388_official, "union_clipped_sensitivity": l2_eval1388_union,
            "note": "same 1388-query denominator as L3 (1343 matched-A + strict 45 B, page-hit only); use this row for the Oracle-minus-actual gap"},
        "L3_actual_top1_frozen_picks": {"official_verbatim": l3_official, "union_clipped_sensitivity": l3_union},
        "auxiliary_old_IoU_only": {
            "EXP-006_top1_accuracy_A_IoU05": old_1c["top1_accuracy_A"],
            "EXP-006_dissolution_B45_IoU05": old_1c["dissolution_B"],
            "EXP-005_ABCD_IoU05": old_1b,
            "note": "auxiliary only; not comparable to official Area Recall; not used for any gate decision",
        },
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    (out_dir / "exp007_official_recompute.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**l1, **l2_official, **l2_union}, ensure_ascii=False, indent=2))
    print(json.dumps(l3_official, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
