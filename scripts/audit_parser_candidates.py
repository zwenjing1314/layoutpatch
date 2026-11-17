"""Independent stage-2 export/evaluation of a fixed 40-page candidate study.

export never opens gold. metrics requires saved export + gold-blind visual review.
verify recomputes metrics from saved candidates. No torch/parser/encoder execution.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import io
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from parser_study_support import (
    ROOT,
    checked,
    enable_geometry_only_imports,
    enable_write_broker,
    read_json,
    read_jsonl,
    sha256,
    within,
    write_bytes,
    write_json,
    write_jsonl,
)

enable_geometry_only_imports()
from layoutpatch.datasets.parser_candidates import (  # noqa: E402
    NEW,
    OLD,
    CandidatePageError,
    augment_page,
    validate_candidates,
)
from layoutpatch.evaluation.localization import (  # noqa: E402
    _greedy_recall,
    doc_bootstrap_diff,
    question_macro,
)
from layoutpatch.evaluation.region_metrics import bbox_iou  # noqa: E402
from layoutpatch.layout.correspondence import area  # noqa: E402

CONFIG = "configs/experiments/parser_candidate_audit_v1.yaml"
METRICS = ("oracle@0.5", "independent_gold_reach@0.5", "all_gold_reachable_independent@0.5", "greedy_all_candidates_gold_recall@0.5")
CODE = ("scripts/audit_parser_candidates.py", "scripts/parser_study_support.py",
        "src/layoutpatch/datasets/parser_candidates.py", "src/layoutpatch/datasets/mineru.py",
        "src/layoutpatch/evaluation/localization.py", "src/layoutpatch/evaluation/region_metrics.py",
        "src/layoutpatch/layout/correspondence.py", "src/layoutpatch/layout/schema.py")


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def peak_rss():
    if os.name == "nt":
        class Memory(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in ("peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        api = ctypes.WinDLL("psapi", use_last_error=True)
        api.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong]
        counters = Memory()
        counters.cb = ctypes.sizeof(counters)
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.peak
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    out = {}
    for label, prob in zip(("min", "p25", "p50", "p75", "p95", "max"), (0, .25, .5, .75, .95, 1), strict=True):
        pos = prob * (len(values)-1)
        frac = pos % 1
        out[label] = values[math.floor(pos)] * (1-frac) + values[math.ceil(pos)] * frac
    return out


def load_config(path):
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (cfg.get("status") != "frozen_candidate_audit" or cfg.get("scope") != "export_and_candidate_reachability_only"
            or cfg["conditions"] != [OLD, NEW] or cfg["fallback"] != "none"
            or any(cfg[k] for k in ("new_parser_inference", "model_scoring", "training"))):
        raise ValueError("not the frozen, geometry-only stage-2 configuration")
    for key in ("preparation_config", "page_manifest", "unit_manifest", "protocol"):
        checked(ROOT, cfg[key], cfg[f"{key}_sha256"])
    prep = yaml.safe_load(within(ROOT, cfg["preparation_config"]).read_text(encoding="utf-8"))
    source = Path(prep["source_root_read_only"]).resolve()
    if source == ROOT or source in ROOT.parents or ROOT in source.parents:
        raise ValueError("read-only source must be separate from the experiment checkout")
    if Path(prep["worktree_root"]).resolve() != ROOT:
        raise ValueError("worktree path identity differs")
    pages = read_jsonl(within(ROOT, cfg["page_manifest"]))
    expected = cfg["effect_denominators"]
    if len(pages) != expected["pages"] or len({p["page_id"] for p in pages}) != len(pages):
        raise ValueError("frozen page denominator/uniqueness changed")
    if [p["sample_order"] for p in pages] != list(range(40)) or len({p["doc_id"] for p in pages}) != 35:
        raise ValueError("frozen page ordering/document count changed")
    if set(cfg["diagnostic_pages_not_effect_sample"]) & {p["page_id"] for p in pages}:
        raise ValueError("technical diagnostics accidentally overlap effect sample")
    return cfg, prep, source, pages


def grouped(rows, key="page_id"):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def output_roots(prep, run_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
        raise ValueError("invalid run_id")
    art = within(ROOT, prep["paths"]["artifacts_root"])
    run = within(ROOT, prep["paths"]["runs_root"]) / "candidate_audit" / run_id
    art.relative_to(ROOT / "artifacts" / "parser_candidate_comparison" / "v1")
    run.relative_to(ROOT / "runs" / "parser_candidate_comparison" / "v1")
    return art, run


def baseline(rows, receipt):
    """Exact old candidates are independent of success of NEW raw export."""
    result = []
    for row in rows:
        result.append({**copy.deepcopy(row), "condition_id": OLD,
                       "candidate_id": f"{OLD}:{row['candidate_id']}", "source_candidate_id": row["candidate_id"],
                       "source_raw_sha256": receipt["raw_sha256"],
                       "source_json_pointer": f"/candidates/by_id/{row['candidate_id']}",
                       "source_locator_kind": "frozen_candidates_jsonl_candidate_id",
                       "source_bbox": list(row["bbox"]), "source_coordinate_frame": "frozen_evaluation_pixels",
                       "transform_id": "identity_frozen_old_candidate", "export_policy_version": "mineru-top-plus-annotations-v1",
                       "node_origin": "old_top", "parent_source_id": None})
    validate_candidates(result, receipt["page_id"], receipt["render"]["page_size"])
    return result


def draw_overlay(page, old, new, path):
    """Only page pixels and candidates; this function cannot see gold."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17) if os.name == "nt" else ImageFont.load_default()
    with Image.open(page["render_path"]) as original:
        if list(original.size) != page["evaluation_page_size"]:
            raise ValueError("overlay image dimensions disagree")
        canvas = original.convert("RGB")
    scale = min(1000/canvas.width, 1350/canvas.height)
    canvas = canvas.resize((round(canvas.width*scale), round(canvas.height*scale)))
    result = Image.new("RGB", (canvas.width, canvas.height+90), "white")
    result.paste(canvas, (0, 90))
    draw = ImageDraw.Draw(result)
    draw.text((8, 8), page["page_id"] + " | no gold / no queries", fill="black", font=font)
    added = [r for r in new if r["node_origin"] == "annotation"]
    draw.text((8, 31), f"BLUE = old ({len(old)}); ORANGE = appended ({len(added)})", fill="black", font=font)
    draw.text((8, 54), page.get("stratum", "rotation diagnostic; outside effect sample"), fill="black", font=font)
    for rows, color in ((old, "#2474c4"), (added, "#ef6500")):
        for row in rows:
            x1, y1, x2, y2 = row["bbox"]
            box = (x1*scale, y1*scale+90, x2*scale, y2*scale+90)
            draw.rectangle(box, outline=color, width=3)
            draw.text((box[0], max(90, box[1]-18)), str(row["layout_id"]), fill=color, font=font)
    stream = io.BytesIO()
    result.save(stream, format="PNG")
    write_bytes(path, stream.getvalue())


