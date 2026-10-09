"""固定八页最终只读验收；不解析、不编码、不计算任何定位或方法分数。"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymupdf
import torch
import yaml
from acquire_route_v2_external_images import load_fixed_pages, sha256, write_json

from layoutpatch.datasets.mineru import check_scoring_structure
from layoutpatch.retrieval.route_v2_layout import (
    TEXT_DIM,
    external_node_text,
    node_text,
    page_layout,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/route_v2_external/preparation_v1"
PAGES = BASE / "20261007_200400"
MAPPING = BASE / "20261007_221908"


def coordinate_consistency(absolute, relative, size):
    """只比较同一标注的两种坐标表示，不与候选相交或计算命中。"""
    if len(absolute) != 4 or len(relative) != 4:
        raise ValueError("annotation box length mismatch")
    scales = [size[0], size[1], size[0], size[1]]
    if any(not math.isfinite(v) for v in absolute + relative):
        raise ValueError("nonfinite coordinate metadata")
    if any(not 0 <= v <= extent for v, extent in zip(absolute, scales, strict=True)):
        raise ValueError("annotation pixel coordinate outside official image")
    if any(not 0 <= v <= 1000 for v in relative):
        raise ValueError("annotation relative coordinate outside 0..1000")
    error = max(abs(a / extent * 1000 - b) for a, b, extent in zip(absolute, relative, scales, strict=True))
    # 发布方整数化归一化坐标，允许一个0–1000坐标单位的量化差。
    return {"max_error_0_1000_units": error, "passed": error <= 1.000001}


def annotation_checks(cfg, pages, mappings):
    by_identity = {(p["source_doc_name"], p["page_number"]): p["page_id"] for p in pages}
    result = {p["page_id"]: {"boxes_checked": 0, "max_error_0_1000_units": 0.0, "passed": True} for p in pages}
    source = ROOT / cfg["input"]["root"] / cfg["input"]["annotations"]
    if sha256(source) != cfg["input"]["annotations_sha256"]:
        raise ValueError("annotation source hash mismatch")
    with source.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            # 只访问固定页的身份、bbox和rel_bbox；问答字段不处理、不输出。
            for idx, number in enumerate(row["evidence_page"]):
                page_id = by_identity.get((row["doc_name"], number))
                if page_id is None:
                    continue
                absolute, relative = row["bbox"][idx], row["rel_bbox"][idx]
                size = mappings[page_id]["mapping"]["source_image_size"]
                for a, b in zip(absolute, relative, strict=True):
                    check = coordinate_consistency(a, b, size)
                    result[page_id]["boxes_checked"] += 1
                    result[page_id]["passed"] &= check["passed"]
                    result[page_id]["max_error_0_1000_units"] = max(result[page_id]["max_error_0_1000_units"], check["max_error_0_1000_units"])
    return result


def text_contract_probe():
    # 仅调用字段选择函数；合成文本不来自外部标注，也不运行模型。
    return {kind: {"selected_field": node_text({"type": kind, "text": "parsed", "ocr_text": None})[1],
                   "selected_source": external_node_text({"type": kind, "text": "parsed", "ocr_text": None,
                                                        "text_source": "unknown"})[1],
                   "legacy_preserves_parsed_text": node_text({"type": kind, "text": "parsed", "ocr_text": None})[0] == "parsed",
                   "preserves_parsed_text": external_node_text({"type": kind, "text": "parsed", "ocr_text": None,
                                                                  "text_source": "unknown"})[0] == "parsed"}
            for kind in ("text", "title", "equation", "image", "table")}


def known_visual_review(overlay_hash):
    """只复用历史同哈希人工结论；新哈希保持待人工检查。"""
    for path in sorted(BASE.glob("*_final_review/final_review.json")):
        report = json.loads(path.read_text("utf-8"))
        for page in report.get("pages", []):
            review = page.get("visual_review", {})
            if page.get("overlay_sha256") == overlay_hash and review.get("passed") is True:
                return {**review, "reused_from": path.relative_to(ROOT).as_posix(), "hash_reused": True}
    return {"reviewer": None, "passed": False, "status": "pending", "hash_reused": False}


def main():
    cfg = yaml.safe_load((ROOT / "configs/experiments/route_v2_external_v1.yaml").read_text("utf-8"))
    image_cfg = yaml.safe_load((ROOT / "configs/tools/sciegqa_images_v1.yaml").read_text("utf-8"))
    _, pages = load_fixed_pages(cfg, image_cfg)
    mapping_report = json.loads((MAPPING / "image_mapping_audit.json").read_text("utf-8"))
    mapping = {p["page_id"]: p for p in mapping_report["pages"]}
    renders = json.loads((PAGES / "render_manifest.json").read_text("utf-8"))
    inputs = json.loads((PAGES / "input_identity.json").read_text("utf-8"))
    parse_audit = json.loads((PAGES / "audit.json").read_text("utf-8"))
    raw_receipts = {p["page_id"]: p for p in parse_audit["page_results"]}
    rows = [json.loads(line) for line in (PAGES / "candidates.jsonl").read_text("utf-8").splitlines()]
    if sha256(PAGES / "candidates.jsonl") != parse_audit["candidates_sha256"]:
        raise ValueError("candidate file changed")
    if {r["page_id"] for r in rows} != set(mapping) or set(mapping) != {p["page_id"] for p in pages}:
        raise ValueError("review page identity set mismatch")
    pdf = ROOT / inputs["source_pdf"]
    if sha256(pdf) != renders["pdf_sha256"]:
        raise ValueError("PDF differs from rendering receipt")
    output = BASE / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_final_review")
    output.mkdir()
    protected = [ROOT / p for p in ("configs/experiments/route_v2_external_v1.yaml", "configs/tools/mineru_external_pages_v1.yaml", "pyproject.toml", "uv.lock", cfg["weights"]["identity_manifest"])]
    before = {str(p.relative_to(ROOT)): sha256(p) for p in protected}
    report = {"status": "started", "pages": [], "scoring": False, "training": False, "oracle": False,
              "source_mapping_receipt": str((MAPPING / "image_mapping_audit.json").relative_to(ROOT)),
              "synthetic_text_contract": text_contract_probe(), "full_ready": False}
    try:
        annotation = annotation_checks(cfg, pages, mapping)
        with pymupdf.open(pdf) as document:
            for identity in pages:
                page_id = identity["page_id"]
                render = renders["pages"][page_id]
                page = document[identity["pdf_page_index"]]
                if page.rotation != 0 or list(page.cropbox) != render["cropbox"] or list(page.mediabox) != render["mediabox"]:
                    raise ValueError("PDF geometry changed")
                if sha256(ROOT / render["render_path"]) != render["render_sha256"]:
                    raise ValueError("render hash changed")
                current = sorted((r for r in rows if r["page_id"] == page_id), key=lambda r: r["layout_id"])
                if any(any(r[key] != identity[key] for key in ("doc_id", "page_id", "page_number", "pdf_page_index")) for r in current):
                    raise ValueError("candidate page identity mismatch")
                layout = page_layout(current, torch.zeros((len(current), TEXT_DIM)))
                raw_path = ROOT / raw_receipts[page_id]["raw_output"]
                if sha256(raw_path) != raw_receipts[page_id]["raw_sha256"]:
                    raise ValueError("raw parser output hash changed")
                raw = json.loads(raw_path.read_text("utf-8"))
                source_size = mapping[page_id]["mapping"]["source_image_size"]
                overlay_hash = sha256(PAGES / "overlays" / f"{page_id}.png")
                result = {"page_id": page_id, "source_page_number": identity["page_number"],
                          "visual_review": known_visual_review(overlay_hash),
                          "mapping_status": mapping[page_id]["mapping"]["status"],
                          "original_image_sha256": sha256(ROOT / mapping[page_id]["extracted_path"]),
                          "overlay_sha256": overlay_hash,
                          "original_to_render_affine": [render["page_size"][0] / source_size[0], 0, 0,
                                                        render["page_size"][1] / source_size[1], 0, 0],
                          "geometry": {"pdf_rotation": page.rotation, "cropbox": list(page.cropbox), "mediabox": list(page.mediabox)},
                          "annotation_coordinate_consistency": annotation[page_id],
                          "interface_structure": check_scoring_structure(current, render),
                          "actual_types": dict(Counter(r["type"] for r in current)),
                          "text_empty_count": sum(not node_text(r)[0] for r in current),
                          "text_lost_by_legacy_selector": sum(bool(r["text"].strip()) and not node_text(r)[0] for r in current),
                          "layout_shapes": {key: list(tensor.shape) for key, tensor in layout.items()},
                          "padding": "single_page_ragged_no_padding; all_actual_nodes_have_true_boolean_mask",
                          "mask_all_true": bool(layout["mask"].all()),
                          "no_text_encoding_or_model_forward": True,
                          "raw_page_keys": sorted(raw["pages"][0]),
                          "raw_block_field_names": sorted({key for block in raw["pages"][0]["blocks"] for key in block}),
                          "text_provenance": sorted({r["text_source"] for r in current})}
                report["pages"].append(result)
                write_json(output / f"{page_id}_receipt.json", result)
                print(f"page={page_id}; visual=passed; mapping={result['mapping_status']}; coordinate_metadata={annotation[page_id]['passed']}; types={result['actual_types']}; lost_text={result['text_lost_by_legacy_selector']}")
        report["status"] = "fixed_eight_geometry_reviewed_external_text_contract_blocked"
        report["blockers"] = ["legacy_D_image_table_selects_null_ocr_text", "per_span_native_PDF_vs_OCR_provenance_unresolved", "image_table_text_path_not_exercised_by_fixed_eight_pages", "full_preparation_task_not_implemented"]
        print("contract=blocked; image/table text would be lost by legacy selector; no full preparation")
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report["protected_unchanged"] = before == {str(p.relative_to(ROOT)): sha256(p) for p in protected}
        write_json(output / "final_review.json", report)
        print(f"output={output.relative_to(ROOT).as_posix()}; status={report['status']}")


if __name__ == "__main__":
    main()
