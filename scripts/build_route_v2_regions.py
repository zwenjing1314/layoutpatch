"""Build route-v2 region units, page candidates and the supervision audit (regions-v1).

Reads MMDocIR annotations (layout_mapping and page lists only; question text and answers
are not written), parsed layouts, processed page paths, cache signatures, data-roles-v1
and internal page-pair evidence. Output: artifacts/route_v2_data/regions_v1/ (never replaced).
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl
import torch

from layoutpatch.datasets.route_v2_regions import build_region_units, normalize_candidate
from layoutpatch.datasets.route_v2_split import ROLES, document_id
from layoutpatch.retrieval.colpali import _source_signature

REPO = Path(__file__).resolve().parents[1]
ANN = REPO / "data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl"
LAYOUTS = REPO / "data/raw/mmdocir_evaluation/MMDocIR_layouts.parquet"
PAGES = REPO / "data/processed/mmdocir_evaluation/pages.parquet"
CACHE = REPO / "artifacts/colpali/mmdocir_evaluation/vidore_colpali"
SPLIT = REPO / "experiments/route_v2_splits/data-roles-v1"
INTERNAL = REPO / "artifacts/route_v2_data/internal_identity_v1.json"
OUT = REPO / "artifacts/route_v2_data/regions_v1"
MODEL = "vidore/colpali"


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    qs = statistics.quantiles(values, n=20) if len(values) > 1 else [values[0]] * 19
    return {"min": min(values), "p05": qs[0], "p25": qs[4], "p50": qs[9], "p75": qs[14],
            "p95": qs[18], "max": max(values), "mean": statistics.fmean(values)}


def role_audit(units: list[dict], questions: list[dict], cands: dict) -> dict:
    gold_types: Counter = Counter()
    best, area, pos = [], [], []
    for u in units:
        lookup = {c["layout_id"]: c for c in cands.get((u["doc_id"], u["page"]), [])}
        for lid, b, a in zip(u["gold_exact_layout_id"], u["gold_best_candidate_iou"],
                             u["gold_area_frac"], strict=True):
            gold_types[lookup[lid]["type"] if lid is not None else "unmatched"] += 1
            best.append(b)
            area.append(a)
        if u["eval_ready"]:
            pos.append(u["patch_pos"])
    ready = [u for u in units if u["eval_ready"]]
    multi = Counter(q["query_id"] for q in questions if len(q["gold_pages"]) > 1)
    trainable = [u for u in units if u["local_loss_ready"] and not u["page_overlap_excluded"]]
    return {
        "questions": len(questions),
        "questions_with_layout_gold": sum(q["has_layout_gold"] for q in questions),
        "questions_multi_gold_page": len(multi),
        "questions_gold_page_outside_question_pages": sum(
            bool(q["gold_pages_outside_question_pages"]) for q in questions),
        "units": len(units),
        "units_eval_ready": len(ready),
        "units_coordinate_conflict": sum(u["coordinate_conflict"] for u in units),
        "units_no_candidates": sum(u["candidate_count"] == 0 for u in units),
        "units_no_positive_patch": sum(u["eval_ready"] and u["patch_pos"] == 0 for u in units),
        "units_page_overlap_excluded": sum(u["page_overlap_excluded"] for u in units),
        "units_local_loss_ready": len(trainable),
        "questions_local_loss_ready": len({u["query_id"] for u in trainable}),
        "documents_local_loss_ready": len({u["doc_id"] for u in trainable}),
        "gold_boxes": len(best),
        "gold_duplicates_removed": sum(u["gold_duplicates_removed"] for u in units),
        "gold_invalid": sum(u["gold_invalid"] for u in units),
        "gold_out_of_bounds": sum(u["gold_out_of_bounds"] for u in units),
        "gold_exact_candidate": sum(t != "unmatched" for t in gold_types.elements()),
        "gold_exact_candidate_type": dict(gold_types.most_common()),
        "gold_best_candidate_iou_ge_0.5": sum(b >= 0.5 for b in best),
        "gold_best_candidate_iou": quantiles(best),
        "gold_area_frac_of_page": quantiles(area),
        "patch_pos_per_eval_unit": quantiles([float(p) for p in pos]),
        "candidates_per_unit": quantiles([float(u["candidate_count"]) for u in units]),
        "oracle_unit_iou_ge_0.5": sum(any(b >= 0.5 for b in u["gold_best_candidate_iou"])
                                      for u in ready),
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite {OUT}")
    lines = ANN.read_text(encoding="utf-8").split("\n")
    rows = [(i, json.loads(line)) for i, line in enumerate(lines) if line.strip()]
    cands: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in pl.read_parquet(LAYOUTS, columns=["doc_name", "page_id", "layout_id", "type", "text",
                                                "ocr_text", "vlm_text", "bbox", "page_size"]).iter_rows(named=True):
        cands[(r["doc_name"], int(r["page_id"]))].append(normalize_candidate(r))
    for value in cands.values():
        value.sort(key=lambda c: c["layout_id"])
    pages = {
        (r["doc_id"], int(r["page_index"]) - 1): r
        for r in pl.read_parquet(PAGES, columns=["doc_id", "page_id", "page_index", "page_image_path"]).to_dicts()
    }
    gold_pages = {
        (document_id(a["doc_name"]), int(m["page"]))
        for _, a in rows
        for q in a["questions"]
        for m in q.get("layout_mapping") or []
    }
    cached, signature_bad = set(), []
    for key in sorted(gold_pages):
        page = pages.get(key)
        path = CACHE / f"{page['page_id']}.pt" if page else None
        if path is None or not path.exists():
            continue
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if payload.get("source_signature") == _source_signature(Path(page["page_image_path"]), MODEL):
            cached.add(key)
        else:
            signature_bad.append(page["page_id"])
    units, questions = build_region_units(rows, cands, cached)
    role_of = {}
    for role in ROLES:
        for line in (SPLIT / f"{role}_ids.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            role_of[row["query_id"]] = role
    doc_role = {}
    for role in ROLES:
        for doc in (SPLIT / f"{role}_doc_ids.txt").read_text(encoding="utf-8").split():
            doc_role[doc] = role
    overlap_pages: dict[tuple[str, int], set[str]] = defaultdict(set)
    for e in json.loads(INTERNAL.read_text(encoding="utf-8"))["page_pair_evidence"]:
        if e["status"] == "rejected":
            continue
        left, right = doc_role[e["left_doc"]], doc_role[e["right_doc"]]
        if left != right and "quarantine" not in (left, right):
            overlap_pages[(e["left_doc"], int(e["left_page"]))].add(right)
            overlap_pages[(e["right_doc"], int(e["right_page"]))].add(left)
    for unit in units:
        unit["role"] = role_of[unit["query_id"]]
        unit["page_overlap_roles"] = sorted(overlap_pages.get((unit["doc_id"], unit["page"]), ()))
        unit["page_overlap_excluded"] = bool(unit["page_overlap_roles"])
    for q in questions:
        q["role"] = role_of[q["query_id"]]
    staging = OUT.with_name(OUT.name + ".partial")  # renamed to OUT only after every file exists
    staging.mkdir(parents=True)
    pl.DataFrame(units).write_parquet(staging / "units.parquet")
    used = sorted({(u["doc_id"], u["page"]) for u in units})
    pl.DataFrame([{"doc_id": d, "page": p, **c} for d, p in used for c in cands.get((d, p), [])]
                 ).write_parquet(staging / "candidates.parquet")
    pl.DataFrame(questions).write_parquet(staging / "questions.parquet")
    audit = {
        "schema": "route-v2-regions-v1",
        "gold_source": "question layout_mapping only; candidates: parsed layout rows of that page",
        "layout_rows_total": sum(len(v) for v in cands.values()),
        "layout_pages_total": len(cands),
        "gold_pages_signature_mismatch": signature_bad,
        "roles": {role: role_audit([u for u in units if u["role"] == role],
                                   [q for q in questions if q["role"] == role], cands)
                  for role in ROLES},
        "inputs": {p.relative_to(REPO).as_posix(): sha(p) for p in (ANN, LAYOUTS, PAGES, INTERNAL,
                                                                    SPLIT / "split_proof.json")},
        "script_sha256": sha(Path(__file__)),
    }
    (staging / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), "utf-8")
    staging.rename(OUT)
    print(json.dumps({r: {k: audit["roles"][r][k] for k in (
        "questions", "questions_with_layout_gold", "units", "units_eval_ready",
        "units_local_loss_ready", "questions_local_loss_ready")} for r in ROLES}, indent=1))


if __name__ == "__main__":
    main()
