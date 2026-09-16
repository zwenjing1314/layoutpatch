"""A/B/C/D diagnosis tests (PAPER_SPEC section 7.3)."""

from __future__ import annotations

from layoutpatch.evaluation.region_metrics import bbox_iou


def test_identical_boxes_have_iou_one():
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_disjoint_boxes_have_iou_zero():
    assert bbox_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_half_overlap():
    # 交集 5×10=50，并集 200-50=150
    iou = bbox_iou([0, 0, 10, 10], [5, 0, 15, 10])

    assert abs(iou - 50 / 150) < 1e-9


def test_touching_edges_have_iou_zero():
    assert bbox_iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0.0
