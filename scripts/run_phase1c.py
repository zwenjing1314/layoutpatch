"""Phase 1C runner (PAPER_SPEC 7.4, batch 5, EXP-006).

Usage (registered in docs/02-commands.md as phase1c-baselines):
    uv run --extra colpali python scripts/run_phase1c.py --limit-docs 2     # smoke
    uv run --extra colpali python scripts/run_phase1c.py                    # full

What it does (beginner):
- For each query, load its doc pages' FROZEN ColPali vectors from
  artifacts/colpali (NO vision re-encode), encode the query text with the frozen
  ColPali text tower (GPU, same model as EXP-001), MaxSim-score the Top-1 gold page,
  then run the three no-train baselines to pick ONE box on that page.
- Measures: (a) 1343 matched A: Top-1 box-pick accuracy (IoU>=0.5 vs gold box);
  (b) 45 B: dissolution rate, i.e. picked box hits the unmapped gold box
  (expected ~0 because the gold box has no candidate; negative result).
- Aggregation grid: Snappy max/mean/iou x fixed coverage/iou_mass x grouping
  eta P25/P50/P75. Outputs artifacts/baselines/mmdocir_1c/phase1c.json plus
  phase1c_picks.json (per-query Top-1 pick node_id per method for Text dual-track).

Cost note: query encoding is GPU (same as EXP-001, batch=2); page vectors are
cache-only. No training, no fusion/ subpackage, no train_fusion.py (ban intact).

Cost note: query encoding is GPU (same as EXP-001, batch=2); page vectors are
cache-only. No training, no fusion/ subpackage, no train_fusion.py (ban intact).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import polars as pl
import torch
import typer
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.paths import artifacts_dir, data_root
from layoutpatch.retrieval.propagation import (
    load_page_vectors,
    patch_scores_from_vectors,
    propagate_region_scores,
    region_candidates,
    top1_pick,
)
from layoutpatch.retrieval.region_grouping import salient_groups
from layoutpatch.retrieval.region_pooling import coverage_region_scores

app = typer.Typer(help="Phase 1C no-train baselines.")


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


@app.command()
def main(
    limit_docs: int | None = typer.Option(None, help="Optional doc limit for smoke."),
    k: int = typer.Option(5, help="Top-K pages from EXP-001."),
    iou: float = typer.Option(0.5, help="Region hit threshold."),
) -> None:
    started = time.monotonic()
    processed = data_root() / "processed" / "mmdocir_evaluation"
    run_dir = Path("runs/retrieval/mmdocir_colpali/20260916_134144")
    out_dir = artifacts_dir() / "baselines" / "mmdocir_1c"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from colpali_engine.models import ColPali, ColPaliProcessor
        from colpali_engine.utils.torch_utils import get_torch_device
    except ImportError as exc:
        raise RuntimeError("Phase 1C needs the colpali extra for query encoding.") from exc

    device = get_torch_device("auto")
    model = ColPali.from_pretrained("vidore/colpali", torch_dtype=torch.bfloat16, device_map=device).eval()
    processor = ColPaliProcessor.from_pretrained("vidore/colpali")

    queries = {r["query_id"]: r for r in pl.read_parquet(processed / "queries.parquet").to_dicts()}
    labels = pl.read_parquet(processed / "region_labels.parquet").to_dicts()
    gold_by_query: dict[str, list[dict]] = {}
    for row in labels:
        gold_by_query.setdefault(row["query_id"], []).append(row)
    matched_q = {r["query_id"] for r in labels if r["source"] == "matched"}

    nodes_rows = pl.read_parquet(processed / "nodes.parquet").to_dicts()
    nodes_by_page: dict[str, dict] = {}
    node_text_by_id: dict[str, str] = {}
    for row in nodes_rows:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        nodes_by_page.setdefault(row["page_id"], []).append(
            {"node_id": row["node_id"], "node_type": row["node_type"], "bbox": [float(v) for v in bbox]}
        )
        node_text_by_id[row["node_id"]] = row.get("text", "") or ""

    if limit_docs is not None:
        docs = sorted({q["doc_id"] for q in queries.values()})[:limit_docs]
        qids = [qid for qid, q in queries.items() if q["doc_id"] in docs]
    else:
        qids = sorted(gold_by_query)

    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    top_pages: dict[str, list[str]] = {}
    for hit in hits:
        if hit["rank"] <= k:
            top_pages.setdefault(hit["query_id"], []).append(hit["page_id"])

    # EXP-005 classes: A = page-hit + matched + topk_hit (1343); B = page-hit + topk_miss (45).
    # Unmapped page-hit is 47 (45 B + 2 A pure-unmapped 00520/00672); dissolution denominator must be strict B=45.
    eval_a: list[str] = []
    eval_b: list[str] = []
    for qid in qids:
        golds = gold_by_query[qid]
        pages = set(top_pages.get(qid, []))
        gold_pages = {g["page_id"] for g in golds}
        page_hit = bool(pages & gold_pages)
        if not page_hit:
            continue
        hit = _topk_hit(qid, golds, pages, nodes_by_page, iou)
        if qid in matched_q and hit:
            eval_a.append(qid)
        elif not hit:
            eval_b.append(qid)

    grid = ["snappy:max", "snappy:mean", "snappy:iou", "fixed:coverage", "fixed:iou_mass",
            "group:P25", "group:P50", "group:P75"]
    acc_a: dict[str, dict] = {g: {"hit": 0, "total": 0} for g in grid}
    dis_b: dict[str, dict] = {g: {"hit": 0, "total": 0} for g in grid}
    picks_log: dict[str, dict[str, str | None]] = {}

    with torch.inference_mode():
        for pos, qid in enumerate(eval_a + eval_b, start=1):
            is_a = qid in eval_a
            golds = gold_by_query[qid]
            pages = set(top_pages.get(qid, []))
            # Top-1 gold page = first gold page inside Top-K (deterministic: min rank)
            rank_of = {p: r for r, p in enumerate(top_pages.get(qid, []))}
            gold_page = min((g["page_id"] for g in golds if g["page_id"] in pages), key=lambda p: rank_of[p])
            gold_rows = [g for g in golds if g["page_id"] == gold_page]
            gold_box = [float(v) for v in gold_rows[0]["bbox"]]
            page_size = gold_rows[0].get("page_size") or [1.0, 1.0]

            qvec = model(**processor.process_queries([queries[qid]["question"]]).to(model.device)).float()
            qvec = normalize(qvec.cpu(), dim=-1)
            pvec = load_page_vectors(gold_page)
            assert pvec.shape[0] == 32 * 32 + 7, f"unexpected cache shape {tuple(pvec.shape)} for {gold_page}"
            pscores = patch_scores_from_vectors(qvec, pvec)
            regions = region_candidates(gold_page, nodes_by_page, [float(v) for v in page_size])

            picks: dict[str, int | None] = {}
            picks["snappy:max"] = top1_pick(propagate_region_scores(pscores, regions, "max")) if regions else None
            picks["snappy:mean"] = top1_pick(propagate_region_scores(pscores, regions, "mean")) if regions else None
            picks["snappy:iou"] = top1_pick(propagate_region_scores(pscores, regions, "iou")) if regions else None
            picks["fixed:coverage"] = top1_pick(coverage_region_scores(pscores, regions, "coverage")) if regions else None
            picks["fixed:iou_mass"] = top1_pick(coverage_region_scores(pscores, regions, "iou_mass")) if regions else None
            for tag, q in (("group:P25", 0.25), ("group:P50", 0.50), ("group:P75", 0.75)):
                eta = _quantile(pscores, q)
                groups = salient_groups(pscores, eta)
                picks[tag] = 0 if groups else None
                if groups:
                    # group pick vs gold: best group box IoU>=thr counts as hit
                    from layoutpatch.layout.correspondence import MODEL_SIZE

                    gb = gold_rows[0]["bbox"]
                    ps = [float(v) for v in (gold_rows[0].get("page_size") or [1.0, 1.0])]
                    scaled = [gb[0] * MODEL_SIZE / ps[0], gb[1] * MODEL_SIZE / ps[1], gb[2] * MODEL_SIZE / ps[0], gb[3] * MODEL_SIZE / ps[1]]
                    best = max(bbox_iou(g["bbox_model"], scaled) for g in groups)
                    store = acc_a if is_a else dis_b
                    store[tag]["total"] += 1
                    store[tag]["hit"] += 1 if best >= iou else 0

            for tag in ("snappy:max", "snappy:mean", "snappy:iou", "fixed:coverage", "fixed:iou_mass"):
                store = acc_a if is_a else dis_b
                store[tag]["total"] += 1
                idx = picks[tag]
                if idx is None:
                    continue
                hit_box = regions[idx]["bbox_orig"]
                store[tag]["hit"] += 1 if bbox_iou(hit_box, gold_box) >= iou else 0

            picks_log[qid] = {
                tag: (regions[idx]["node_id"] if idx is not None and tag not in ("group:P25", "group:P50", "group:P75") else None)
                for tag, idx in picks.items()
            }

            if pos % 100 == 0 or pos == len(eval_a) + len(eval_b):
                print(f"[1C] {pos}/{len(eval_a) + len(eval_b)} A={len(eval_a)} B={len(eval_b)} elapsed={time.monotonic() - started:.0f}s", flush=True)

    result = {
        "meta": {"k": k, "iou_threshold": iou, "limit_docs": limit_docs, "eval_A_matched": len(eval_a), "eval_B_strict45": len(eval_b),
                 "patch_layout": "[7 prefix, 1024 patches] (asserted per page)", "note": "no training; cache-only pages; gold only for scoring; B denominator is strict Top-K B=45, NOT unmapped_only page-hit=47"},
        "top1_accuracy_A": {g: {"hit": v["hit"], "total": v["total"], "acc": round(v["hit"] / v["total"], 4) if v["total"] else 0.0} for g, v in acc_a.items()},
        "dissolution_B": {g: {"hit": v["hit"], "total": v["total"], "rate": round(v["hit"] / v["total"], 4) if v["total"] else 0.0} for g, v in dis_b.items()},
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    (out_dir / ("phase1c_smoke.json" if limit_docs else "phase1c.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not limit_docs:
        (out_dir / "phase1c_picks.json").write_text(
            json.dumps({"meta": {"k": k, "iou_threshold": iou, "methods": grid,
                                 "note": "per-query Top-1 pick node_id for fixed-candidate methods; group methods are self-drawn boxes (None); for Text dual-track scoring"},
                        "picks": picks_log}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _topk_hit(qid: str, golds: list[dict], pages: set[str], nodes_by_page: dict, iou: float) -> bool:
    for gold in golds:
        if gold["page_id"] not in pages:
            continue
        gb = [float(v) for v in gold["bbox"]]
        for cand in nodes_by_page.get(gold["page_id"], []):
            cb = cand["bbox"]
            if isinstance(cb, str):
                cb = json.loads(cb)
            if bbox_iou([float(v) for v in cb], gb) >= iou:
                return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-docs", type=int, default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--iou", type=float, default=0.5)
    ns = parser.parse_args()
    main(limit_docs=ns.limit_docs, k=ns.k, iou=ns.iou)
