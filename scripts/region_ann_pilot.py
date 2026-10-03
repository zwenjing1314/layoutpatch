"""Local 40-question region-annotation workflow. Not training. No gold.

Creates an independent annotator file, a local HTML session sheet, and a
format check. Never writes chosen_box_ids / cover_ok / no_candidate from
heuristics. Never overwrites the template or manifests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from region_ann_workbook import build_workbook

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "experiments/region_annotation/arxivqa_pilot_manifest.jsonl"
MATERIALS = REPO / "experiments/region_annotation/pilot_materials"
SAMPLES = MATERIALS / "samples"
WORKBOOK = MATERIALS / "workbook.html"
PROTOCOL = "region-ann-v1"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED = (
    "sample_id",
    "chosen_box_ids",
    "cover_levels",
    "cover_ok",
    "no_candidate",
    "cross_box",
    "remark",
    "annotator",
    "labeled_at",
    "protocol_version",
    "label_status",
)
PROTECTED = (
    REPO / "experiments/region_annotation/label_template.jsonl",
    REPO / "experiments/region_annotation/arxivqa_pilot_manifest.jsonl",
    REPO / "experiments/region_annotation/arxivqa_train_fit_manifest.jsonl",
)
LABEL_FILES = {
    "A": REPO / "experiments/region_annotation/labels_annotator_A.jsonl",
    "B": REPO / "experiments/region_annotation/labels_annotator_B.jsonl",
}
CHECK_FILES = {
    "A": REPO / "experiments/region_annotation/labels_annotator_A.check.json",
    "B": REPO / "experiments/region_annotation/labels_annotator_B.check.json",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def empty_label(row: dict, annotator: str) -> dict:
    candidates = [
        {
            "box_id": int(box["box_id"]),
            "bbox": [float(v) for v in box["bbox"]],
            "type": box.get("type"),
        }
        for box in row["candidates"]
    ]
    return {
        "sample_id": row["sample_id"],
        "query_id": row["query_id"],
        "line_index": row["line_index"],
        "query": row["query"],
        "pos_doc": row["pos_doc"],
        "pos_page": row["pos_page"],
        "page_png": f"pilot_materials/samples/{row['sample_id']}/page.png",
        "overlay_png": f"pilot_materials/samples/{row['sample_id']}/overlay.png",
        "card": f"pilot_materials/samples/{row['sample_id']}/card.md",
        "candidates": candidates,
        "chosen_box_ids": [],
        "cover_levels": {},
        "cover_ok": None,
        "no_candidate": None,
        "cross_box": None,
        "remark": "",
        "note": "",
        "annotator": annotator,
        "annotator_id": annotator,
        "labeled_at": None,
        "protocol_version": PROTOCOL,
        "label_status": "pending",
    }


def verify_images(rows: list[dict]) -> dict:
    opened = 0
    failures: list[dict] = []
    for row in rows:
        sid = row["sample_id"]
        dest = SAMPLES / sid
        for name in ("page.png", "overlay.png"):
            path = dest / name
            try:
                with Image.open(path) as image:
                    image.load()
                    width, height = image.size
                if width < 10 or height < 10:
                    failures.append({"sample_id": sid, "file": name, "error": f"tiny {width}x{height}"})
                else:
                    opened += 1
            except OSError as exc:
                failures.append({"sample_id": sid, "file": name, "error": str(exc)})
    return {
        "n_questions": len(rows),
        "png_opened": opened,
        "png_expected": len(rows) * 2,
        "failures": failures,
        "complete": opened == len(rows) * 2 and not failures,
    }


def legal_box_ids(row: dict) -> set[int]:
    return {int(box["box_id"]) for box in row.get("candidates") or []}


def _as_int_box(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _num_eq(left, right, eps: float = 1e-6) -> bool:
    try:
        return abs(float(left) - float(right)) <= eps
    except (TypeError, ValueError):
        return False


def metadata_errors(row: dict, rec: dict) -> list[str]:
    sid = rec.get("sample_id")
    errors: list[str] = []
    for key in ("query_id", "line_index", "query", "pos_doc", "pos_page"):
        if key in rec and rec.get(key) != row.get(key):
            errors.append(f"{sid}: metadata {key} changed")
    rec_boxes = rec.get("candidates")
    if rec_boxes is None:
        return errors
    if not isinstance(rec_boxes, list):
        errors.append(f"{sid}: candidates must be list")
        return errors
    pilot_boxes = row.get("candidates") or []
    if len(rec_boxes) != len(pilot_boxes):
        errors.append(f"{sid}: candidate count changed")
        return errors
    for rec_box, pilot_box in zip(rec_boxes, pilot_boxes, strict=True):
        if int(rec_box.get("box_id")) != int(pilot_box.get("box_id")):
            errors.append(f"{sid}: candidate box_id changed")
        if rec_box.get("type") != pilot_box.get("type"):
            errors.append(f"{sid}: candidate type changed")
        rec_bbox = rec_box.get("bbox")
        pilot_bbox = pilot_box.get("bbox")
        if not (
            isinstance(rec_bbox, list)
            and isinstance(pilot_bbox, list)
            and len(rec_bbox) == len(pilot_bbox) == 4
            and all(_num_eq(a, b) for a, b in zip(rec_bbox, pilot_bbox, strict=True))
        ):
            errors.append(f"{sid}: candidate bbox changed")
    return errors


def record_errors(row: dict, rec: dict, annotator: str | None) -> list[str]:
    sid = rec.get("sample_id")
    errors: list[str] = []
    missing = [key for key in REQUIRED if key not in rec]
    if missing:
        errors.append(f"{sid}: missing {missing}")
    if rec.get("protocol_version") != PROTOCOL:
        errors.append(f"{sid}: protocol_version={rec.get('protocol_version')}")
    status = rec.get("label_status")
    if status not in {"pending", "labeled", "skipped", "adjudicated"}:
        errors.append(f"{sid}: illegal label_status={status}")
    for key in ("cover_ok", "no_candidate", "cross_box"):
        if rec.get(key) not in {True, False, None}:
            errors.append(f"{sid}: {key} must be true/false/null")
    if not isinstance(rec.get("remark", ""), str):
        errors.append(f"{sid}: remark must be string")
    if rec.get("annotator") not in {"A", "B", ""}:
        errors.append(f"{sid}: annotator must be A or B")
    if annotator and rec.get("annotator") not in {None, "", annotator}:
        errors.append(f"{sid}: annotator={rec.get('annotator')} != {annotator}")
    legal = legal_box_ids(row)
    chosen = rec.get("chosen_box_ids")
    if not isinstance(chosen, list):
        errors.append(f"{sid}: chosen_box_ids must be list")
        chosen_ids: list[int] = []
    else:
        chosen_ids = []
        seen: set[int] = set()
        for bid in chosen:
            parsed = _as_int_box(bid)
            if parsed is None or parsed not in legal:
                errors.append(f"{sid}: illegal box_id {bid}")
                continue
            if parsed in seen:
                errors.append(f"{sid}: duplicate box_id {parsed}")
            seen.add(parsed)
            chosen_ids.append(parsed)
    levels = rec.get("cover_levels")
    if levels is None:
        levels = {}
    if not isinstance(levels, dict):
        errors.append(f"{sid}: cover_levels must be object")
    else:
        for key, value in levels.items():
            try:
                bid = int(key)
            except (TypeError, ValueError):
                errors.append(f"{sid}: illegal cover_levels key {key}")
                continue
            if bid not in legal:
                errors.append(f"{sid}: cover_levels key {key} not in candidates")
            if value not in {"full", "partial"}:
                errors.append(f"{sid}: cover_levels[{key}] must be full/partial")
            if bid not in chosen_ids:
                errors.append(f"{sid}: cover_levels key {key} not selected")
    labeled_at = rec.get("labeled_at")
    if status == "pending":
        if labeled_at not in {None, ""}:
            errors.append(f"{sid}: pending labeled_at must be null")
        if chosen_ids:
            errors.append(f"{sid}: pending cannot have chosen_box_ids")
        if rec.get("cover_ok") is not None:
            errors.append(f"{sid}: pending cover_ok must be null")
        if rec.get("no_candidate") is not None:
            errors.append(f"{sid}: pending no_candidate must be null")
        if rec.get("cross_box") is not None:
            errors.append(f"{sid}: pending cross_box must be null")
        if levels:
            errors.append(f"{sid}: pending cover_levels must be empty")
    elif labeled_at not in {None, ""} and not (isinstance(labeled_at, str) and UTC_RE.match(labeled_at)):
        errors.append(f"{sid}: labeled_at must be UTC like 2026-09-29T10:19:36Z")
    if rec.get("no_candidate") is True:
        if chosen_ids:
            errors.append(f"{sid}: no_candidate cannot have chosen_box_ids")
        if rec.get("cover_ok") is True:
            errors.append(f"{sid}: no_candidate cannot have cover_ok=true")
        if status != "skipped":
            errors.append(f"{sid}: no_candidate must be skipped")
    if status == "labeled":
        if not chosen_ids:
            errors.append(f"{sid}: labeled needs chosen_box_ids")
        if rec.get("no_candidate") is True:
            errors.append(f"{sid}: labeled cannot be no_candidate")
        if rec.get("cover_ok") is None:
            errors.append(f"{sid}: labeled needs cover_ok")
        if len(chosen_ids) == 1 and rec.get("cross_box") is True:
            errors.append(f"{sid}: one box cannot be cross_box=true")
    if status == "skipped":
        if rec.get("no_candidate") is not True:
            errors.append(f"{sid}: skipped requires no_candidate=true")
        if chosen_ids:
            errors.append(f"{sid}: skipped cannot have chosen_box_ids")
        if rec.get("cover_ok") is not False:
            errors.append(f"{sid}: skipped cover_ok must be false")
        if rec.get("cross_box") is not False:
            errors.append(f"{sid}: skipped cross_box must be false")
        if levels:
            errors.append(f"{sid}: skipped cover_levels must be empty")
    return errors


def check_labels(pilot: list[dict], labels: list[dict], annotator: str | None = None) -> dict:
    expected = [row["sample_id"] for row in pilot]
    expected_set = set(expected)
    by_id = {row["sample_id"]: row for row in pilot}
    seen: list[str] = []
    missing_fields: list[dict] = []
    illegal_box_ids: list[dict] = []
    protocol_errors: list[dict] = []
    status_errors: list[dict] = []
    type_errors: list[dict] = []
    conflict_errors: list[dict] = []
    extra_ids: list[str] = []
    review_conflicts: list[dict] = []
    metadata_errors_found: list[dict] = []
    for rec in labels:
        sid = rec.get("sample_id")
        if sid not in expected_set:
            extra_ids.append(str(sid))
            continue
        seen.append(sid)
        levels = rec.get("cover_levels") or {}
        if (
            rec.get("cover_ok") is True
            and rec.get("cross_box") is True
            and isinstance(levels, dict)
            and any(value == "full" for value in levels.values())
        ):
            review_conflicts.append(
                {
                    "sample_id": sid,
                    "error": f"{sid}: full and cross_box=true needs human review",
                }
            )
        for msg in metadata_errors(by_id[sid], rec):
            metadata_errors_found.append({"sample_id": sid, "error": msg})
        for msg in record_errors(by_id[sid], rec, annotator):
            if "missing" in msg:
                missing_fields.append({"sample_id": sid, "error": msg})
            elif "protocol_version" in msg:
                protocol_errors.append({"sample_id": sid, "error": msg})
            elif "illegal label_status" in msg or "pending" in msg or "skipped" in msg or "labeled" in msg:
                status_errors.append({"sample_id": sid, "error": msg})
            elif "box_id" in msg or "cover_levels" in msg:
                illegal_box_ids.append({"sample_id": sid, "error": msg})
            elif "no_candidate" in msg or "cross_box" in msg or "cover_ok" in msg:
                conflict_errors.append({"sample_id": sid, "error": msg})
            else:
                type_errors.append({"sample_id": sid, "error": msg})
    counts = Counter(seen)
    duplicates = sorted(sid for sid, n in counts.items() if n > 1)
    missing_ids = [sid for sid in expected if sid not in counts]
    pending = sum(1 for rec in labels if rec.get("sample_id") in expected_set and rec.get("label_status") == "pending")
    labeled = sum(1 for rec in labels if rec.get("sample_id") in expected_set and rec.get("label_status") == "labeled")
    skipped = sum(1 for rec in labels if rec.get("sample_id") in expected_set and rec.get("label_status") == "skipped")
    problems = (
        missing_fields
        + duplicates
        + illegal_box_ids
        + protocol_errors
        + status_errors
        + type_errors
        + conflict_errors
        + extra_ids
        + missing_ids
        + metadata_errors_found
    )
    return {
        "n_pilot": len(expected),
        "n_label_rows": len(labels),
        "missing_fields": missing_fields,
        "duplicate_sample_ids": duplicates,
        "illegal_box_ids": illegal_box_ids,
        "protocol_errors": protocol_errors,
        "status_errors": status_errors,
        "type_errors": type_errors,
        "conflict_errors": conflict_errors,
        "review_conflicts": review_conflicts,
        "metadata_errors": metadata_errors_found,
        "extra_sample_ids": extra_ids,
        "missing_sample_ids": missing_ids,
        "pending": pending,
        "labeled": labeled,
        "skipped": skipped,
        "unlabeled": pending + len(missing_ids),
        "ok": not problems,
        "test_eval_ids_opened": False,
        "evaluation_gold_used": False,
        "auto_labels_written": False,
        "training_started": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and check the 40-question region annotation workflow.")
    parser.add_argument("mode", choices=["prepare", "check"], help="prepare rebuilds workbook only; check validates a label file.")
    parser.add_argument("--annotator", choices=["A", "B"], default="A", help="Which independent label file to check.")
    parser.add_argument("--labels", default="", help="Optional path to a JSONL file. Does not overwrite A/B files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in PROTECTED:
        if not path.is_file():
            raise RuntimeError(f"protected file missing: {path}")
    if args.mode == "prepare" and args.labels:
        raise RuntimeError("prepare does not take --labels; it never overwrites human files")
    if args.mode == "check" and args.annotator == "B" and args.labels == "" and not LABEL_FILES["B"].is_file():
        raise RuntimeError("labels_annotator_B.jsonl does not exist yet; export it from the workbook first")
    labels_path = Path(args.labels) if args.labels else LABEL_FILES[args.annotator]
    check_path = CHECK_FILES[args.annotator]
    if args.labels:
        check_path = REPO / "tmp" / f"region_ann_check_{args.annotator}.json"
    pilot = load_jsonl(PILOT)
    if len(pilot) != 40:
        raise RuntimeError(f"expected 40 pilot rows, got {len(pilot)}")
    images = verify_images(pilot)
    if not images["complete"]:
        raise RuntimeError(f"page/overlay images incomplete: {images}")
    if args.mode == "prepare":
        WORKBOOK.write_text(build_workbook(pilot), encoding="utf-8")
        report = {
            "images": images,
            "workbook": str(WORKBOOK),
            "human_files_untouched": [str(LABEL_FILES["A"]), str(LABEL_FILES["B"])],
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "test_eval_ids_opened": False,
            "evaluation_gold_used": False,
            "auto_labels_written": False,
            "training_started": False,
        }
        print(json.dumps({"mode": "prepare", "report": report}, ensure_ascii=False, indent=2))
        return 0
    if not labels_path.is_file():
        raise RuntimeError(f"missing {labels_path}")
    labels = load_jsonl(labels_path)
    report = check_labels(pilot, labels, args.annotator)
    report["images"] = images
    report["labels_path"] = str(labels_path)
    report["created_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    check_path.parent.mkdir(parents=True, exist_ok=True)
    check_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": "check", "labels": str(labels_path), "report": report}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] or report["unlabeled"] == 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
