"""Audit overlay generation (M4, PAPER_SPEC section 6 step 4: >=20 pages for human check).

说明（新手向）：
- 叠图 = 页图 + patch 网格线 + OCR/Layout 框，给人看"表格线/栏边界是否对齐"，
  判断由用户做（第 6 节：任何一页不通过 → 停工修数据链）。代码只生成材料。
- 抽样规则（第 6 节）：表格页、双栏页、大图页各 ≥5 张，补足 20 张。
  第一版用启发式：nodes 里含 table/figure 类型的页优先，按页区域数分层抽样。
- 输出目录：artifacts/audit/mmdocir_evaluation/overlays/（gitignore，人看完留档）。
"""

from __future__ import annotations

import random
from pathlib import Path

import polars as pl
from PIL import Image, ImageDraw

from layoutpatch.layout.correspondence import GRID
from layoutpatch.paths import artifacts_dir, data_root

OVERLAY_COUNT = 20
TABLE_MIN = 5
FIGURE_MIN = 5


def select_pages_for_audit(
    nodes_path: Path, count: int = OVERLAY_COUNT, seed: int = 7
) -> list[dict]:
    """按 PAPER_SPEC 第 6 节抽样：table/figure 页优先，各 ≥5，再随机补足。"""
    nodes = pl.read_parquet(nodes_path).to_dicts()
    by_page: dict[str, list[dict]] = {}
    for row in nodes:
        by_page.setdefault(f"{row['doc_id']}|{row['page_id']}", []).append(row)
    table_pages = []
    figure_pages = []
    text_pages = []
    for key, rows in sorted(by_page.items()):
        types = {row["node_type"] for row in rows}
        if "table_block" in types:
            table_pages.append(key)
        elif "figure" in types:
            figure_pages.append(key)
        else:
            text_pages.append(key)
    rng = random.Random(seed)
    selected = []
    selected += rng.sample(table_pages, min(TABLE_MIN, len(table_pages)))
    selected += rng.sample(figure_pages, min(FIGURE_MIN, len(figure_pages)))
    remaining = count - len(selected)
    if remaining > 0:
        pool = [key for key in text_pages if key not in selected]
        selected += rng.sample(pool, min(remaining, len(pool)))
    return [{"key": key, "rows": by_page[key]} for key in selected]


def draw_overlay(
    page_image_path: Path,
    rows: list[dict],
    out_path: Path,
    page_size: list[float] | None = None,
) -> Path:
    """页图上画 32×32 patch 网格与布局框（原图坐标，因为框与图同坐标系）。"""
    image = Image.open(page_image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    # 网格按模型 32×32 等分画在原图上（resize 假设下的对应位置）
    for i in range(1, GRID):
        x = width * i / GRID
        y = height * i / GRID
        draw.line([(x, 0), (x, height)], fill=(0, 160, 255), width=1)
        draw.line([(0, y), (width, y)], fill=(0, 160, 255), width=1)
    color_map = {"table_block": (255, 0, 0), "figure": (0, 180, 0), "paragraph": (255, 160, 0), "gold": (255, 255, 0)}
    for row in rows:
        bbox = _parse_bbox(row.get("bbox"))
        if bbox is None:
            continue
        color = color_map.get(row["node_type"], (200, 0, 200))
        width = 6 if row["node_type"] == "gold" else 3
        draw.rectangle(bbox, outline=color, width=width)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="JPEG", quality=85)
    return out_path


def _parse_bbox(value: object) -> list[float] | None:
    """nodes 表 bbox 列是 JSON 字符串；统一转 list[float]，坏值返回 None。"""
    import json

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, list) and len(value) == 4:
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return None
    return None


def _page_image_for(page_id: str, images: Path) -> Path | None:
    """nodes 的 page_id（如 `<doc>_p126`）直接对应页图 `<doc>_126.jpg`。

    事实依据（文本判别法双文档验证）：layouts 表 page_id 与 pages 表 passage_id
    同义（IBM 文档直配 779 vs 差一 3；arXiv 文档直配 135 vs 差一 0），
    且 adapters.py 两边都用 page_id(doc, raw_int) 原样拼 `_pX`，
    页图文件名来自 pages 表的 image_path（passage 原序号）。
    旧注释的 `-1` 映射是错误的，已废弃——它把叠图贴错了页。
    """
    prefix, _, index = page_id.rpartition("_p")
    try:
        serial = int(index)
    except ValueError:
        return None
    candidate = images / f"{prefix}_{serial}.jpg"
    return candidate if candidate.exists() else None


def generate_overlays(
    output_root: Path | None = None,
    nodes_path: Path | None = None,
    images_root: Path | None = None,
    count: int = OVERLAY_COUNT,
) -> tuple[list[Path], list[str]]:
    """生成 ≥20 张叠图；返回（叠图路径, 缺页图警告）。"""
    nodes_file = nodes_path or data_root() / "processed" / "mmdocir_evaluation" / "nodes.parquet"
    images = images_root or data_root() / "interim" / "mmdocir_evaluation" / "page_images"
    overlays_dir = output_root or artifacts_dir() / "audit" / "mmdocir_evaluation" / "overlays"
    selected = select_pages_for_audit(nodes_file, count)
    paths: list[Path] = []
    missing: list[str] = []
    for item in selected:
        key = item["key"]
        doc_id, page_id = key.split("|", 1)
        image_path = _page_image_for(page_id, images)
        if image_path is None:
            missing.append(page_id)
            continue
        out = overlays_dir / f"{page_id}.jpg"
        draw_overlay(image_path, item["rows"], out)
        paths.append(out)
    return paths, missing
