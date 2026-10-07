"""route-v2 问题缓存的精确映射、来源绑定与完整性验证。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import torch

from layoutpatch.datasets.route_v2_split import document_id

QUERY_SCHEMA = "route-v2-query-cache-v1"
MODEL = "vidore/colpali"
SOURCE_ROLES = ("source_train", "source_val", "source_dev")


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_queries(annotation: Path, split: Path) -> tuple[list[dict], dict]:
    """按原始物理行/题内下标定位；隔离题只核对 ID，不提取问题文本。"""
    proof = json.loads((split / "split_proof.json").read_text("utf-8"))
    if not proof.get("data_identity_ready") or proof["identity_units_crossing_roles"]:
        raise ValueError("data-roles-v1 identity gate failed")
    if any(proof["pairwise_document_intersections"].values()):
        raise ValueError("data-roles-v1 roles overlap")
    hashes = {name: file_sha256(split / name) for name in proof["file_sha256"]}
    if hashes != proof["file_sha256"]:
        raise ValueError("data-roles-v1 manifest hash mismatch")
    origin = json.loads((split / "identity_inputs.json").read_text("utf-8"))
    ann_hash = file_sha256(annotation)
    ann_key = "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
    if origin["provenance"]["inputs"][ann_key] != ann_hash:
        raise ValueError("annotation hash differs from data-roles-v1 source")
    manifests = []
    for role in (*SOURCE_ROLES, "quarantine"):
        rows = [json.loads(line) for line in (split / f"{role}_ids.jsonl").read_text("utf-8").splitlines()]
        ids = (split / f"{role}_query_ids.txt").read_text("utf-8").splitlines()
        if len(ids) != len(rows) or set(ids) != {r["query_id"] for r in rows}:
            raise ValueError(f"query ID list mismatch: {role}")
        if any(r["role"] != role for r in rows):
            raise ValueError(f"manifest role mismatch: {role}")
        manifests.extend(rows)
    by_ref = {}
    ids = set()
    for row in manifests:
        ref = row["source_ref"]
        key = (ref["annotation_line"], ref["question_index"])
        if key in by_ref or row["query_id"] in ids:
            raise ValueError("duplicate source reference or query ID")
        by_ref[key] = row
        ids.add(row["query_id"])
    output, seen = [], set()
    index = 0
    with annotation.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle):
            if not line.strip():
                continue
            source = json.loads(line)
            for question_no, question in enumerate(source["questions"]):
                key = (line_no, question_no)
                row = by_ref.get(key)
                if row is None or row["query_id"] != f"mmdocir_{index:05d}":
                    raise ValueError(f"source query ID mismatch at {key}")
                if document_id(source["doc_name"]) != row["doc_id"]:
                    raise ValueError(f"source document mismatch at {key}")
                index += 1
                seen.add(key)
                if row["role"] == "quarantine":
                    continue
                text = question["Q"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(f"empty/invalid question: {row['query_id']}")
                output.append({"query_id": row["query_id"], "doc_id": row["doc_id"],
                               "role": row["role"], "source_ref": row["source_ref"],
                               "text": text, "text_sha256": text_sha256(text)})
    if seen != set(by_ref):
        raise ValueError("manifest source references missing from annotations")
    hashes.update({name: file_sha256(split / name) for name in ("split_proof.json", "identity_inputs.json")})
    return output, {"annotation_path": str(annotation.resolve()), "annotation_sha256": ann_hash,
                    "manifest_path": str(split.resolve()), "manifest_sha256": hashes,
                    "role_counts": dict(Counter(r["role"] for r in output)),
                    "queries": [{k: v for k, v in r.items() if k != "text"} for r in output]}


def validate_embedding(embedding: torch.Tensor) -> None:
    if not isinstance(embedding, torch.Tensor) or embedding.ndim != 2:
        raise ValueError("query embedding must be a two-dimensional tensor")
    if embedding.shape[0] < 11 or embedding.shape[1] != 128 or not embedding.is_floating_point():
        raise ValueError(f"invalid query embedding shape/dtype: {embedding.shape}, {embedding.dtype}")
    if not bool(torch.isfinite(embedding).all()):
        raise ValueError("nonfinite query embedding")
    norms = embedding.float().norm(dim=-1)
    if not bool(((norms - 1).abs() < 0.03).all()):
        raise ValueError("query embedding has zero/abnormal token norms")


def unpad_embedding(embedding: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    """只移除 attention=0 且向量全零的批内补齐；增广 token 必须保留。"""
    if embedding.ndim != 2 or attention_mask.ndim != 1 or len(embedding) != len(attention_mask):
        raise ValueError("embedding/attention shape mismatch")
    if not bool(torch.isfinite(embedding).all()):
        raise ValueError("nonfinite model output")
    if not bool(((attention_mask == 0) | (attention_mask == 1)).all()):
        raise ValueError("invalid attention mask")
    keep = attention_mask.bool()
    if bool((embedding[~keep] != 0).any()):
        raise ValueError("masked padding must have exactly zero embeddings")
    result = embedding[keep].detach().cpu().contiguous()
    validate_embedding(result)
    return result


def validate_cache(payload: dict, provenance: dict, identity: dict, encoding: dict) -> dict:
    if payload.get("schema") != QUERY_SCHEMA or payload.get("model") != MODEL:
        raise ValueError("query cache schema/model mismatch; refusing overwrite")
    for key, expected in (("provenance", provenance), ("identity", identity), ("encoding", encoding)):
        if payload.get(key) != expected:
            raise ValueError(f"query cache {key} mismatch; refusing overwrite")
    expected_ids = {r["query_id"] for r in provenance["queries"]}
    embeddings, tokens = payload["embeddings"], payload["tokens"]
    if set(embeddings) != expected_ids or set(tokens) != expected_ids:
        raise ValueError("query cache ID coverage mismatch")
    for qid, embedding in embeddings.items():
        validate_embedding(embedding)
        record = tokens[qid]
        if record["shape"] != list(embedding.shape) or record["dtype"] != str(embedding.dtype):
            raise ValueError(f"query cache shape/dtype mismatch: {qid}")
        if len(record["input_ids"]) != len(embedding) or record["attention_mask"] != [1] * len(embedding):
            raise ValueError(f"query cache token alignment mismatch: {qid}")
        if record["input_ids"][-10:] != [identity["pad_token_id"]] * 10:
            raise ValueError(f"query augmentation tokens missing: {qid}")
        digest = hashlib.sha256(embedding.view(torch.uint8).numpy().tobytes()).hexdigest()
        if record["embedding_sha256"] != digest:
            raise ValueError(f"query embedding hash mismatch: {qid}")
    lengths = [len(e) for e in embeddings.values()]
    return {"passed": True, "queries": len(embeddings), "role_counts": provenance["role_counts"],
            "token_rows_min": min(lengths), "token_rows_max": max(lengths),
            "dimension": 128, "nonfinite_values": 0, "zero_token_rows": 0,
            "exact_id_coverage": True, "source_and_manifest_hashes_match": True}
