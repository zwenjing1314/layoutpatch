"""Phase 2-R DUDE training. Frozen scheme A. Not fusion.

DUDE train_fit updates a new w,b. DUDE train_dev only early-stops.
One dev_eval judgment. No test_eval scores. No y(c).
Never writes artifacts/phase2r/arxivqa/ranker.pt.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import polars as pl
import torch
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import recall_layout
from layoutpatch.io import write_hits
from layoutpatch.layout.correspondence import clamp_bbox, scale_bbox_to_model
from layoutpatch.retrieval.propagation import patch_scores_from_vectors
from layoutpatch.retrieval.region_pooling import coverage_region_scores
from layoutpatch.retrieval.rerank.box_ranker import (
    BATCH_SIZE,
    EARLY_STOP_ROUNDS,
    TRAIN_K,
    BoxRanker,
    area_at_k,
    build_features,
    page_pair_loss,
    rank_all,
)
from layoutpatch.schemas import QueryRecord, RetrievalHit

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_train/hf_hub/annotations_top1_negative/DUDE_train.jsonl"
EVAL_ANN = REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
FIT = REPO / "experiments/s2_splits/train_fit_ids.jsonl"
DEV = REPO / "experiments/s2_splits/train_dev_ids.jsonl"
DEV_EVAL = REPO / "experiments/s2_splits/dev_eval_ids.jsonl"
TEST_EVAL = REPO / "experiments/s2_splits/test_eval_ids.jsonl"
REGION_401 = REPO / "experiments/s2_splits/dev_eval_region_401.txt"
PATCH_DIR = REPO / "artifacts/colpali/mmdocir_train/vidore_colpali"
TEXT_DIR = REPO / "artifacts/bge_m3/mmdocir_train_boxes"
EVAL_PATCH = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
PROCESSED = REPO / "data/processed/mmdocir_evaluation"
OUT = REPO / "artifacts/phase2r/dude"
ARXIV_RANKER = REPO / "artifacts/phase2r/arxivqa/ranker.pt"
FROZEN_PRED = REPO / "runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet"
RUN_ROOT = REPO / "runs/retrieval/mmdocir_phase2r_dude"
EXPECTED_FIT = 2312
EXPECTED_DEV = 292
EXPECTED_FIT_PAGES = 3330
EXPECTED_DEV_PAGES = 422
VRAM_LIMIT = 12 * 1024**3


def norm_doc(name: str) -> str:
    text = str(name)
    return text[:-4] if text.lower().endswith(".pdf") else text


def cache_name(doc: str, page: int) -> str:
    raw = f"{doc}\0{page}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", doc).strip("_")[:40]
    return f"{safe}__p{page}__{digest}"


def refuse_test(path: Path) -> None:
    if path.resolve() == TEST_EVAL.resolve():
        raise RuntimeError("test_eval scores are forbidden")


def load_pool(path: Path) -> set[int]:
    refuse_test(path)
    out = set()
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("domain") == "DUDE":
            out.add(int(row["line_index"]))
    return out


def page_paths(doc: str, page: int) -> tuple[Path, Path]:
    stem = cache_name(doc, page)
    return PATCH_DIR / f"{stem}.pt", TEXT_DIR / f"{stem}.pt"


def page_ready(doc: str, page: int) -> bool:
    patch_path, text_path = page_paths(doc, page)
    return (
        patch_path.is_file()
        and text_path.is_file()
        and patch_path.stat().st_size > 0
        and text_path.stat().st_size > 0
    )


def page_bundle(doc: str, page: int) -> dict | None:
    patch_path, text_path = page_paths(doc, page)
    if not patch_path.is_file() or not text_path.is_file():
        return None
    patch = torch.load(patch_path, map_location="cpu", weights_only=False)
    text = torch.load(text_path, map_location="cpu", weights_only=False)
    page_size = [float(text["page_w"]), float(text["page_h"])]
    boxes = []
    for bbox, vec in zip(text["boxes"], text["vecs"], strict=True):
        raw = [float(v) for v in bbox]
        boxes.append(
            {
                "bbox": raw,
                "bbox_model": clamp_bbox(scale_bbox_to_model(raw, page_size)),
                "text_vec": None if not vec or vec == [0.0] else vec,
            }
        )
    return {"embedding": patch["embedding"], "boxes": boxes, "page_w": page_size[0], "page_h": page_size[1]}


def feats_of(query_vecs, bundle) -> tuple[torch.Tensor, torch.Tensor]:
    if bundle is None or not bundle["boxes"]:
        empty = torch.zeros((0, 6))
        return empty, empty.new_zeros((0,))
    page = normalize(bundle["embedding"].float(), dim=-1)
    scores = patch_scores_from_vectors(query_vecs, page)
    feats = build_features(scores, bundle["boxes"], bundle["page_w"], bundle["page_h"], None)
    return feats, feats[:, 1] if feats.numel() else feats.new_zeros((0,))


def load_pairs(indexes: set[int]) -> tuple[list[dict], set[tuple[str, int]]]:
    rows = []
    pages: set[tuple[str, int]] = set()
    for index, line in enumerate(ANN.open(encoding="utf-8")):
        if index not in indexes:
            continue
        row = json.loads(line)
        if "y_c" in row or "coverage" in row:
            raise RuntimeError("y(c) labels are forbidden")
        pos, neg = row["positive_passages"], row["negative_passages"]
        pair = [
            (norm_doc(pos[0]["doc_name"]), int(pos[0]["page_id"])),
            (norm_doc(neg[0]["doc_name"]), int(neg[0]["page_id"])),
        ]
        if not all(page_ready(*key) for key in pair):
            continue
        pages.update(pair)
        rows.append({"query": row["query"], "pos": pair[0], "neg": pair[1]})
    return rows, pages


def encode_queries(texts: list[str], cache: Path):
    if cache.is_file() and cache.stat().st_size > 0:
        return torch.load(cache, map_location="cpu", weights_only=False)
    from layoutpatch.retrieval.colpali import ColPaliPageRetriever

    retriever = ColPaliPageRetriever(
        "mmdocir_train",
        {"model": "vidore/colpali", "use_embedding_cache": False, "query_batch_size": 32},
    )
    vecs = retriever.encode_queries(
        [
            QueryRecord(query_id=str(i), dataset="mmdocir_train", doc_id="dude", question=text)
            for i, text in enumerate(texts)
        ]
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    torch.save(vecs, cache)
    return vecs


def precompute(rows: list[dict], queries, cache_path: Path):
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        loaded = torch.load(cache_path, map_location="cpu", weights_only=False)
        print(json.dumps({"precomputed_cache": len(loaded)}), flush=True)
        return loaded
    cache: dict[tuple[str, int], dict | None] = {}
    out = []
    for row, vec in zip(rows, queries, strict=True):
        for key in (row["pos"], row["neg"]):
            if key not in cache:
                cache[key] = page_bundle(*key)
        pos_f, pos_a = feats_of(vec, cache[row["pos"]])
        neg_f, neg_a = feats_of(vec, cache[row["neg"]])
        out.append((pos_f, pos_a, neg_f, neg_a))
    print(json.dumps({"precomputed": len(out), "pages": len(cache)}), flush=True)
    torch.save(out, cache_path)
    return out


def check_vram() -> None:
    if torch.cuda.is_available() and torch.cuda.max_memory_allocated() > VRAM_LIMIT:
        raise RuntimeError("batch 32 exceeds 12GB")


def train() -> tuple[BoxRanker, int, int, int, float]:
    OUT.mkdir(parents=True, exist_ok=True)
    if ARXIV_RANKER.resolve() == (OUT / "ranker.pt").resolve():
        raise RuntimeError("refusing to share the ArxivQA ranker path")
    fit_rows, fit_pages = load_pairs(load_pool(FIT))
    dev_rows, dev_pages = load_pairs(load_pool(DEV))
    if len(fit_rows) != EXPECTED_FIT or len(fit_pages) != EXPECTED_FIT_PAGES:
        raise SystemExit(json.dumps({"stop": "fit", "questions": len(fit_rows), "pages": len(fit_pages)}))
    if len(dev_rows) != EXPECTED_DEV or len(dev_pages) != EXPECTED_DEV_PAGES:
        raise SystemExit(json.dumps({"stop": "dev", "questions": len(dev_rows), "pages": len(dev_pages)}))
    print(json.dumps({"fit": len(fit_rows), "fit_pages": len(fit_pages), "dev": len(dev_rows), "dev_pages": len(dev_pages)}), flush=True)
    fit_q = encode_queries([row["query"] for row in fit_rows], OUT / "fit_queries.pt")
    dev_q = encode_queries([row["query"] for row in dev_rows], OUT / "dev_queries.pt")
    fit_ready = precompute(fit_rows, fit_q, OUT / "fit_ready.pt")
    dev_ready = precompute(dev_rows, dev_q, OUT / "dev_ready.pt")
    del fit_q, dev_q, fit_rows, dev_rows
    ranker = BoxRanker()
    opt = torch.optim.Adam(ranker.parameters(), lr=1e-2)
    best = -1.0
    best_epoch = 0
    stale = 0
    stopped = 0
    torch.manual_seed(42)
    for epoch in range(1, 21):
        order = torch.randperm(len(fit_ready)).tolist()
        ranker.train()
        for start in range(0, len(order), BATCH_SIZE):
            losses = []
            for idx in order[start : start + BATCH_SIZE]:
                pos_f, pos_a, neg_f, neg_a = fit_ready[idx]
                loss = page_pair_loss(ranker, pos_f, pos_a, neg_f, neg_a, k=TRAIN_K)
                if loss is not None:
                    losses.append(loss)
            if not losses:
                continue
            total = torch.stack(losses).mean()
            opt.zero_grad()
            total.backward()
            opt.step()
            check_vram()
        ranker.eval()
        with torch.no_grad():
            hits = 0
            scored = 0
            for pos_f, _, neg_f, _ in dev_ready:
                if pos_f.numel() == 0 or neg_f.numel() == 0:
                    continue
                scored += 1
                hits += int(float(ranker.score(pos_f).max()) > float(ranker.score(neg_f).max()))
        rate = hits / len(dev_ready) if dev_ready else 0.0
        print(json.dumps({"epoch": epoch, "train_dev_hit": round(rate, 6), "scored": scored}), flush=True)
        if rate > best:
            best = rate
            best_epoch = epoch
            stale = 0
            torch.save({"w": ranker.linear.weight.detach().cpu(), "b": ranker.linear.bias.detach().cpu()}, OUT / "ranker.pt")
        else:
            stale += 1
        stopped = epoch
        if stale >= EARLY_STOP_ROUNDS:
            break
    saved = torch.load(OUT / "ranker.pt", map_location="cpu", weights_only=True)
    if set(saved) != {"w", "b"}:
        raise RuntimeError(f"ranker keys {sorted(saved)}")
    ranker.linear.weight.data.copy_(saved["w"])
    ranker.linear.bias.data.copy_(saved["b"])
    ranker.eval()
    (OUT / "train_meta.json").write_text(
        json.dumps(
            {
                "train_questions": EXPECTED_FIT,
                "early_stop_questions": EXPECTED_DEV,
                "early_stop_round": stopped,
                "best_epoch": best_epoch,
                "best_hit": best,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ranker, EXPECTED_FIT, EXPECTED_DEV, stopped, best_epoch


def unjson(value):
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def query_id_by_index() -> dict[tuple[int, int], str]:
    flat = []
    for line_index, line in enumerate(EVAL_ANN.open(encoding="utf-8")):
        item = json.loads(line)
        for question_index, _question in enumerate(item["questions"]):
            flat.append((line_index, question_index))
    queries = pl.read_parquet(PROCESSED / "queries.parquet").sort("query_id")["query_id"].to_list()
    if len(queries) != len(flat):
        raise RuntimeError(f"query count {len(queries)} != annotation questions {len(flat)}")
    return dict(zip(flat, queries, strict=True))


def dev_eval_rows() -> list[dict]:
    refuse_test(DEV_EVAL)
    ids = query_id_by_index()
    ann = [json.loads(line) for line in EVAL_ANN.open(encoding="utf-8")]
    out = []
    for line in DEV_EVAL.open(encoding="utf-8"):
        row = json.loads(line)
        key = (int(row["annotation_line"]), int(row["question_index"]))
        item = ann[key[0]]
        out.append({"query_id": ids[key], "doc": norm_doc(item["doc_name"]), "question": item["questions"][key[1]]})
    if len(out) != 415:
        raise RuntimeError(f"dev_eval rows {len(out)} != 415")
    return out


def within_doc_top5(rows: list[dict]) -> dict[str, set[str]]:
    """Frozen ColPali page order, Top-5 inside each question's document."""
    wanted = {row["query_id"]: row["doc"] for row in rows}
    hits = pl.read_parquet(FROZEN_PRED)
    grouped: dict[str, list] = {}
    for hit in hits.filter(pl.col("query_id").is_in(list(wanted))).sort(["query_id", "rank"]).iter_rows(named=True):
        if hit["doc_id"] != wanted[hit["query_id"]]:
            continue
        grouped.setdefault(hit["query_id"], [])
        if len(grouped[hit["query_id"]]) < 5:
            grouped[hit["query_id"]].append(hit["page_id"])
    return {qid: set(pages) for qid, pages in grouped.items()}


