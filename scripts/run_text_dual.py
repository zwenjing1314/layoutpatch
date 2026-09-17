"""Text Recall/F1 dual track on stored 1C Top-1 picks (PAPER_SPEC 8 / THESIS_SPEC 8.3, EXP-007 addendum).

What (beginner):
- IoU asks "did the method's Top-1 box land right"; Text asks "did that SAME box
  contain the right words". Both tracks score the IDENTICAL stored pick from
  phase1c_picks.json (no recompute, no oracle substitution).
- Tokenization (frozen, THESIS_SPEC 8.3): Chinese by char, English by word,
  lowercased, whitespace stripped. Gold text = concat of nodes with IoU>=0.5
  with the gold box; B class gold text empty -> Text undefined -> excluded (NaN),
  not zeroed. Pred text = stored pick's node text.
- Anti-gaming: pred box area > 50% page area -> Text zeroed; count reported.
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
    zeroed = 0
    high_text_miss: list[dict] = []
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
        for m in methods:
            nid = mpicks.get(m)
            node = node_by_id.get(nid) if nid else None
            pred_text = node["text"] if node else ""
            pred_area = 0.0
            if node:
                b = node["bbox"]
                pred_area = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            rec, f1 = text_scores(pred_text, gold_text)
            if pred_area > 0.5 * page_area:
                rec, f1 = 0.0, 0.0
                zeroed += 1
            per_method[m].append((rec, f1))
            if m == "fixed:iou_mass" and not iou_hit_oracle and rec >= 0.8 and not math.isnan(rec):
                high_text_miss.append({"query_id": qid, "text_recall": round(rec, 4)})

    def mean(xs: list[float]) -> float:
        vs = [x for x in xs if not (isinstance(x, float) and math.isnan(x))]
        return sum(vs) / len(vs) if vs else float("nan")

    result = {
        "meta": {"k": k, "iou": iou, "scope": "SAME stored Top-1 picks as phase1c.json (per-method); gold text = concat IoU>=0.5 nodes; B gold-empty excluded (NaN)",
                 "tokenization": "Chinese by char, English by word, lowercased, whitespace stripped (THESIS_SPEC 8.3)",
                 "antigaming": "pred box area > 50% page area -> Text zeroed",
                 "encoding": "utf-8"},
        "n_scored": n_scored,
        "per_method_text": {
            m: {"text_recall_mean": mean([r for r, _ in vs]), "text_f1_mean": mean([f for _, f in vs])}
            for m, vs in per_method.items()
        },
        "oversize_zeroed_cells": zeroed,
        "iou_miss_text_ge08": {"n": len(high_text_miss), "sample": high_text_miss[:30],
                               "verdict": "condition-not-met" if len(high_text_miss) < 20 else "ready-for-review",
                               "note": "IoU-miss-but-Text-ge0.8 needs >=20 cases for human review; current n<20, dual-track defense gap, not fabricated"},
    }
    (out_dir / "text_dual.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--iou", type=float, default=0.5)
    ns = parser.parse_args()
    main(k=ns.k, iou=ns.iou)
