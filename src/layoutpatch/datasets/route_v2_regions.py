"""Route-v2 region units: question-linked gold boxes, page candidates and patch labels.

A unit is one (query, gold page). Gold boxes come only from a question's official
``layout_mapping``; candidates come only from that page's parsed layout rows and are
never derived from gold. Boxes stay in the page frame (``page_size`` points) and are
scaled to the 448 model canvas only for patch labels.

Patch rule (borrowed from RegionRAG Sec. 3.3): positive if the patch centre lies inside
any gold box (edges inclusive); negative if the patch has zero overlap with every gold
box; otherwise ignored. Ignored patches are never used as negatives.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

from layoutpatch.datasets.route_v2_split import document_id
from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.layout.correspondence import (
    GRID,
    area,
    clamp_bbox,
    intersection_area,
    patch_bbox,
    scale_bbox_to_model,
)
from layoutpatch.layout.schema import canonical_layout_type

EXACT_MATCH_TOL = 1.0  # points: official gold boxes are integer-rounded parser boxes
PAGE_SIZE_TOL = 0.5
BOUNDS_TOL = 1.0
POSITIVE, NEGATIVE, IGNORED = 1, 0, -1


def _box(values: Sequence[Any]) -> list[float]:
    box = [float(v) for v in values]
    if len(box) != 4:
        raise ValueError(f"bbox needs four values, got {values}")
    return box


def patch_labels(gold_boxes: Sequence[Sequence[float]], page_size: Sequence[float]) -> list[int]:
    """1024 labels in row-major patch order: 1 positive, 0 negative, -1 ignored."""
    scaled = [
        clamp_bbox(scale_bbox_to_model(_box(b), [float(v) for v in page_size])) for b in gold_boxes
    ]
    scaled = [s for s in scaled if area(s) > 0]
    labels = []
    for index in range(GRID * GRID):
        cell = patch_bbox(index)
        cx, cy = (cell[0] + cell[2]) / 2, (cell[1] + cell[3]) / 2
        if any(s[0] <= cx <= s[2] and s[1] <= cy <= s[3] for s in scaled):
            labels.append(POSITIVE)
        elif all(intersection_area(cell, s) <= 0 for s in scaled):
            labels.append(NEGATIVE)
        else:
            labels.append(IGNORED)
    return labels


def normalize_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical candidate record from one raw layout row; text kept only as lengths."""

    def chars(key: str) -> int:
        value = row.get(key)
        return len(value.strip()) if isinstance(value, str) else 0

    return {
        "layout_id": int(row["layout_id"]),
        "raw_type": row.get("type"),
        "type": canonical_layout_type(row.get("type")),
        "bbox": _box(row["bbox"]),
        "page_size": [float(v) for v in row["page_size"]],
        "text_chars": chars("text"),
        "ocr_chars": chars("ocr_text"),
        "vlm_chars": chars("vlm_text"),
    }


def _same_size(a: Sequence[float], b: Sequence[float]) -> bool:
    return len(a) == len(b) == 2 and all(
        abs(x - y) <= PAGE_SIZE_TOL for x, y in zip(a, b, strict=True)
    )


