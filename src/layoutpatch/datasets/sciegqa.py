"""SciEGQA固定版本的元数据适配；不返回题目、答案或gold坐标。"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import PurePosixPath

FIELDS = {"query", "answer", "doc_name", "category", "evidence_page", "bbox", "rel_bbox", "subimg_type"}


def _safe_name(value):
    return (isinstance(value, str) and bool(value) and not any(c in value for c in '\\/:*?"<>|')
            and PurePosixPath(value).name == value and value not in {".", ".."})


def _valid_box(box, *, relative):
    if not isinstance(box, list) or len(box) != 4:
        return False
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
        return False
    x1, y1, x2, y2 = box
    # 发布方转换器明确使用0–1000，不能将“normalized”解释为0–1。
    return 0 <= x1 < x2 and 0 <= y1 < y2 and (not relative or (x2 <= 1000 and y2 <= 1000))


def metadata_manifest(records):
    """保留每行身份及失败状态；页选择仅按文档/页号，不看标注覆盖。"""
    questions, pages, failures = [], {}, Counter()
    formats, docs = Counter(), set()
    for index, row in enumerate(records):
        qid = f"sciegqa_{index:05d}"
        errors = []
        if not isinstance(row, dict):
            questions.append({"query_id": qid, "source_row": index, "errors": ["not_object"]})
            failures["not_object"] += 1
            continue
        if set(row) != FIELDS:
            errors.append("unsupported_fields")
        name, category = row.get("doc_name"), row.get("category")
        identity_ok = _safe_name(name) and _safe_name(category)
        doc_id = name.removesuffix(".pdf") if identity_ok else None
        evidence = row.get("evidence_page")
        page_ok = isinstance(evidence, list) and bool(evidence) and all(type(p) is int and p >= 1 for p in evidence)
        if not identity_ok:
            errors.append("invalid_document_identity")
        if not page_ok or len(set(evidence)) != len(evidence):
            errors.append("invalid_evidence_pages")
        if not isinstance(row.get("query"), str) or not isinstance(row.get("answer"), str):
            errors.append("invalid_text_field_types")
        if page_ok:
            formats[len(evidence)] += 1
            arrays_ok = all(isinstance(row.get(k), list) and len(row[k]) == len(evidence) for k in ("bbox", "rel_bbox", "subimg_type"))
            if not arrays_ok:
                errors.append("page_annotation_alignment")
            else:
                for absolute, relative, kinds in zip(row["bbox"], row["rel_bbox"], row["subimg_type"], strict=True):
                    if not all(isinstance(v, list) for v in (absolute, relative, kinds)) or not absolute or len(absolute) != len(relative) or len(absolute) != len(kinds):
                        errors.append("box_annotation_alignment")
                        continue
                    if not all(_valid_box(b, relative=False) for b in absolute):
                        errors.append("invalid_absolute_box")
                    if not all(_valid_box(b, relative=True) for b in relative):
                        errors.append("invalid_relative_box")
                    if not all(isinstance(kind, str) for kind in kinds):
                        errors.append("invalid_region_type")
            if identity_ok:
                docs.add(doc_id)
                for page in evidence:
                    key = doc_id, page
                    value = {"doc_id": doc_id, "source_doc_name": name, "category": category,
                             "page_number": page, "pdf_page_index": page - 1, "page_id": f"{doc_id}_p{page - 1}",
                             "official_image_relative_path": f"{category}/{doc_id}/{doc_id}_{page}.png",
                             "original_image_size": None, "rendered_size": None, "render_transform": None,
                             "mapping_status": "pending_real_render_and_original_frame_verification"}
                    if key in pages and pages[key] != value:
                        errors.append("document_page_identity_conflict")
                    pages[key] = value
        errors = sorted(set(errors))
        failures.update(errors)
        questions.append({"query_id": qid, "source_row": index, "doc_id": doc_id,
                          "evidence_pages": evidence if page_ok else None, "errors": errors})
    ordered = [pages[key] for key in sorted(pages)]
    return {"schema": "sciegqa-metadata-v1", "questions": questions, "pages": ordered,
            "sample_page_ids": [p["page_id"] for p in ordered[:8]],
            "counts": {"questions": len(records), "documents": len(docs), "unique_evidence_pages": len(ordered),
                       "question_page_units": sum(len(q.get("evidence_pages") or []) for q in questions),
                       "pages_per_question": dict(sorted(formats.items())),
                       "failed_questions": sum(bool(q["errors"]) for q in questions)},
            "validation_errors": dict(failures), "failed_questions_retained": True,
            "gold_coordinates_exported": False, "candidates_generated": False, "effect_metrics_computed": False}
