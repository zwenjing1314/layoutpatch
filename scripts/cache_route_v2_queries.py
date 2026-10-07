"""仅用本地冻结 ColPali 编码 data-roles-v1 来源问题，不加载页面或外部测试。"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch  # noqa: E402
from colpali_engine.models import ColPali, ColPaliProcessor  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402

from layoutpatch.retrieval.route_v2_query_cache import (  # noqa: E402
    MODEL,
    QUERY_SCHEMA,
    file_sha256,
    source_queries,
    unpad_embedding,
    validate_cache,
)

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "artifacts/route_v2_data/query_cache_v1"
OUT = ROOT / "source_queries.pt"
ENCODING = {"batch_size": 2, "first_batch_size": 1, "device": "cuda:0", "dtype": "torch.bfloat16",
            "process_queries": "defaults", "pooling": None, "drop_rows": "attention=0 and all-zero",
            "frozen": True, "eval": True, "inference_mode": True, "seed": 42}


def snapshot_identity(model: str) -> tuple[Path, dict]:
    path = Path(snapshot_download(model, local_files_only=True,
                                  allow_patterns=["config.json", "adapter_config.json", "*.safetensors", "*.safetensors.index.json"]))
    index = path / "model.safetensors.index.json"
    if index.exists():
        shards = set(json.loads(index.read_text("utf-8"))["weight_map"].values())
        if any(not (path / shard).is_file() for shard in shards):
            raise FileNotFoundError(f"local model shard missing: {model}")
    files = {p.name: file_sha256(p) for p in sorted(path.iterdir()) if p.is_file()}
    if not any(n.endswith(".safetensors") for n in files):
        raise FileNotFoundError(f"local model weights absent: {model} ({path})")
    return path, {"model": model, "revision": path.name, "path": str(path), "file_sha256": files}


def main() -> None:
    started = time.perf_counter()
    run = ROOT / "runs" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run.mkdir(parents=True, exist_ok=False)
    report = {"status": "started", "output": str(OUT), "encoding": ENCODING,
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()}
    try:
        rows, provenance = source_queries(
            REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl",
            REPO / "experiments/route_v2_splits/data-roles-v1")
        print(json.dumps({"stage": "manifest_verified", "queries": len(rows),
                          "role_counts": provenance["role_counts"]}), flush=True)
        snap, model_identity = snapshot_identity(MODEL)
        adapter = json.loads((snap / "adapter_config.json").read_text("utf-8"))
        _, base_identity = snapshot_identity(adapter["base_model_name_or_path"])
        processor = ColPaliProcessor.from_pretrained(str(snap), local_files_only=True)
        identity = {"model": model_identity, "base_model": base_identity,
                    "processor_class": type(processor).__name__, "tokenizer_class": type(processor.tokenizer).__name__,
                    "pad_token_id": processor.tokenizer.pad_token_id,
                    "packages": {name: version(name) for name in ("torch", "transformers", "colpali-engine", "peft")},
                    "implementation_sha256": {cls.__name__: file_sha256(Path(inspect.getfile(cls)))
                                              for cls in (ColPali, ColPaliProcessor, type(processor).__mro__[1])}}
        if OUT.exists():
            payload = torch.load(OUT, map_location="cpu", weights_only=True)
            report["integrity"] = validate_cache(payload, provenance, identity, ENCODING)
            report["status"] = "reused"
        else:
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA unavailable; encoding stopped")
            torch.manual_seed(42)
            torch.cuda.reset_peak_memory_stats()
            load_start = time.perf_counter()
            model = ColPali.from_pretrained(str(snap), local_files_only=True,
                                           torch_dtype=torch.bfloat16, device_map="cuda:0").eval()
            model.requires_grad_(False)
            report["model_load_seconds"] = time.perf_counter() - load_start
            report["gpu"] = torch.cuda.get_device_name(0)
            payload = {"schema": QUERY_SCHEMA, "model": MODEL, "provenance": provenance,
                       "identity": identity, "encoding": ENCODING, "embeddings": {}, "tokens": {}}
            batches = []
            start = 0
            encode_start = time.perf_counter()
            while start < len(rows):
                size = 1 if start == 0 else ENCODING["batch_size"]
                selected = rows[start:start + size]
                batch = processor.process_queries([r["text"] for r in selected]).to("cuda:0")
                torch.cuda.synchronize()
                batch_start = time.perf_counter()
                with torch.inference_mode():
                    encoded = model(**batch)
                torch.cuda.synchronize()
                elapsed = time.perf_counter() - batch_start
                for row, emb, mask, ids in zip(selected, encoded, batch["attention_mask"], batch["input_ids"], strict=True):
                    result = unpad_embedding(emb, mask)
                    input_ids = ids[mask.bool()].cpu().tolist()
                    if input_ids[-10:] != [processor.tokenizer.pad_token_id] * 10:
                        raise ValueError(f"augmentation token mismatch: {row['query_id']}")
                    qid = row["query_id"]
                    payload["embeddings"][qid] = result
                    payload["tokens"][qid] = {"input_ids": input_ids, "attention_mask": [1] * len(result),
                                               "shape": list(result.shape), "dtype": str(result.dtype),
                                               "embedding_sha256": hashlib.sha256(result.view(torch.uint8).numpy().tobytes()).hexdigest()}
                start += len(selected)
                batches.append({"completed": start, "size": len(selected), "seconds": elapsed})
                if len(batches) <= 2 or start % 100 == 1 or start == len(rows):
                    print(json.dumps({**batches[-1], "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                                      "peak_reserved_bytes": torch.cuda.max_memory_reserved()}), flush=True)
                del encoded, batch
            report["encoding_seconds"] = time.perf_counter() - encode_start
            report["batches"] = batches
            report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            report["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
            report["integrity"] = validate_cache(payload, provenance, identity, ENCODING)
            # 写入独立临时文件并回读校验；Windows rename 在目标存在时拒绝覆盖。
            temporary = run / "source_queries.pt.partial"
            payload["run_info"] = {k: v for k, v in report.items() if k != "batches"}
            torch.save(payload, temporary)
            validate_cache(torch.load(temporary, map_location="cpu", weights_only=True), provenance, identity, ENCODING)
            if OUT.exists():
                raise FileExistsError(f"refusing overwrite: {OUT}")
            temporary.rename(OUT)
            report["status"] = "created"
        report["cache_sha256"] = file_sha256(OUT)
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        (run / "run_info.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "batches"}, ensure_ascii=False), flush=True)
        print(f"run_dir: {run}", flush=True)


if __name__ == "__main__":
    main()
