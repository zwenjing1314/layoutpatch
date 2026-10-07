"""EXP-015开跑前一致性检查；不调用模型定位评分。"""
from __future__ import annotations

import json
import math
from pathlib import Path

import polars as pl
import torch
import yaml

from layoutpatch.evaluation.localization import question_macro, rank_candidates, unit_metrics
from layoutpatch.retrieval.route_v2_query_cache import file_sha256, source_queries, validate_cache

SHARED = ("seeds", "max_epochs", "optimizer", "units_per_update", "tau", "clip_max_norm", "early_stopping",
          "shuffle", "checkpoint", "device", "dtype", "mixed_precision", "scheduler", "tf32", "deterministic_algorithms",
          "vram_budget_gib", "split", "regions", "query_cache", "page_cache")


def check_budget(config, baseline):
    for key in SHARED:
        if config[key] != baseline[key]:
            raise ValueError(f"frozen budget/protocol mismatch: {key}")
    if config["trainable_parameters"] != 273410 or config["C_trainable_parameters"] != 66176:
        raise ValueError("parameter declaration mismatch")


def check_predictions(rows, units, candidates):
    by_unit = {u["unit_id"]: u for u in units}
    methods = {}
    for method in ("A", "B", "C_seed_0", "C_seed_1", "C_seed_2"):
        selected = [r for r in rows if r["method"] == method]
        if len(selected) != len(units) or {r["unit_id"] for r in selected} != set(by_unit):
            raise ValueError("baseline unit denominator mismatch")
        for r in selected:
            u = by_unit[r["unit_id"]]
            if (r["query_id"], r["doc_id"], r["role"]) != (u["query_id"], u["doc_id"], "source_dev"):
                raise ValueError("baseline question/role mismatch")
            cs = candidates[u["doc_id"], u["page"]]
            ids, scores = r["ranked_layout_ids"], r["ranked_scores"]
            if len(ids) != len(cs) or set(ids) != set(cs):
                raise ValueError("baseline candidate mismatch")
            ordered = rank_candidates([s if s is not None else -math.inf for s in scores], ids)
            if ordered != list(range(len(ids))):
                raise ValueError("baseline ranking/tie rule mismatch")
            expected = unit_metrics([cs[i]["bbox"] for i in ids], u["gold_boxes"], u["page_size"])
            for key, value in expected.items():
                if not math.isclose(r[key], value, abs_tol=1e-12, rel_tol=1e-12):
                    raise ValueError(f"baseline saved metric mismatch: {method}/{key}")
        methods[method] = selected
    return methods


