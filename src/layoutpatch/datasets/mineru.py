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


def _transform_point(point, matrix):
    x, y = point
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _map_box(box, width, height, render):
    matrix = render.get("pdf_to_render_matrix", [1, 0, 0, 1, 0, 0])
    points = [_transform_point(point, matrix) for point in (
        (box[0] * width, box[1] * height),
        (box[2] * width, box[1] * height),
        (box[0] * width, box[3] * height),
        (box[2] * width, box[3] * height),
    )]
    scale = render.get("render_scale", 2.0)
    pixel_origin = render.get("pixel_origin", [0, 0])
    xs = [point[0] * scale - pixel_origin[0] for point in points]
    ys = [point[1] * scale - pixel_origin[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _same_box(left, right):
    return len(left) == len(right) and all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(left, right, strict=True))


def export_page(payload, identity, render):
    """只导出顶层页块，不裁剪或使用gold；保留PDF到渲染坐标的仿射变换。"""
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
    media_size = render["pdf_size_points"]
    page_rect = render.get("page_rect", [0, 0, media_size[0], media_size[1]])
    rotated_size = [page_rect[2] - page_rect[0], page_rect[3] - page_rect[1]]
    if _same_box(size, media_size):
        parser_coordinate_frame = "unrotated_media_points"
        map_render = render
    elif _same_box(size, rotated_size):
        parser_coordinate_frame = "rotated_page_points"
        map_render = {**render, "pdf_to_render_matrix": [1, 0, 0, 1, -page_rect[0], -page_rect[1]]}
    else:
        raise ValueError("parser/PDF coordinate frame mismatch")
    if not _same_box(render["cropbox"], render["mediabox"]):
        raise ValueError("CropBox differs from MediaBox; coordinate origin needs verification")
    width, height = size
    page_width, page_height = render["page_size"]
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
        mapped = _map_box(box, width, height, map_render)
        if any(v < -1e-6 for v in mapped[:2]) or mapped[2] > page_width + 1e-6 or mapped[3] > page_height + 1e-6:
            outside += 1
            continue
        seen[tuple(box)] += 1
        candidates.append({
            "doc_id": identity["doc_id"], "page_id": identity["page_id"],
            "page_number": identity["page_number"], "pdf_page_index": index,
            "layout_id": block["index"], "candidate_id": f"{identity['page_id']}:block:{block['index']}",
            "type": TYPE_MAP[block["type"]], "parser_type": block["type"],
            "bbox": mapped, "page_size": [page_width, page_height], "parser_bbox_unit": box,
            "text": _text(block), "ocr_text": None, "vlm_text": None,
            "text_source": "unknown",
        })
    audit = {"candidate_count": len(candidates), "invalid_boxes": invalid, "out_of_bounds_boxes": outside,
             "duplicate_boxes": sum(n - 1 for n in seen.values()), "no_candidates": not candidates,
             "types": dict(Counter(c["parser_type"] for c in candidates)),
             "coordinate_contract": "unit_xyxy_parser_frame_to_PyMuPDF_render_pixels",
             "parser_coordinate_frame": parser_coordinate_frame,
             "parser_to_render_matrix": map_render["pdf_to_render_matrix"],
             "parser_page_size_points": size}
    if invalid or outside:
        raise ValueError(f"invalid_boxes={invalid}; out_of_bounds_boxes={outside}; no clipping performed")
    ids = [c["layout_id"] for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate layout IDs")
    return sorted(candidates, key=lambda c: c["layout_id"]), audit


def check_scoring_structure(candidates, render):
    """检查既有候选接口，不调用模型、排序或指标函数。"""
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