def judge(ranker: BoxRanker) -> dict:
    region_ids = {line.strip() for line in REGION_401.read_text(encoding="utf-8").splitlines() if line.strip()}
    if len(region_ids) != 401:
        raise RuntimeError(f"region id list {len(region_ids)} != 401")
    by_id = {row["query_id"]: row for row in pl.read_parquet(PROCESSED / "queries.parquet").to_dicts()}
    labels = pl.read_parquet(PROCESSED / "region_labels.parquet").to_dicts()
    gold: dict[str, list] = {}
    for row in labels:
        gold.setdefault(row["query_id"], []).append(row)
    nodes: dict[str, list] = {}
    for row in pl.read_parquet(PROCESSED / "nodes.parquet").to_dicts():
        bbox = unjson(row["bbox"])
        nodes.setdefault(row["page_id"], []).append({"node_id": row["node_id"], "bbox": [float(v) for v in bbox]})
    rows = dev_eval_rows()
    top5 = within_doc_top5(rows)
    texts = [row["question"]["Q"] for row in rows]
    qvecs = encode_queries(texts, OUT / "dev_eval_queries.pt")
    area1 = area5 = base1 = base5 = 0.0
    page_hit = 0
    region_n = 0
    seen_region = []
    with torch.no_grad():
        for row, vec in zip(rows, qvecs, strict=True):
            query = by_id[row["query_id"]]
            evidence = set(unjson(query["evidence_page_ids"]) or [])
            if top5.get(query["query_id"], set()) & evidence:
                page_hit += 1
            if query["query_id"] not in region_ids:
                continue
            golds = [g for g in gold.get(query["query_id"], []) if g["source"] == "matched"]
            if not golds:
                raise RuntimeError(f"{query['query_id']} is in the 401 list but has no matched gold")
            region_n += 1
            seen_region.append(query["query_id"])
            page_id = golds[0]["page_id"]
            cands = nodes.get(page_id, [])
            page_size = [float(v) for v in unjson(golds[0]["page_size"])]
            payload = torch.load(EVAL_PATCH / f"{page_id}.pt", map_location="cpu", weights_only=False)
            emb = payload["embedding"] if isinstance(payload, dict) else payload
            boxes = [
                {
                    "bbox": cand["bbox"],
                    "bbox_model": clamp_bbox(scale_bbox_to_model(cand["bbox"], page_size)),
                    "text_vec": None,
                }
                for cand in cands
            ]
            scores = patch_scores_from_vectors(vec, normalize(emb.float(), dim=-1))
            feats = build_features(scores, boxes, page_size[0], page_size[1], None)
            layout_indices = [(i, int(page_id.rsplit("_p", 1)[1]), *cand["bbox"]) for i, cand in enumerate(cands)]
            mapping = [{"page": int(g["page_id"].rsplit("_p", 1)[1]), "bbox": unjson(g["bbox"])} for g in golds]
            order = rank_all(ranker, feats)
            area1 += float(recall_layout(order[:1], layout_indices, mapping))
            area5 += float(recall_layout(order[:5], layout_indices, mapping))
            base_scores = coverage_region_scores(scores, boxes, "iou_mass")
            base_scores = [0.0 if s == float("-inf") else s for s in base_scores]
            base1 += area_at_k(layout_indices, mapping, base_scores, 1)
            base5 += area_at_k(layout_indices, mapping, base_scores, 5)
    if region_n != 401 or set(seen_region) != region_ids:
        raise RuntimeError(f"region denominator {region_n} != 401")
    # 2-R does not change page order. Both sides are this 415-question frozen ColPali Top-5.
    page_delta_pp = 0.0
    return {
        "region_n": 401,
        "area1": area1 / 401,
        "area5": area5 / 401,
        "base1": base1 / 401,
        "base5": base5 / 401,
        "page_hits": page_hit,
        "page_n": 415,
        "page_r5": page_hit / 415,
        "page_baseline_hits": page_hit,
        "page_baseline_n": 415,
        "page_r5_baseline": page_hit / 415,
        "page_r5_delta_pp": page_delta_pp,
        "page_r5_within_0_3pp": True,
        "page_order": "frozen ColPali within-document Top-5, unchanged by 2-R",
    }


