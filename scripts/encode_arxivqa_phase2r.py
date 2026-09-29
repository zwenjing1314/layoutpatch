"""Encode approved ArxivQA pages. Not a training license by itself.

Scope: train_fit + train_dev ArxivQA questions whose positive and negative
pages both have at least one layout box. Writes ColPali page vectors and
bge-m3 box-text vectors. Existing .pt files are not rewritten.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from pathlib import Path

import pyarrow.parquet as pq
import torch
from PIL import Image

from layoutpatch.retrieval.colpali import ColPaliPageRetriever
from layoutpatch.schemas import PageRecord

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_train/hf_hub/annotations_top1_negative/ArxivQA_train.jsonl"
PARQUET = REPO / "data/raw/mmdocir_train/hf_hub/parquet/ArxivQA_filter.parquet"
FIT = REPO / "experiments/s2_splits/train_fit_ids.jsonl"
DEV = REPO / "experiments/s2_splits/train_dev_ids.jsonl"
PATCH_DIR = REPO / "artifacts/colpali/mmdocir_train/vidore_colpali"
TEXT_DIR = REPO / "artifacts/bge_m3/mmdocir_train_boxes"
META = REPO / "artifacts/colpali/mmdocir_train/arxivqa_scope.json"


def norm_doc(name: str) -> str:
    text = str(name)
    return text[:-4] if text.lower().endswith(".pdf") else text


def cache_name(doc: str, page: int) -> str:
    raw = f"{doc}\0{page}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", doc).strip("_")[:40]
    return f"{safe}__p{page}__{digest}"


def load_indexes(path: Path) -> set[int]:
    out = set()
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if row["domain"] == "ArxivQA":
            out.add(int(row["line_index"]))
    return out


def wanted_pages() -> tuple[set[tuple[str, int]], dict]:
    fit = load_indexes(FIT)
    dev = load_indexes(DEV)
    pages: set[tuple[str, int]] = set()
    fit_q = dev_q = 0
    for index, line in enumerate(ANN.open(encoding="utf-8")):
        pool = "fit" if index in fit else "dev" if index in dev else ""
        if not pool:
            continue
        row = json.loads(line)
        pos, neg = row["positive_passages"], row["negative_passages"]
        if not pos or not neg:
            continue
        pair = [
            (norm_doc(pos[0]["doc_name"]), int(pos[0]["page_id"])),
            (norm_doc(neg[0]["doc_name"]), int(neg[0]["page_id"])),
        ]
        pages.update(pair)
        if pool == "fit":
            fit_q += 1
        else:
            dev_q += 1
    return pages, {"fit_q_before_box": fit_q, "dev_q_before_box": dev_q}


def main() -> int:
    pages, counts = wanted_pages()
    box_n: dict[tuple[str, int], int] = {}
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
                box_n[key] = 0 if lays is None else len(lays)
    keep = {key for key in pages if box_n.get(key, 0) >= 1}
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(
        json.dumps({"n_pages": len(keep), **counts}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps({"keep": len(keep)}), flush=True)

    pending = []
    for doc, page in sorted(keep):
        name = cache_name(doc, page)
        if not (PATCH_DIR / f"{name}.pt").is_file() or not (TEXT_DIR / f"{name}.pt").is_file():
            pending.append((doc, page, name))
    print(json.dumps({"pending": len(pending), "done": len(keep) - len(pending)}), flush=True)
    if not pending:
        return 0

    retriever = ColPaliPageRetriever(
        "mmdocir_train",
        {
            "model": "vidore/colpali",
            "use_embedding_cache": False,
            "image_batch_size": 1,
        },
    )
    need_patch = any(not (PATCH_DIR / f"{name}.pt").is_file() for _, _, name in pending)
    if need_patch:
        retriever._load_model()
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    encoded = 0
    pf = pq.ParquetFile(PARQUET)
    want = {(doc, page) for doc, page, _ in pending}
    names = {(doc, page): name for doc, page, name in pending}
    for batch in pf.iter_batches(batch_size=8, columns=["file_name", "page", "image", "page_size", "layouts"]):
        rows = list(
            zip(
                batch.column("file_name").to_pylist(),
                batch.column("page").to_pylist(),
                batch.column("image").to_pylist(),
                batch.column("page_size").to_pylist(),
                batch.column("layouts").to_pylist(),
                strict=True,
            )
        )
        for name, page, blob, page_size, lays in rows:
            key = (norm_doc(name), int(page))
            if key not in want:
                continue
            stem = names[key]
            patch_path = PATCH_DIR / f"{stem}.pt"
            text_path = TEXT_DIR / f"{stem}.pt"
            if not patch_path.is_file():
                image = Image.open(io.BytesIO(blob)).convert("RGB")
                tmp = PATCH_DIR / f".tmp_{stem}.jpg"
                image.save(tmp, format="JPEG", quality=95)
                record = PageRecord(doc_id=key[0], page_id=stem, page_index=key[1], page_image_path=str(tmp))
                emb = retriever.encode_pages([record])[0]
                torch.save({"doc": key[0], "page": key[1], "embedding": emb.cpu()}, patch_path)
                tmp.unlink(missing_ok=True)
            if not text_path.is_file():
                boxes = []
                for lay in lays or []:
                    boxes.append([float(v) for v in lay["bbox"]])
                # Train parquet layouts have type+bbox only. No OCR string, so every box text vector is 0.
                vecs = [[0.0] for _ in boxes]
                pw = float(page_size[0]) if page_size else 0.0
                ph = float(page_size[1]) if page_size else 0.0
                torch.save(
                    {"doc": key[0], "page": key[1], "page_w": pw, "page_h": ph, "boxes": boxes, "vecs": vecs},
                    text_path,
                )
            encoded += 1
            want.remove(key)
            if encoded % 20 == 0:
                print(json.dumps({"encoded": encoded, "sec": round(time.perf_counter() - started, 1)}), flush=True)
    print(json.dumps({"encoded": encoded, "sec": round(time.perf_counter() - started, 1), "left": len(want)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