def export(cfg_path, run_id):
    started, begin = now(), time.perf_counter()
    cfg, prep, source, pages = load_config(cfg_path)
    art, run = output_roots(prep, run_id)
    if run.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {run}")
    candidates_path = checked(source, prep["paths"]["source_candidates"], prep["paths"]["source_candidates_sha256"])
    source_candidates = grouped(read_jsonl(candidates_path))
    for rows in source_candidates.values():
        rows.sort(key=lambda r: r["layout_id"])
    page_ids = {p["page_id"] for p in pages}
    if sum(len(source_candidates[p]) for p in page_ids) != cfg["effect_denominators"]["old_candidates"]:
        raise ValueError("old candidate denominator mismatch")
    identity = {"run_id": run_id, "started_at": started, "config_path": str(cfg_path), "config_sha256": sha256(cfg_path),
                "config": cfg, "preparation": prep, "source_root": str(source),
                "code_sha256": {p: sha256(ROOT / p) for p in CODE},
                "raw_parser_run": False, "model_scoring": False, "gold_read_during_export": False,
                "source_candidates_sha256": sha256(candidates_path)}
    # Freeze identity on disk before touching new candidates or outcomes.
    write_json(run / "identity.json", identity)
    for path in CODE:
        target = run / "code" / path
        write_bytes(target, (ROOT / path).read_bytes())
    write_json(run / "config.json", cfg)
    all_pages = list(pages)
    for page_id in cfg["diagnostic_pages_not_effect_sample"]:
        receipt_path = within(source, prep["paths"]["source_receipts"]) / f"{page_id}_receipt.json"
        receipt = read_json(receipt_path)
        all_pages.append({"page_id": page_id, "doc_id": receipt["doc_id"], "receipt_path": str(receipt_path),
                          "evaluation_page_size": receipt["render"]["page_size"],
                          "render_path": str(within(source, receipt["render"]["render_path"])),
                          "raw_path": str(within(source, receipt["raw_output"])), "raw_sha256": receipt["raw_sha256"]})
    visual_ids = []
    seen_strata = set()
    for page in pages:
        if page["stratum"] not in seen_strata:
            visual_ids.append(page["page_id"])
            seen_strata.add(page["stratum"])
    visual_ids += cfg["diagnostic_pages_not_effect_sample"]
    exports, receipts, aliases, overlays, diagnostics = {OLD: [], NEW: []}, [], [], [], []
    for page in all_pages:
        page_begin, page_started = time.perf_counter(), now()
        page_id = page["page_id"]
        receipt_path = within(source, page["receipt_path"])
        receipt = read_json(receipt_path)
        if receipt["page_id"] != page_id or receipt["render"]["page_size"] != page["evaluation_page_size"]:
            raise ValueError("page/receipt identity mismatch")
        checked(source, receipt["render"]["render_path"], receipt["render"]["render_sha256"])
        checked(source, receipt["image"]["path"], receipt["image"]["sha256"])
        if page_id in page_ids and (page["parser_image_sha256"] != receipt["image"]["sha256"] or within(source, page["parser_image_path"]) != within(source, receipt["image"]["path"])):
            raise ValueError("parser input differs from cached ColPali image identity")
        ref = {"page_id": page_id, "effect_sample": page_id in page_ids, "receipt_path": str(receipt_path),
               "receipt_sha256": sha256(receipt_path), "raw_path": str(within(source, page["raw_path"])),
               "expected_raw_sha256": page["raw_sha256"], "raw_already_saved_by_original_parser": True}
        # Raw reference and original identity are persisted BEFORE this page export.
        write_json(run / "raw_references" / f"{page_id}.json", ref)
        old = baseline(source_candidates[page_id], receipt)
        new, page_aliases, audit = [], [], None
        status, error_type, error_message = "passed", None, None
        input_check_seconds = time.perf_counter() - page_begin
        raw_begin = time.perf_counter()
        try:
            if within(source, receipt["raw_output"]) != within(source, page["raw_path"]) or receipt["raw_sha256"] != page["raw_sha256"]:
                raise CandidatePageError("raw identity inconsistent with frozen page manifest")
            raw_path = checked(source, page["raw_path"], page["raw_sha256"])
            payload = read_json(raw_path)
            raw_seconds = time.perf_counter() - raw_begin
            export_begin = time.perf_counter()
            _, new, page_aliases, audit = augment_page(payload, receipt, source_candidates[page_id])
            export_seconds = time.perf_counter()-export_begin
        except (CandidatePageError, OSError, json.JSONDecodeError) as exc:
            raw_seconds, export_seconds = time.perf_counter()-raw_begin, None
            status, error_type, error_message = "failed", type(exc).__name__, str(exc)
        common = {"page_id": page_id, "input_image_sha256": receipt["image"]["sha256"],
                  "started_at": page_started, "parser_id": "saved_MinerU_4.0.10_DocVortex_2.0",
                  "parser_revision": "358310b4f64b95f9fefc372ad899356e4111f376",
                  "implementation_sha256": identity["code_sha256"]["src/layoutpatch/datasets/parser_candidates.py"],
                  "parameters_sha256": identity["config_sha256"], "raw_path": page["raw_path"],
                  "raw_sha256": page["raw_sha256"], "raw_read_seconds": raw_seconds,
                  "input_check_seconds": input_check_seconds,
                  "export_seconds": export_seconds, "elapsed_seconds": time.perf_counter()-page_begin,
                  "load_seconds": 0, "new_parser_run": False, "historical_parse_seconds": receipt.get("parse_seconds"),
                  "peak_rss_bytes": peak_rss(), "memory_scope": "cumulative_export_process_peak_working_set",
                  "peak_vram_allocated_bytes": None, "peak_vram_reserved_bytes": None, "gpu_used": False,
                  "truncated": False, "attempt_count": 1, "effect_sample": page_id in page_ids}
        for condition, rows in ((OLD, old), (NEW, new)):
            record = {**common, "condition_id": condition, "status": status if condition == NEW else "passed",
                      "candidate_count": len(rows), "exit_code": int(condition == NEW and status != "passed"),
                      "error_type": error_type if condition == NEW else None, "error_message": error_message if condition == NEW else None,
                      "audit": audit if condition == NEW else {"exact_frozen_parent_rows": True}}
            if page_id in page_ids:
                receipts.append(record)
                exports[condition].extend(rows)
            else:
                diagnostics.append(record)
        if page_id in page_ids:
            aliases.extend(page_aliases)
        else:
            write_jsonl(run / "diagnostics" / f"{page_id}_new.jsonl", new)
            write_jsonl(run / "diagnostics" / f"{page_id}_aliases.jsonl", page_aliases)
        if page_id in visual_ids:
            overlay_path = art / "overlays" / run_id / f"{page_id}.png"
            draw_overlay(page, old, new, overlay_path)
            overlays.append({"page_id": page_id, "path": str(overlay_path), "sha256": sha256(overlay_path),
                             "effect_sample": page_id in page_ids, "new_export_status": status, "gold_drawn": False})
    outputs = {}
    for condition, rows in exports.items():
        path = art / "candidates" / condition / run_id / "candidates.jsonl"
        write_jsonl(path, rows)
        outputs[condition] = {"path": str(path), "sha256": sha256(path), "count": len(rows)}
    write_jsonl(run / "page_receipts.jsonl", receipts)
    write_jsonl(run / "aliases.jsonl", aliases)
    write_jsonl(run / "diagnostic_receipts.jsonl", diagnostics)
    write_json(run / "overlay_manifest.json", overlays)
    result = {"status": "export_completed_awaiting_visual_review", "outputs": outputs,
              "effect_pages": 40, "technical_diagnostic_pages": 2, "required_visual_pages": visual_ids,
              "failed_new_pages": [r["page_id"] for r in receipts if r["condition_id"] == NEW and r["status"] != "passed"],
              "effect_aliases": len(aliases), "elapsed_seconds": time.perf_counter()-begin,
              "peak_rss_bytes": peak_rss(), "models_loaded": False, "raw_parser_run": False, "gold_read": False,
              "artifacts": {name: sha256(run / name) for name in ("page_receipts.jsonl", "aliases.jsonl", "diagnostic_receipts.jsonl", "overlay_manifest.json")}}
    if "torch" in sys.modules:
        raise RuntimeError("unexpected torch import in geometry-only export")
    write_json(run / "export_manifest.json", result)
    print(json.dumps({"run": str(run), **result}, ensure_ascii=True))


