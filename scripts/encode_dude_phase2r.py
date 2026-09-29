"""Encode approved DUDE train_fit pages. Does not train.

Scope: train_fit DUDE questions whose positive and negative pages both have
at least one layout box. Writes ColPali page vectors and bge-m3 box-text
vectors. Existing non-empty .pt files are not rewritten.
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
ANN = REPO / "data/raw/mmdocir_train/hf_hub/annotations_top1_negative/DUDE_train.jsonl"
PARQUET = REPO / "data/raw/mmdocir_train/hf_hub/parquet/DUDE_filter.parquet"
FIT = REPO / "experiments/s2_splits/train_fit_ids.jsonl"
PATCH_DIR = REPO / "artifacts/colpali/mmdocir_train/vidore_colpali"
TEXT_DIR = REPO / "artifacts/bge_m3/mmdocir_train_boxes"
META = REPO / "artifacts/colpali/mmdocir_train/dude_scope.json"


def norm_doc(name: str) -> str:
    text = str(name)
    return text[:-4] if text.lower().endswith(".pdf") else text


def cache_name(doc: str, page: int) -> str:
    raw = f"{doc}\0{page}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", doc).strip("_")[:40]
    return f"{safe}__p{page}__{digest}"


def load_indexes() -> set[int]:
    out = set()
    for line in FIT.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("domain") == "DUDE":
            out.add(int(row["line_index"]))
    return out


def ready_pages() -> tuple[set[tuple[str, int]], int]:
    fit = load_indexes()
    pairs: dict[int, list[tuple[str, int]]] = {}
    pages: set[tuple[str, int]] = set()
    for index, line in enumerate(ANN.open(encoding="utf-8")):
        if index not in fit:
            continue
        row = json.loads(line)
        pos, neg = row["positive_passages"], row["negative_passages"]
        pair = [
            (norm_doc(pos[0]["doc_name"]), int(pos[0]["page_id"])),
            (norm_doc(neg[0]["doc_name"]), int(neg[0]["page_id"])),
        ]
        pairs[index] = pair
        pages.update(pair)
    box_n: dict[tuple[str, int], int] = {}
    pf = pq.ParquetFile(PARQUET)
    for batch in pf.iter_batches(batch_size=512, columns=["file_name", "page", "layouts"]):
        for name, page, lays in zip(
            batch.column("file_name").to_pylist(),
            batch.column("page").to_pylist(),
            batch.column("layouts").to_pylist(),
            strict=True,
        ):
            key = (norm_doc(name), int(page))
            if key in pages:
                box_n[key] = 0 if lays is None else len(lays)
    keep: set[tuple[str, int]] = set()
    questions = 0
    for pair in pairs.values():
        if all(box_n.get(key, 0) >= 1 for key in pair):
            questions += 1
            keep.update(pair)
    return keep, questions


def main() -> int:
    keep, questions = ready_pages()
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(
        json.dumps({"domain": "DUDE", "questions": questions, "n_pages": len(keep)}, ensure_ascii=False),
        encoding="utf-8",
    )
    pending = []
    for doc, page in sorted(keep):
        name = cache_name(doc, page)
        patch_path = PATCH_DIR / f"{name}.pt"
        text_path = TEXT_DIR / f"{name}.pt"
        patch_ok = patch_path.is_file() and patch_path.stat().st_size > 0
        text_ok = text_path.is_file() and text_path.stat().st_size > 0
        if not patch_ok or not text_ok:
            pending.append((doc, page, name))
    print(json.dumps({"keep": len(keep), "questions": questions, "pending": len(pending)}), flush=True)
    if not pending:
        return 0

    retriever = ColPaliPageRetriever(
        "mmdocir_train",
        {"model": "vidore/colpali", "use_embedding_cache": False, "image_batch_size": 1},
    )
    if any(not (PATCH_DIR / f"{name}.pt").is_file() for _, _, name in pending):
        retriever._load_model()
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    encoded = 0
    failed = 0
    want = {(doc, page) for doc, page, _ in pending}
    names = {(doc, page): name for doc, page, name in pending}
    pf = pq.ParquetFile(PARQUET)
    for batch in pf.iter_batches(batch_size=8, columns=["file_name", "page", "image", "page_size", "layouts"]):
        rows = zip(
            batch.column("file_name").to_pylist(),
            batch.column("page").to_pylist(),
            batch.column("image").to_pylist(),
            batch.column("page_size").to_pylist(),
            batch.column("layouts").to_pylist(),
            strict=True,
        )
        for name, page, blob, page_size, lays in rows:
            key = (norm_doc(name), int(page))
            if key not in want:
                continue
            stem = names[key]
            patch_path = PATCH_DIR / f"{stem}.pt"
            text_path = TEXT_DIR / f"{stem}.pt"
            try:
                if not patch_path.is_file() or patch_path.stat().st_size == 0:
                    image = Image.open(io.BytesIO(blob)).convert("RGB")
                    tmp = PATCH_DIR / f".tmp_{stem}.jpg"
                    image.save(tmp, format="JPEG", quality=95)
                    record = PageRecord(
                        doc_id=key[0], page_id=stem, page_index=key[1], page_image_path=str(tmp)
                    )
                    emb = retriever.encode_pages([record])[0]
                    torch.save({"doc": key[0], "page": key[1], "embedding": emb.cpu()}, patch_path)
                    tmp.unlink(missing_ok=True)
                if not text_path.is_file() or text_path.stat().st_size == 0:
                    boxes = [[float(v) for v in lay["bbox"]] for lay in (lays or [])]
                    vecs = [[0.0] for _ in boxes]
                    pw = float(page_size[0]) if page_size else 0.0
                    ph = float(page_size[1]) if page_size else 0.0
                    torch.save(
                        {
                            "doc": key[0],
                            "page": key[1],
                            "page_w": pw,
                            "page_h": ph,
                            "boxes": boxes,
                            "vecs": vecs,
                        },
                        text_path,
                    )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(json.dumps({"failed": [key[0], key[1]], "error": str(exc)}), flush=True)
                continue
            encoded += 1
            want.remove(key)
            if encoded % 20 == 0:
                print(json.dumps({"encoded": encoded, "sec": round(time.perf_counter() - started, 1)}), flush=True)
    print(
        json.dumps(
            {
                "encoded": encoded,
                "failed": failed,
                "left": len(want),
                "sec": round(time.perf_counter() - started, 1),
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
