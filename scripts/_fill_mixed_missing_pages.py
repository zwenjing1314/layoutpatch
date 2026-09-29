"""Fill only the pages missing from the mixed ArxivQA+DUDE cache.

Does not rewrite existing .pt files. Empty box text is stored as 0.
"""

from __future__ import annotations

import io
import json
import time

import pyarrow.parquet as pq
import torch
from PIL import Image

import encode_dude_phase2r as dude
import train_phase2r_arxivqa_dude as mixed
from layoutpatch.retrieval.colpali import ColPaliPageRetriever
from layoutpatch.schemas import PageRecord

PARQUETS = {
    "ArxivQA": dude.REPO / "data/raw/mmdocir_train/hf_hub/parquet/ArxivQA_filter.parquet",
    "DUDE": dude.PARQUET,
}


def missing_pages() -> list[tuple[str, str, int, str]]:
    _, _, fit_missing = mixed.load_pairs(mixed.FIT)
    _, _, dev_missing = mixed.load_pairs(mixed.DEV)
    seen = set()
    out = []
    for domain, doc, page in fit_missing + dev_missing:
        key = (domain, doc, int(page))
        if key in seen:
            continue
        seen.add(key)
        stem = mixed.cache_name(doc, int(page))
        patch = mixed.PATCH_DIR / f"{stem}.pt"
        text = mixed.TEXT_DIR / f"{stem}.pt"
        if patch.is_file() and text.is_file() and patch.stat().st_size > 0 and text.stat().st_size > 0:
            continue
        out.append(key + (stem,))
    return out


def main() -> int:
    pending = missing_pages()
    print(json.dumps({"name_mismatch": 0, "to_encode": len(pending)}), flush=True)
    if not pending:
        return 0
    retriever = ColPaliPageRetriever(
        "mmdocir_train",
        {"model": "vidore/colpali", "use_embedding_cache": False, "image_batch_size": 1},
    )
    retriever._load_model()
    written = 0
    failed = []
    by_domain: dict[str, dict] = {}
    for domain, doc, page, stem in pending:
        by_domain.setdefault(domain, {})[(doc, page)] = stem
    started = time.perf_counter()
    for domain, want in by_domain.items():
        pf = pq.ParquetFile(PARQUETS[domain])
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
                key = (mixed.norm_doc(name), int(page))
                if key not in want:
                    continue
                stem = want.pop(key)
                patch_path = mixed.PATCH_DIR / f"{stem}.pt"
                text_path = mixed.TEXT_DIR / f"{stem}.pt"
                try:
                    if not patch_path.is_file() or patch_path.stat().st_size == 0:
                        image = Image.open(io.BytesIO(blob)).convert("RGB")
                        tmp = mixed.PATCH_DIR / f".tmp_{stem}.jpg"
                        image.save(tmp, format="JPEG", quality=95)
                        record = PageRecord(doc_id=key[0], page_id=stem, page_index=key[1], page_image_path=str(tmp))
                        emb = retriever.encode_pages([record])[0]
                        torch.save({"doc": key[0], "page": key[1], "embedding": emb.cpu()}, patch_path)
                        tmp.unlink(missing_ok=True)
                    if not text_path.is_file() or text_path.stat().st_size == 0:
                        boxes = [[float(v) for v in lay["bbox"]] for lay in (lays or [])]
                        torch.save(
                            {
                                "doc": key[0],
                                "page": key[1],
                                "page_w": float(page_size[0]) if page_size else 0.0,
                                "page_h": float(page_size[1]) if page_size else 0.0,
                                "boxes": boxes,
                                "vecs": [[0.0] for _ in boxes],
                            },
                            text_path,
                        )
                    written += 1
                except Exception as exc:  # noqa: BLE001
                    failed.append([domain, key[0], key[1], str(exc)])
        failed.extend([[domain, doc, page, "not_found_in_parquet"] for doc, page in want])
    print(json.dumps({"written": written, "failed": len(failed), "sec": round(time.perf_counter() - started, 1)}), flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
