"""Format checks for independent region labels. No gold. No training."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "region_ann_pilot.py"


@pytest.fixture(scope="module")
def pilot_mod():
    spec = importlib.util.spec_from_file_location("region_ann_pilot", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row() -> dict:
    return {
        "sample_id": "ann-0004",
        "candidates": [
            {"box_id": 0, "bbox": [0, 0, 1, 1], "type": "text"},
            {"box_id": 1, "bbox": [1, 1, 2, 2], "type": "image"},
        ],
    }


def _base(**overrides) -> dict:
    rec = {
        "sample_id": "ann-0004",
        "chosen_box_ids": [],
        "cover_levels": {},
        "cover_ok": None,
        "no_candidate": None,
        "cross_box": None,
        "remark": "uncertain",
        "annotator": "A",
        "labeled_at": None,
        "protocol_version": "region-ann-v1",
        "label_status": "pending",
    }
    rec.update(overrides)
    return rec


def test_pending_all_null_is_legal(pilot_mod) -> None:
    errors = pilot_mod.record_errors(_row(), _base(), "A")
    assert errors == []


def test_pending_false_flags_are_illegal(pilot_mod) -> None:
    rec = _base(cover_ok=False, no_candidate=False, cross_box=False)
    errors = pilot_mod.record_errors(_row(), rec, "A")
    assert any("pending cover_ok must be null" in msg for msg in errors)
    assert any("pending no_candidate must be null" in msg for msg in errors)
    assert any("pending cross_box must be null" in msg for msg in errors)


def test_multiple_full_boxes_do_not_force_cross_box(pilot_mod) -> None:
    rec = _base(
        chosen_box_ids=[0, 1],
        cover_levels={"0": "full", "1": "full"},
        cover_ok=True,
        no_candidate=False,
        cross_box=False,
        remark="two independent full boxes",
        labeled_at="2026-09-30T20:27:29Z",
        label_status="labeled",
    )
    assert pilot_mod.record_errors(_row(), rec, "A") == []
    report = pilot_mod.check_labels([_row()], [rec], "A")
    assert report["ok"] is True
    assert report["review_conflicts"] == []


def test_full_and_cross_box_true_is_review_not_auto_fix(pilot_mod) -> None:
    rec = _base(
        chosen_box_ids=[0, 1],
        cover_levels={"0": "full", "1": "partial"},
        cover_ok=True,
        no_candidate=False,
        cross_box=True,
        remark="needs review",
        labeled_at="2026-09-30T20:27:29Z",
        label_status="labeled",
    )
    assert pilot_mod.record_errors(_row(), rec, "A") == []
    report = pilot_mod.check_labels([_row()], [rec], "A")
    assert report["ok"] is True
    assert report["review_conflicts"][0]["sample_id"] == "ann-0004"


def test_metadata_change_is_caught(pilot_mod) -> None:
    rec = _base()
    rec["query"] = "changed"
    rec["pos_page"] = 99
    rec["candidates"] = [
        {"box_id": 0, "bbox": [0, 0, 1, 1], "type": "text"},
        {"box_id": 1, "bbox": [9, 9, 10, 10], "type": "image"},
    ]
    errors = pilot_mod.metadata_errors(_row(), rec)
    assert any("query changed" in msg for msg in errors)
    assert any("pos_page changed" in msg for msg in errors)
    assert any("bbox changed" in msg for msg in errors)


def test_skipped_complete_is_legal(pilot_mod) -> None:
    rec = _base(
        cover_ok=False,
        no_candidate=True,
        cross_box=False,
        remark="no evidence",
        labeled_at="2026-09-30T20:27:29Z",
        label_status="skipped",
    )
    assert pilot_mod.record_errors(_row(), rec, "A") == []


def test_numeric_bbox_aliases_match_pilot(pilot_mod) -> None:
    rec = _base(
        query_id=58,
        line_index=58,
        query="q",
        pos_doc="doc",
        pos_page=2,
        candidates=[
            {"box_id": 0, "bbox": [0, 0, 1, 1], "type": "text"},
            {"box_id": 1, "bbox": [1, 1, 2, 2], "type": "image"},
        ],
    )
    row = {
        "sample_id": "ann-0004",
        "query_id": 58,
        "line_index": 58,
        "query": "q",
        "pos_doc": "doc",
        "pos_page": 2,
        "candidates": [
            {"box_id": 0, "bbox": [0.0, 0.0, 1.0, 1.0], "type": "text"},
            {"box_id": 1, "bbox": [1.0, 1.0, 2.0, 2.0], "type": "image"},
        ],
    }
    assert pilot_mod.metadata_errors(row, rec) == []
