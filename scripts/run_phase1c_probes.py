"""Phase 1C efficiency probes (PAPER_SPEC 9.4, B1 publishable cells, EXP-006 addendum).

What (beginner):
- This script does NOT re-rank or change any 1C decision numbers. It only times
  what the main runner already does, on a tiny deterministic subset, so B1 gets
  honest per-query latency and peak-memory cells instead of "missing".
- Two probes, both frozen-cache, both query-text-GPU:
  - query_encode: encode ONE query text with the frozen ColPali text tower,
    record wall ms + torch.cuda.max_memory_allocated peak MB (reset before).
  - box_select: on ONE fixed page (first matched-A gold page), run the seven
    no-train selectors over cached vectors, record wall ms + peak MB.
- Text index weighing: BM25/BGE on-disk sizes are "missing by construction"
  (vectors computed on the fly, never persisted); this probe weighs what IS
  persisted (predictions.parquet outputs) and reports text-index cells as 缺
  with the reason, not a fabricated number.

Usage:
    uv run --extra colpali python scripts/run_phase1c_probes.py --n-queries 20
Output: artifacts/baselines/mmdocir_1c/phase1c_probes.json
"""

from __future__ import annotations

import argparse
import json
import time

import polars as pl
import torch
import typer
from torch.nn.functional import normalize

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

app = typer.Typer(help="Phase 1C efficiency probes.")


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] * (1 - (pos - lo)) + ordered[hi] * (pos - lo)


def main(n_queries: int = 20, k: int = 5, iou: float = 0.5) -> None:
    from colpali_engine.models import ColPali, ColPaliProcessor
    from colpali_engine.utils.torch_utils import get_torch_device

    t0 = time.monotonic()
    device = get_torch_device("auto")
    model = ColPali.from_pretrained("vidore/colpali", torch_dtype=torch.bfloat16, device_map=device).eval()
    processor = ColPaliProcessor.from_pretrained("vidore/colpali")
    load_s = time.monotonic() - t0

    processed = data_root() / "processed" / "mmdocir_evaluation"
    run_dir = __import__("pathlib").Path("runs/retrieval/mmdocir_colpali/20260916_134144")
    queries = {r["query_id"]: r for r in pl.read_parquet(processed / "queries.parquet").to_dicts()}
    labels = pl.read_parquet(processed / "region_labels.parquet").to_dicts()
    gold_by_query: dict[str, list[dict]] = {}
    for row in labels:
        gold_by_query.setdefault(row["query_id"], []).append(row)
    nodes_rows = pl.read_parquet(processed / "nodes.parquet").to_dicts()
    nodes_by_page: dict[str, list[dict]] = {}
    for row in nodes_rows:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            bbox = json.loads(bbox)
        nodes_by_page.setdefault(row["page_id"], []).append(
            {"node_id": row["node_id"], "node_type": row["node_type"], "bbox": [float(v) for v in bbox]}
        )
    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    top_pages: dict[str, list[str]] = {}
    for hit in hits:
        if hit["rank"] <= k:
            top_pages.setdefault(hit["query_id"], []).append(hit["page_id"])

    matched_q = {r["query_id"] for r in labels if r["source"] == "matched"}
    subset: list[str] = []
    for qid in sorted(gold_by_query):
        if qid in matched_q and any(g["page_id"] in set(top_pages.get(qid, [])) for g in gold_by_query[qid]):
            subset.append(qid)
        if len(subset) == n_queries:
            break

    # probe 1: pure query-encode latency + peak
    lat_ms: list[float] = []
    peak_mb: list[float] = []
    with torch.inference_mode():
        for qid in subset:
            torch.cuda.reset_peak_memory_stats()
            s = time.perf_counter()
            _ = model(**processor.process_queries([queries[qid]["question"]]).to(model.device))
            torch.cuda.synchronize()
            lat_ms.append((time.perf_counter() - s) * 1000)
            peak_mb.append(torch.cuda.max_memory_allocated() / 1024**2)

    # probe 2: box-select on one fixed page (first subset query's top-1 gold page)
    qid0 = subset[0]
    pages = set(top_pages[qid0])
    rank_of = {p: r for r, p in enumerate(top_pages[qid0])}
    gold_page = min((g["page_id"] for g in gold_by_query[qid0] if g["page_id"] in pages), key=lambda p: rank_of[p])
    page_size = [float(v) for v in gold_by_query[qid0][0].get("page_size") or [1.0, 1.0]]
    regions = region_candidates(gold_page, nodes_by_page, page_size)
    pvec = load_page_vectors(gold_page)
    with torch.inference_mode():
        qvec = model(**processor.process_queries([queries[qid0]["question"]]).to(model.device)).float()
        qvec = normalize(qvec.cpu(), dim=-1)
    pscores = patch_scores_from_vectors(qvec, pvec)
    torch.cuda.reset_peak_memory_stats()
    s = time.perf_counter()
    top1_pick(propagate_region_scores(pscores, regions, "max"))
    top1_pick(propagate_region_scores(pscores, regions, "mean"))
    top1_pick(propagate_region_scores(pscores, regions, "iou"))
    top1_pick(coverage_region_scores(pscores, regions, "coverage"))
    top1_pick(coverage_region_scores(pscores, regions, "iou_mass"))
    for q in (0.25, 0.50, 0.75):
        salient_groups(pscores, _quantile(pscores, q))
    torch.cuda.synchronize()
    select_ms = (time.perf_counter() - s) * 1000
    select_peak = torch.cuda.max_memory_allocated() / 1024**2

    # text-index weighing: what is persisted vs missing by construction
    weighed = {}
    for name in ("mmdocir_bge_m3_page/20260917_113452", "mmdocir_hybrid_page/20260917_115238", "mmdocir_colpali/20260916_134144"):
        p = __import__("pathlib").Path("runs/retrieval") / name / "predictions.parquet"
        weighed[name] = round(p.stat().st_size / 1024**2, 2) if p.exists() else None

    result = {
        "meta": {"n_queries": len(subset), "k": k, "iou": iou, "device": str(device), "model_load_s": round(load_s, 1),
                 "note": "probes only; no re-rank; text-index cells stay 缺 (vectors computed on the fly, never persisted)"},
        "query_encode_latency_ms": {"n": len(lat_ms), "mean": round(sum(lat_ms) / len(lat_ms), 1), "p50": round(sorted(lat_ms)[len(lat_ms) // 2], 1), "max": round(max(lat_ms), 1)},
        "query_encode_peak_MB": {"mean": round(sum(peak_mb) / len(peak_mb), 1), "max": round(max(peak_mb), 1)},
        "box_select_7way_ms": round(select_ms, 1),
        "box_select_peak_MB": round(select_peak, 1),
        "persisted_predictions_MB": weighed,
        "text_index_weighed": "缺 (BM25 inverted + BGE page vectors never persisted; see persisted_predictions_MB for output-only sizes, not index)",
    }
    out_dir = artifacts_dir() / "baselines" / "mmdocir_1c"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase1c_probes.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-queries", type=int, default=20)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--iou", type=float, default=0.5)
    ns = parser.parse_args()
    main(n_queries=ns.n_queries, k=ns.k, iou=ns.iou)
