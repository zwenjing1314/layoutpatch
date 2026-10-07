"""D训练/内部验证节点缓存：仅既有本地BGE-M3，不编码图像。"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import polars as pl  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from layoutpatch.retrieval.route_v2_layout import TEXT_RULE, node_text, page_layout  # noqa: E402
from layoutpatch.retrieval.route_v2_query_cache import file_sha256, text_sha256  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts/route_v2_data/d_nodes_v1"
REV = "5617a9f61b028005a4858fdac845db406aefb181"
MODEL = Path.home() / f".cache/huggingface/hub/models--BAAI--bge-m3/snapshots/{REV}"
ENCODING = {"model": "BAAI/bge-m3", "revision": REV, "dimension": 1024, "pooling": "CLS",
            "normalize_embeddings": True, "max_seq_length": 512, "batch_size": 2,
            "dtype": "float32", "device": "cuda:0", "rule": TEXT_RULE, "frozen": True}
SOURCE = {"dataset_revision": "bdcb36ecb3eee73667180ee3fb24fe433f6dd2a4",
          "url": "https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset/blob/bdcb36ecb3eee73667180ee3fb24fe433f6dd2a4/README.md",
          "section": "Miscellaneous Document Files / 3. MMDocIR Layout-related files",
          "text": "for text/equation layouts only, raw text extracted using OCR tools",
          "ocr_text": "for table/figure layouts only, raw text extracted using OCR tools",
          "vlm_text": "for table/figure layouts only, text description using VLM",
          "consumer": "https://github.com/mmdocrag/MMDocIR/blob/main/encode.py#get_layouts",
          "limitations": "Publisher gives OCR provenance but not per-node OCR engine/version; title follows official non-table/image text branch."}


def dump(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def prepare_inputs(dev_only=False):
    region = REPO / "artifacts/route_v2_data/regions_v1"
    source = REPO / "data/raw/mmdocir_evaluation/MMDocIR_layouts.parquet"
    audit = json.loads((region / "audit.json").read_text("utf-8"))
    if file_sha256(source) != audit["inputs"][source.relative_to(REPO).as_posix()]:
        raise ValueError("layout source hash mismatch")
    # 条件下推只物化train/val；节点按页面完整保留，gold不进入节点构造。
    selection = ((pl.col("role") == "source_dev") & pl.col("eval_ready")) if dev_only else (
        ((pl.col("role") == "source_train") & pl.col("local_loss_ready") & ~pl.col("page_overlap_excluded")) |
        ((pl.col("role") == "source_val") & pl.col("eval_ready")))
    units = pl.scan_parquet(region / "units.parquet").filter(selection).select("doc_id", "page", "role").collect().to_dicts()
    role_of = {}
    hashes = {str(source.relative_to(REPO)): file_sha256(source)}
    for role in (("source_dev",) if dev_only else ("source_train", "source_val")):
        p = REPO / f"experiments/route_v2_splits/data-roles-v1/{role}_ids.jsonl"
        hashes[str(p.relative_to(REPO))] = file_sha256(p)
        for line in p.read_text("utf-8").splitlines():
            r = json.loads(line)
            if r["doc_id"] in role_of and role_of[r["doc_id"]] != role:
                raise ValueError("role leakage")
            role_of[r["doc_id"]] = role
    pages = {(u["doc_id"], u["page"]): u["role"] for u in units}
    if any(role_of[d] != role for (d, _), role in pages.items()):
        raise ValueError("unit/manifest role mismatch")
    wanted = pl.DataFrame([{"doc_id": d, "page": p} for d, p in sorted(pages)])
    candidates = pl.scan_parquet(region / "candidates.parquet").join(wanted.lazy(), on=["doc_id", "page"], how="semi").collect()
    raw = pl.scan_parquet(source).filter(pl.col("doc_name").is_in(list(role_of))).select(
        "doc_name", "page_id", "layout_id", "type", "bbox", "page_size", "text", "ocr_text", "vlm_text"
    ).rename({"doc_name": "doc_id", "page_id": "page"}).join(wanted.lazy(), on=["doc_id", "page"], how="semi").collect()
    lookup = {(r["doc_id"], r["page"], r["layout_id"]): r for r in raw.to_dicts()}
    if len(lookup) != len(raw) or len(candidates) != len(raw):
        raise ValueError("raw/candidate ID coverage mismatch")
    rows, counts = [], {}
    for c in candidates.sort(["doc_id", "page", "layout_id"]).to_dicts():
        key = c["doc_id"], c["page"], c["layout_id"]
        r = lookup[key]
        if r["bbox"] != c["bbox"] or r["page_size"] != c["page_size"] or r["type"] != c["raw_type"]:
            raise ValueError(f"candidate metadata mismatch: {key}")
        text, field = node_text(r)
        role = pages[key[:2]]
        tag = role + "/" + r["type"]
        counter = counts.setdefault(tag, Counter())
        counter["nodes"] += 1
        for f in ("text", "ocr_text", "vlm_text"):
            counter[f + "_nonempty"] += bool((r[f] or "").strip())
        counter["selected_nonempty"] += bool(text)
        rows.append({**r, "role": role, "selected_text": text, "selected_field": field,
                     "node_id": json.dumps(key, ensure_ascii=False), "text_sha256": text_sha256(text)})
    for name in ("units.parquet", "candidates.parquet", "audit.json"):
        hashes[str((region / name).relative_to(REPO))] = file_sha256(region / name)
    return rows, {"source_evidence": SOURCE, "input_sha256": hashes, "counts": counts,
                  "pages": len(pages), "nodes": len(rows), "nonempty": sum(bool(r["selected_text"]) for r in rows),
                  "scope": "source_dev eval-ready pages; all candidates" if dev_only else "source_train loss-ready pages and source_val eval-ready pages; all candidates on each page",
                  "source_dev_accessed": dev_only, "external_test_accessed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-only", action="store_true")
    dev_only = parser.parse_args().dev_only
    output = OUT.with_name("d_nodes_dev_v1") if dev_only else OUT
    preserved = {}
    reference = None
    if dev_only:
        reference = json.loads((OUT / "manifest.json").read_text("utf-8"))
        if file_sha256(OUT / "manifest.json") != "4514800ee81cad1343635e27bbe6edad73e880e44f30af32224ffed7ec2160d6":
            raise ValueError("train/val node manifest changed")
        preserved = {str(OUT / "manifest.json"): file_sha256(OUT / "manifest.json")}
        for page in reference["pages"]:
            path = OUT / page["file"]
            if file_sha256(path) != page["sha256"]:
                raise ValueError("train/val node cache changed")
            preserved[str(path)] = page["sha256"]
        if reference["encoding"] != ENCODING:
            raise ValueError("encoding rule differs from train/val")
    started = time.perf_counter()
    run = OUT.parent / "d_nodes_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=False)
    info = {"status": "started", "encoding": ENCODING}
    try:
        if output.exists():
            raise FileExistsError(f"existing node cache preserved; explicit validation required: {output}")
        rows, audit = prepare_inputs(dev_only)
        dump(run / "text_audit.json", audit)
        print(json.dumps({"stage": "text_audit", **{k: v for k, v in audit.items() if k not in {"input_sha256", "source_evidence"}}}), flush=True)
        required = ["config.json", "modules.json", "tokenizer.json", "1_Pooling/config.json"]
        missing = [p for p in required if not (MODEL / p).is_file()]
        if not any((MODEL / p).is_file() for p in ("model.safetensors", "pytorch_model.bin")):
            missing.append("model.safetensors OR pytorch_model.bin")
        if missing:
            raise FileNotFoundError(f"required local encoder files missing: {missing}; {MODEL}")
        identity = {"path": str(MODEL), "file_sha256": {str(p.relative_to(MODEL)): file_sha256(p) for p in MODEL.rglob("*") if p.is_file()}}
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        torch.cuda.reset_peak_memory_stats()
        model = SentenceTransformer(str(MODEL), local_files_only=True, device="cuda:0").float().eval()
        model.requires_grad_(False)
        model.max_seq_length = ENCODING["max_seq_length"]
        if model.get_sentence_embedding_dimension() != 1024:
            raise ValueError("encoder dimension mismatch")
        identity["class"] = type(model).__name__
        if reference is not None and identity != reference["identity"]:
            raise ValueError("encoder identity differs from train/val")
        info["frozen_encoder_parameters"] = sum(p.numel() for p in model.parameters())
        vectors = torch.zeros(len(rows), 1024)
        indices = [i for i, r in enumerate(rows) if r["selected_text"]]
        t = time.perf_counter()
        truncated = 0
        for start in range(0, len(indices), 2):
            ids = indices[start:start + 2]
            texts = [rows[i]["selected_text"] for i in ids]
            lengths = [len(model.tokenizer(t, truncation=False)["input_ids"]) for t in texts]
            truncated += sum(n > 512 for n in lengths)
            with torch.inference_mode():
                encoded = model.encode(texts, batch_size=2, convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=False).cpu()
            if not bool(torch.isfinite(encoded).all()) or not bool(((encoded.norm(dim=-1) - 1).abs() < 1e-4).all()):
                raise FloatingPointError("invalid text embeddings")
            vectors[ids] = encoded
            for i, length in zip(ids, lengths, strict=True):
                rows[i]["token_length_before_truncation"] = length
            if torch.cuda.max_memory_reserved() > 12 * 1024**3:
                raise RuntimeError("VRAM budget exceeded")
            if start % 500 == 0:
                print(json.dumps({"encoded": start + len(ids), "total": len(indices), "seconds": time.perf_counter() - t}), flush=True)
        info.update({"encoding_seconds": time.perf_counter() - t, "truncated_nodes": truncated,
                     "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()})
        staging = run / "nodes.partial"
        staging.mkdir()
        pages = {}
        for i, r in enumerate(rows):
            pages.setdefault((r["doc_id"], r["page"]), []).append(i)
        manifest = []
        for n, ((doc, page), ids) in enumerate(sorted(pages.items())):
            rs = [rows[i] for i in ids]
            layout = page_layout(rs, vectors[ids])
            payload = {"doc_id": doc, "page": page, "role": rs[0]["role"], "layout": layout,
                       "nodes": [{k: r.get(k) for k in ("node_id", "layout_id", "type", "bbox", "page_size", "selected_field", "text_sha256", "token_length_before_truncation")}
                                 | {"text_missing": not bool(r["selected_text"])} for r in rs]}
            name = f"page_{n:05d}.pt"
            torch.save(payload, staging / name)
            manifest.append({"doc_id": doc, "page": page, "role": rs[0]["role"], "file": name,
                             "sha256": file_sha256(staging / name), "nodes": len(rs)})
        dump(staging / "manifest.json", {"schema": "route-v2-d-nodes-v1", "encoding": ENCODING, "identity": identity,
                                         "audit": audit, "pages": manifest, "run_info": info})
        for path, digest in preserved.items():
            if file_sha256(Path(path)) != digest:
                raise ValueError("train/val node cache changed during dev encoding")
        info["train_val_preserved"] = bool(preserved)
        info["missing_nodes"] = len(rows) - len(indices)
        if output.exists():
            raise FileExistsError("refusing overwrite")
        staging.rename(output)
        info["status"] = "completed"
        info["cache"] = str(output)
        info["manifest_sha256"] = file_sha256(output / "manifest.json")
    except Exception as exc:
        info["status"] = "failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        dump(run / "run_info.json", info)
        print(json.dumps({"run": str(run), **info}), flush=True)


if __name__ == "__main__":
    main()