def _unit(
    query_id: str,
    doc: str,
    page: int,
    mappings: Sequence[Mapping[str, Any]],
    question_pages: Sequence[int],
    num_gold_pages: int,
    candidates: Sequence[Mapping[str, Any]],
    cache_ready: bool,
) -> dict[str, Any]:
    sizes = [[float(v) for v in m.get("page_size") or []] for m in mappings]
    page_size = sizes[0]
    size_conflict = any(not _same_size(s, page_size) for s in sizes)
    raw = [_box(m["bbox"]) for m in mappings]
    unique: list[list[float]] = []
    for box in raw:
        if box not in unique:
            unique.append(box)
    valid, invalid, out_of_bounds = [], 0, 0
    width, height = (page_size + [0.0, 0.0])[:2]
    for box in unique:
        if box[2] <= box[0] or box[3] <= box[1] or width <= 0 or height <= 0:
            invalid += 1
            continue
        if (
            min(box[0], box[1]) < -BOUNDS_TOL
            or box[2] > width + BOUNDS_TOL
            or box[3] > height + BOUNDS_TOL
        ):
            out_of_bounds += 1
        valid.append(box)
    candidate_conflict = any(not _same_size(c["page_size"], page_size) for c in candidates)
    exact, best = [], []
    for box in valid:
        hits = [
            c["layout_id"]
            for c in candidates
            if max(abs(g - v) for g, v in zip(box, c["bbox"], strict=True)) <= EXACT_MATCH_TOL
        ]
        exact.append(min(hits) if hits else None)
        best.append(max((bbox_iou(box, c["bbox"]) for c in candidates), default=0.0))
    labels = patch_labels(valid, page_size) if valid and not size_conflict else [NEGATIVE] * GRID**2
    pos = [i for i, v in enumerate(labels) if v == POSITIVE]
    ignored = [i for i, v in enumerate(labels) if v == IGNORED]
    coordinate_conflict = size_conflict or candidate_conflict
    eval_ready = cache_ready and bool(valid) and not coordinate_conflict
    page_area = width * height if width > 0 and height > 0 else 0.0
    return {
        "unit_id": f"{query_id}#p{page}",
        "query_id": query_id,
        "doc_id": doc,
        "page": page,
        "page_cache_id": f"{doc}_p{page}",
        "question_pages": list(question_pages),
        "page_in_question_pages": page in question_pages,
        "num_gold_pages": num_gold_pages,
        "page_size": page_size,
        "gold_boxes": valid,
        "gold_raw_count": len(raw),
        "gold_duplicates_removed": len(raw) - len(unique),
        "gold_invalid": invalid,
        "gold_out_of_bounds": out_of_bounds,
        "gold_area_frac": [area(b) / page_area if page_area else 0.0 for b in valid],
        "gold_exact_layout_id": exact,
        "gold_best_candidate_iou": best,
        "candidate_count": len(candidates),
        "coordinate_conflict": coordinate_conflict,
        "patch_pos_idx": pos,
        "patch_ignore_idx": ignored,
        "patch_pos": len(pos),
        "patch_ignore": len(ignored),
        "patch_neg": GRID**2 - len(pos) - len(ignored),
        "cache_ready": cache_ready,
        "eval_ready": eval_ready,
        "local_loss_ready": eval_ready and bool(pos) and len(pos) + len(ignored) < GRID**2,
    }


def build_region_units(
    annotation_rows: Iterable[tuple[int, Mapping[str, Any]]],
    candidates_by_page: Mapping[tuple[str, int], Sequence[Mapping[str, Any]]],
    cached_pages: Collection[tuple[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(units, questions)``; query IDs follow the global source question order."""
    units: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    counter = 0
    for _, annotation in sorted(annotation_rows, key=lambda row: row[0]):
        doc = document_id(annotation["doc_name"])
        for question in annotation["questions"]:
            query_id = f"mmdocir_{counter:05d}"
            counter += 1
            mappings = list(question.get("layout_mapping") or [])
            question_pages = sorted({int(p) for p in question.get("page_id") or []})
            by_page: dict[int, list[Mapping[str, Any]]] = {}
            for mapping in mappings:
                by_page.setdefault(int(mapping["page"]), []).append(mapping)
            questions.append(
                {
                    "query_id": query_id,
                    "doc_id": doc,
                    "has_layout_gold": bool(mappings),
                    "gold_mapping_count": len(mappings),
                    "gold_pages": sorted(by_page),
                    "question_pages": question_pages,
                    "gold_pages_outside_question_pages": sorted(set(by_page) - set(question_pages)),
                }
            )
            for page, page_mappings in sorted(by_page.items()):
                units.append(
                    _unit(
                        query_id,
                        doc,
                        page,
                        page_mappings,
                        question_pages,
                        len(by_page),
                        candidates_by_page.get((doc, page), []),
                        (doc, page) in cached_pages,
                    )
                )
    return units, questions
