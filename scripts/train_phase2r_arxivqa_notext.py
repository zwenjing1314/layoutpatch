"""Phase 2-R training. Frozen scheme A. Not fusion.

ArxivQA train_fit updates w,b. train_dev only early-stops.
One dev_eval judgment. No test_eval scores. No y(c).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

import polars as pl
import torch
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import recall_layout
from layoutpatch.io import _unjsonify
from layoutpatch.layout.correspondence import clamp_bbox, scale_bbox_to_model
from layoutpatch.retrieval.propagation import patch_scores_from_vectors
from layoutpatch.retrieval.rerank.box_ranker import (
    BATCH_SIZE,
    EARLY_STOP_ROUNDS,
    BoxRanker,
    area_at_k,
    build_features,
    page_pair_loss,
    rank_all,
)
from layoutpatch.schemas import QueryRecord

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_train/hf_hub/annotations_top1_negative/ArxivQA_train.jsonl"
EVAL_ANN = REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
FIT = REPO / "experiments/s2_splits/train_fit_ids.jsonl"
DEV = REPO / "experiments/s2_splits/train_dev_ids.jsonl"
DEV_EVAL = REPO / "experiments/s2_splits/dev_eval_ids.jsonl"
TEST_EVAL = REPO / "experiments/s2_splits/test_eval_ids.jsonl"
PATCH_DIR = REPO / "artifacts/colpali/mmdocir_train/vidore_colpali"
TEXT_DIR = REPO / "artifacts/bge_m3/mmdocir_train_boxes"
EVAL_PATCH = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
PROCESSED = REPO / "data/processed/mmdocir_evaluation"
OUT = REPO / "artifacts/phase2r/arxivqa_notext"
RUN = REPO / "runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet"
RUN_ROOT = REPO / "runs/retrieval/mmdocir_phase2r_arxivqa_notext"


def norm_doc(name: str) -> str:
    text = str(name)
    return text[:-4] if text.lower().endswith(".pdf") else text


def cache_name(doc: str, page: int) -> str:
    raw = f"{doc}\0{page}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", doc).strip("_")[:40]
    return f"{safe}__p{page}__{digest}"


def load_pool(path: Path) -> set[int]:
    if path.resolve() == TEST_EVAL.resolve():
        raise RuntimeError("test_eval scores are forbidden")
    out = set()
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("domain") == "ArxivQA":
            out.add(int(row["line_index"]))
    return out


def page_ready(doc: str, page: int) -> bool:
    stem = cache_name(doc, page)
    patch_path = PATCH_DIR / f"{stem}.pt"
    text_path = TEXT_DIR / f"{stem}.pt"
    return patch_path.is_file() and text_path.is_file() and patch_path.stat().st_size > 0 and text_path.stat().st_size > 0


def page_bundle(doc: str, page: int) -> dict | None:
    stem = cache_name(doc, page)
    patch_path = PATCH_DIR / f"{stem}.pt"
    text_path = TEXT_DIR / f"{stem}.pt"
    if not patch_path.is_file() or not text_path.is_file():
        return None
    patch = torch.load(patch_path, map_location="cpu", weights_only=False)
    text = torch.load(text_path, map_location="cpu", weights_only=False)
    page_size = [float(text["page_w"]), float(text["page_h"])]
    boxes = []
    for bbox in text["boxes"]:
        raw = [float(v) for v in bbox]
        boxes.append({"bbox": raw, "bbox_model": clamp_bbox(scale_bbox_to_model(raw, page_size)), "text_vec": None})
    return {"embedding": patch["embedding"], "boxes": boxes, "page_w": page_size[0], "page_h": page_size[1]}


def iou_mass_scores(patch_scores: torch.Tensor, boxes: list[dict]) -> torch.Tensor:
    """Same iou_mass weights as coverage_region_scores, vectorized over boxes."""
    from layoutpatch.retrieval.propagation import _area, patch_boxes

    if not boxes:
        return patch_scores.new_zeros((0,))
    grid = torch.tensor(patch_boxes(), dtype=torch.float32)
    regs = torch.tensor([box["bbox_model"] for box in boxes], dtype=torch.float32)
    # grid [1024,4], regs [M,4]
    x1 = torch.maximum(grid[:, None, 0], regs[None, :, 0])
    y1 = torch.maximum(grid[:, None, 1], regs[None, :, 1])
    x2 = torch.minimum(grid[:, None, 2], regs[None, :, 2])
    y2 = torch.minimum(grid[:, None, 3], regs[None, :, 3])
    inter = (x2 - x1).clamp_min(0) * (y2 - y1).clamp_min(0)
    patch_area = _area([0.0, 0.0, 14.0, 14.0])
    reg_area = (regs[:, 2] - regs[:, 0]).clamp_min(0) * (regs[:, 3] - regs[:, 1]).clamp_min(0)
    union = patch_area + reg_area[None, :] - inter
    weight = torch.where(union > 0, inter / union, torch.zeros_like(inter))
    return weight.T @ patch_scores.float()


def feats_of(query_vecs, bundle) -> tuple[torch.Tensor, torch.Tensor]:
    if bundle is None or not bundle["boxes"]:
        empty = torch.zeros((0, 6))
        return empty, empty.new_zeros((0,))
    page = normalize(bundle["embedding"].float(), dim=-1)
    image = page[7:] if page.shape[0] == 1031 else page
    sims = query_vecs.float() @ image.T
    scores = sims.reshape(-1, image.shape[0]).amax(dim=0)
    pooled = iou_mass_scores(scores, bundle["boxes"])
    pw, ph = bundle["page_w"], bundle["page_h"]
    page_area = pw * ph
    rows = []
    for box, acc in zip(bundle["boxes"], pooled.tolist(), strict=True):
        x1, y1, x2, y2 = box["bbox"]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        rows.append(
            [
                acc,
                area,
                area / page_area if page_area > 0 else 0.0,
                ((x1 + x2) / 2.0) / pw if pw > 0 else 0.0,
                ((y1 + y2) / 2.0) / ph if ph > 0 else 0.0,
                0.0,
            ]
        )
    feats = torch.tensor(rows, dtype=torch.float32)
    return feats, feats[:, 1]


def load_pairs(indexes: set[int]) -> list[dict]:
    rows = []
    for index, line in enumerate(ANN.open(encoding="utf-8")):
        if index not in indexes:
            continue
        row = json.loads(line)
        if "y_c" in row or "coverage" in row:
            raise RuntimeError("y(c) labels are forbidden")
        pos, neg = row["positive_passages"], row["negative_passages"]
        if not pos or not neg:
            continue
        pos_key = (norm_doc(pos[0]["doc_name"]), int(pos[0]["page_id"]))
        neg_key = (norm_doc(neg[0]["doc_name"]), int(neg[0]["page_id"]))
        if not page_ready(*pos_key) or not page_ready(*neg_key):
            continue
        rows.append({"query": row["query"], "pos": pos_key, "neg": neg_key})
    return rows


def encode_queries(texts: list[str], cache: Path):
    if cache.is_file():
        return torch.load(cache, map_location="cpu", weights_only=False)
    source = REPO / "artifacts/phase2r/arxivqa" / cache.name
    if source.is_file() and cache.name == "fit_queries.pt" and len(texts) > 9241:
        old = torch.load(source, map_location="cpu", weights_only=False)
        if len(old) == 9241:
            return old
    if source.is_file() and cache.name != "fit_queries.pt":
        return torch.load(source, map_location="cpu", weights_only=False)
    raise RuntimeError("local query cache missing; download is forbidden")


def precompute(rows: list[dict], queries, cache_path: Path) -> list[tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]]:
    if cache_path.is_file():
        loaded = torch.load(cache_path, map_location="cpu", weights_only=False)
        print(json.dumps({"precomputed_cache": len(loaded)}), flush=True)
        return loaded
    cache: dict[tuple[str, int], dict] = {}
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
    pos_f, _ = feats_of(query_vecs, page_bundle(*row["pos"]))
    neg_f, _ = feats_of(query_vecs, page_bundle(*row["neg"]))
    if pos_f.numel() == 0 or neg_f.numel() == 0:
        return False
    return float(ranker.score(pos_f).max()) > float(ranker.score(neg_f).max())


def train() -> tuple[BoxRanker, int, int]:
    OUT.mkdir(parents=True, exist_ok=True)
    fit_rows = load_pairs(load_pool(FIT))
    dev_rows = load_pairs(load_pool(DEV))
    print(json.dumps({"fit": len(fit_rows), "dev": len(dev_rows)}), flush=True)
    fit_q = encode_queries([row["query"] for row in fit_rows], OUT / "fit_queries.pt")
    if len(fit_q) != len(fit_rows):
        fit_rows = fit_rows[: len(fit_q)]
    dev_q = encode_queries([row["query"] for row in dev_rows], OUT / "dev_queries.pt")
    fit_ready = precompute(fit_rows, fit_q, OUT / "fit_ready.pt")
    dev_ready = precompute(dev_rows, dev_q, OUT / "dev_ready.pt")
    del fit_q, dev_q, fit_rows, dev_rows
    ranker = BoxRanker()
    opt = torch.optim.Adam(ranker.parameters(), lr=1e-2)
    best = -1.0
    stale = 0
    stopped = 0
    torch.manual_seed(42)
    n_fit = len(fit_ready)
    for epoch in range(1, 21):
        order = torch.randperm(n_fit).tolist()
        ranker.train()
        for start in range(0, len(order), BATCH_SIZE):
            losses = []
            for idx in order[start : start + BATCH_SIZE]:
                pos_f, pos_a, neg_f, neg_a = fit_ready[idx]
                loss = page_pair_loss(ranker, pos_f, pos_a, neg_f, neg_a)
                if loss is not None:
                    losses.append(loss)
            if not losses:
                continue
            total = torch.stack(losses).mean()
            opt.zero_grad()
            total.backward()
            opt.step()
            if torch.cuda.is_available() and torch.cuda.max_memory_allocated() > 12 * 1024**3:
                raise RuntimeError("batch 32 exceeds 12GB")
        ranker.eval()
        with torch.no_grad():
            hits = 0
            for pos_f, _, neg_f, _ in dev_ready:
                if pos_f.numel() == 0 or neg_f.numel() == 0:
                    continue
                hits += int(float(ranker.score(pos_f).max()) > float(ranker.score(neg_f).max()))
        rate = hits / len(dev_ready) if dev_ready else 0.0
        print(json.dumps({"epoch": epoch, "train_dev_hit": round(rate, 6)}), flush=True)
        if rate > best:
            best = rate
            stale = 0
            torch.save(ranker.state_dict(), OUT / "ranker.pt")
        else:
            stale += 1
        stopped = epoch
        if stale >= EARLY_STOP_ROUNDS:
            break
    ranker.load_state_dict(torch.load(OUT / "ranker.pt", map_location="cpu", weights_only=True))
    ranker.eval()
    (OUT / "train_meta.json").write_text(
        json.dumps({"train_questions": len(fit_ready), "early_stop_round": stopped}, ensure_ascii=False),
        encoding="utf-8",
    )
    return ranker, len(fit_ready), stopped


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
    if DEV_EVAL.resolve() == TEST_EVAL.resolve():
        raise RuntimeError("test_eval scores are forbidden")
    ids = query_id_by_index()
    ann = [json.loads(line) for line in EVAL_ANN.open(encoding="utf-8")]
    out = []
    for line in DEV_EVAL.open(encoding="utf-8"):
        row = json.loads(line)
        key = (int(row["annotation_line"]), int(row["question_index"]))
        item = ann[key[0]]
        out.append(
            {
                "query_id": ids[key],
                "doc": Path(item["doc_name"]).stem,
                "question": item["questions"][key[1]],
            }
        )
    return out


def judge(ranker: BoxRanker) -> dict:
    by_id = {row["query_id"]: row for row in pl.read_parquet(PROCESSED / "queries.parquet").to_dicts()}
    labels = pl.read_parquet(PROCESSED / "region_labels.parquet").to_dicts()
    gold = {}
    for row in labels:
        gold.setdefault(row["query_id"], []).append(row)
    nodes = {}
    for row in pl.read_parquet(PROCESSED / "nodes.parquet").to_dicts():
        bbox = json.loads(row["bbox"]) if isinstance(row["bbox"], str) else row["bbox"]
        nodes.setdefault(row["page_id"], []).append({"node_id": row["node_id"], "bbox": [float(v) for v in bbox]})
    hits = pl.read_parquet(RUN).filter(pl.col("rank") <= 5).to_dicts()
    top5 = {}
    for hit in hits:
        top5.setdefault(hit["query_id"], set()).add(hit["page_id"])
    rows = dev_eval_rows()
    texts = [row["question"]["Q"] for row in rows]
    qvecs = encode_queries(texts, OUT / "dev_eval_queries.pt")
    area1 = area5 = base1 = base5 = 0.0
    page_hit = 0
    region_n = 0
    with torch.no_grad():
        for row, vec in zip(rows, qvecs, strict=True):
            question = row["question"]
            query = by_id[row["query_id"]]
            golds = [g for g in gold.get(query["query_id"], []) if g["source"] == "matched"]
            evidence = set(_unjsonify("evidence_page_ids", query["evidence_page_ids"]) or [])
            if top5.get(query["query_id"], set()) & evidence:
                page_hit += 1
            if not golds:
                continue
            region_n += 1
            page_id = golds[0]["page_id"]
            cands = nodes.get(page_id, [])
            page_size = [float(v) for v in golds[0]["page_size"]]
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
            learned = ranker.score(feats).detach().tolist() if feats.numel() else []
            layout_indices = [
                (i, int(page_id.rsplit("_p", 1)[1]), *cand["bbox"]) for i, cand in enumerate(cands)
            ]
            mapping = [{"page": int(g["page_id"].rsplit("_p", 1)[1]), "bbox": g["bbox"]} for g in golds]
            order = rank_all(ranker, feats)
            area1 += float(recall_layout(order[:1], layout_indices, mapping))
            area5 += float(recall_layout(order[:5], layout_indices, mapping))
            base1 += area_at_k(layout_indices, mapping, [0.0 if s == float("-inf") else s for s in coverage_scores(scores, boxes)], 1)
            base5 += area_at_k(layout_indices, mapping, [0.0 if s == float("-inf") else s for s in coverage_scores(scores, boxes)], 5)
            del learned
    n = region_n or 1
    return {
        "region_n": region_n,
        "area1": area1 / n,
        "area5": area5 / n,
        "base1": base1 / n,
        "base5": base5 / n,
        "page_r5": page_hit / len(rows) if rows else 0.0,
        "page_n": len(rows),
    }


def coverage_scores(scores, boxes):
    from layoutpatch.retrieval.region_pooling import coverage_region_scores

    return coverage_region_scores(scores, boxes, "iou_mass")


def assert_caches() -> None:
    patch = [p for p in PATCH_DIR.glob("*.pt") if p.stat().st_size > 0]
    text = [p for p in TEXT_DIR.glob("*.pt") if p.stat().st_size > 0]
    if len(patch) < 8341 or len(text) < 8341:
        raise SystemExit(json.dumps({"status": "stopped", "patch": len(patch), "text": len(text)}))


def main() -> int:
    assert_caches()
    started = time.perf_counter()
    if not (OUT / "ranker.pt").is_file():
        ranker, n_train, stopped = train()
    else:
        meta = json.loads((OUT / "train_meta.json").read_text(encoding="utf-8"))
        ranker = BoxRanker()
        ranker.load_state_dict(torch.load(OUT / "ranker.pt", map_location="cpu", weights_only=True))
        ranker.eval()
        n_train, stopped = meta["train_questions"], meta["early_stop_round"]
    metrics = judge(ranker)
    metrics.update(
        {
            "encoded_pages": 8341,
            "train_questions": n_train,
            "early_stop_round": stopped,
            "hours": round((time.perf_counter() - started) / 3600, 4),
        }
    )
    (OUT / "dev_eval.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUN_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(
        json.dumps({"name": "mmdocir_phase2r_arxivqa_notext", "scheme": "notext", "text_vec": None, "k": 4, "batch": 32, "test_eval": "not_read"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "run_info.json").write_text(json.dumps({"timestamp": stamp, "train_questions": n_train, "test_eval": "not_read"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(f"# notext\n\n- Area@1 {metrics['area1']}\n- Area@5 {metrics['area5']}\n- page {metrics.get('page_hits', metrics.get('page_r5'))}\n", encoding="utf-8")
    shutil.copyfile(RUN, run_dir / "predictions.parquet")
    print(json.dumps({"run": str(run_dir)}, ensure_ascii=False), flush=True)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
