"""只用合成数据验证来源映射与缓存拒绝条件。"""

import copy
import hashlib
import json

import pytest
import torch

from layoutpatch.retrieval.route_v2_query_cache import (
    MODEL,
    QUERY_SCHEMA,
    SOURCE_ROLES,
    file_sha256,
    source_queries,
    unpad_embedding,
    validate_cache,
)


def fixture_source(tmp_path):
    annotation = tmp_path / "annotations.jsonl"
    annotation.write_text('\n{"doc_name":"a.b.pdf","questions":[{"Q":"First?"},{"Q":"Second?"}]}\n', "utf-8")
    split = tmp_path / "split"
    split.mkdir()
    for role in (*SOURCE_ROLES, "quarantine"):
        index = {"source_train": 0, "quarantine": 1}.get(role)
        rows = [] if index is None else [{"query_id": f"mmdocir_{index:05d}", "doc_id": "a.b", "role": role,
                                         "source_ref": {"annotation_line": 1, "question_index": index}}]
        (split / f"{role}_ids.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        (split / f"{role}_query_ids.txt").write_text("".join(r["query_id"] + "\n" for r in rows), "utf-8")
    proof = {"data_identity_ready": True, "identity_units_crossing_roles": [],
             "pairwise_document_intersections": {"train_val": []},
             "file_sha256": {p.name: file_sha256(p) for p in split.iterdir()}}
    (split / "split_proof.json").write_text(json.dumps(proof), "utf-8")
    origin = {"provenance": {"inputs": {"data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl": file_sha256(annotation)}}}
    (split / "identity_inputs.json").write_text(json.dumps(origin), "utf-8")
    return annotation, split


def test_mapping_preserves_physical_line_index_and_quarantine(tmp_path):
    annotation, split = fixture_source(tmp_path)
    rows, provenance = source_queries(annotation, split)
    assert len(rows) == 1 and rows[0]["text"] == "First?"
    assert rows[0]["query_id"] == "mmdocir_00000"
    assert rows[0]["source_ref"] == {"annotation_line": 1, "question_index": 0}
    assert provenance["role_counts"] == {"source_train": 1}
    annotation.write_text(annotation.read_text("utf-8").replace("First?", "Changed?"), "utf-8")
    with pytest.raises(ValueError, match="annotation hash"):
        source_queries(annotation, split)


def test_mapping_rejects_id_mismatch_even_with_updated_manifest_hash(tmp_path):
    annotation, split = fixture_source(tmp_path)
    manifest = split / "source_train_ids.jsonl"
    manifest.write_text(manifest.read_text("utf-8").replace("00000", "00999"), "utf-8")
    (split / "source_train_query_ids.txt").write_text("mmdocir_00999\n", "utf-8")
    proof_path = split / "split_proof.json"
    proof = json.loads(proof_path.read_text("utf-8"))
    for name in proof["file_sha256"]:
        proof["file_sha256"][name] = file_sha256(split / name)
    proof_path.write_text(json.dumps(proof), "utf-8")
    with pytest.raises(ValueError, match="source query ID mismatch"):
        source_queries(annotation, split)


def test_unpad_keeps_augmentation_and_rejects_nonfinite_or_nonzero_padding():
    embedding = torch.nn.functional.normalize(torch.randn(12, 128), dim=-1)
    embedding[-1] = 0
    mask = torch.tensor([1] * 11 + [0])
    assert unpad_embedding(embedding, mask).shape == (11, 128)
    embedding[-1, 0] = 1
    with pytest.raises(ValueError, match="masked padding"):
        unpad_embedding(embedding, mask)
    embedding[-1, 0] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        unpad_embedding(embedding, mask)


def test_cache_integrity_rejects_missing_id_source_change_and_tensor_change():
    embedding = torch.nn.functional.normalize(torch.randn(11, 128), dim=-1)
    provenance = {"queries": [{"query_id": "q"}], "role_counts": {"source_train": 1}}
    identity = {"pad_token_id": 0}
    payload = {"schema": QUERY_SCHEMA, "model": MODEL, "provenance": provenance,
               "identity": identity, "encoding": {}, "embeddings": {"q": embedding},
               "tokens": {"q": {"shape": [11, 128], "dtype": str(embedding.dtype),
                                  "input_ids": [2] + [0] * 10, "attention_mask": [1] * 11,
                                  "embedding_sha256": hashlib.sha256(embedding.view(torch.uint8).numpy().tobytes()).hexdigest()}}}
    assert validate_cache(payload, provenance, identity, {})["passed"]
    with pytest.raises(ValueError, match="provenance mismatch"):
        validate_cache(payload, {**provenance, "changed": True}, identity, {})
    changed = copy.deepcopy(payload)
    changed["embeddings"]["q"][0] *= -1
    with pytest.raises(ValueError, match="embedding hash mismatch"):
        validate_cache(changed, provenance, identity, {})
    del changed["embeddings"]["q"]
    with pytest.raises(ValueError, match="ID coverage"):
        validate_cache(changed, provenance, identity, {})