def copy_frozen_hits(run_dir: Path, rows: list[dict]) -> None:
    """Page order is frozen. Copy the same within-document Top-5, not a new ranking."""
    by_doc = {row["query_id"]: row["doc"] for row in rows}
    kept = []
    seen: dict[str, int] = {}
    frame = pl.read_parquet(FROZEN_PRED).filter(pl.col("query_id").is_in(list(by_doc))).sort(["query_id", "rank"])
    for hit in frame.iter_rows(named=True):
        if hit["doc_id"] != by_doc[hit["query_id"]]:
            continue
        seen[hit["query_id"]] = seen.get(hit["query_id"], 0) + 1
        if seen[hit["query_id"]] > 5:
            continue
        kept.append(
            RetrievalHit(
                query_id=hit["query_id"],
                rank=seen[hit["query_id"]],
                score=float(hit["score"]),
                doc_id=hit["doc_id"],
                page_id=hit["page_id"],
                retriever="frozen_colpali_page",
            )
        )
    write_hits(run_dir / "predictions.parquet", kept)


def write_run(metrics: dict, stamp: str, best_epoch: int) -> Path:
    run_dir = RUN_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "name": "mmdocir_phase2r_dude",
                "scheme": "A",
                "features": ["patch_iou_mass", "geometry", "bge_text"],
                "k": 4,
                "early_stop_rounds": 2,
                "batch": 32,
                "domain": "DUDE",
                "test_eval": "not_read",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    verdict = metrics["verdict"]
    (run_dir / "run_info.json").write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "train_questions": EXPECTED_FIT,
                "early_stop_questions": EXPECTED_DEV,
                "early_stop_round": metrics["early_stop_round"],
                "best_epoch": best_epoch,
                "page_order": "frozen ColPali within-document Top-5",
                "region_denominator": 401,
                "page_hits": f"{metrics['page_hits']}/415",
                "verdict": verdict,
                "scope": "DUDE-trained head, one judgment on multi-domain dev_eval",
                "region_id_list": "experiments/s2_splits/dev_eval_region_401.txt",
                "test_eval": "not_read",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Phase 2-R DUDE dev_eval",
                "",
                f"- 训练题数 {EXPECTED_FIT}。早停题数 {EXPECTED_DEV}。早停第 {metrics['early_stop_round']} 轮，最好第 {best_epoch} 轮。",
                f"- 同一 401 题 Area@1 {metrics['area1']:.4f} 对照 {metrics['base1']:.4f}；Area@5 {metrics['area5']:.4f} 对照 {metrics['base5']:.4f}。",
                f"- 页级 {metrics['page_hits']}/415，对照也是 {metrics['page_baseline_hits']}/415，差值 {metrics['page_r5_delta_pp']}。{verdict}。",
                "- 范围只写 DUDE 训出来的头，在多域 dev_eval 上这一次。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    copy_frozen_hits(run_dir, dev_eval_rows())
    return run_dir


def main() -> int:
    arxiv_mtime = ARXIV_RANKER.stat().st_mtime_ns
    started = time.perf_counter()
    ranker, n_train, n_dev, stopped, best_epoch = train()
    if ARXIV_RANKER.stat().st_mtime_ns != arxiv_mtime:
        raise RuntimeError("arxivqa ranker.pt mtime changed")
    metrics = judge(ranker)
    check_vram()
    rose = metrics["area1"] > metrics["base1"] and metrics["area5"] > metrics["base5"] and metrics["page_r5_within_0_3pp"]
    metrics.update(
        {
            "train_questions": n_train,
            "early_stop_questions": n_dev,
            "early_stop_round": stopped,
            "best_epoch": best_epoch,
            "hours": round((time.perf_counter() - started) / 3600, 4),
            "verdict": "算涨" if rose else "不算涨",
            "test_eval": "not_read",
        }
    )
    (OUT / "dev_eval.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = write_run(metrics, stamp, best_epoch)
    print(json.dumps({"run": str(run_dir), **metrics}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



