"""Correspondence W tests (M4, PAPER_SPEC sections 5.3/6: Snappy 公式与边界).

覆盖第 6 节机器门限要求的四类单元用例：
1. 整页框：cover 行全 1（每个 patch 完全被框覆盖）；
2. 四角 patch：单区域只命中左上角 patch，且权重 1.0；
3. 跨界框：跨两个 patch 时按面积分摊，两 patch 权重之和 = 框在 patch 网格上的面积；
4. 越界框：裁剪后只算画布内面积，行内不再有画布外权重。
另覆盖行归一化只在非空行做的硬性规定。
"""

from __future__ import annotations

from layoutpatch.layout.correspondence import (
    clamp_bbox,
    correspondence_row,
    patch_bbox,
    row_normalize,
    scale_bbox_to_model,
    stack_correspondence,
)


def test_full_page_box_covers_every_patch_fully():
    row = correspondence_row([0, 0, 800, 600], [800.0, 600.0])

    assert len(row) == 1024
    assert all(abs(value - 1.0) < 1e-9 for value in row)


def test_top_left_region_hits_first_patch_only():
    # 区域正好是左上角一个 14×14 patch（原图 448×448 无缩放）
    row = correspondence_row([0, 0, 14, 14], [448.0, 448.0])

    assert abs(row[0] - 1.0) < 1e-9
    assert all(value == 0.0 for value in row[1:])


def test_crossing_box_splits_weight_by_area():
    # 区域横跨第 0、1 两个 patch 的右半/左半各 7px（模型坐标 7..21 宽，高 0..14）
    row = correspondence_row([7, 0, 21, 14], [448.0, 448.0])

    assert abs(row[0] - 0.5) < 1e-9
    assert abs(row[1] - 0.5) < 1e-9
    assert abs(sum(row) - 1.0) < 1e-9


def test_out_of_bounds_box_is_clamped():
    # 框超出画布右边界：裁剪后只剩画布内部分
    # 行 7（y=98..112），patch 28 下标 = 7*32+28=252，覆盖 x 392..406；框 400..448
    clamped = clamp_bbox([400, 98, 500, 112], 448)

    assert clamped == [400.0, 98.0, 448.0, 112.0]

    row = correspondence_row([400, 98, 500, 112], [448.0, 448.0])

    # patch 252 覆盖 6×14，patch 253/254/255 各覆盖 14×14，行 7 之外全 0
    assert abs(row[252] - (6 * 14) / 196) < 1e-9
    assert abs(row[253] - 1.0) < 1e-9
    assert abs(row[255] - 1.0) < 1e-9
    assert all(value == 0.0 for value in row[256:])


def test_scaling_matches_snappy_formula():
    # PAPER_SPEC 5.6: B'(r) = (x1*I/W, y1*I/H, x2*I/W, y2*I/H)
    scaled = scale_bbox_to_model([100, 200, 300, 400], [800.0, 800.0])

    assert scaled == [56.0, 112.0, 168.0, 224.0]


def test_row_normalize_skips_empty_rows():
    weights = [[0.5, 0.5], [0.0, 0.0]]

    normalized = row_normalize(weights)

    assert normalized[0] == [0.5, 0.5]
    assert normalized[1] == [0.0, 0.0]


def test_stack_reports_empty_patches_and_bounds():
    result = stack_correspondence([[0, 0, 14, 14], [0, 0, 0, 0]], [448.0, 448.0])

    assert result.empty_patches[0] == 1  # patch 0 被区域 0 覆盖，patch 1 起为空
    assert result.out_of_bounds_ratio >= 0.0
    assert abs(patch_bbox(0)[2] - 14.0) < 1e-9  # 第一个 patch 右边界 14
