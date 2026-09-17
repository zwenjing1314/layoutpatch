"""Text Recall/F1 dual track on stored 1C Top-1 picks (PAPER_SPEC 8 / THESIS_SPEC 8.3, EXP-007 addendum).

What (beginner):
- IoU asks "did the method's Top-1 box land right"; Text asks "did that SAME box
  contain the right words". Both tracks score the IDENTICAL stored pick from
  phase1c_picks.json (no recompute, no oracle substitution).
- Tokenization (frozen, THESIS_SPEC 8.3): Chinese by char, English by word,
  lowercased, whitespace stripped, then SET-deduped (recall/precision over
  token SETS, frequencies ignored). Gold text = concat of nodes with IoU>=0.5
  with the gold box; B class gold text empty -> Text undefined -> excluded (NaN),
  not zeroed. Pred text = stored pick's node text.
- Anti-gaming: pred box area > 50% page area -> Text zeroed; per-method
  zeroed counts reported.
- Group P25/P50/P75: NOT scored (self-drawn boxes have no node text;
  Text undefined by construction) -> reported as not-run, not fabricated.
- iou_miss_text_ge08: reported under BOTH calibers; current gold-text
  definition makes B rows NaN so the group is EMPTY BY CONSTRUCTION
  (not an empirical zero); retest with lifted page constraint confirms n=0.
- Output: artifacts/diagnosis/mmdocir_evaluation/text_dual.json with per-method
  means on 1343A + IoU-miss-but-Text>=0.8 group (needs >=20 for human check).

Usage: uv run python scripts/run_text_dual.py --k 5 --iou 0.5
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import polars as pl

from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.paths import artifacts_dir, data_root


def tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    toks = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", lowered)
    return [t for t in toks if t.strip()]


def text_scores(pred: str, gold: str) -> tuple[float, float]:
    pt, gt = set(tokenize(pred)), set(tokenize(gold))
    if not gt:
        return (float("nan"), float("nan"))
    if not pt:
        return (0.0, 0.0)
    inter = len(pt & gt)
    rec = inter / len(gt)
    prec = inter / len(pt)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return (rec, f1)


def main(k: int = 5, iou: float = 0.5) -> None:
    processed = data_root() / "processed" / "mmdocir_evaluation"
    run_dir = Path("runs/retrieval/mmdocir_colpali/20260916_134144")
    out_dir = artifacts_dir() / "diagnosis" / "mmdocir_evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    phase1c = json.loads((artifacts_dir() / "baselines" / "mmdocir_1c" / "phase1c.json").read_text(encoding="utf-8"))
    assert phase1c["meta"]["k"] == k and phase1c["meta"]["iou_threshold"] == iou
    picks_doc = json.loads((artifacts_dir() / "baselines" / "mmdocir_1c" / "phase1c_picks.json").read_text(encoding="utf-8"))
    picks: dict[str, dict[str, str | None]] = picks_doc["picks"]

    labels = pl.read_parquet(processed / "region_labels.parquet").to_dicts()
    gold_by_query: dict[str, list[dict]] = {}
    for row in labels:
        gold_by_query.setdefault(row["query_id"], []).append(row)
    nodes_rows = pl.read_parquet(processed / "nodes.parquet").to_dicts()
    nodes_by_page: dict[str, list[dict]] = {}
    node_by_id: dict[str, dict] = {}
    for row in nodes_rows:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        rec = {"node_id": row["node_id"], "text": row.get("text", "") or "", "bbox": [float(v) for v in bbox]}
        nodes_by_page.setdefault(row["page_id"], []).append(rec)
        node_by_id[row["node_id"]] = rec
    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    top_pages: dict[str, list[str]] = {}
    for hit in hits:
        if hit["rank"] <= k:
            top_pages.setdefault(hit["query_id"], []).append(hit["page_id"])

    methods = ["snappy:max", "snappy:mean", "snappy:iou", "fixed:coverage", "fixed:iou_mass"]
    per_method: dict[str, list[tuple[float, float]]] = {m: [] for m in methods}
    oracle_scores: list[tuple[float, float]] = []
    zeroed_total = 0
    zeroed_by_method: dict[str, int] = {m: 0 for m in methods}
    nan_by_method: dict[str, int] = {m: 0 for m in methods}
    high_text_miss: list[dict] = []
    high_text_miss_lifted: list[dict] = []
    n_scored = 0
    for qid, mpicks in picks.items():
        pages = set(top_pages.get(qid, []))
        golds = gold_by_query[qid]
        gold_pages = {g["page_id"] for g in golds}
        if not (pages & gold_pages):
            continue
        n_scored += 1
        rank_of = {p: r for r, p in enumerate(top_pages.get(qid, []))}
        gold_page = min((g["page_id"] for g in golds if g["page_id"] in pages), key=lambda p: rank_of[p])
        gold_rows = [g for g in golds if g["page_id"] == gold_page]
        gb = [float(v) for v in gold_rows[0]["bbox"]]
        ps = [float(v) for v in (gold_rows[0].get("page_size") or [1.0, 1.0])]
        page_area = max(1.0, ps[0] * ps[1])
        cands = nodes_by_page.get(gold_page, [])
        gold_text = " ".join(c["text"] for c in cands if bbox_iou(c["bbox"], gb) >= iou)
        iou_hit_oracle = any(bbox_iou(c["bbox"], gb) >= iou for c in cands)
        oracle_cand = max(cands, key=lambda c: bbox_iou(c["bbox"], gb)) if cands else None
        oracle_text = oracle_cand["text"] if oracle_cand else ""
        oracle_area = 0.0
        if oracle_cand:
            b = oracle_cand["bbox"]
            oracle_area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        oracle_rec, oracle_f1 = text_scores(oracle_text, gold_text)
        if oracle_area > 0.5 * page_area:
            oracle_rec, oracle_f1 = 0.0, 0.0
        oracle_scores.append((oracle_rec, oracle_f1))
        for m in methods:
            nid = mpicks.get(m)
            node = node_by_id.get(nid) if nid else None
            pred_text = node["text"] if node else ""
            pred_area = 0.0
            if node:
                b = node["bbox"]
                pred_area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            rec, f1 = text_scores(pred_text, gold_text)
            if math.isnan(rec):
                nan_by_method[m] += 1
            if pred_area > 0.5 * page_area:
                rec, f1 = 0.0, 0.0
                zeroed_total += 1
                zeroed_by_method[m] += 1
            per_method[m].append((rec, f1))
            if m == "fixed:iou_mass" and not iou_hit_oracle and rec >= 0.8 and not math.isnan(rec):
                high_text_miss.append({"query_id": qid, "text_recall": round(rec, 4)})
        # lifted caliber: drop the page-hit constraint -> gold text = concat of
        # IoU>=0.5 nodes over ALL gold pages of this query (B rows still NaN).
        gold_pages_all = {g["page_id"] for g in golds}
        lifted_text = " ".join(
            c["text"]
            for pid in gold_pages_all
            for c in nodes_by_page.get(pid, [])
            if bbox_iou(c["bbox"], [float(v) for v in next(g for g in golds if g["page_id"] == pid)["bbox"]]) >= iou
        )
        lifted_rec, _ = text_scores(node_by_id.get(mpicks.get("fixed:iou_mass") or "", {"text": ""})["text"], lifted_text)
        if not iou_hit_oracle and lifted_rec >= 0.8 and not math.isnan(lifted_rec):
            high_text_miss_lifted.append({"query_id": qid, "text_recall": round(lifted_rec, 4)})

    def mean(xs: list[float]) -> float:
        vs = [x for x in xs if not (isinstance(x, float) and math.isnan(x))]
        return sum(vs) / len(vs) if vs else float("nan")

    def counts(vs: list[tuple[float, float]]) -> dict[str, int]:
        n_nan = sum(1 for r, _ in vs if math.isnan(r))
        return {"n_total": len(vs), "n_nan": n_nan, "n_valid": len(vs) - n_nan}

    result = {
        "meta": {"k": k, "iou": iou, "scope": "SAME stored Top-1 picks as phase1c.json (per-method) + oracle best-IoU pick upper bound; gold text = concat IoU>=0.5 nodes; B gold-empty excluded (NaN)",
                 "tokenization": "Chinese by char, English by word, lowercased, whitespace stripped, SET-deduped (THESIS_SPEC 8.3)",
                 "antigaming": "pred box area > 50% page area -> Text zeroed (per-method counts)",
                 "group_text": "not-run (self-drawn boxes carry no node text; Text undefined by construction)",
                 "encoding": "utf-8"},
        "n_scored": n_scored,
        "denominator": {m: counts(vs) for m, vs in per_method.items()},
        "oracle_text_upper_bound": {"text_recall_mean": mean([r for r, _ in oracle_scores]), "text_f1_mean": mean([f for _, f in oracle_scores])},
        "per_method_text": {
            m: {"text_recall_mean": mean([r for r, _ in vs]), "text_f1_mean": mean([f for _, f in vs])}
            for m, vs in per_method.items()
        },
        "oversize_zeroed_cells": zeroed_total,
        "oversize_zeroed_by_method": dict(zeroed_by_method),
        "iou_miss_text_ge08": {"n": len(high_text_miss), "sample": high_text_miss[:30],
                               "verdict": "condition-not-met" if len(high_text_miss) < 20 else "ready-for-review",
                               "note": "IoU-miss-but-Text-ge0.8 needs >=20 cases for human review; current n=0 EMPTY BY CONSTRUCTION (B gold-text NaN), not an empirical zero"},
        "iou_miss_text_ge08_lifted": {"n": len(high_text_miss_lifted), "sample": high_text_miss_lifted[:30],
                                      "verdict": "condition-not-met" if len(high_text_miss_lifted) < 20 else "ready-for-review",
                                      "note": "retest with page-hit constraint lifted (gold text over ALL gold pages); still n=0 EMPTY BY CONSTRUCTION (B gold-text NaN)"},
    }
    (out_dir / "text_dual.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--iou", type=float, default=0.5)
    ns = parser.parse_args()
    main(k=ns.k, iou=ns.iou)
