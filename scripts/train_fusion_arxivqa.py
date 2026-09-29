"""First formal ArxivQA fusion training. Page-pair MaxSim only. No y(c).

Does not load ColPali, encode pages, read test_eval, or overwrite ranker.pt.
train_dev is early-stop only. One later dev_eval judgment.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from datetime import datetime
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
import torch
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import bbox_iou, recall_layout
from layoutpatch.io import write_hits
from layoutpatch.layout.correspondence import row_normalize, stack_correspondence
from layoutpatch.layout.nodes import D, TextLayoutEncoder
from layoutpatch.retrieval.fusion.sparse_fusion import SparseLocalFusion
from layoutpatch.retrieval.propagation import patch_scores_from_vectors
from layoutpatch.retrieval.region_pooling import coverage_region_scores
from layoutpatch.retrieval.rerank.box_ranker import area_at_k
from layoutpatch.schemas import RetrievalHit

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_train/hf_hub/annotations_top1_negative/ArxivQA_train.jsonl"
PARQUET = REPO / "data/raw/mmdocir_train/hf_hub/parquet/ArxivQA_filter.parquet"
FIT = REPO / "experiments/s2_splits/train_fit_ids.jsonl"
DEV = REPO / "experiments/s2_splits/train_dev_ids.jsonl"
DEV_EVAL = REPO / "experiments/s2_splits/dev_eval_ids.jsonl"
TEST_EVAL = REPO / "experiments/s2_splits/test_eval_ids.jsonl"
REGION_401 = REPO / "experiments/s2_splits/dev_eval_region_401.txt"
EVAL_ANN = REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
PATCH_DIR = REPO / "artifacts/colpali/mmdocir_train/vidore_colpali"
TEXT_DIR = REPO / "artifacts/bge_m3/mmdocir_train_boxes"
EVAL_PATCH = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
PROCESSED = REPO / "data/processed/mmdocir_evaluation"
FIT_Q = REPO / "artifacts/phase2r/arxivqa/fit_queries.pt"
DEV_Q = REPO / "artifacts/phase2r/arxivqa/dev_queries.pt"
DEV_EVAL_Q = REPO / "artifacts/phase2r/arxivqa/dev_eval_queries.pt"
FROZEN_PRED = REPO / "runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet"
OUT = REPO / "artifacts/fusion/arxivqa"
TMP_W = OUT / "tmp_w"
RUN_ROOT = REPO / "runs/retrieval/mmdocir_fusion_arxivqa"
RANKERS = (
    REPO / "artifacts/phase2r/arxivqa/ranker.pt",
    REPO / "artifacts/phase2r/arxivqa_dude/ranker.pt",
    REPO / "artifacts/phase2r/arxivqa_notext/ranker.pt",
    REPO / "artifacts/phase2r/dude/ranker.pt",
)
SEED = 42
BATCH = 4
FALLBACK_BATCH = 2
LR = 1e-3
MAX_EPOCHS = 8
EARLY_STOP = 2
TEXT_DIM = 32
NUM_TYPES = 6
VRAM_LIMIT = 12 * 1024**3
TYPE_TO_ID = {"text": 1, "title": 2, "table": 3, "image": 4, "interline_equation": 5}
EVAL_TYPE_TO_ID = {
    "paragraph": 1,
    "title": 2,
    "table": 3,
    "table_block": 3,
    "image": 4,
    "figure": 4,
    "interline_equation": 5,
}
GEOM_AREA1 = 0.46726432578302896
GEOM_AREA5 = 0.7726699451254816
FIXED_AREA1 = 0.28594452702337386
FIXED_AREA5 = 0.7441786161356058
EXP009_AREA1 = 0.46726432578302896
EXP009_AREA5 = 0.770560608819146
PAGE_R5_FROZEN = 0.8939759036144578
GEOM_IOU = 214
FIXED_IOU = 130
EXP009_IOU = 214


def refuse_test(path: Path) -> None:
    if path.resolve() == TEST_EVAL.resolve():
        raise RuntimeError("test_eval scores are forbidden")


def norm_doc(name: str) -> str:
    text = str(name)
    return text[:-4] if text.lower().endswith(".pdf") else text


def cache_name(doc: str, page: int) -> str:
    raw = f"{doc}\0{page}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", doc).strip("_")[:40]
    return f"{safe}__p{page}__{digest}"


def page_ready(doc: str, page: int) -> bool:
    stem = cache_name(doc, page)
    patch_path = PATCH_DIR / f"{stem}.pt"
    text_path = TEXT_DIR / f"{stem}.pt"
    return patch_path.is_file() and text_path.is_file() and patch_path.stat().st_size > 0 and text_path.stat().st_size > 0


def load_pool(path: Path) -> set[int]:
    refuse_test(path)
    out = set()
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("domain") == "ArxivQA":
            out.add(int(row["line_index"]))
    return out


def box_counts(pages: set[tuple[str, int]]) -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = {}
    pf = pq.ParquetFile(PARQUET)
    for batch in pf.iter_batches(batch_size=256, columns=["file_name", "page", "layouts"]):
        for name, page, lays in zip(
            batch.column("file_name").to_pylist(),
            batch.column("page").to_pylist(),
            batch.column("layouts").to_pylist(),
            strict=True,
        ):
            key = (norm_doc(name), int(page))
            if key in pages:
                counts[key] = 0 if lays is None else len(lays)
    return counts


def load_pairs(pool: Path) -> list[dict]:
    indexes = load_pool(pool)
    rows = []
    pages: set[tuple[str, int]] = set()
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
        item = {"line_index": index, "pos": pos_key, "neg": neg_key, "query": row["query"]}
        rows.append(item)
        pages.update((pos_key, neg_key))
    counts = box_counts(pages)
    boxed = []
    for item in rows:
        if counts.get(item["pos"], 0) < 1 or counts.get(item["neg"], 0) < 1:
            continue
        item["fit_pos"] = len(boxed)
        boxed.append(item)
    return boxed


def image_patches(doc: str, page: int) -> torch.Tensor:
    payload = torch.load(PATCH_DIR / f"{cache_name(doc, page)}.pt", map_location="cpu", weights_only=False)
    emb = payload["embedding"].float()
    if emb.shape[0] == 1024 + 7:
        emb = emb[7:]
    if emb.shape != (1024, D):
        raise ValueError(f"unexpected P shape {tuple(emb.shape)} for {doc} p{page}")
    return normalize(emb, dim=-1)


def eval_patches(page_id: str) -> torch.Tensor:
    payload = torch.load(EVAL_PATCH / f"{page_id}.pt", map_location="cpu", weights_only=False)
    emb = payload["embedding"].float() if isinstance(payload, dict) else payload.float()
    if emb.shape[0] == 1024 + 7:
        emb = emb[7:]
    if emb.shape != (1024, D):
        raise ValueError(f"unexpected eval P shape {tuple(emb.shape)} for {page_id}")
    return normalize(emb, dim=-1)


def page_from_layouts(lays: list | None, page_size: list[float], type_map: dict[str, int]) -> dict | None:
    if not lays or not page_size or float(page_size[0]) <= 0 or float(page_size[1]) <= 0:
        return None
    boxes = []
    types = []
    for lay in lays:
        raw = lay.get("bbox", lay.get("bbox"))
        if raw is None:
            continue
        bbox = [float(v) for v in raw]
        if len(bbox) != 4:
            continue
        boxes.append(bbox)
        types.append(type_map.get(str(lay.get("type") or lay.get("node_type") or ""), 0))
    if not boxes:
        return None
    result = stack_correspondence(boxes, [float(page_size[0]), float(page_size[1])])
    width, height = float(page_size[0]), float(page_size[1])
    coords = []
    for x1, y1, x2, y2 in boxes:
        coords.append(
            [x1 / width, y1 / height, x2 / width, y2 / height, (x2 - x1) / width, (y2 - y1) / height]
        )
    return {
        "weights": torch.tensor(row_normalize(result.weights), dtype=torch.float32),
        "coords": torch.tensor(coords, dtype=torch.float32),
        "type_ids": torch.tensor(types, dtype=torch.long),
        "boxes": boxes,
        "m": len(boxes),
        "page_size": [width, height],
    }


def tmp_w_path(doc: str, page: int) -> Path:
    return TMP_W / f"{cache_name(doc, page)}.pt"


def load_or_build_layout(doc: str, page: int, built: dict | None = None) -> dict:
    path = tmp_w_path(doc, page)
    if path.is_file():
        payload = torch.load(path, map_location="cpu", weights_only=False)
        payload["patches"] = image_patches(doc, page)
        return payload
    if built is None:
        raise RuntimeError(f"missing layout cache for {doc} p{page}")
    payload = {
        "weights": built["weights"],
        "coords": built["coords"],
        "type_ids": built["type_ids"],
        "m": built["m"],
        "boxes": built["boxes"],
        "page_size": built["page_size"],
    }
    TMP_W.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)
    payload["patches"] = image_patches(doc, page)
    return payload


def prefetch_layouts(keys: set[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    layouts: dict[tuple[str, int], dict] = {}
    missing = {key for key in keys if not tmp_w_path(*key).is_file()}
    raw: dict[tuple[str, int], dict] = {}
    if missing:
        pf = pq.ParquetFile(PARQUET)
        for batch in pf.iter_batches(batch_size=256, columns=["file_name", "page", "page_size", "layouts"]):
            for name, page, page_size, lays in zip(
                batch.column("file_name").to_pylist(),
                batch.column("page").to_pylist(),
                batch.column("page_size").to_pylist(),
                batch.column("layouts").to_pylist(),
                strict=True,
            ):
                key = (norm_doc(name), int(page))
                if key not in missing:
                    continue
                built = page_from_layouts(lays, page_size, TYPE_TO_ID)
                if built is None:
                    continue
                raw[key] = built
                if len(raw) == len(missing):
                    break
            if len(raw) == len(missing):
                break
    for key in keys:
        if tmp_w_path(*key).is_file():
            layouts[key] = load_or_build_layout(*key)
            continue
        if key not in raw:
            raise RuntimeError(f"missing layouts for {key}")
        layouts[key] = load_or_build_layout(*key, raw[key])
    return layouts


def pack_pages(pages: list[dict], device: torch.device) -> dict:
    batch = len(pages)
    max_m = max(page["m"] for page in pages)
    patches = torch.stack([page["patches"] for page in pages], dim=0).to(device)
    weights = torch.zeros(batch, 1024, max_m, device=device)
    coords = torch.zeros(batch, max_m, 6, device=device)
    type_ids = torch.zeros(batch, max_m, dtype=torch.long, device=device)
    valid = torch.zeros(batch, max_m, dtype=torch.bool, device=device)
    text = torch.zeros(batch, max_m, TEXT_DIM, device=device)
    for i, page in enumerate(pages):
        m = page["m"]
        weights[i, :, :m] = page["weights"].to(device)
        coords[i, :m] = page["coords"].to(device)
        type_ids[i, :m] = page["type_ids"].to(device)
        valid[i, :m] = True
    return {
        "patches": patches,
        "weights": weights,
        "coords": coords,
        "type_ids": type_ids,
        "valid": valid,
        "text": text,
        "max_m": max_m,
    }


def maxsim(query: torch.Tensor, patches: torch.Tensor) -> torch.Tensor:
    query = normalize(query.float(), dim=-1)
    patches = normalize(patches.float(), dim=-1)
    return (query @ patches.T).amax(dim=-1).sum()


def page_contrast(pos_score: torch.Tensor, neg_score: torch.Tensor) -> torch.Tensor:
    joined = torch.stack((pos_score, neg_score))
    return -(pos_score - torch.logsumexp(joined, dim=0))


def fuse_pages(encoder: TextLayoutEncoder, fusion: SparseLocalFusion, packed: dict) -> torch.Tensor:
    nodes = encoder(packed["text"], packed["coords"], packed["type_ids"], packed["valid"])
    return fusion(packed["patches"], packed["weights"], nodes)


def pair_loss(
    encoder: TextLayoutEncoder,
    fusion: SparseLocalFusion,
    layouts: dict[tuple[str, int], dict],
    rows: list[dict],
    queries: list[torch.Tensor],
    device: torch.device,
) -> torch.Tensor:
    unique = list(dict.fromkeys(key for row in rows for key in (row["pos"], row["neg"])))
    packed = pack_pages([layouts[key] for key in unique], device)
    fused = fuse_pages(encoder, fusion, packed)
    index = {key: i for i, key in enumerate(unique)}
    losses = []
    for row, query in zip(rows, queries, strict=True):
        pos = fused[index[row["pos"]]]
        neg = fused[index[row["neg"]]]
        losses.append(page_contrast(maxsim(query, pos), maxsim(query, neg)))
    return torch.stack(losses).mean()


def ranker_mtime() -> dict[Path, int]:
    return {path: path.stat().st_mtime_ns for path in RANKERS if path.is_file()}


def assert_rankers(before: dict[Path, int]) -> None:
    after = ranker_mtime()
    for path, stamp in before.items():
        if after.get(path) != stamp:
            raise RuntimeError(f"ranker overwritten: {path}")


def load_queries(path: Path, n: int) -> list[torch.Tensor]:
    if not path.is_file():
        raise RuntimeError(f"missing query cache {path}")
    queries = torch.load(path, map_location="cpu", weights_only=False)
    if len(queries) != n:
        raise RuntimeError(f"query cache {path} has {len(queries)} != {n}")
    return queries


def query_id_by_index() -> dict[tuple[int, int], str]:
    ids = {}
    index = 0
    for line_index, line in enumerate(EVAL_ANN.open(encoding="utf-8")):
        item = json.loads(line)
        for question_index, _question in enumerate(item.get("questions", [])):
            ids[(line_index, question_index)] = f"mmdocir_{index:05d}"
            index += 1
    return ids


def unjson(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def dev_eval_rows() -> list[dict]:
    refuse_test(DEV_EVAL)
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
    if len(out) != 415:
        raise RuntimeError(f"dev_eval rows {len(out)} != 415")
    return out


def within_doc_topk(rows: list[dict], k: int) -> dict[str, list[str]]:
    by_doc = {row["query_id"]: row["doc"] for row in rows}
    grouped: dict[str, list[str]] = {}
    frame = pl.read_parquet(FROZEN_PRED).filter(pl.col("query_id").is_in(list(by_doc))).sort(["query_id", "rank"])
    for hit in frame.iter_rows(named=True):
        qid = hit["query_id"]
        if hit["doc_id"] != by_doc[qid]:
            continue
        grouped.setdefault(qid, [])
        if len(grouped[qid]) < k:
            grouped[qid].append(hit["page_id"])
    return grouped


def geom_order(boxes: list[list[float]]) -> list[int]:
    scored = []
    for i, box in enumerate(boxes):
        area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
        scored.append((-area, i))
    scored.sort()
    return [i for _area, i in scored]


def copy_frozen_hits(run_dir: Path, rows: list[dict]) -> None:
    by_doc = {row["query_id"]: row["doc"] for row in rows}
    kept = []
    seen: dict[str, int] = {}
    frame = pl.read_parquet(FROZEN_PRED).filter(pl.col("query_id").is_in(list(by_doc))).sort(["query_id", "rank"])
    for hit in frame.iter_rows(named=True):
        if hit["doc_id"] != by_doc[hit["query_id"]]:
            continue
        seen[hit["query_id"]] = seen.get(hit["query_id"], 0) + 1
        if seen[hit["query_id"]] > 10:
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


def train_loop(
    fit_rows: list[dict],
    dev_rows: list[dict],
    fit_q: list[torch.Tensor],
    dev_q: list[torch.Tensor],
    layouts: dict[tuple[str, int], dict],
) -> tuple[TextLayoutEncoder, SparseLocalFusion, dict]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("CUDA required")
    encoder = TextLayoutEncoder(text_dim=TEXT_DIM, num_types=NUM_TYPES).to(device)
    fusion = SparseLocalFusion().to(device)
    opt = torch.optim.Adam(list(encoder.parameters()) + list(fusion.parameters()), lr=LR)
    batch = BATCH
    history = []
    best = -1.0
    best_epoch = 0
    stale = 0
    stopped = 0
    peak = 0.0
    torch.manual_seed(SEED)
    random.seed(SEED)
    n_fit = len(fit_rows)
    OUT.mkdir(parents=True, exist_ok=True)
    TMP_W.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, MAX_EPOCHS + 1):
        encoder.train()
        fusion.train()
        order = torch.randperm(n_fit).tolist()
        losses = []
        grads = []
        epoch_t0 = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        start = 0
        while start < n_fit:
            idxs = order[start : start + batch]
            rows = [fit_rows[i] for i in idxs]
            queries = [fit_q[row["fit_pos"]].float().to(device) for row in rows]
            opt.zero_grad(set_to_none=True)
            try:
                loss = pair_loss(encoder, fusion, layouts, rows, queries, device)
                if not torch.isfinite(loss):
                    raise RuntimeError(f"nonfinite loss at epoch {epoch} batch={batch}")
                loss.backward()
                step_grad = 0.0
                for param in list(encoder.parameters()) + list(fusion.parameters()):
                    if param.grad is not None:
                        step_grad += float(param.grad.detach().abs().sum().cpu())
                opt.step()
            except RuntimeError as exc:
                if batch == BATCH and ("out of memory" in str(exc).lower() or "12GB" in str(exc)):
                    print(json.dumps({"batch_fallback": FALLBACK_BATCH, "reason": str(exc)}), flush=True)
                    batch = FALLBACK_BATCH
                    opt.zero_grad(set_to_none=True)
                    torch.cuda.empty_cache()
                    continue
                raise
            used = torch.cuda.max_memory_allocated()
            if used > VRAM_LIMIT:
                if batch == BATCH:
                    print(json.dumps({"batch_fallback": FALLBACK_BATCH, "reason": "vram>12GB"}), flush=True)
                    batch = FALLBACK_BATCH
                    opt.zero_grad(set_to_none=True)
                    torch.cuda.empty_cache()
                    continue
                raise RuntimeError("batch 2 exceeds 12GB")
            peak = max(peak, used / (1024**3))
            losses.append(float(loss.detach().cpu()))
            grads.append(step_grad)
            start += batch
        encoder.eval()
        fusion.eval()
        dev_losses = []
        hits = 0
        with torch.no_grad():
            for begin in range(0, len(dev_rows), batch):
                chunk = dev_rows[begin : begin + batch]
                queries = [dev_q[row["fit_pos"]].float().to(device) for row in chunk]
                unique = list(dict.fromkeys(key for row in chunk for key in (row["pos"], row["neg"])))
                packed = pack_pages([layouts[key] for key in unique], device)
                fused = fuse_pages(encoder, fusion, packed)
                index = {key: i for i, key in enumerate(unique)}
                chunk_losses = []
                for row, query in zip(chunk, queries, strict=True):
                    pos_s = maxsim(query, fused[index[row["pos"]]])
                    neg_s = maxsim(query, fused[index[row["neg"]]])
                    chunk_losses.append(page_contrast(pos_s, neg_s))
                    hits += int(float(pos_s) > float(neg_s))
                dev_losses.append(float(torch.stack(chunk_losses).mean().cpu()))
        train_loss = sum(losses) / len(losses) if losses else math.nan
        dev_loss = sum(dev_losses) / len(dev_losses) if dev_losses else math.nan
        hit_rate = hits / len(dev_rows) if dev_rows else 0.0
        rec = {
            "epoch": epoch,
            "batch": batch,
            "train_loss": train_loss,
            "train_dev_loss": dev_loss,
            "train_dev_page_hit": hit_rate,
            "grad_abs_sum": sum(grads) / len(grads) if grads else 0.0,
            "peak_gb": peak,
            "seconds": time.perf_counter() - epoch_t0,
        }
        history.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        if hit_rate > best:
            best = hit_rate
            best_epoch = epoch
            stale = 0
            torch.save(
                {
                    "encoder": encoder.state_dict(),
                    "fusion": fusion.state_dict(),
                    "epoch": epoch,
                    "note": "formal ArxivQA fusion, not ranker.pt",
                },
                OUT / "fusion.pt",
            )
        else:
            stale += 1
        stopped = epoch
        if stale >= EARLY_STOP:
            break
    payload = torch.load(OUT / "fusion.pt", map_location="cpu", weights_only=False)
    encoder.load_state_dict(payload["encoder"])
    fusion.load_state_dict(payload["fusion"])
    encoder.eval()
    fusion.eval()
    meta = {
        "history": history,
        "best_epoch": best_epoch,
        "stopped": stopped,
        "batch": batch,
        "peak_gb": peak,
        "best_train_dev_page_hit": best,
    }
    return encoder, fusion, meta


def eval_layout_from_nodes(cands: list[dict], page_size: list[float]) -> dict:
    lays = [{"bbox": cand["bbox"], "type": cand.get("node_type", "")} for cand in cands]
    built = page_from_layouts(lays, page_size, EVAL_TYPE_TO_ID)
    if built is None:
        raise RuntimeError("eval page has no boxes")
    return built


def score_boxes(query: torch.Tensor, fused: torch.Tensor, boxes: list[list[float]], page_size: list[float]) -> list[float]:
    patch_scores = patch_scores_from_vectors(query.cpu(), fused.detach().cpu())
    regions = []
    from layoutpatch.layout.correspondence import clamp_bbox, scale_bbox_to_model

    for box in boxes:
        regions.append({"bbox_model": clamp_bbox(scale_bbox_to_model(box, page_size)), "bbox": box})
    raw = coverage_region_scores(patch_scores, regions, "iou_mass")
    return [0.0 if s == float("-inf") else float(s) for s in raw]


def judge(encoder: TextLayoutEncoder, fusion: SparseLocalFusion) -> dict:
    refuse_test(DEV_EVAL)
    region_ids = [line.strip() for line in REGION_401.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(region_ids) != 401:
        raise RuntimeError(f"region id list {len(region_ids)} != 401")
    rows = dev_eval_rows()
    if not DEV_EVAL_Q.is_file():
        raise RuntimeError("missing artifacts/phase2r/arxivqa/dev_eval_queries.pt")
    qvecs = torch.load(DEV_EVAL_Q, map_location="cpu", weights_only=False)
    if len(qvecs) != 415:
        raise RuntimeError(f"dev_eval queries {len(qvecs)} != 415")
    by_id = {row["query_id"]: row for row in pl.read_parquet(PROCESSED / "queries.parquet").to_dicts()}
    gold: dict[str, list] = {}
    for row in pl.read_parquet(PROCESSED / "region_labels.parquet").to_dicts():
        if row["source"] == "matched":
            gold.setdefault(row["query_id"], []).append(row)
    nodes: dict[str, list] = {}
    for row in pl.read_parquet(PROCESSED / "nodes.parquet").to_dicts():
        bbox = unjson(row["bbox"])
        nodes.setdefault(row["page_id"], []).append(
            {"node_id": row["node_id"], "bbox": [float(v) for v in bbox], "node_type": row.get("node_type", "")}
        )
    top1 = within_doc_topk(rows, 1)
    top5 = within_doc_topk(rows, 5)
    top10 = within_doc_topk(rows, 10)
    device = next(encoder.parameters()).device
    encoder.eval()
    fusion.eval()
    area1 = area5 = geom1 = geom5 = fixed1 = fixed5 = 0.0
    iou_hit = geom_iou = fixed_iou = 0
    page_r1 = page_r5_hits = page_r10 = 0
    seen = []
    vs_geom = {"win1": 0, "tie1": 0, "lose1": 0, "win5": 0, "tie5": 0, "lose5": 0}
    vs_max = {"win1": 0, "tie1": 0, "lose1": 0, "win5": 0, "tie5": 0, "lose5": 0}
    with torch.no_grad():
        for row, vec in zip(rows, qvecs, strict=True):
            query = by_id[row["query_id"]]
            evidence = set(unjson(query["evidence_page_ids"]) or [])
            page_r1 += int(bool(set(top1.get(query["query_id"], [])) & evidence))
            page_r5_hits += int(bool(set(top5.get(query["query_id"], [])) & evidence))
            page_r10 += int(bool(set(top10.get(query["query_id"], [])) & evidence))
            if query["query_id"] not in set(region_ids):
                continue
            golds = gold[query["query_id"]]
            page_id = golds[0]["page_id"]
            cands = nodes.get(page_id, [])
            page_size = [float(v) for v in unjson(golds[0]["page_size"])]
            built = eval_layout_from_nodes(cands, page_size)
            built["patches"] = eval_patches(page_id)
            packed = pack_pages([built], device)
            fused = fuse_pages(encoder, fusion, packed)[0]
            boxes = built["boxes"]
            fusion_scores = score_boxes(vec.float(), fused, boxes, page_size)
            raw_scores = score_boxes(vec.float(), built["patches"], boxes, page_size)
            layout = [(i, int(page_id.rsplit("_p", 1)[1]), *box) for i, box in enumerate(boxes)]
            mapping = [{"page": int(g["page_id"].rsplit("_p", 1)[1]), "bbox": unjson(g["bbox"])} for g in golds]
            fusion_order = sorted(range(len(fusion_scores)), key=lambda i: (-fusion_scores[i], i))
            geom = geom_order(boxes)
            a1 = float(recall_layout(fusion_order[:1], layout, mapping))
            a5 = float(recall_layout(fusion_order[:5], layout, mapping))
            g1 = float(recall_layout(geom[:1], layout, mapping))
            g5 = float(recall_layout(geom[:5], layout, mapping))
            f1 = area_at_k(layout, mapping, raw_scores, 1)
            f5 = area_at_k(layout, mapping, raw_scores, 5)
            area1 += a1
            area5 += a5
            geom1 += g1
            geom5 += g5
            fixed1 += f1
            fixed5 += f5
            gold_boxes = [unjson(g["bbox"]) for g in golds]
            def top1_iou(order: list[int]) -> float:
                if not order:
                    return 0.0
                box = boxes[order[0]]
                return max(bbox_iou(box, gb) for gb in gold_boxes)
            if top1_iou(fusion_order) >= 0.5:
                iou_hit += 1
            if top1_iou(geom) >= 0.5:
                geom_iou += 1
            fixed_order = sorted(range(len(raw_scores)), key=lambda i: (-raw_scores[i], i))
            if top1_iou(fixed_order) >= 0.5:
                fixed_iou += 1
            vs_geom["win1" if a1 > g1 else "tie1" if a1 == g1 else "lose1"] += 1
            vs_geom["win5" if a5 > g5 else "tie5" if a5 == g5 else "lose5"] += 1
            vs_max["win1" if a1 > g1 else "tie1" if a1 == g1 else "lose1"] += 1
            vs_max["win5" if a5 > g5 else "tie5" if a5 == g5 else "lose5"] += 1
            seen.append(query["query_id"])
    if len(seen) != 401 or set(seen) != set(region_ids):
        raise RuntimeError(f"region denominator {len(seen)} != 401")
    if abs(geom1 / 401 - GEOM_AREA1) > 1e-6 or abs(geom5 / 401 - GEOM_AREA5) > 1e-6:
        raise RuntimeError(f"geom replay drifted: {geom1/401} {geom5/401}")
    if abs(fixed1 / 401 - FIXED_AREA1) > 1e-6 or abs(fixed5 / 401 - FIXED_AREA5) > 1e-6:
        raise RuntimeError(f"fixed replay drifted: {fixed1/401} {fixed5/401}")
    page_r5 = page_r5_hits / 415
    delta_pp = (page_r5 - PAGE_R5_FROZEN) * 100
    gate = area1 / 401 > GEOM_AREA1 and area5 / 401 > GEOM_AREA5 and abs(delta_pp) <= 0.3
    return {
        "region_n": 401,
        "page_n": 415,
        "page_r1": page_r1 / 415,
        "page_r5": page_r5,
        "page_r10": page_r10 / 415,
        "page_r1_hits": page_r1,
        "page_r5_hits": page_r5_hits,
        "page_r10_hits": page_r10,
        "area1": area1 / 401,
        "area5": area5 / 401,
        "iou_hit": iou_hit,
        "iou_hit_rate": iou_hit / 401,
        "geom_area1": geom1 / 401,
        "geom_area5": geom5 / 401,
        "geom_iou": geom_iou,
        "maxbox_area1": geom1 / 401,
        "maxbox_area5": geom5 / 401,
        "fixed_area1": fixed1 / 401,
        "fixed_area5": fixed5 / 401,
        "fixed_iou": fixed_iou,
        "exp009_area1": EXP009_AREA1,
        "exp009_area5": EXP009_AREA5,
        "exp009_iou": EXP009_IOU,
        "page_r5_frozen": PAGE_R5_FROZEN,
        "page_r5_delta_pp": delta_pp,
        "page_r5_within_0_3pp": abs(delta_pp) <= 0.3,
        "vs_geom_area": vs_geom,
        "vs_max_box": vs_max,
        "dev_gate": gate,
        "test_eval": "not_read",
    }


def write_run(metrics: dict, meta: dict, n_fit: int, n_dev: int, hours: float) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUN_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    rows = dev_eval_rows()
    copy_frozen_hits(run_dir, rows)
    verdict = "通过 dev Gate" if metrics["dev_gate"] else "dev 失败诊断"
    config = {
        "name": "mmdocir_fusion_arxivqa",
        "domain": "ArxivQA",
        "seed": SEED,
        "batch": meta["batch"],
        "lr": LR,
        "max_epochs": MAX_EPOCHS,
        "early_stop_rounds": EARLY_STOP,
        "loss": "page_maxsim_contrast",
        "text": "zeros",
        "test_eval": "not_read",
        "new_pages_encoded": 0,
        "colpali_loaded": False,
        "y_c": False,
    }
    (run_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "run_info.json").write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "train_questions": n_fit,
                "early_stop_questions": n_dev,
                "best_epoch": meta["best_epoch"],
                "stopped": meta["stopped"],
                "batch": meta["batch"],
                "peak_gb": meta["peak_gb"],
                "hours": hours,
                "history": meta["history"],
                "checkpoint": str(OUT / "fusion.pt"),
                "region_denominator": 401,
                "page_denominator": 415,
                "dev_gate": metrics["dev_gate"],
                "verdict": verdict,
                "test_eval": "not_read",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    payload = dict(metrics)
    payload.update(
        {
            "train_questions": n_fit,
            "early_stop_questions": n_dev,
            "best_epoch": meta["best_epoch"],
            "early_stop_round": meta["stopped"],
            "batch": meta["batch"],
            "peak_gb": meta["peak_gb"],
            "hours": hours,
            "history": meta["history"],
        }
    )
    (run_dir / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Fusion ArxivQA dev_eval",
                "",
                f"- 训练 {n_fit} 题。早停 {n_dev} 题。最好第 {meta['best_epoch']} 轮，停在第 {meta['stopped']} 轮。",
                f"- 页级 R@1/5/10：{metrics['page_r1']} / {metrics['page_r5']} / {metrics['page_r10']}。分母 415。",
                f"- Area@1/5：{metrics['area1']} / {metrics['area5']}。IoU@0.5：{metrics['iou_hit']}/401。",
                f"- geom:area Area@1/5：{metrics['geom_area1']} / {metrics['geom_area5']}。",
                f"- 最大框与 geom:area 同一排序。fixed:iou_mass Area@1/5：{metrics['fixed_area1']} / {metrics['fixed_area5']}。",
                f"- 2-R EXP-009 Area@1/5：{EXP009_AREA1} / {EXP009_AREA5}。",
                f"- {verdict}。test_eval 未读取。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return run_dir


def main() -> int:
    if TEST_EVAL.is_file():
        refuse_test(FIT)
        refuse_test(DEV)
        refuse_test(DEV_EVAL)
    before = ranker_mtime()
    started = time.perf_counter()
    fit_rows = load_pairs(FIT)
    dev_rows = load_pairs(DEV)
    if len(fit_rows) != 9241:
        raise RuntimeError(f"train_fit boxed {len(fit_rows)} != 9241")
    if len(dev_rows) != 1592:
        raise RuntimeError(f"train_dev boxed {len(dev_rows)} != 1592")
    if not DEV_Q.is_file():
        raise RuntimeError("missing artifacts/phase2r/arxivqa/dev_queries.pt")
    fit_q = load_queries(FIT_Q, len(fit_rows))
    dev_q = load_queries(DEV_Q, len(dev_rows))
    keys = set()
    for row in fit_rows + dev_rows:
        keys.add(row["pos"])
        keys.add(row["neg"])
    print(json.dumps({"fit": len(fit_rows), "dev": len(dev_rows), "pages": len(keys)}), flush=True)
    layouts = prefetch_layouts(keys)
    encoder, fusion, meta = train_loop(fit_rows, dev_rows, fit_q, dev_q, layouts)
    metrics = judge(encoder, fusion)
    hours = (time.perf_counter() - started) / 3600
    run_dir = write_run(metrics, meta, len(fit_rows), len(dev_rows), hours)
    assert_rankers(before)
    print(json.dumps({"run": str(run_dir), "dev_gate": metrics["dev_gate"], "best_epoch": meta["best_epoch"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


