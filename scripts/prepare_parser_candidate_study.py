"""Read-only stage-1 audit and outcome-blind stage-2 sample; no model or parser calls.

Emits one JSON bundle to stdout. The PowerShell wrapper saves it exclusively inside
this worktree. Imports the worktree's pure geometry/metric functions, never torch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import statistics
import subprocess
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Package __init__ files eagerly import torch/pandas. Isolate this audit process
# to the unchanged pure source modules; do not execute those package initializers.
for package in ("layoutpatch", "layoutpatch.datasets", "layoutpatch.evaluation", "layoutpatch.layout"):
    namespace = types.ModuleType(package)
    namespace.__path__ = [str(ROOT / "src" / package.replace(".", "/"))]
    sys.modules[package] = namespace

from layoutpatch.datasets.mineru import export_page  # noqa: E402
from layoutpatch.evaluation.localization import _greedy_recall, question_macro  # noqa: E402
from layoutpatch.evaluation.region_metrics import bbox_iou  # noqa: E402
from layoutpatch.layout.correspondence import area, intersection_area  # noqa: E402

SALT = "parser-candidate-v1:20261116:"
PREP = "artifacts/route_v2_external/full_prep_v1/20261008_222512"
ENC = "artifacts/route_v2_external/encoding_v1/runs/20261009_141912"
BINDINGS = {
    f"{PREP}/candidates.jsonl": "19dbd7257d696bca19859fd1a53e69520e3380590d5fe0445fac61d8d2518263",
    f"{ENC}/manifest.json": "87386a31e2300093d59f0f0c5bd81ecac7161292ab9df49736581ecf2217aa4f",
    "artifacts/route_v2_external/preparation_v1/20261007_152240/weights.json": "5a1bc2a05dfdd5b7287862a6b04928f30b0d90612b6cc2abb77aad7c4bebbe0f",
    "artifacts/route_v2_external/preparation_v1/20261007_155402/manifest.json": "387b2f498ec4bb54abb7aab0a149ef46aa7856c284d2472541d61a7940d0347d",
    "data/raw/sciegqa_bench/9bdca77be633cc3259d7e3739d35b38ab00bf5d9/SciEGQA_Bench.jsonl": "338b701830495b984acca753e5b5065b35a7566c308f2d5c81f76b8401a3053f",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_path(root, value):
    path = (root / value).resolve()
    path.relative_to(root)
    return path


def checked(root, value, expected):
    path = source_path(root, value)
    actual = digest(path)
    if actual != expected:
        raise ValueError(f"identity mismatch: {path}")
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def quantiles(values):
    values = sorted(values)
    out = {}
    for label, p in zip(("min", "p25", "p50", "p75", "p95", "max"), (0, .25, .5, .75, .95, 1), strict=True):
        x = p * (len(values) - 1)
        out[label] = values[math.floor(x)] * (1 - x % 1) + values[math.ceil(x)] * (x % 1)
    return out


def stratum(rows):
    kinds = {r["type"] for r in rows}
    content = "both" if {"table", "image"} <= kinds else "table" if "table" in kinds else "image" if "image" in kinds else "text_other"
    width, height = rows[0]["page_size"]
    boxes = [r["bbox"] for r in rows if r["type"] == "text" and (r["bbox"][2] - r["bbox"][0]) / width <= .55]
    # A reproducible layout proxy, not a certified column detector.
    multi = any(a[2] <= .55 * width and b[0] >= .45 * width and a[2] <= b[0]
                and min(a[3], b[3]) - max(a[1], b[1]) >= .02 * height for a in boxes for b in boxes)
    return content + (":two_column_proxy" if multi else ":other_layout")


def prepare(source):
    identities = {name: checked(source, name, sha) for name, sha in BINDINGS.items()}
    candidates = defaultdict(list)
    for line in (source / f"{PREP}/candidates.jsonl").read_text(encoding="utf-8").strip().split("\n"):
        row = json.loads(line)
        candidates[row["page_id"]].append(row)
    for rows in candidates.values():
        rows.sort(key=lambda r: r["layout_id"])
    assert len(candidates) == 837 and sum(map(len, candidates.values())) == 9746
    manifest = read(source / f"{ENC}/manifest.json")
    page_records = {r["page_id"]: r for r in manifest["pages"]}
    assert set(page_records) == set(candidates)

    # Freeze the sample BEFORE opening annotations, raw children or saved outcomes.
    strata = defaultdict(list)
    for page_id, rows in candidates.items():
        strata[stratum(rows)].append(page_id)
    def key(page_id):
        return hashlib.sha256((SALT + page_id).encode()).hexdigest()
    for values in strata.values():
        values.sort(key=key)
    chosen = []
    rounds = 0
    while len(chosen) < 40:
        for name in sorted(strata):
            if rounds < len(strata[name]) and len(chosen) < 40:
                chosen.append(strata[name][rounds])
        rounds += 1
    selected = set(chosen)

    receipt_stats = Counter()
    nested_types = Counter()
    raw_paths = Counter()
    parse_modes = Counter()
    nested_pages = set()
    nested_unique_pages = set()
    all_receipts = {}
    nested_equal_parent = 0
    nested_new_boxes = 0
    invalid_nested = 0
    raw_bytes = 0
    export_mismatches = []
    receipt_recipe_mismatches = []
    export_max_pixel_delta = 0.0
    coordinate_contracts = Counter()
    times, memory = [], []
    for page_id in sorted(candidates):
        receipt = read(source / f"{PREP}/{page_id}_receipt.json")
        all_receipts[page_id] = receipt
        raw_path = source_path(source, receipt["raw_output"])
        checked(source, receipt["raw_output"], receipt["raw_sha256"])
        raw_bytes += raw_path.stat().st_size
        payload = read(raw_path)
        parse_modes[payload["extensions"]["mineru"]["parse_mode"]] += 1
        receipt_stats[receipt["status"]] += 1
        for k in ("invalid_boxes", "out_of_bounds_boxes", "duplicate_boxes"):
            receipt_stats[k] += receipt.get(k, 0)
        receipt_stats[f"rotation_{receipt['render']['rotation']}"] += 1
        receipt_stats[f"image_mapping_{receipt['image']['mapping']['status']}"] += 1
        times.append(receipt["parse_seconds"])
        memory.append(receipt["peak_working_set_bytes"])
        seen = {tuple(b["bbox"]) for b in payload["pages"][0]["blocks"]}
        def walk(obj, loc=""):
            if isinstance(obj, dict):
                if "bbox" in obj:
                    raw_paths[loc] += 1
                for k, v in obj.items():
                    walk(v, loc + "/" + k)
            elif isinstance(obj, list):
                for value in obj:
                    walk(value, loc + "[]")
        walk(payload)
        for block in payload["pages"][0]["blocks"]:
            for child in block.get("content", []):
                if not isinstance(child, dict) or "bbox" not in child:
                    continue
                nested_pages.add(page_id)
                nested_types[block["type"] + " -> " + child["type"]] += 1
                box = child["bbox"]
                invalid_nested += int(not (len(box) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in box) and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1))
                nested_equal_parent += box == block["bbox"]
                if tuple(box) not in seen:
                    nested_new_boxes += 1
                    nested_unique_pages.add(page_id)
                    seen.add(tuple(box))
        render = dict(receipt["render"])
        if "pdf_to_render_matrix" not in render:
            if render["rotation"] != 0:
                raise ValueError(f"missing rotated transform: {page_id}")
            render["pdf_to_render_matrix"] = [1, 0, 0, 1, 0, 0]
        exported, _ = export_page(payload, receipt, render)
        old = candidates[page_id]
        coordinate_contracts[receipt["coordinate_contract"]] += 1
        export_max_pixel_delta = max(export_max_pixel_delta, max(abs(x-y) for a,b in zip(old,exported,strict=True) for x,y in zip(a["bbox"],b["bbox"],strict=True)))
        if len(old) != len(exported) or any(a["layout_id"] != b["layout_id"] or a["type"] != b["type"] or any(abs(x-y) > 1e-6 for x,y in zip(a["bbox"], b["bbox"], strict=True)) for a,b in zip(old, exported, strict=True)):
            export_mismatches.append(page_id)
        if receipt["coordinate_contract"] == "unit_xyxy_top_left_to_render_pixels":
            width, height = receipt["render"]["page_size"]
            expected = [[b["bbox"][0]*width,b["bbox"][1]*height,b["bbox"][2]*width,b["bbox"][3]*height] for b in sorted(payload["pages"][0]["blocks"],key=lambda b:b["index"])]
        elif receipt["coordinate_contract"] in {"unit_xyxy_to_pdf_points_to_rotated_render_pixels", "unit_xyxy_parser_frame_to_PyMuPDF_render_pixels"}:
            expected = [r["bbox"] for r in exported]
        else:
            raise ValueError(f"unknown historical coordinate recipe: {page_id}")
        if any(abs(x-y)>1e-6 for a,b in zip(old,expected,strict=True) for x,y in zip(a["bbox"],b,strict=True)):
            receipt_recipe_mismatches.append(page_id)

    sample_rows = []
    sampled_checks = []
    for i, page_id in enumerate(chosen):
        receipt, record = all_receipts[page_id], page_records[page_id]
        assert record["image_sha256"] == receipt["image"]["sha256"]
        assert source_path(source, record["image_path"]) == source_path(source, receipt["image"]["path"])
        for path, sha in ((record["image_path"], record["image_sha256"]),
                          (f"{ENC}/{record['file']}", record["sha256"]),
                          (receipt["render"]["render_path"], receipt["render"]["render_sha256"])):
            sampled_checks.append(checked(source, path, sha))
        sample_rows.append({"sample_order": i, "page_id": page_id, "doc_id": receipt["doc_id"],
                            "stratum": stratum(candidates[page_id]), "sample_hash": key(page_id),
                            "page_number": receipt["page_number"], "pdf_page_index": receipt["pdf_page_index"],
                            "old_candidate_count": len(candidates[page_id]), "evaluation_page_size": receipt["render"]["page_size"],
                            "parser_image_path": str(source_path(source, record["image_path"])),
                            "parser_image_sha256": record["image_sha256"],
                            "parser_image_size": receipt["image"]["mapping"]["source_image_size"],
                            "render_path": str(source_path(source, receipt["render"]["render_path"])),
                            "receipt_path": str(source / f"{PREP}/{page_id}_receipt.json"),
                            "raw_path": str(source_path(source, receipt["raw_output"])), "raw_sha256": receipt["raw_sha256"],
                            "page_cache_path": str(source / ENC / record["file"]), "page_cache_sha256": record["sha256"]})
    annotations_path = next(p for p in BINDINGS if p.endswith('SciEGQA_Bench.jsonl'))
    units, selected_units, diagnostics = [], [], []
    reasons, gold_types = Counter(), Counter()
    reasons_by_type = defaultdict(Counter)
    best_type_pairs = Counter()
    question_total_units = Counter()
    for idx, line in enumerate((source / annotations_path).read_text(encoding="utf-8").strip().split("\n")):
        ann = json.loads(line)
        query = f"sciegqa_{idx:05d}"
        doc = ann["doc_name"].removesuffix(".pdf")
        fields = (ann["evidence_page"], ann["rel_bbox"], ann["subimg_type"])
        assert len({len(v) for v in fields}) == 1
        for number, relative, kinds in zip(*fields, strict=True):
            page_id = f"{doc}_p{number-1}"
            width, height = candidates[page_id][0]["page_size"]
            assert len(relative) == len(kinds) and relative
            assert all(0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000 for b in relative)
            gold = [[b[0]*width/1000, b[1]*height/1000, b[2]*width/1000, b[3]*height/1000] for b in relative]
            boxes = [r["bbox"] for r in candidates[page_id]]
            reachable = [max(bbox_iou(c, g) for c in boxes) >= .5 for g in gold]
            unit = {"query_id": query, "doc_id": doc, "page_id": page_id, "unit_id": f"{query}:{page_id}",
                    "oracle@0.5": float(any(reachable)), "independent_gold_reach@0.5": statistics.mean(reachable),
                    "all_gold_reachable_independent@0.5": float(all(reachable)),
                    "greedy_all_candidates_gold_recall@0.5": _greedy_recall(boxes, gold, .5)}
            units.append(unit)
            question_total_units[query] += 1
            if page_id in selected:
                selected_units.append({"query_id": query, "doc_id": doc, "page_id": page_id,
                                       "unit_id": unit["unit_id"], "page_size": [width,height],
                                       "gold_boxes": gold, "gold_types": kinds, "role": "exploratory_supplement"})
            for gidx, (g, kind) in enumerate(zip(gold, kinds, strict=True)):
                best = max(range(len(boxes)), key=lambda i: bbox_iou(boxes[i], g))
                iou = bbox_iou(boxes[best], g)
                cover = intersection_area(boxes[best], g) / area(g)
                fill = intersection_area(boxes[best], g) / area(boxes[best])
                # Descriptive geometry only: neither 'missing' nor 'granularity' is proven.
                reason = "reachable" if iou >= .5 else "no_overlap" if iou == 0 else "larger_contains_gold_proxy" if cover >= .8 else "smaller_inside_gold_proxy" if fill >= .8 else "partial_overlap"
                reasons[reason] += 1
                reasons_by_type[str(kind)][reason] += 1
                best_type_pairs[str(kind) + " -> " + candidates[page_id][best]["type"]] += 1
                gold_types[str(kind)] += 1
                if page_id in selected:
                    diagnostics.append({"unit_id": unit["unit_id"], "gold_index": gidx, "gold_type": kind,
                                        "best_old_layout_id": candidates[page_id][best]["layout_id"],
                                        "best_old_type": candidates[page_id][best]["type"], "best_iou": iou,
                                        "candidate_to_gold_area": area(boxes[best])/area(g),
                                        "gold_covered_fraction": cover, "candidate_inside_gold_fraction": fill,
                                        "diagnostic_geometry_only": reason})
    assert len(units) == 1941 and len(question_total_units) == 1623
    weights = read(source / "artifacts/route_v2_external/preparation_v1/20261007_152240/weights.json")
    checkpoint_checks = [{**r, **checked(source, r["checkpoint"], r["sha256"])} for r in weights["D-no-text"]["weights"]]
    query_check = checked(source, f"{ENC}/{manifest['queries']['file']}", manifest['queries']['sha256'])
    saved = read(source / "runs/retrieval/route_v2_external_eval_v1/20261009_163938/metrics.json")
    def aggregate(rows):
        return {k: statistics.mean(question_macro(rows, k).values()) for k in units[0] if k not in {"query_id","doc_id","page_id","unit_id"}}
    all_metrics = aggregate(units)
    assert abs(all_metrics["oracle@0.5"] - saved["analytical"]["methods"]["A"]["all"]["metrics"]["oracle@0.5"]) < 1e-12
    sample_metrics = aggregate([r for r in units if r["page_id"] in selected])
    sample_queries = Counter(r["query_id"] for r in selected_units)
    packages = {}
    for name in ("torch", "transformers", "tokenizers", "colpali-engine", "flash-attn", "vllm"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    audit = {"schema": "parser-candidate-study-stage1-v1", "status": "read_only_audit_completed",
             "source_root": str(source), "worktree_root": str(ROOT),
             "baseline_commit": subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
             "input_identity": identities, "raw_files": len(all_receipts), "raw_bytes": raw_bytes,
             "raw_bbox_paths": dict(raw_paths), "parse_modes": dict(parse_modes), "receipts": dict(receipt_stats),
             "nested_types": dict(nested_types), "nested_pages": len(nested_pages),
             "nested_equal_parent": nested_equal_parent, "nested_invalid": invalid_nested,
             "nested_new_unique_boxes_vs_top": nested_new_boxes, "nested_new_unique_pages": len(nested_unique_pages),
             "old_export_geometry_type_id_mismatches": export_mismatches,
             "current_export_max_coordinate_delta_pixels": export_max_pixel_delta,
             "receipt_coordinate_contracts": dict(coordinate_contracts),
             "receipt_recipe_geometry_mismatches": receipt_recipe_mismatches,
             "old_candidate_count_quantiles": quantiles([len(x) for x in candidates.values()]),
             "old_candidate_area_fraction_quantiles": quantiles([area(r["bbox"])/(r["page_size"][0]*r["page_size"][1]) for rows in candidates.values() for r in rows]),
             "historical_parse_seconds_quantiles_not_new_benchmark": quantiles(times),
             "historical_peak_parser_rss_bytes_max": max(memory),
             "old_all_question_macro": all_metrics, "old_sample_question_macro": sample_metrics,
             "all_gold_geometry_counts": dict(reasons), "all_gold_types": dict(gold_types),
             "all_gold_geometry_counts_by_type": {k:dict(v) for k,v in reasons_by_type.items()},
             "best_iou_candidate_type_pairs_diagnostic_only": dict(best_type_pairs),
             "sample_population_strata": {k:len(v) for k,v in sorted(strata.items())},
             "sample_selected_strata": dict(Counter(r["stratum"] for r in sample_rows)),
             "sample_denominators": {"pages":40, "documents":len({r["doc_id"] for r in sample_rows}),
                                     "questions":len(sample_queries), "units":len(selected_units),
                                     "gold_boxes":sum(len(r["gold_boxes"]) for r in selected_units),
                                     "old_candidates":sum(len(candidates[p]) for p in selected),
                                     "partially_selected_multi_page_questions":sum(n < question_total_units[q] for q,n in sample_queries.items())},
             "sample_file_checks": sampled_checks, "query_file_check": query_check,
             "D_no_text_checkpoint_checks": checkpoint_checks, "source_python_packages": packages,
             "models_loaded": False, "new_candidates_exported": False, "new_parser_run": False,
             "limitations": ["Geometry proxies are not causal failure labels", "Raw schema audit is not OCR accuracy validation", "Only sampled P/image/render files were rehashed; tensors not loaded", "Historical parser timing is not a new speed comparison"]}
    return {"audit":audit, "sample_pages":sample_rows, "sample_units":selected_units, "old_sample_gold_diagnostics":diagnostics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    json.dump(prepare(args.source_root.resolve()), sys.stdout, ensure_ascii=True, allow_nan=False)
    print()
