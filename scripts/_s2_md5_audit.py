"""S2 page-image md5 reuse audit. Read-only. Stop condition is reuse_count > 0.

Hashes raw page-image bytes. Does not decode images and does not touch gold boxes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

EVAL_PAGES = Path("data/raw/mmdocir_evaluation/MMDocIR_pages.parquet")
TRAIN_DIR = Path("data/raw/mmdocir_train/hf_hub/parquet")
OUT = Path("experiments/s2_exclusion/md5_reuse.json")
BATCH = 256


def digest(payload: bytes | None) -> str | None:
    if not payload:
        return None
    return hashlib.md5(payload).hexdigest()


def main() -> None:
    eval_index: dict[str, list[dict]] = {}
    eval_rows = 0
    eval_empty = 0
    eval_file = pq.ParquetFile(EVAL_PAGES)
    for batch in eval_file.iter_batches(batch_size=BATCH, columns=["doc_name", "passage_id", "image_binary"]):
        docs = batch.column("doc_name").to_pylist()
        pages = batch.column("passage_id").to_pylist()
        images = batch.column("image_binary").to_pylist()
        for doc, page, image in zip(docs, pages, images, strict=True):
            eval_rows += 1
            key = digest(image)
            if key is None:
                eval_empty += 1
                continue
            eval_index.setdefault(key, []).append({"doc_name": doc, "passage_id": page})
    print(f"eval_hashed={len(eval_index)} rows={eval_rows} empty={eval_empty}", flush=True)

    hits: list[dict] = []
    train_rows = 0
    train_empty = 0
    for path in sorted(TRAIN_DIR.glob("*_filter.parquet")):
        train_file = pq.ParquetFile(path)
        for batch in train_file.iter_batches(batch_size=BATCH, columns=["file_name", "page", "domain", "image"]):
            names = batch.column("file_name").to_pylist()
            pages = batch.column("page").to_pylist()
            domains = batch.column("domain").to_pylist()
            images = batch.column("image").to_pylist()
            for name, page, domain, image in zip(names, pages, domains, images, strict=True):
                train_rows += 1
                key = digest(image)
                if key is None:
                    train_empty += 1
                    continue
                matched = eval_index.get(key)
                if matched:
                    hits.append(
                        {
                            "md5": key,
                            "train_domain": domain,
                            "train_file_name": name,
                            "train_page": page,
                            "eval_hits": matched,
                        }
                    )
        print(f"scanned={path.name} train_rows={train_rows} hits={len(hits)}", flush=True)

    report = {
        "hash": "md5 of raw image bytes; no decode",
        "eval_rows": eval_rows,
        "eval_empty": eval_empty,
        "eval_unique_md5": len(eval_index),
        "train_rows": train_rows,
        "train_empty": train_empty,
        "reuse_count": len(hits),
        "reuse_unique_md5": len({hit["md5"] for hit in hits}),
        "hits": hits,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"reuse_count={len(hits)} wrote={OUT}", flush=True)


if __name__ == "__main__":
    main()
