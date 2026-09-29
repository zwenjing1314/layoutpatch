"""Encode approved train_dev DUDE pages. Does not train.

Scope: train_dev DUDE questions whose positive and negative pages both have
at least one layout box. Expected after that filter: 292 questions, 422 pages.
Reuses encode_dude_phase2r.py document-name, cache-name, and output dirs.
Existing non-empty .pt files are not rewritten. Empty box text is stored as 0.
"""

from __future__ import annotations

import json
import time

import pyarrow.parquet as pq

import encode_dude_phase2r as dude

DEV = dude.REPO / "experiments/s2_splits/train_dev_ids.jsonl"
OUT = dude.REPO / "experiments/s2_splits/dude_train_dev_pages.json"


def ready_pages() -> tuple[set[tuple[str, int]], int]:
    indexes: set[int] = set()
    for line in DEV.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("domain") == "DUDE":
            indexes.add(int(row["line_index"]))
    pairs: dict[int, list[tuple[str, int]]] = {}
    pages: set[tuple[str, int]] = set()
    for index, line in enumerate(dude.ANN.open(encoding="utf-8")):
        if index not in indexes:
            continue
        row = json.loads(line)
        pos, neg = row["positive_passages"], row["negative_passages"]
        pair = [
            (dude.norm_doc(pos[0]["doc_name"]), int(pos[0]["page_id"])),
            (dude.norm_doc(neg[0]["doc_name"]), int(neg[0]["page_id"])),
        ]
        pairs[index] = pair
        pages.update(pair)
    box_n: dict[tuple[str, int], int] = {}
    pf = pq.ParquetFile(dude.PARQUET)
    for batch in pf.iter_batches(batch_size=512, columns=["file_name", "page", "layouts"]):
        for name, page, lays in zip(
            batch.column("file_name").to_pylist(),
            batch.column("page").to_pylist(),
            batch.column("layouts").to_pylist(),
            strict=True,
        ):
            key = (dude.norm_doc(name), int(page))
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
    if questions != 292 or len(keep) != 422:
        print(json.dumps({"stop": "page_count", "questions": questions, "n_pages": len(keep)}), flush=True)
        return 2
    pending = []
    for doc, page in sorted(keep):
        name = dude.cache_name(doc, page)
        patch_path = dude.PATCH_DIR / f"{name}.pt"
        text_path = dude.TEXT_DIR / f"{name}.pt"
        patch_ok = patch_path.is_file() and patch_path.stat().st_size > 0
        text_ok = text_path.is_file() and text_path.stat().st_size > 0
        if not patch_ok or not text_ok:
            pending.append((doc, page, name, patch_ok, text_ok))
    print(json.dumps({"questions": questions, "n_pages": len(keep), "pending": len(pending)}), flush=True)

    import io

    import torch
    from PIL import Image

    from layoutpatch.retrieval.colpali import ColPaliPageRetriever
    from layoutpatch.schemas import PageRecord

    need_patch = any(not patch_ok for _, _, _, patch_ok, _ in pending)
    retriever = None
    if need_patch:
        retriever = ColPaliPageRetriever(
            "mmdocir_train",
            {"model": "vidore/colpali", "use_embedding_cache": False, "image_batch_size": 1},
        )
        retriever._load_model()
    dude.PATCH_DIR.mkdir(parents=True, exist_ok=True)
    dude.TEXT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    new_colpali = 0
    new_bge = 0
    failed: list[list] = []
    want = {(doc, page) for doc, page, _, _, _ in pending}
    names = {(doc, page): (name, patch_ok, text_ok) for doc, page, name, patch_ok, text_ok in pending}
    if want:
        pf = pq.ParquetFile(dude.PARQUET)
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
                key = (dude.norm_doc(name), int(page))
                if key not in want:
                    continue
                stem, patch_ok, text_ok = names[key]
                patch_path = dude.PATCH_DIR / f"{stem}.pt"
                text_path = dude.TEXT_DIR / f"{stem}.pt"
                try:
                    if not patch_ok:
                        assert retriever is not None
                        image = Image.open(io.BytesIO(blob)).convert("RGB")
                        tmp = dude.PATCH_DIR / f".tmp_{stem}.jpg"
                        image.save(tmp, format="JPEG", quality=95)
                        record = PageRecord(
                            doc_id=key[0], page_id=stem, page_index=key[1], page_image_path=str(tmp)
                        )
                        emb = retriever.encode_pages([record])[0]
                        torch.save({"doc": key[0], "page": key[1], "embedding": emb.cpu()}, patch_path)
                        tmp.unlink(missing_ok=True)
                        new_colpali += 1
                    if not text_ok:
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
                        new_bge += 1
                except Exception as exc:  # noqa: BLE001
                    failed.append([key[0], key[1], str(exc)])
                    print(json.dumps({"failed": failed[-1]}), flush=True)
                    continue
                want.remove(key)
                done = new_colpali + new_bge
                if done and done % 20 == 0:
                    print(json.dumps({"new_colpali": new_colpali, "new_bge": new_bge, "sec": round(time.perf_counter() - started, 1)}), flush=True)
        for key in sorted(want):
            failed.append([key[0], key[1], "not_found_in_parquet"])
    OUT.write_text(
        json.dumps(
            {
                "questions": 292,
                "n_pages": 422,
                "new_colpali": new_colpali,
                "new_bge": new_bge,
                "failed": len(failed),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"new_colpali": new_colpali, "new_bge": new_bge, "failed": len(failed), "left": len(want)}), flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