def verify(repo: Path, config: dict):
    baseline = repo / config["baseline_run"]
    old = json.loads((baseline / "config.json").read_text("utf-8"))
    check_budget(config, old)
    # 原评分/指标/损失实现逐字节与EXP-014实际快照一致。
    hashes = {}
    for name in ("src/layoutpatch/retrieval/route_v2_scoring.py", "src/layoutpatch/evaluation/localization.py",
                 "src/layoutpatch/retrieval/colpali_layout.py", "src/layoutpatch/datasets/route_v2_regions.py"):
        if file_sha256(repo / name) != file_sha256(baseline / "code" / name):
            raise ValueError(f"EXP-014 scoring/supervision implementation changed: {name}")
        hashes[name] = file_sha256(repo / name)
    proof = json.loads((repo / config["split"] / "split_proof.json").read_text("utf-8"))
    if not proof["data_identity_ready"] or proof["identity_units_crossing_roles"] or any(proof["pairwise_document_intersections"].values()):
        raise ValueError("role isolation failed")
    _, provenance = source_queries(repo / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl", repo / config["split"])
    query = torch.load(repo / config["query_cache"], map_location="cpu", weights_only=True)
    validate_cache(query, provenance, query["identity"], query["encoding"])
    for s in json.loads((baseline / "checkpoint_selection.json").read_text("utf-8")).values():
        if file_sha256(baseline / s["checkpoint"]) != s["checkpoint_sha256"]:
            raise ValueError("baseline checkpoint identity mismatch")
    hashes.update({str((baseline / name).relative_to(repo)): file_sha256(baseline / name)
                   for name in ("config.json", "predictions.parquet", "metrics.json", "checkpoint_selection.json")})
    units = pl.read_parquet(repo / config["regions"] / "units.parquet").to_dicts()
    candidates = {}
    for c in pl.read_parquet(repo / config["regions"] / "candidates.parquet").to_dicts():
        candidates.setdefault((c["doc_id"], c["page"]), {})[c["layout_id"]] = c
    manifests = []
    for key, allowed, hash_key in (("node_cache_train_val", {"source_train", "source_val"}, "node_manifest_sha256"),
                                    ("node_cache_dev", {"source_dev"}, "dev_node_manifest_sha256")):
        root = repo / config[key]
        path = root / "manifest.json"
        digest = file_sha256(path)
        if hash_key in config and config[hash_key] != digest:
            raise ValueError(f"node manifest hash mismatch: {key}")
        hashes[str(path.relative_to(repo))] = digest
        m = json.loads(path.read_text("utf-8"))
        for name, sha in m["audit"]["input_sha256"].items():
            if file_sha256(repo / name) != sha:
                raise ValueError(f"node input changed: {name}")
        wanted = {(u["doc_id"], u["page"]) for u in units if u["role"] in allowed and
                  (u["local_loss_ready"] and not u["page_overlap_excluded"] if u["role"] == "source_train" else u["eval_ready"])}
        if {(r["doc_id"], r["page"]) for r in m["pages"]} != wanted:
            raise ValueError("node page coverage mismatch")
        for r in m["pages"]:
            p = root / r["file"]
            if r["role"] not in allowed or file_sha256(p) != r["sha256"]:
                raise ValueError("node cache role/hash mismatch")
            hashes[str(p.relative_to(repo))] = r["sha256"]
            payload = torch.load(p, map_location="cpu", weights_only=True)
            cs = candidates[r["doc_id"], r["page"]]
            if [n["layout_id"] for n in payload["nodes"]] != sorted(cs):
                raise ValueError("node candidate identity/order mismatch")
            for n in payload["nodes"]:
                c = cs[n["layout_id"]]
                if n["bbox"] != c["bbox"] or n["page_size"] != c["page_size"]:
                    raise ValueError("node geometry mismatch")
            if not all(bool(torch.isfinite(t).all()) for t in payload["layout"].values()):
                raise FloatingPointError("nonfinite node cache")
        manifests.append(m)
    if manifests[0]["identity"] != manifests[1]["identity"] or manifests[0]["encoding"] != manifests[1]["encoding"]:
        raise ValueError("train/dev encoder or input rule mismatch")
    dev = [u for u in units if u["role"] == "source_dev" and u["eval_ready"]]
    if len(dev) != 545 or len({u["query_id"] for u in dev}) != 412:
        raise ValueError("EXP-014 dev denominator mismatch")
    methods = check_predictions(pl.read_parquet(baseline / "predictions.parquet").to_dicts(), dev, candidates)
    metrics = json.loads((baseline / "metrics.json").read_text("utf-8"))
    for method, rows in methods.items():
        values = question_macro(rows, "hit1@0.5")
        if abs(sum(values.values()) / len(values) - metrics["methods"][method]["all"]["metrics"]["hit1@0.5"]) > 1e-12:
            raise ValueError("baseline question macro mismatch")
    return {"passed": True, "input_sha256": hashes, "dev_questions": 412, "dev_units": 545,
            "baseline_rows": sum(len(rows) for rows in methods.values()), "baseline_rescored": False,
            "dev_nodes": manifests[1]["audit"]["nodes"], "dev_nonempty": manifests[1]["audit"]["nonempty"],
            "dev_pages": len(manifests[1]["pages"]), "dev_encoding": manifests[1]["run_info"]}


if __name__ == "__main__":
    from datetime import datetime

    repo = Path(__file__).resolve().parents[1]
    out = repo / "artifacts/route_v2_data/exp015_preflight" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    result = {"passed": False}
    try:
        result = verify(repo, yaml.safe_load((repo / "configs/experiments/route_v2_exp2_D.yaml").read_text("utf-8")))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (out / "preflight.json").write_text(json.dumps(result, indent=2), "utf-8")
        print(json.dumps({"out": str(out), **{k: v for k, v in result.items() if k != "input_sha256"}}, indent=2))