def candidate_metrics(rows, gold):
    if not gold:
        raise ValueError("evaluation unit without gold")
    rows = sorted(rows, key=lambda r: r["layout_id"])
    boxes = [r["bbox"] for r in rows]
    best = [max((bbox_iou(c, g) for c in boxes), default=0.0) for g in gold]
    hits = [x >= .5 for x in best]
    return {"oracle@0.5": float(any(hits)), "independent_gold_reach@0.5": statistics.mean(hits),
            "all_gold_reachable_independent@0.5": float(all(hits)),
            "greedy_all_candidates_gold_recall@0.5": _greedy_recall(boxes, gold, .5)}, best


def evaluate_saved(cfg_path, run_id):
    cfg, prep, source, pages = load_config(cfg_path)
    _, run = output_roots(prep, run_id)
    identity, manifest = read_json(run / "identity.json"), read_json(run / "export_manifest.json")
    if identity["config_sha256"] != sha256(cfg_path) or any(sha256(ROOT / p) != h for p, h in identity["code_sha256"].items()):
        raise ValueError("config/code changed after export; use a new run, never overwrite")
    for name, digest in manifest["artifacts"].items():
        checked(run, name, digest)
    visual = read_json(run / "visual_review.json")
    if (visual.get("status") != "passed" or visual.get("gold_used") is not False
            or visual.get("overlay_manifest_sha256") != sha256(run / "overlay_manifest.json")
            or {r["page_id"] for r in visual["pages"]} != set(manifest["required_visual_pages"])
            or not all(r["status"] == "passed" for r in visual["pages"])):
        raise ValueError("gold-blind technical visual review incomplete")
    for row in read_json(run / "overlay_manifest.json"):
        checked(ROOT, row["path"], row["sha256"])
    checked(source, prep["paths"]["source_annotations"], prep["paths"]["source_annotations_sha256"])
    # First gold deserialization occurs here, in evaluation of SAVED candidates.
    units = read_jsonl(within(ROOT, cfg["unit_manifest"]))
    unit_ids = {u["unit_id"] for u in units}
    if len(units) != 126 or len(unit_ids) != 126 or len({u["query_id"] for u in units}) != 125 or sum(len(u["gold_boxes"]) for u in units) != 159:
        raise ValueError("evaluation denominators changed")
    page_map = {p["page_id"]: p for p in pages}
    if {u["page_id"] for u in units} != set(page_map):
        raise ValueError("effect unit/page coverage changed")
    receipts = read_jsonl(run / "page_receipts.jsonl")
    if len(receipts) != 80 or {(r["condition_id"], r["page_id"]) for r in receipts} != {(c, p) for c in cfg["conditions"] for p in page_map}:
        raise ValueError("every condition/page must retain a receipt")
    by_condition, candidates = {}, {}
    all_rows, gold_rows = [], []
    for condition in cfg["conditions"]:
        output = manifest["outputs"][condition]
        path = checked(ROOT, output["path"], output["sha256"])
        flat = read_jsonl(path)
        if len(flat) != output["count"] or any(r["condition_id"] != condition for r in flat):
            raise ValueError("candidate file identity mismatch")
        cand = grouped(flat)
        if set(cand) - set(page_map):
            raise ValueError("candidate pages outside sample")
        for receipt in (r for r in receipts if r["condition_id"] == condition):
            pid = receipt["page_id"]
            rows = cand[pid]
            validate_candidates(rows, pid, page_map[pid]["evaluation_page_size"])
            if len(rows) != receipt["candidate_count"] or (receipt["status"] != "passed" and rows):
                raise ValueError("failed/empty page denominator handling mismatch")
        condition_rows = []
        for unit in units:
            values, best = candidate_metrics(cand[unit["page_id"]], unit["gold_boxes"])
            row = {k: unit[k] for k in ("unit_id", "query_id", "doc_id", "page_id")}
            row.update({"condition_id": condition, "candidate_count": len(cand[unit["page_id"]]), **values})
            condition_rows.append(row)
            for i, (score, kind) in enumerate(zip(best, unit["gold_types"], strict=True)):
                gold_rows.append({"condition_id": condition, "unit_id": unit["unit_id"], "page_id": unit["page_id"],
                                  "gold_index": i, "gold_type": kind, "best_iou": score, "reachable@0.5": score >= .5})
        by_condition[condition], candidates[condition] = condition_rows, cand
        all_rows.extend(condition_rows)
    paired = []
    for old, new in zip(by_condition[OLD], by_condition[NEW], strict=True):
        if old["unit_id"] != new["unit_id"]:
            raise ValueError("unit pairing mismatch")
        paired.append({"unit_id": old["unit_id"], "query_id": old["query_id"], "page_id": old["page_id"],
                       "old_candidate_count": old["candidate_count"], "new_candidate_count": new["candidate_count"],
                       "old": {m: old[m] for m in METRICS}, "new": {m: new[m] for m in METRICS},
                       "delta": {m: new[m]-old[m] for m in METRICS}})
    doc_of = {u["query_id"]: u["doc_id"] for u in units}
    summaries, pairs, distributions, strata = {}, {}, {}, {}
    for condition in cfg["conditions"]:
        summaries[condition] = {m: statistics.mean(question_macro(by_condition[condition], m).values()) for m in METRICS}
        rows = [r for values in candidates[condition].values() for r in values]
        distributions[condition] = {"candidate_count": len(rows), "counts_per_page": quantiles([len(candidates[condition][p]) for p in page_map]),
                                    "area_fraction": quantiles([area(r["bbox"])/(r["page_size"][0]*r["page_size"][1]) for r in rows]),
                                    "types": dict(Counter(r["type"] for r in rows)), "parser_types": dict(Counter(r["parser_type"] for r in rows))}
    for metric in METRICS:
        old = question_macro(by_condition[OLD], metric)
        new = question_macro(by_condition[NEW], metric)
        pairs[metric] = {**doc_bootstrap_diff(new, old, doc_of, iterations=2000, seed=0),
                         "unit_improved": sum(p["delta"][metric] > 0 for p in paired), "unit_worsened": sum(p["delta"][metric] < 0 for p in paired),
                         "unit_unchanged": sum(p["delta"][metric] == 0 for p in paired),
                         "question_improved": sum(new[q] > old[q] for q in old), "question_worsened": sum(new[q] < old[q] for q in old),
                         "ci_role": "descriptive_exploratory_candidate_metrics_not_primary_scoring_family"}
    for stratum in sorted({p["stratum"] for p in pages}):
        pids = {p["page_id"] for p in pages if p["stratum"] == stratum}
        selected = [u for u in units if u["page_id"] in pids]
        strata[stratum] = {"pages": len(pids), "questions": len({u["query_id"] for u in selected}), "units": len(selected),
                           "old_candidates": sum(len(candidates[OLD][p]) for p in pids), "new_candidates": sum(len(candidates[NEW][p]) for p in pids),
                           "metrics": {c: {m: statistics.mean(question_macro([r for r in by_condition[c] if r["page_id"] in pids], m).values()) for m in METRICS} for c in cfg["conditions"]}}
    failures = {c: [r["page_id"] for r in receipts if r["condition_id"] == c and r["status"] != "passed"] for c in cfg["conditions"]}
    result = {"denominators": cfg["effect_denominators"], "aggregation": "mean_selected_units_per_question_then_question_macro",
              "partial_multi_page_questions": 43, "metrics": summaries, "paired_new_minus_old": pairs,
              "distributions": distributions, "strata": strata, "failed_pages": failures,
              "failed_page_rate": {c: len(v)/40 for c, v in failures.items()},
              "pages_with_added_candidates": sum(len(candidates[NEW][p]) > len(candidates[OLD][p]) for p in page_map),
              "export_seconds": quantiles([r["export_seconds"] for r in receipts if r["condition_id"] == NEW and r["export_seconds"] is not None]),
              "raw_read_seconds": quantiles([r["raw_read_seconds"] for r in receipts if r["condition_id"] == NEW]),
              "export_process_peak_rss_bytes": manifest["peak_rss_bytes"], "export_wall_seconds_including_overlays": manifest["elapsed_seconds"],
              "new_parser_failure_rate": None, "new_parser_failure_rate_reason": "No parser was rerun; report raw-export failure rate instead",
              "model_scoring": False, "training": False, "same_success_subset_needed": any(failures.values())}
    return run, result, all_rows, paired, gold_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / CONFIG)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", choices=("export", "metrics", "verify"), required=True)
    parser.add_argument("--write-broker", action="store_true", help="Use the acknowledged PowerShell exclusive-write broker")
    args = parser.parse_args()
    if args.write_broker:
        enable_write_broker()
    if args.stage == "export":
        export(args.config.resolve(), args.run_id)
        return
    run, result, rows, paired, gold = evaluate_saved(args.config.resolve(), args.run_id)
    if args.stage == "metrics":
        write_json(run / "metrics.json", result)
        write_jsonl(run / "unit_metrics.jsonl", rows)
        write_jsonl(run / "paired_unit_changes.jsonl", paired)
        write_jsonl(run / "gold_reachability.jsonl", gold)
        write_json(run / "completed.json", {"status": "completed", "completed_at": now(),
                                            "files_sha256": {name: sha256(run / name) for name in ("metrics.json", "unit_metrics.jsonl", "paired_unit_changes.jsonl", "gold_reachability.jsonl", "visual_review.json")}})
    else:
        if result != read_json(run / "metrics.json") or rows != read_jsonl(run / "unit_metrics.jsonl") or paired != read_jsonl(run / "paired_unit_changes.jsonl") or gold != read_jsonl(run / "gold_reachability.jsonl"):
            raise ValueError("saved results do not reproduce exactly")
        for path, digest in read_json(run / "completed.json")["files_sha256"].items():
            checked(run, path, digest)
    if "torch" in sys.modules:
        raise RuntimeError("unexpected torch import")
    print(json.dumps({"stage": args.stage, "status": "passed", "run": str(run), "metrics": result["metrics"],
                      "distributions": result["distributions"], "failed_pages": result["failed_pages"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
