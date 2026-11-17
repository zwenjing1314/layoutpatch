"""Gold-blind, receipt-bound MinerU annotation augmentation; no parser/model calls."""
from __future__ import annotations

import copy
import math
from collections import Counter

from layoutpatch.datasets.mineru import TYPE_MAP, _map_box, _same_box, _text
from layoutpatch.layout.schema import TYPE_TO_ID

OLD = "mineru_top_v1"
NEW = "mineru_top_plus_annotations_v1"
POLICY = "mineru-top-plus-annotations-v1"
LEGACY = "unit_xyxy_top_left_to_render_pixels"
POINTS = "unit_xyxy_to_pdf_points_to_rotated_render_pixels"
FRAME = "unit_xyxy_parser_frame_to_PyMuPDF_render_pixels"
CHILD_TYPES = frozenset(f"{parent}_{suffix}" for parent in ("image", "chart", "table", "code") for suffix in ("caption", "footnote"))
BODY_TYPES = {"image_body": "image", "chart_body": "chart", "table_body": "table", "code_body": "code", "algorithm_body": "code"}


class CandidatePageError(ValueError):
    """An invalid candidate page: callers must retain its units with empty candidates."""


def validate_box(box, size):
    if (not isinstance(box, (list, tuple)) or len(box) != 4
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in box)):
        raise CandidatePageError("bbox must contain four finite nonboolean numbers")
    if not (0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1]):
        raise CandidatePageError(f"invalid or out-of-bounds bbox: {box}; canvas={size}")


def transform_spec(payload, receipt):
    if payload.get("schema") != "docvortex.middle" or payload.get("schema_version") != "2.0":
        raise CandidatePageError("unexpected raw schema")
    if [p["page_idx"] for p in payload["pages"]] != [receipt["pdf_page_index"]]:
        raise CandidatePageError("raw page identity differs from receipt")
    geometry = payload["extensions"]["docvortex_layout"]
    sizes = [p for p in geometry["pages"] if p["page_idx"] == receipt["pdf_page_index"]]
    if geometry["version"] != 1 or len(sizes) != 1:
        raise CandidatePageError("missing unique parser geometry")
    render = copy.deepcopy(receipt["render"])
    size = [sizes[0]["width_pt"], sizes[0]["height_pt"]]
    for dimensions in (size, render["page_size"]):
        if len(dimensions) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in dimensions):
            raise CandidatePageError("invalid page dimensions")
    if not _same_box(render["cropbox"], render["mediabox"]):
        raise CandidatePageError("unverified crop origin")
    contract = receipt["coordinate_contract"]
    if contract == LEGACY:
        if render["rotation"] != 0 or not _same_box(size, render["pdf_size_points"]):
            raise CandidatePageError("legacy transform requires unrotated full-page frame")
        return {"transform_id": contract, "parser_size_points": size,
                "page_size": render["page_size"], "parser_frame": "page_unit_xyxy", "render": render}
    if contract not in {POINTS, FRAME}:
        raise CandidatePageError(f"unknown receipt coordinate contract: {contract}")
    if "pdf_to_render_matrix" not in render:
        raise CandidatePageError("missing explicit PDF transform")
    page_rect = render.get("page_rect", [0, 0, *render["pdf_size_points"]])
    rotated = [page_rect[2] - page_rect[0], page_rect[3] - page_rect[1]]
    if _same_box(size, render["pdf_size_points"]):
        frame = "unrotated_media_points"
    elif contract == FRAME and _same_box(size, rotated):
        frame = "rotated_page_points"
        render["pdf_to_render_matrix"] = [1, 0, 0, 1, -page_rect[0], -page_rect[1]]
    else:
        raise CandidatePageError("parser geometry and receipt frame disagree")
    return {"transform_id": contract, "parser_size_points": size,
            "page_size": render["page_size"], "parser_frame": frame, "render": render}


