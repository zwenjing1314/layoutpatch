"""Synthetic page-aware IoU checks; no dataset or checkpoint access."""

from layoutpatch.evaluation.region_metrics import best_same_page_iou


def test_identical_coordinates_on_another_page_do_not_match() -> None:
    box = [0.0, 0.0, 10.0, 10.0]
    assert best_same_page_iou(box, "doc_p0", [("doc_p1", box)]) == 0.0


def test_best_same_page_gold_ignores_better_overlap_on_another_page() -> None:
    box = [0.0, 0.0, 10.0, 10.0]
    gold = [
        ("doc_p1", box),
        ("doc_p0", [0.0, 0.0, 2.0, 10.0]),
        ("doc_p0", [0.0, 0.0, 5.0, 10.0]),
    ]
    assert best_same_page_iou(box, "doc_p0", iter(gold)) == 0.5


def test_empty_gold_has_zero_iou() -> None:
    assert best_same_page_iou([0.0, 0.0, 10.0, 10.0], "doc_p0", []) == 0.0
