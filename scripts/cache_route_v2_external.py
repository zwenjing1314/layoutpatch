"""Encode the fixed SciEGQA external inputs into an isolated cache.

This entry point only builds page, query, and candidate-node vectors. It does
not load comparison checkpoints, score candidates, compute an oracle, or alter
any source cache.
"""
from __future__ import annotations

import gc
import inspect
import json
import os
import shutil
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch  # noqa: E402
import yaml  # noqa: E402
from colpali_engine.models import ColPali, ColPaliProcessor  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from layoutpatch.retrieval.colpali_layout import split_page_embedding  # noqa: E402
from layoutpatch.retrieval.route_v2_layout import external_node_text, page_layout  # noqa: E402
from layoutpatch.retrieval.route_v2_query_cache import (  # noqa: E402
    file_sha256,
    unpad_embedding,
    validate_embedding,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/tools/route_v2_external_encoding_v1.yaml"
RUN_ROOT = ROOT / "artifacts/route_v2_external/encoding_v1"
EXPECTED_CANDIDATE_SHA = "19dbd7257d696bca19859fd1a53e69520e3380590d5fe0445fac61d8d2518263"
EXPECTED_PAGE_SHAPE = (1031, 128)


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return file_sha256(path)


def model_snapshot(model: str, patterns: list[str]) -> tuple[Path, dict]:
    path = Path(snapshot_download(model, local_files_only=True, allow_patterns=patterns))
    files = {str(p.relative_to(path)): sha256(p) for p in sorted(path.rglob("*")) if p.is_file()}
    if not any(name.endswith(".safetensors") for name in files):
        raise FileNotFoundError(f"local model weights absent: {model}")
    return path, {"model": model, "revision": path.name, "path": str(path), "file_sha256": files}


def bge_snapshot(revision: str) -> tuple[Path, dict]:
    path = Path.home() / f".cache/huggingface/hub/models--BAAI--bge-m3/snapshots/{revision}"
    files = {str(p.relative_to(path)): sha256(p) for p in sorted(path.rglob("*")) if p.is_file()} if path.is_dir() else {}
    if not any(name.endswith((".safetensors", ".bin")) for name in files):
        raise FileNotFoundError(f"local model weights absent: BAAI/bge-m3 revision {revision}")
    return path, {"model": "BAAI/bge-m3", "revision": revision, "path": str(path), "file_sha256": files}


def load_external_inputs(cfg: dict) -> tuple[dict, list[dict], list[dict], dict[str, list[dict]]]:
    source = ROOT / cfg["input"]["root"]
    annotations = source / cfg["input"]["annotations"]
    manifest_path = ROOT / cfg["input"]["fixed_manifest"]
    audit_path = ROOT / cfg["input"]["final_audit"]
    candidates_path = ROOT / cfg["input"]["final_candidates"]
    if sha256(annotations) != cfg["input"]["annotations_sha256"]:
        raise ValueError("external annotations hash mismatch")
    if sha256(manifest_path) != cfg["input"]["fixed_manifest_sha256"]:
        raise ValueError("fixed page manifest hash mismatch")
    if sha256(candidates_path) != EXPECTED_CANDIDATE_SHA or sha256(candidates_path) != cfg["input"]["final_candidates_sha256"]:
        raise ValueError("final candidates hash mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "ready" or audit.get("failed_pages") != 0:
        raise ValueError("final external audit is not ready")
    if (audit.get("candidate_rows"), audit.get("candidate_key_count")) != (9746, 9746):
        raise ValueError("final candidate count mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = sorted(manifest["pages"], key=lambda row: (row["doc_id"], row["pdf_page_index"]))
    if len(pages) != 837:
        raise ValueError("fixed page count mismatch")
    results = {row["page_id"]: row for row in audit["page_results"]}
    if set(results) != {row["page_id"] for row in pages}:
        raise ValueError("audit page coverage mismatch")
    for row in results.values():
        if row["status"] != "passed" or not row.get("image", {}).get("path"):
            raise ValueError("audit page image path is not ready")
    questions = []
    with annotations.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            row = json.loads(line)
            questions.append({"query_id": f"sciegqa_{index:05d}", "text": row["query"], "doc_id": row["doc_name"].removesuffix(".pdf")})
    if len(questions) != 1623:
        raise ValueError("external question count mismatch")
    nodes: dict[str, list[dict]] = defaultdict(list)
    with candidates_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            nodes[row["page_id"]].append(row)
    if set(nodes) != set(results) or sum(map(len, nodes.values())) != 9746:
        raise ValueError("candidate page coverage mismatch")
    for page_id, rows in nodes.items():
        rows.sort(key=lambda row: row["layout_id"])
        if [row["layout_id"] for row in rows] != sorted({row["layout_id"] for row in rows}):
            raise ValueError(f"candidate order/uniqueness mismatch: {page_id}")
        for row in rows:
            text, _ = external_node_text(row)
            if text and not isinstance(text, str):
                raise ValueError("external node text is not a string")
    return manifest, pages, questions, nodes


def image_paths(audit: dict) -> dict[str, Path]:
    return {row["page_id"]: ROOT / row["image"]["path"] for row in audit["page_results"]}


def identity_for_colpali(snapshot: Path, processor) -> dict:
    adapter_path = snapshot / "adapter_config.json"
    base = None
    if adapter_path.is_file():
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
        base_path, base = model_snapshot(adapter["base_model_name_or_path"], ["config.json", "*.safetensors", "*.safetensors.index.json"])
        base["path"] = str(base_path)
    return {"adapter": {"path": str(snapshot), "files_sha256": {str(p.relative_to(snapshot)): sha256(p) for p in snapshot.rglob("*") if p.is_file()}},
            "base_model": base, "processor_class": type(processor).__name__,
            "tokenizer_class": type(processor.tokenizer).__name__, "pad_token_id": processor.tokenizer.pad_token_id,
            "packages": {name: version(name) for name in ("torch", "transformers", "colpali-engine", "peft")},
            "implementation_sha256": {cls.__name__: sha256(Path(inspect.getfile(cls))) for cls in (ColPali, ColPaliProcessor)}}


def gpu_stats() -> dict:
    return {"peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()}


def encode_pages(cfg, pages, paths, out, report):
    snapshot, model_identity = model_snapshot("vidore/colpali", ["config.json", "adapter_config.json", "*.safetensors", "*.safetensors.index.json"])
    processor = ColPaliProcessor.from_pretrained(str(snapshot), local_files_only=True)
    identity = identity_for_colpali(snapshot, processor)
    model = ColPali.from_pretrained(str(snapshot), local_files_only=True, torch_dtype=torch.bfloat16, device_map="cuda:0").eval()
    model.requires_grad_(False)
    from PIL import Image

    started = time.perf_counter()
    first_checked = False
    records = []
    for index, page in enumerate(pages):
        page_id = page["page_id"]
        image_path = paths[page_id]
        if not image_path.is_file():
            raise FileNotFoundError(f"missing audited page image: {image_path}")
        with Image.open(image_path) as image:
            batch = processor.process_images([image.convert("RGB")]).to("cuda:0")
        with torch.inference_mode():
            encoded = model(**batch)[0].detach().cpu().contiguous()
        if tuple(encoded.shape) != EXPECTED_PAGE_SHAPE or not bool(torch.isfinite(encoded).all()):
            raise ValueError(f"invalid page embedding shape/value: {page_id}")
        patches, prompt = split_page_embedding(encoded)
        if patches.shape != (1024, 128) or prompt.shape != (7, 128):
            raise ValueError("page token split mismatch")
        if not first_checked:
            first_checked = True
            report["first_batch_checks"] = {"page_id": page_id, "shape": list(encoded.shape), "patch_shape": list(patches.shape), "prompt_shape": list(prompt.shape), "finite": True}
        name = f"{index:05d}_{page_id}.pt"
        torch.save({"page_id": page_id, "doc_id": page["doc_id"], "page_number": page["page_number"], "embedding": encoded, "image_path": str(image_path), "image_sha256": sha256(image_path)}, out / name)
        records.append({"page_id": page_id, "file": f"pages/{name}", "sha256": sha256(out / name), "shape": list(encoded.shape), "image_path": str(image_path), "image_sha256": sha256(image_path)})
        if index == 0 or (index + 1) % 100 == 0:
            print(json.dumps({"stage": "pages", "completed": index + 1, "total": 837, **gpu_stats()}), flush=True)
    report["page_encoding_seconds"] = time.perf_counter() - started
    report["page_gpu"] = gpu_stats()
    return model, processor, model_identity, identity, records


def encode_queries(cfg, questions, processor, model, out, report):
    started = time.perf_counter()
    embeddings, tokens = {}, {}
    batch_size = cfg["encoding"]["query_batch_size"]
    first_checked = False
    for start in range(0, len(questions), batch_size):
        selected = questions[start:start + batch_size]
        batch = processor.process_queries([row["text"] for row in selected]).to("cuda:0")
        with torch.inference_mode():
            encoded = model(**batch)
        for row, emb, mask, ids in zip(selected, encoded, batch["attention_mask"], batch["input_ids"], strict=True):
            result = unpad_embedding(emb, mask)
            input_ids = ids[mask.bool()].cpu().tolist()
            if input_ids[-10:] != [processor.tokenizer.pad_token_id] * 10:
                raise ValueError(f"query augmentation token mismatch: {row['query_id']}")
            embeddings[row["query_id"]] = result
            tokens[row["query_id"]] = {"input_ids": input_ids, "attention_mask": [1] * len(result), "shape": list(result.shape), "dtype": str(result.dtype)}
            if not first_checked:
                validate_embedding(result)
                first_checked = True
                report["first_query_checks"] = {"query_id": row["query_id"], "shape": list(result.shape), "finite": True, "padding_removed": True}
        del batch, encoded
        if start == 0 or start + len(selected) == len(questions) or start % 200 == 0:
            print(json.dumps({"stage": "queries", "completed": start + len(selected), "total": len(questions), **gpu_stats()}), flush=True)
    payload = {"schema": "route-v2-external-query-cache-v1", "model": "vidore/colpali", "embeddings": embeddings, "tokens": tokens}
    torch.save(payload, out)
    report["query_encoding_seconds"] = time.perf_counter() - started
    report["query_gpu"] = gpu_stats()
    return payload


def encode_nodes(cfg, nodes, out, report):
    snapshot, model_identity = bge_snapshot(cfg["models"]["bge_m3"]["revision"])
    model = SentenceTransformer(str(snapshot), local_files_only=True, device="cuda:0").float().eval()
    model.requires_grad_(False)
    model.max_seq_length = 512
    if model.get_sentence_embedding_dimension() != 1024:
        raise ValueError("BGE-M3 dimension mismatch")
    vectors, metadata = {}, {}
    nonempty = truncated = 0
    started = time.perf_counter()
    all_rows = [row for page_rows in nodes.values() for row in page_rows]
    for start in range(0, len(all_rows), cfg["encoding"]["node_batch_size"]):
        selected = all_rows[start:start + cfg["encoding"]["node_batch_size"]]
        texts = []
        lengths = []
        sources = []
        for row in selected:
            text, source = external_node_text(row)
            texts.append(text)
            sources.append(source)
            nonempty += bool(text)
            length = len(model.tokenizer(text, truncation=False)["input_ids"]) if text else 0
            truncated += length > 512
            lengths.append(length)
        vectors_batch = torch.zeros((len(selected), 1024), dtype=torch.float32)
        active = [i for i, text in enumerate(texts) if text]
        if active:
            with torch.inference_mode():
                encoded = model.encode([texts[i] for i in active], batch_size=len(active), convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=False).float().cpu().clone()
            vectors_batch[active] = encoded
        for row, vector, text, source, length in zip(selected, vectors_batch, texts, sources, lengths, strict=True):
            metadata[row["candidate_id"]] = {"page_id": row["page_id"], "layout_id": row["layout_id"], "text_source": source, "text_missing": not bool(text), "token_length_before_truncation": length}
            if text and (not bool(torch.isfinite(vector).all()) or abs(float(vector.norm()) - 1) > 1e-4):
                raise FloatingPointError("invalid BGE-M3 embedding")
            vectors[row["candidate_id"]] = vector
        if start == 0 or start + len(selected) == len(all_rows) or start % 500 == 0:
            print(json.dumps({"stage": "nodes", "completed": start + len(selected), "total": len(all_rows), **gpu_stats()}), flush=True)
    page_records = []
    for index, (page_id, rows) in enumerate(sorted(nodes.items())):
        text = torch.stack([vectors[row["candidate_id"]] for row in rows])
        layout = page_layout(rows, text)
        name = f"{index:05d}_{page_id}.pt"
        torch.save({"page_id": page_id, "layout_id_order": [row["layout_id"] for row in rows], "layout": layout,
                    "nodes": [metadata[row["candidate_id"]] for row in rows]}, out / name)
        page_records.append({"page_id": page_id, "file": f"nodes/{name}", "sha256": sha256(out / name), "nodes": len(rows), "missing_text": sum(metadata[row["candidate_id"]]["text_missing"] for row in rows)})
    report.update({"node_encoding_seconds": time.perf_counter() - started, "node_gpu": gpu_stats(), "nonempty_text_nodes": nonempty, "missing_text_nodes": len(all_rows) - nonempty, "truncated_text_nodes": truncated})
    return model_identity, page_records


def find_resumable_run() -> Path | None:
    runs = RUN_ROOT / "runs"
    if not runs.is_dir():
        return None
    for path in sorted(runs.iterdir(), reverse=True):
        info = path / "run_info.json"
        if not info.is_file() or not (path / "queries.pt").is_file():
            continue
        report = json.loads(info.read_text(encoding="utf-8"))
        if report.get("status") == "failed" and len(list((path / "pages").glob("*.pt"))) == 837:
            return path
    return None


def reuse_colpali(run, pages, paths, questions):
    snapshot, model_identity = model_snapshot("vidore/colpali", ["config.json", "adapter_config.json", "*.safetensors", "*.safetensors.index.json"])
    processor = ColPaliProcessor.from_pretrained(str(snapshot), local_files_only=True)
    identity = identity_for_colpali(snapshot, processor)
    records = []
    for index, page in enumerate(pages):
        name = f"{index:05d}_{page['page_id']}.pt"
        path = run / "pages" / name
        payload = torch.load(path, map_location="cpu", weights_only=True)
        embedding = payload["embedding"]
        if payload["page_id"] != page["page_id"] or tuple(embedding.shape) != EXPECTED_PAGE_SHAPE or not bool(torch.isfinite(embedding).all()):
            raise ValueError("resumed page cache identity/shape mismatch")
        split_page_embedding(embedding)
        if payload["image_sha256"] != sha256(paths[page["page_id"]]):
            raise ValueError("resumed page image hash mismatch")
        records.append({"page_id": page["page_id"], "file": f"pages/{name}", "sha256": sha256(path), "shape": list(embedding.shape), "image_path": str(paths[page["page_id"]]), "image_sha256": payload["image_sha256"]})
    query_payload = torch.load(run / "queries.pt", map_location="cpu", weights_only=True)
    expected = {row["query_id"] for row in questions}
    if set(query_payload.get("embeddings", {})) != expected or set(query_payload.get("tokens", {})) != expected:
        raise ValueError("resumed query cache ID mismatch")
    for qid, embedding in query_payload["embeddings"].items():
        validate_embedding(embedding)
        record = query_payload["tokens"][qid]
        if record["shape"] != list(embedding.shape) or record["attention_mask"] != [1] * len(embedding):
            raise ValueError("resumed query token alignment mismatch")
        if record["input_ids"][-10:] != [processor.tokenizer.pad_token_id] * 10:
            raise ValueError("resumed query augmentation mismatch")
    return model_identity, identity, records, query_payload


def reuse_nodes(run: Path, nodes: dict[str, list[dict]], cfg: dict) -> tuple[dict, list[dict]]:
    _, identity = bge_snapshot(cfg["models"]["bge_m3"]["revision"])
    records = []
    for index, (page_id, rows) in enumerate(sorted(nodes.items())):
        name = f"{index:05d}_{page_id}.pt"
        path = run / "nodes" / name
        payload = torch.load(path, map_location="cpu", weights_only=True)
        expected_order = [row["layout_id"] for row in rows]
        if payload.get("page_id") != page_id or payload.get("layout_id_order") != expected_order:
            raise ValueError("resumed node identity/order mismatch")
        layout = payload["layout"]
        count = len(rows)
        expected_shapes = {"text": (count, 1024), "coords": (count, 6), "types": (count,), "mask": (count,), "W_raw": (1024, count), "W_attn": (1024, count), "cover_mass": (1024, 1)}
        if any(tuple(layout[key].shape) != shape for key, shape in expected_shapes.items()):
            raise ValueError("resumed page_layout shape mismatch")
        if not all(bool(torch.isfinite(value).all()) for value in layout.values() if value.is_floating_point()):
            raise ValueError("resumed node layout has nonfinite values")
        missing = [i for i, row in enumerate(payload["nodes"]) if row["text_missing"]]
        if missing and bool((layout["text"][missing] != 0).any()):
            raise ValueError("resumed missing-text vector is nonzero")
        records.append({"page_id": page_id, "file": f"nodes/{name}", "sha256": sha256(path), "nodes": count, "missing_text": len(missing)})
    return identity, records


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; external encoding stopped")
    started = time.perf_counter()
    resume = find_resumable_run()
    run = resume or (RUN_ROOT / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    if resume is None:
        run.mkdir(parents=True, exist_ok=False)
        (run / "pages").mkdir()
        (run / "nodes").mkdir()
    report = {"status": "started", "config": str(CONFIG.relative_to(ROOT)), "run": str(run.relative_to(ROOT)), "resumed": resume is not None, "scoring": False, "oracle": False, "training": False, "checkpoint_comparison": False, "source_cache_overwrite": False}
    try:
        manifest, pages, questions, nodes = load_external_inputs(cfg)
        audit = json.loads((ROOT / cfg["input"]["final_audit"]).read_text(encoding="utf-8"))
        paths = image_paths(audit)
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        if resume is not None:
            page_model_identity, page_identity, page_records, query_payload = reuse_colpali(run, pages, paths, questions)
            report["resumed_checks"] = {"pages": len(page_records), "queries": len(query_payload["embeddings"]), "input_and_image_hashes": True, "shape_and_tokens": True}
        else:
            page_model, processor, page_model_identity, page_identity, page_records = encode_pages(cfg, pages, paths, run / "pages", report)
            query_payload = encode_queries(cfg, questions, processor, page_model, run / "queries.pt", report)
            del page_model, processor
            gc.collect()
            torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        if len(list((run / "nodes").glob("*.pt"))) == 837:
            node_model, node_records = reuse_nodes(run, nodes, cfg)
            report["resumed_node_checks"] = {"pages": len(node_records), "candidates": sum(row["nodes"] for row in node_records), "identity_order_shapes_finite_missing_zero": True}
        else:
            node_model, node_records = encode_nodes(cfg, nodes, run / "nodes", report)
        report["model_identities"] = {"colpali": {"model": page_model_identity, "resolved": page_identity}, "bge_m3": node_model}
        report["counts"] = {"pages": len(page_records), "queries": len(query_payload["embeddings"]), "candidates": sum(record["nodes"] for record in node_records)}
        if report["counts"] != {"pages": 837, "queries": 1623, "candidates": 9746}:
            raise ValueError("encoded count mismatch")
        input_paths = {"annotations": ROOT / cfg["input"]["root"] / cfg["input"]["annotations"], "fixed_manifest": ROOT / cfg["input"]["fixed_manifest"], "final_audit": ROOT / cfg["input"]["final_audit"], "final_candidates": ROOT / cfg["input"]["final_candidates"]}
        cache_manifest = {"schema": "route-v2-external-encoding-v1", "config": cfg, "input_sha256": {key: sha256(path) for key, path in input_paths.items()}, "candidate_sha256": sha256(input_paths["final_candidates"]), "pages": page_records, "queries": {"file": "queries.pt", "sha256": sha256(run / "queries.pt"), "ids": sorted(query_payload["embeddings"])}, "nodes": node_records, "model_identities": report["model_identities"], "run_info": str((run / "run_info.json").relative_to(ROOT))}
        dump(run / "manifest.json", cache_manifest)
        report["manifest_sha256"] = sha256(run / "manifest.json")
        report["status"] = "ready"
    except BaseException as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        report["disk_free_bytes_end"] = shutil.disk_usage(ROOT).free
        report["git_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() or "unknown"
        dump(run / "run_info.json", report)
        print(json.dumps({key: value for key, value in report.items() if key not in {"model_identities"}}, ensure_ascii=False), flush=True)
        print(f"run_dir: {run}", flush=True)
    if report.get("status") != "ready":
        raise RuntimeError("external encoding failed; cache is not ready")


if __name__ == "__main__":
    main()
