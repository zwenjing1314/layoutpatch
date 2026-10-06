"""Synthetic checks for route-v2 region units and RegionRAG-style patch labels."""

from __future__ import annotations

from layoutpatch.datasets.route_v2_regions import (
    IGNORED,
    NEGATIVE,
    POSITIVE,
    build_region_units,
    normalize_candidate,
    patch_labels,
)
from layoutpatch.retrieval.colpali_layout import patch_index

SQUARE = [448.0, 448.0]  # page frame equals the 448 model canvas


def test_centre_inside_is_positive_partial_overlap_is_ignored_rest_negative():
    labels = patch_labels([[10, 14, 42, 28]], SQUARE)
    assert labels[patch_index(1, 1)] == POSITIVE and labels[patch_index(1, 2)] == POSITIVE
    assert labels[patch_index(1, 0)] == IGNORED  # overlaps x in [10, 14], centre x=7 outside
    assert labels[patch_index(0, 1)] == NEGATIVE  # touches only along y=14 (zero area)
    assert labels.count(POSITIVE) == 2 and labels.count(IGNORED) == 1


def test_box_without_patch_centre_has_no_positive():
    labels = patch_labels([[15, 15, 20, 20]], SQUARE)
    assert labels.count(POSITIVE) == 0 and labels.count(IGNORED) == 1


def test_labels_scale_non_square_pages_per_axis():
    labels = patch_labels([[0, 0, 50, 50]], [100.0, 200.0])  # -> [0, 0, 224, 112] on canvas
    assert labels[patch_index(7, 15)] == POSITIVE
    assert labels[patch_index(8, 15)] == NEGATIVE and labels[patch_index(7, 16)] == NEGATIVE


def candidate(layout_id, raw_type, bbox, page_size, **text):
    return normalize_candidate(
        {"layout_id": layout_id, "type": raw_type, "bbox": bbox, "page_size": page_size, **text}
    )


def test_units_link_gold_to_parsed_candidates_without_injecting_gold():
    annotations = [
        (0, {"doc_name": "paper.v2.pdf", "questions": [
            {"page_id": [0], "layout_mapping": [
                {"page": 0, "page_size": SQUARE, "bbox": [10, 14, 42, 28]},
                {"page": 0, "page_size": SQUARE, "bbox": [10, 14, 42, 28]},
            ]},
            {"page_id": [1], "layout_mapping": []},
        ]}),
        (2, {"doc_name": "report.pdf", "questions": [
            {"page_id": [0], "layout_mapping": [
                {"page": 0, "page_size": [100, 200], "bbox": [0, 0, 50, 50]},
                {"page": 3, "page_size": [100, 200], "bbox": [0, 0, 50, 50]},
            ]},
        ]}),
    ]
    candidates = {
        ("paper.v2", 0): [
            candidate(5, "text", [10.4, 14.2, 41.6, 28.3], SQUARE, text="abc", ocr_text=""),
            candidate(2, "image", [0, 100, 448, 448], SQUARE),
        ],
        ("report", 0): [candidate(0, "table_block", [0, 0, 100, 100], [100, 201])],
    }
    cached = {("paper.v2", 0), ("report", 0), ("report", 3)}
    units, questions = build_region_units(annotations, candidates, cached)
    assert [q["query_id"] for q in questions] == ["mmdocir_00000", "mmdocir_00001", "mmdocir_00002"]
    assert questions[1]["has_layout_gold"] is False
    assert questions[2]["gold_pages_outside_question_pages"] == [3]
    by_id = {u["unit_id"]: u for u in units}
    assert sorted(by_id) == ["mmdocir_00000#p0", "mmdocir_00002#p0", "mmdocir_00002#p3"]
    first = by_id["mmdocir_00000#p0"]
    assert first["gold_raw_count"] == 2 and first["gold_duplicates_removed"] == 1
    assert first["gold_exact_layout_id"] == [5] and first["candidate_count"] == 2
    assert (first["patch_pos"], first["patch_ignore"]) == (2, 1)
    assert first["eval_ready"] and first["local_loss_ready"]
    conflict = by_id["mmdocir_00002#p0"]
    assert conflict["coordinate_conflict"] and not conflict["eval_ready"]
    empty = by_id["mmdocir_00002#p3"]
    assert empty["candidate_count"] == 0 and empty["eval_ready"]
    assert empty["num_gold_pages"] == 2 and not empty["page_in_question_pages"]
    table = candidates[("report", 0)][0]
    assert table["type"] == "table" and table["text_chars"] == 0
    assert candidates[("paper.v2", 0)][0]["text_chars"] == 3
