"""Backfill Top-1 picks for mmdocir_00520/00672 (EXP-006漏选2题, 同冻结方法).

方法与 scripts/run_phase1c.py 逐题逻辑完全一致 (冻结ColPali query编码 +
缓存页向量 + 同一5规则Top-1 + group三档None), 仅 qids=[00520,00672].
输出 artifacts/baselines/mmdocir_1c/phase1c_picks_backfill_2.json (本地产物).
原 phase1c_picks.json 保持冻结不动.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import polars as pl
import torch
from torch.nn.functional import normalize

QIDS = ["mmdocir_00520", "mmdocir_00672"]


def load_phase1c():
    spec = importlib.util.spec_from_file_location("phase1c_mod", Path("scripts/run_phase1c.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    started = time.monotonic()
    m = load_phase1c()
    processed = Path("data/processed/mmdocir_evaluation")
    run_dir = Path("runs/retrieval/mmdocir_colpali/20260916_134144")
    out_path = Path("artifacts/baselines/mmdocir_1c/phase1c_picks_backfill_2.json")

    try:
        from colpali_engine.models import ColPali, ColPaliProcessor
        from colpali_engine.utils.torch_utils import get_torch_device
    except ImportError as exc:
        raise RuntimeError("Backfill needs the colpali extra for query encoding.") from exc

    device = get_torch_device("auto")
    model = ColPali.from_pretrained("vidore/colpali", torch_dtype=torch.bfloat16, device_map=device).eval()
    processor = ColPaliProcessor.from_pretrained("vidore/colpali")

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
        if hit["rank"] <= 5:
            top_pages.setdefault(hit["query_id"], []).append(hit["page_id"])

    picks_log: dict[str, dict[str, str | None]] = {}
    with torch.inference_mode():
        for qid in QIDS:
            golds = gold_by_query[qid]
            pages = set(top_pages.get(qid, []))
            gold_pages = {g["page_id"] for g in golds}
            assert pages & gold_pages, f"{qid} not page-hit, refuse backfill"
            rank_of = {p: r for r, p in enumerate(top_pages.get(qid, []))}
            gold_page = min((g["page_id"] for g in golds if g["page_id"] in pages), key=lambda p: rank_of[p])
            gold_rows = [g for g in golds if g["page_id"] == gold_page]
            page_size = gold_rows[0].get("page_size") or [1.0, 1.0]

            qvec = model(**processor.process_queries([queries[qid]["question"]]).to(model.device)).float()
            qvec = normalize(qvec.cpu(), dim=-1)
            pvec = m.load_page_vectors(gold_page)
            assert pvec.shape[0] == 32 * 32 + 7
            pscores = m.patch_scores_from_vectors(qvec, pvec)
            regions = m.region_candidates(gold_page, nodes_by_page, [float(v) for v in page_size])
            assert regions, f"{qid} has no candidate regions on {gold_page}"

            picks: dict[str, int | None] = {}
            picks["snappy:max"] = m.top1_pick(m.propagate_region_scores(pscores, regions, "max"))
            picks["snappy:mean"] = m.top1_pick(m.propagate_region_scores(pscores, regions, "mean"))
            picks["snappy:iou"] = m.top1_pick(m.propagate_region_scores(pscores, regions, "iou"))
            picks["fixed:coverage"] = m.top1_pick(m.coverage_region_scores(pscores, regions, "coverage"))
            picks["fixed:iou_mass"] = m.top1_pick(m.coverage_region_scores(pscores, regions, "iou_mass"))
            for tag in ("group:P25", "group:P50", "group:P75"):
                picks[tag] = None
            picks_log[qid] = {
                tag: (regions[idx]["node_id"] if idx is not None and not tag.startswith("group:") else None)
                for tag, idx in picks.items()
            }
            print(f"[backfill] {qid} page={gold_page} picks={picks_log[qid]}", flush=True)

    out_path.write_text(
        json.dumps({"meta": {"method": "identical to scripts/run_phase1c.py per-query logic",
                             "qids": QIDS, "k": 5},
                    "picks": picks_log}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done in {time.monotonic() - started:.1f}s -> {out_path}")


if __name__ == "__main__":
    main()
