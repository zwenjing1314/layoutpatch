"""Route-v2 pipeline smoke: <=16 fixed source_train questions, <=200 steps, frozen backbone.

Checks every precondition first and writes preconditions.json. If any fails it stops
before training (exit 2) and never substitutes inputs. Trainable part: the no-layout
PatchAdapter control (the candidate layout module is not frozen yet). Shows only that
the local signal is learnable on these questions; it is not a generalization result.
Output: artifacts/route_v2_smoke/<timestamp>/.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

import polars as pl
import torch

from layoutpatch.evaluation.localization import rank_candidates, unit_metrics
from layoutpatch.retrieval.colpali_layout import split_page_embedding
from layoutpatch.retrieval.route_v2_scoring import (
    PatchAdapter,
    patch_iou_matrix,
    patch_scores,
    region_scores,
    train_local_steps,
)

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO / "docs/ROUTE_V2_PROTOCOL.md"
SPLIT = REPO / "experiments/route_v2_splits/data-roles-v1/split_proof.json"
REGIONS = REPO / "artifacts/route_v2_data/regions_v1"
COORDS = REPO / "artifacts/route_v2_data/coordinate_audit_v1.json"
PAGE_CACHE = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
QUERY_CACHE = REPO / "artifacts/route_v2_data/query_cache_v1/source_queries.pt"
OUT_ROOT = REPO / "artifacts/route_v2_smoke"
SEED, QUESTIONS, STEPS, LR, VRAM_BUDGET_GB = 42, 16, 200, 1e-3, 12.0
QUERY_SCHEMA = "route-v2-query-cache-v1"  # {"schema", "model", "embeddings": {query_id: [T,128]}}


def check(name: str, ok: bool, detail: object) -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def select_questions(units: list[dict]) -> list[str]:
    ready = sorted({u["query_id"] for u in units if u["role"] == "source_train"
                    and u["local_loss_ready"] and not u["page_overlap_excluded"]})
    random.Random(SEED).shuffle(ready)
    return sorted(ready[:QUESTIONS])


def preconditions() -> tuple[list[dict], list[dict], dict | None]:
    results = []
    text = PROTOCOL.read_text(encoding="utf-8") if PROTOCOL.exists() else ""
    results.append(check("protocol", "route-v2-smoke-v1" in text and "数据角色声明" in text,
                         str(PROTOCOL.relative_to(REPO))))
    proof = json.loads(SPLIT.read_text(encoding="utf-8")) if SPLIT.exists() else {}
    isolated = bool(proof) and all(not v for v in proof["pairwise_document_intersections"].values())
    results.append(check("source_identity", proof.get("data_identity_ready") is True,
                         proof.get("evidence", {}).get("independence_status")))
    results.append(check("train_dev_isolation", isolated and not proof["identity_units_crossing_roles"],
                         proof.get("roles")))
    coords = json.loads(COORDS.read_text(encoding="utf-8")) if COORDS.exists() else {}
    results.append(check("coordinates", coords.get("passed") is True, coords.get("conclusion")))
    units = pl.read_parquet(REGIONS / "units.parquet").to_dicts() if (REGIONS / "units.parquet").exists() else []
    chosen = select_questions(units)
    results.append(check("fixed_questions", len(chosen) == QUESTIONS, chosen))
    picked = [u for u in units if u["query_id"] in chosen and u["local_loss_ready"]
              and not u["page_overlap_excluded"]]
    results.append(check("page_cache", bool(picked) and all(u["cache_ready"] for u in picked),
                         f"{len(picked)} units, signature-checked in regions_v1"))
    cache = None
    if QUERY_CACHE.exists():
        cache = torch.load(QUERY_CACHE, map_location="cpu", weights_only=True)
    missing = chosen if cache is None else [q for q in chosen if q not in cache.get("embeddings", {})]
    ok = cache is not None and cache.get("schema") == QUERY_SCHEMA and cache.get("model") == "vidore/colpali"
    results.append(check("query_cache", ok and not missing,
                         {"path": str(QUERY_CACHE.relative_to(REPO)), "missing_query_ids": missing}))
    return results, picked, cache


def evaluate(units: list[dict], items: list[dict], cands: dict, module: torch.nn.Module) -> float:
    hits = []
    with torch.no_grad():
        for u, item in zip(units, items, strict=True):
            boxes = [c["bbox"] for c in cands.get((u["doc_id"], u["page"]), [])]
            ids = [c["layout_id"] for c in cands.get((u["doc_id"], u["page"]), [])]
            s = region_scores(patch_scores(item["query"], module(item["patches"])),
                              patch_iou_matrix(boxes, u["page_size"])).tolist()
            ranked = [boxes[i] for i in rank_candidates(s, ids)]
            hits.append(unit_metrics(ranked, u["gold_boxes"], u["page_size"])["hit1@0.5"])
    return sum(hits) / len(hits)


def main() -> int:
    out = OUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    results, units, cache = preconditions()
    report = {"preconditions": results, "passed": all(r["passed"] for r in results),
              "policy": {"seed": SEED, "questions": QUESTIONS, "steps": STEPS, "lr": LR,
                         "vram_budget_gb": VRAM_BUDGET_GB, "trainable": "PatchAdapter(hidden=256)",
                         "device": "cpu"}}
    (out / "preconditions.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    if not report["passed"]:
        print(json.dumps({"run_dir": str(out), "blocked_by": [r["check"] for r in results if not r["passed"]]}))
        return 2
    torch.manual_seed(SEED)
    items = []
    for u in units:
        payload = torch.load(PAGE_CACHE / f"{u['page_cache_id']}.pt", map_location="cpu", weights_only=True)
        patches, _ = split_page_embedding(payload["embedding"].float())
        pos = torch.zeros(1024, dtype=torch.bool)
        pos[u["patch_pos_idx"]] = True
        ignore = torch.zeros(1024, dtype=torch.bool)
        ignore[u["patch_ignore_idx"]] = True
        items.append({"query": cache["embeddings"][u["query_id"]].float(), "patches": patches,
                      "pos": pos, "neg": ~(pos | ignore)})
    cands: dict = {}
    for c in pl.read_parquet(REGIONS / "candidates.parquet").to_dicts():
        cands.setdefault((c["doc_id"], c["page"]), []).append(c)
    module = PatchAdapter()
    before = evaluate(units, items, cands, module)
    result = train_local_steps(module, items, steps=STEPS, lr=LR)
    result["train_units"] = len(items)
    result["train_hit1@0.5_before"] = before
    result["train_hit1@0.5_after"] = evaluate(units, items, cands, module)
    result["note"] = "training-set diagnostics only; not a generalization or paper result"
    torch.save(module.state_dict(), out / "adapter.pt")
    (out / "smoke_result.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps({"run_dir": str(out), "initial": result["initial"], "final": result["final"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
