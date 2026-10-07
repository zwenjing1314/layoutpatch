"""MinerU 4 / DocVortex 2.0 页块到既有定位候选字段的无评分适配。"""
from __future__ import annotations

import math
from collections import Counter

TYPE_MAP = {
    "text": "text", "list": "text", "index": "text", "ref_text": "text",
    "header": "text", "footer": "text", "page_number": "text", "aside_text": "text",
    "page_footnote": "text", "code": "text", "doc_title": "title", "paragraph_title": "title",
    "image": "image", "chart": "image", "table": "table", "equation": "equation",
}


def _text(value):
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content
        return " ".join(filter(None, (_text(v) for k, v in value.items() if k not in {"bbox", "image_base64", "image_path"})))
    if isinstance(value, list):
        return " ".join(filter(None, map(_text, value)))
    return ""


def export_page(payload, identity, render):
    """只导出顶层页块，保留原框；越界/空框立即停，不裁剪或使用gold。"""
    if payload.get("schema") != "docvortex.middle" or payload.get("schema_version") != "2.0":
        raise ValueError("unsupported MinerU schema")
    index = identity["pdf_page_index"]
    if [p["page_idx"] for p in payload["pages"]] != [index]:
        raise ValueError("parser output must contain only the requested source page")
    geometry = payload["extensions"]["docvortex_layout"]
    sizes = [p for p in geometry["pages"] if p["page_idx"] == index]
    if geometry["version"] != 1 or len(sizes) != 1:
        raise ValueError("missing unique original page geometry")
    size = [sizes[0]["width_pt"], sizes[0]["height_pt"]]
    if any(not math.isclose(a, b, abs_tol=1e-5) for a, b in zip(size, render["pdf_size_points"], strict=True)):
        raise ValueError("parser/PDF coordinate frame mismatch")
    if render["rotation"] != 0 or render["cropbox"] != render["mediabox"]:
        raise ValueError("rotation or crop mapping requires separate verification")
    width, height = render["page_size"]
    candidates, seen = [], Counter()
    invalid = outside = 0
    for block in payload["pages"][0]["blocks"]:
        box = block.get("bbox")
        if (not isinstance(box, list) or len(box) != 4 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box) or
                not (box[0] < box[2] and box[1] < box[3])):
            invalid += 1
            continue
        if any(v < 0 or v > 1 for v in box):
            outside += 1
            continue
        if block.get("type") not in TYPE_MAP or type(block.get("index")) is not int:
            raise ValueError("unresolved candidate type or block identity")
        mapped = [box[0] * width, box[1] * height, box[2] * width, box[3] * height]
        seen[tuple(box)] += 1
        candidates.append({
            "doc_id": identity["doc_id"], "page_id": identity["page_id"],
            "page_number": identity["page_number"], "pdf_page_index": index,
            "layout_id": block["index"], "candidate_id": f"{identity['page_id']}:block:{block['index']}",
            "type": TYPE_MAP[block["type"]], "parser_type": block["type"],
            "bbox": mapped, "page_size": [width, height], "parser_bbox_unit": box,
            "text": _text(block), "ocr_text": None, "vlm_text": None,
            "text_source": "MinerU_basic_auto_native_PDF_or_OCR_per_span_unresolved_no_VLM_description",
        })
    audit = {"candidate_count": len(candidates), "invalid_boxes": invalid, "out_of_bounds_boxes": outside,
             "duplicate_boxes": sum(n - 1 for n in seen.values()), "no_candidates": not candidates,
             "types": dict(Counter(c["parser_type"] for c in candidates)),
             "coordinate_contract": "unit_xyxy_top_left_to_render_pixels", "parser_page_size_points": size}
    if invalid or outside:
        raise ValueError(f"invalid_boxes={invalid}; out_of_bounds_boxes={outside}; no clipping performed")
    ids = [c["layout_id"] for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate layout IDs")
    return sorted(candidates, key=lambda c: c["layout_id"]), audit


def check_scoring_structure(candidates, render):
    """检查现有page_layout/区域指标所需字段，不调用模型、排序或指标函数。"""
    from layoutpatch.layout.correspondence import scale_bbox_to_model
    from layoutpatch.layout.schema import TYPE_TO_ID

    for candidate in candidates:
        if candidate["page_size"] != render["page_size"] or candidate["type"] not in TYPE_TO_ID:
            raise ValueError("candidate interface mismatch")
        mapped = scale_bbox_to_model(candidate["bbox"], candidate["page_size"])
        if not all(math.isfinite(v) and 0 <= v <= 448 for v in mapped):
            raise ValueError("candidate-to-patch frame conversion failed")
    return {"status": "passed", "fields": ["layout_id", "bbox", "page_size", "type", "text"],
            "patch_frame": [448, 448], "scores_computed": False,
            "embedding_cache_checked": False, "external_text_encoding_rule_pending": True}
