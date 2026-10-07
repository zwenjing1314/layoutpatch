"""只读核验正式实验输入，不重新划分、编码、训练或评分。"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import polars as pl
import torch

from layoutpatch.retrieval.colpali import _source_signature
from layoutpatch.retrieval.colpali_layout import split_page_embedding
from layoutpatch.retrieval.route_v2_query_cache import file_sha256, source_queries, validate_cache

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "artifacts/route_v2_data"
SPLIT = REPO / "experiments/route_v2_splits/data-roles-v1"
REGIONS = ROOT / "regions_v1"
QUERY = ROOT / "query_cache_v1/source_queries.pt"
PAGE = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"


def read(path):
    return json.loads(path.read_text("utf-8"))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify() -> dict:
    hashes = {}

    def bind(path, expected=None):
        digest = file_sha256(path)
        require(expected is None or digest == expected, f"input hash mismatch: {path}")
        hashes[path.relative_to(REPO).as_posix()] = digest

    rows, provenance = source_queries(REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl", SPLIT)
    cache = torch.load(QUERY, map_location="cpu", weights_only=True)
    receipt = read(ROOT / "query_cache_v1/runs/20261006_153320_261096/run_info.json")
    bind(QUERY, receipt["cache_sha256"])
    integrity = validate_cache(cache, provenance, cache["identity"], cache["encoding"])
    # 只核对本地模型文件身份，不实例化模型或重编码。
    for name in ("model", "base_model"):
        identity = cache["identity"][name]
        for filename, digest in identity["file_sha256"].items():
            require(file_sha256(Path(identity["path"]) / filename) == digest, f"model identity mismatch: {name}/{filename}")
    for p in SPLIT.iterdir():
        if p.is_file():
            bind(p)
    audit = read(REGIONS / "audit.json")
    for name, digest in audit["inputs"].items():
        bind(REPO / name, digest)
    for name in ("units.parquet", "candidates.parquet", "questions.parquet", "audit.json"):
        bind(REGIONS / name)
    for path in (ROOT / "coordinate_audit_v1.json", REPO / "artifacts/route_v2_smoke/20261006_153418/metrics.json",
                 REPO / "artifacts/route_v2_smoke/20261006_153418/preconditions.json"):
        require(read(path)["passed"], f"existing gate failed: {path}")
        bind(path)
    role_of = {r["query_id"]: r for r in rows}
    all_roles = {}
    for role in ("source_train", "source_val", "source_dev", "quarantine"):
        for line in (SPLIT / f"{role}_ids.jsonl").read_text("utf-8").splitlines():
            r = json.loads(line)
            require(r["doc_id"] not in all_roles or all_roles[r["doc_id"]] == role, "document role leakage")
            all_roles[r["doc_id"]] = role
    units = pl.read_parquet(REGIONS / "units.parquet").to_dicts()
    questions = pl.read_parquet(REGIONS / "questions.parquet").to_dicts()
    require(len({u["unit_id"] for u in units}) == len(units), "duplicate unit ID")
    require(len({q["query_id"] for q in questions}) == len(questions) == 1658, "question ID coverage mismatch")
    for u in units + questions:
        require(all_roles[u["doc_id"]] == u["role"], f"region role mismatch: {u['query_id']}")
        if u["role"] != "quarantine":
            require(u["query_id"] in role_of and role_of[u["query_id"]]["doc_id"] == u["doc_id"]
                    and role_of[u["query_id"]]["role"] == u["role"], "region query identity mismatch")
    internal = read(ROOT / "internal_identity_v1.json")
    excluded = set()
    for e in internal["page_pair_evidence"]:
        a, b = all_roles[e["left_doc"]], all_roles[e["right_doc"]]
        if e["status"] != "rejected" and a != b and "quarantine" not in (a, b):
            for side in ("left", "right"):
                excluded.add((e[f"{side}_doc"], int(e[f"{side}_page"])))
    for u in units:
        require(u["page_overlap_excluded"] == ((u["doc_id"], u["page"]) in excluded), "page exclusion mismatch")
    cands = pl.read_parquet(REGIONS / "candidates.parquet").to_dicts()
    counts = Counter((c["doc_id"], c["page"]) for c in cands)
    require(len({(c["doc_id"], c["page"], c["layout_id"]) for c in cands}) == len(cands), "duplicate candidate ID")
    for u in units:
        require(u["candidate_count"] == counts[u["doc_id"], u["page"]], "candidate count mismatch")
    pages = {r["page_id"]: r for r in pl.read_parquet(REPO / "data/processed/mmdocir_evaluation/pages.parquet",
                                                    columns=["page_id", "page_image_path"]).to_dicts()}
    needed = sorted({u["page_cache_id"] for u in units if u["role"] != "quarantine"})
    for pid in needed:
        path = PAGE / f"{pid}.pt"
        payload = torch.load(path, map_location="cpu", weights_only=True)
        require(payload.get("model_name") == "vidore/colpali", f"page model mismatch: {pid}")
        require(payload["source_signature"] == _source_signature(Path(pages[pid]["page_image_path"]), "vidore/colpali"), f"page signature mismatch: {pid}")
        patches, _ = split_page_embedding(payload["embedding"])
        require(patches.shape == (1024, 128) and bool(torch.isfinite(payload["embedding"]).all()), f"page shape/nonfinite: {pid}")
        bind(path)
    distribution = {}
    for role in ("source_train", "source_val", "source_dev"):
        us = [u for u in units if u["role"] == role]
        qs = [q for q in questions if q["role"] == role]
        ready = [u for u in us if u["eval_ready"]]
        train = [u for u in us if u["local_loss_ready"] and not u["page_overlap_excluded"]]
        for key, count in (("units", len(us)), ("questions", len(qs)), ("units_eval_ready", len(ready)), ("units_local_loss_ready", len(train))):
            require(audit["roles"][role][key] == count, f"audit count mismatch: {role}/{key}")
        distribution[role] = {"questions": len(qs), "units": len(us), "eval_units": len(ready),
                              "eval_questions": len({u["query_id"] for u in ready}), "loss_units": len(train),
                              "page_excluded_units": sum(u["page_overlap_excluded"] for u in us),
                              "no_positive_eval_units": sum(u["patch_pos"] == 0 for u in ready),
                              "no_negative_eval_units": sum(u["patch_neg"] == 0 for u in ready)}
    return {"passed": True, "input_sha256": hashes, "query_integrity": integrity, "roles": distribution,
            "page_cache_count": len(needed), "external_test_opened": False, "model_scoring_performed": False}


if __name__ == "__main__":
    out = ROOT / "exp1_verification" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    result = {"passed": False}
    try:
        result = verify()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result["elapsed_seconds"] = time.perf_counter() - start
        (out / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps({"out": str(out), **{k: v for k, v in result.items() if k != "input_sha256"}}, ensure_ascii=False), flush=True)
