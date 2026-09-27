"""BBox IoU in original-page pixel coordinates (PAPER_SPEC section 8 formal metric).

IoU = 交集面积 / 并集面积，两个框都在原图绝对像素坐标系（第 6 节审计保证）。
"""

from __future__ import annotations


def bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def calculate_overlap_score(bbox1, bbox2):  # noqa: ANN001, ANN202 - verbatim official
    top1, left1, bottom1, right1 = bbox1
    top2, left2, bottom2, right2 = bbox2
    inter_top = max(top1, top2)
    inter_left = max(left1, left2)
    inter_bottom = min(bottom1, bottom2)
    inter_right = min(right1, right2)
    if inter_top < inter_bottom and inter_left < inter_right:
        return (inter_bottom - inter_top) * (inter_right - inter_left)
    return 0.0


def recall_layout(layout_topk, layout_indices, layout_mapping):  # noqa: ANN001, ANN202
    """Verbatim port of MMDocIR metric_eval.py: recall_layout. Not a new metric."""
    recall_area = 0
    for layout_id in layout_topk:
        _, page_id, x1, y1, x2, y2 = layout_indices[layout_id]
        for gt_layout in layout_mapping:
            if page_id == gt_layout["page"]:
                recall_area += calculate_overlap_score([x1, y1, x2, y2], gt_layout["bbox"])
    gt_area = 0
    for gt_layout in layout_mapping:
        top, left, bottom, right = gt_layout["bbox"]
        gt_area += (bottom - top) * (right - left)
    if gt_area == 0:
        return 0.0
    return recall_area / gt_area

