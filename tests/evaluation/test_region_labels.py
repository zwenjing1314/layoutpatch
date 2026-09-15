"""Region labels tests (M2.5, decoupled: demo-scale data only, no real tables).

覆盖四件事（新手向）：
1. 能对上节点的框标 matched 并带真实 node_id；
2. 官方有框但 nodes 无对应的标 unmapped 且 node_id 为空；
3. 无框 query 不出现在结果中（不进区域分母）；
4. IoU 与 Snappy 式坐标缩放公式正确。
"""

from __future__ import annotations

from layoutpatch.evaluation.region_labels import (
    bbox_iou,
    build_region_labels_from_annotations,
    labels_by_query,
    scale_bbox_to_model,
)


def _annotations():
    return [
        {
            "doc_name": "doc_a.pdf",
            "questions": [
                {
                    "Q": "q1",
                    "layout_mapping": [
                        {"page": 0, "page_size": [100.0, 200.0], "bbox": [10, 20, 50, 80]},
                        {"page": 1, "page_size": [100.0, 200.0], "bbox": [0, 0, 1000, 2000]},
                    ],
                },
                {"Q": "q2", "layout_mapping": []},
            ],
        }
    ]


def test_matched_and_unmapped_sources() -> None:
    lookup = {("doc_a", "doc_a_p0", (10.0, 20.0, 50.0, 80.0)): "doc_a_p0_l0"}

    labels = build_region_labels_from_annotations(_annotations(), lookup)

    assert len(labels) == 2
    assert labels[0].query_id == "mmdocir_00000"
    assert (labels[0].node_id, labels[0].source) == ("doc_a_p0_l0", "matched")
    assert (labels[1].node_id, labels[1].source) == ("", "unmapped")


def test_empty_query_excluded_from_denominator() -> None:
    labels = build_region_labels_from_annotations(_annotations(), {})

    grouped = labels_by_query(labels)

    assert "mmdocir_00000" in grouped
    assert "mmdocir_00001" not in grouped


def test_bbox_iou_and_scaling() -> None:
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert bbox_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert abs(bbox_iou([0, 0, 10, 10], [5, 5, 15, 15]) - 25 / 175) < 1e-9

    scaled = scale_bbox_to_model([50, 100, 100, 200], [200.0, 400.0], 448)
    assert scaled == [112.0, 112.0, 224.0, 224.0]
