"""Patch-region correspondence matrix W (M4, new code per PAPER_SPEC section 5.3).

坐标约定：
- 原图坐标：页图原始像素 (W,H)，OCR/Layout bbox 与 region_labels 都在这个坐标系；
- 模型坐标：ColPali 输入 448×448，1024 个 patch 按 32×32 网格排列，每 patch 覆盖 14×14 模型像素；
- `scale_bbox_to_model`：原图 bbox → 448 模型坐标，公式来自 PAPER_SPEC 5.6 节
  B'(r)=(x1*I/W, y1*I/H, x2*I/W, y2*I/H)；页图非正方形时 x 与 y 各自缩放（等效 resize 假设，
  是否成立由第 6 节审计叠图人工核对，若渲染带 padding 则在 audit.py 里换公式）。

W 的三种候选定义（PAPER_SPEC 5.3，dev 定一种，test 不许换）：
- cover：Area(P∩R)/Area(P)，patch 被框占多少（定位敏感，首选）；
- fill：Area(P∩R)/Area(R)，框被 patch 覆盖多少（大框友好）；
- iou：Area(P∩R)/Area(P∪R)，对称版本（小框数值过小）。

硬性规定（5.3 实现要求）：行归一化只在非空行做；分母为 0 的行记空 patch（全 0 行）；
多框覆盖同一 patch 按行归一化分摊，不重复送分。
"""

from __future__ import annotations

from dataclasses import dataclass

GRID = 32  # ColPali 448 输入 / 14 patch 像素 = 32×32 = 1024 patch
MODEL_SIZE = 448
PATCH_PIXELS = MODEL_SIZE // GRID  # 14


def scale_bbox_to_model(
    bbox: list[float], page_size: list[float], model_size: int = MODEL_SIZE
) -> list[float]:
    """原图绝对像素 → 448 模型坐标（PAPER_SPEC 5.6 Snappy 公式）。"""
    width, height = page_size
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid page size: {page_size}")
    x1, y1, x2, y2 = bbox
    return [
        x1 * model_size / width,
        y1 * model_size / height,
        x2 * model_size / width,
        y2 * model_size / height,
    ]


def clamp_bbox(bbox: list[float], model_size: int = MODEL_SIZE) -> list[float]:
    """越界框裁剪到模型画布内（PAPER_SPEC 第 6 节审计规则），并保证 x2>=x1。"""
    x1 = min(max(bbox[0], 0.0), float(model_size))
    y1 = min(max(bbox[1], 0.0), float(model_size))
    x2 = min(max(bbox[2], 0.0), float(model_size))
    y2 = min(max(bbox[3], 0.0), float(model_size))
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def patch_bbox(index: int, grid: int = GRID, model_size: int = MODEL_SIZE) -> list[float]:
    """patch 一维下标 → 模型坐标框；光栅顺序：左→右、上→下（PAPER_SPEC 第 6 节待确认项）。"""
    row, col = divmod(index, grid)
    cell = model_size / grid
    return [col * cell, row * cell, (col + 1) * cell, (row + 1) * cell]


def intersection_area(a: list[float], b: list[float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def area(b: list[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


@dataclass(frozen=True)
class CorrespondenceResult:
    weights: list[list[float]]  # [num_patches][num_regions]，未归一化
    empty_patches: list[int]  # 全 0 行下标（走 5.5 节兜底）
    out_of_bounds_ratio: float  # 越界 patch 比例（audit 门限用）


def correspondence_row(
    region_bbox: list[float],
    page_size: list[float],
    grid: int = GRID,
    model_size: int = MODEL_SIZE,
) -> list[float]:
    """单个布局区域对所有 patch 的 cover 权重行（W_ij = Area(Pi∩Rj)/Area(Pi)）。

    返回长度 grid*grid 的列表；区域为空或退化时返回全 0。
    """
    scaled = clamp_bbox(scale_bbox_to_model(region_bbox, page_size, model_size), model_size)
    if area(scaled) <= 0:
        return [0.0] * (grid * grid)
    patch_area = (model_size / grid) ** 2
    return [
        intersection_area(patch_bbox(i, grid, model_size), scaled) / patch_area
        for i in range(grid * grid)
    ]


def stack_correspondence(
    region_bboxes: list[list[float]],
    page_size: list[float],
    grid: int = GRID,
    model_size: int = MODEL_SIZE,
) -> CorrespondenceResult:
    """一页的多个区域 → W 矩阵 + 空 patch 标记 + 越界统计（未归一化，audit 用）。"""
    rows = [correspondence_row(b, page_size, grid, model_size) for b in region_bboxes]
    num_patches = grid * grid
    weights = [[rows[j][i] for j in range(len(rows))] for i in range(num_patches)]
    empty_patches = [i for i, row in enumerate(weights) if sum(row) <= 0.0]
    scaled = [
        clamp_bbox(scale_bbox_to_model(b, page_size, model_size), model_size)
        for b in region_bboxes
    ]
    out_of_bounds = sum(
        1
        for b, s in zip(region_bboxes, scaled, strict=True)
        if s != [float(v) for v in b] and (s[0] > 0 or s[1] > 0 or s[2] < model_size or s[3] < model_size) is False
        or area(s) <= 0
    )
    ratio = out_of_bounds / len(region_bboxes) if region_bboxes else 0.0
    return CorrespondenceResult(weights, empty_patches, ratio)


def row_normalize(weights: list[list[float]]) -> list[list[float]]:
    """行归一化只在非空行做（PAPER_SPEC 5.3 硬性规定 3）；全 0 行保持全 0。"""
    normalized = []
    for row in weights:
        total = sum(row)
        normalized.append([value / total for value in row] if total > 0 else list(row))
    return normalized