def map_box(box, spec):
    validate_box(box, [1, 1])
    if spec["transform_id"] == LEGACY:
        width, height = spec["page_size"]
        mapped = [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
    else:
        mapped = _map_box(box, *spec["parser_size_points"], spec["render"])
    validate_box(mapped, spec["page_size"])
    return mapped


def validate_candidates(rows, page_id, page_size):
    ids = [r["layout_id"] for r in rows]
    if any(type(i) is not int or i < 0 for i in ids) or ids != sorted(set(ids)):
        raise CandidatePageError("layout IDs must be ascending unique nonnegative integers")
    if len({r["candidate_id"] for r in rows}) != len(rows):
        raise CandidatePageError("duplicate candidate ID")
    for row in rows:
        if row["page_id"] != page_id or row["page_size"] != page_size:
            raise CandidatePageError("candidate/page identity mismatch")
        if row["type"] not in TYPE_TO_ID or not isinstance(row["text"], str):
            raise CandidatePageError("invalid node type/text")
        validate_box(row["bbox"], page_size)


def provenance(condition, page_id, pointer, box, receipt, spec, parent=None):
    return {"condition_id": condition, "candidate_id": f"{condition}:{page_id}:{pointer}",
            "source_raw_sha256": receipt["raw_sha256"], "source_json_pointer": pointer,
            "source_bbox": list(box), "source_coordinate_frame": spec["parser_frame"],
            "parent_source_id": parent, "transform_id": spec["transform_id"], "export_policy_version": POLICY}


def augment_page(payload, receipt, old_rows):
    """Return OLD, NEW, aliases, structural audit; receives no questions or gold.

    Any invalid child invalidates the NEW page: no partial result is returned.
    Caller separately retains the OLD page, never uses it as a NEW fallback.
    """
    spec = transform_spec(payload, receipt)
    page_id = receipt["page_id"]
    validate_candidates(old_rows, page_id, spec["page_size"])
    blocks = payload["pages"][0]["blocks"]
    block_ids = [b["index"] for b in blocks]
    if any(type(i) is not int or i < 0 for i in block_ids) or len(set(block_ids)) != len(block_ids):
        raise CandidatePageError("duplicate/invalid raw block identity")
    if sorted(block_ids) != [r["layout_id"] for r in old_rows]:
        raise CandidatePageError("old/raw candidate IDs disagree")
    by_id = {b["index"]: (i, b) for i, b in enumerate(blocks)}
    old, new, aliases, seen = [], [], [], {}
    for row in old_rows:
        pos, block = by_id[row["layout_id"]]
        pointer = f"/pages/0/blocks/{pos}"
        mapped = map_box(block["bbox"], spec)
        if (TYPE_MAP.get(block["type"]) != row["type"] or row["parser_type"] != block["type"]
                or row["parser_bbox_unit"] != block["bbox"]
                or any(abs(x-y) > 1e-6 for x, y in zip(mapped, row["bbox"], strict=True))):
            raise CandidatePageError("receipt replay differs from frozen parent candidate")
        for condition, target in ((OLD, old), (NEW, new)):
            target.append({**copy.deepcopy(row), **provenance(condition, page_id, pointer, block["bbox"], receipt, spec),
                           "source_candidate_id": row["candidate_id"], "node_origin": "old_top"})
        seen.setdefault(tuple(block["bbox"]), new[-1]["candidate_id"])
    next_id = max(block_ids, default=-1) + 1
    expected_pointers = {f"/pages/0/blocks/{i}" for i in range(len(blocks))}
    for parent_id in sorted(by_id):
        pos, parent = by_id[parent_id]
        parent_pointer = f"/pages/0/blocks/{pos}"
        for child_pos, child in enumerate(parent.get("content", [])):
            if not isinstance(child, dict) or "bbox" not in child:
                continue
            pointer = f"{parent_pointer}/content/{child_pos}"
            expected_pointers.add(pointer)
            box = child["bbox"]
            mapped = map_box(box, spec)
            kind = child.get("type")
            body = kind in BODY_TYPES and BODY_TYPES[kind] == parent["type"]
            if body and box != parent["bbox"]:
                raise CandidatePageError("body does not equal parent geometry")
            if not body and (kind not in CHILD_TYPES or not kind.startswith(parent["type"] + "_")):
                raise CandidatePageError(f"unexpected child geometry/type at {pointer}: {kind}")
            info = provenance(NEW, page_id, pointer, box, receipt, spec, parent_pointer)
            text = _text(child)
            if tuple(box) in seen:
                aliases.append({**info, "parser_type": kind, "text": text, "bbox": mapped,
                                "alias_of": seen[tuple(box)], "reason": "parent_equal_body" if body else "exact_source_bbox_duplicate"})
                continue
            new.append({**info, "doc_id": receipt["doc_id"], "page_id": page_id,
                        "page_number": receipt["page_number"], "pdf_page_index": receipt["pdf_page_index"],
                        "layout_id": next_id, "source_candidate_id": None, "type": "text", "parser_type": kind,
                        "bbox": mapped, "page_size": list(spec["page_size"]), "parser_bbox_unit": list(box),
                        "text": text, "text_source": "unknown", "ocr_text": None, "vlm_text": None,
                        "node_origin": "annotation"})
            seen[tuple(box)] = info["candidate_id"]
            next_id += 1

    def bbox_pointers(value, pointer=""):
        found = set()
        if isinstance(value, dict):
            if "bbox" in value:
                found.add(pointer)
            for key, child in value.items():
                found.update(bbox_pointers(child, f"{pointer}/{key}"))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                found.update(bbox_pointers(child, f"{pointer}/{i}"))
        return found

    actual_pointers = bbox_pointers(payload)
    if actual_pointers != expected_pointers:
        raise CandidatePageError(f"unhandled nested bbox paths: {sorted(actual_pointers ^ expected_pointers)}")
    validate_candidates(old, page_id, spec["page_size"])
    validate_candidates(new, page_id, spec["page_size"])
    return old, new, aliases, {"old_candidates": len(old), "new_candidates": len(new),
                               "added": len(new)-len(old), "aliases": len(aliases),
                               "raw_bbox_count": len(actual_pointers), "all_raw_bbox_sources_accounted": True,
                               "transform": spec, "new_types": dict(Counter(r["parser_type"] for r in new[len(old):])),
                               "parent_replay_passed": True, "invalid_boxes": 0, "out_of_bounds_boxes": 0,
                               "duplicate_new_geometry": 0, "unknown_types": 0}
