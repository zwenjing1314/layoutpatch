"""Coordinate audit for Phase 1B (M4, PAPER_SPEC section 6 machine thresholds).

说明（新手向）：
- 第 6 节是 Phase 1 的前置硬 Gate：PaliGemma 448×448、32×32 网格、s=14；OCR 框是原图
  绝对像素。如果 resize/padding 假设错了，W 全错且**静默失败**——检索照常跑分，
  但区域全部对不上。所以先机器门限、再人工抽查（叠图），都不许跳。
- 机器门限（PAPER_SPEC 6 节原文）：越界率 < 1%；页级 OCR 框覆盖率均值合理且
  无页级为 0 的异常页。阈值在首次全量扫描后冻结写回 PAPER_SPEC 第 6 节。
- 输出 audit.json（W,H,I,G,s、越界处理、机器门限数值）+ 叠图目录；叠图人工判断
  "表格线/栏边界是否对齐"由用户完成，代码只准备材料。
- coverage 定义：一个 patch 被任意布局区域覆盖的面积比例（cover 行取 max 后求和/patch 数），
  页级取该页 1024 个 patch 的均值。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

from layoutpatch.layout.correspondence import (
    GRID,
    MODEL_SIZE,
    correspondence_row,
)
from layoutpatch.paths import data_root


@dataclass(frozen=True)
class PageAudit:
    doc_id: str
    page_id: str
    width: float
    height: float
    num_regions: int
    oob_regions: int  # 越界（裁剪后面积变化）的区域数
    coverage_mean: float  # 1024 patch 被覆盖比例的均值


@dataclass(frozen=True)
class AuditReport:
    model_size: int
    grid: int
    patch_pixels: int
    pages_audited: int
    total_regions: int
    out_of_bounds_regions: int
    out_of_bounds_ratio: float
    coverage_mean: float
    pages_zero_coverage: list[str]
    gate_oob_pass: bool
    gate_zero_page_pass: bool
    gate_all_pass: bool


def _parse_bbox(value: object) -> list[float] | None:
    """nodes 表 bbox 列存的是 JSON 字符串，读回时统一转 list[float]。"""
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
    """nodes 的 page_id（`<doc>_p126`）直接对应页图 `<doc>_126.jpg`。

    文本判别法双文档验证：layouts.page_id 与 pages.passage_id 同义
    （IBM 直配 779 vs 差一 3；arXiv 直配 135 vs 差一 0），
    页图文件名沿用 passage 原序号，故不做 -1 偏移。
    """
    prefix, _, index = page_id.rpartition("_p")
    try:
        serial = int(index)
    except ValueError:
        return None
    candidate = images / f"{prefix}_{serial}.jpg"
    return candidate if candidate.exists() else None


def audit_nodes_table(
    nodes_path: Path | None = None,
    limit_pages: int | None = None,
    grid: int = GRID,
    model_size: int = MODEL_SIZE,
    images_root: Path | None = None,
) -> tuple[list[PageAudit], AuditReport]:
    """全量扫描 nodes 表，逐页算越界与覆盖，输出机器门限报告。"""
    from PIL import Image

    root = nodes_path or data_root() / "processed" / "mmdocir_evaluation" / "nodes.parquet"
    images = images_root or data_root() / "interim" / "mmdocir_evaluation" / "page_images"
    nodes = pl.read_parquet(root).to_dicts()
    by_page: dict[str, list[dict]] = {}
    for row in nodes:
        bbox = _parse_bbox(row.get("bbox"))
        row["bbox"] = bbox
        if bbox is not None:
            by_page.setdefault(row["page_id"], []).append(row)
    audits: list[PageAudit] = []
    page_items = sorted(by_page.items())
    if limit_pages is not None:
        page_items = page_items[:limit_pages]
    for page_id, rows in page_items:
        image_path = _page_image_for(page_id, images)
        if image_path is None:
            continue
        with Image.open(image_path) as image:
            size = [float(image.size[0]), float(image.size[1])]
        doc_id = rows[0]["doc_id"]
        oob = 0
        coverage = [0.0] * (grid * grid)
        from layoutpatch.layout.correspondence import area as bbox_area

        for row in rows:
            bbox = row["bbox"]
            assert bbox is not None
            # 越界判定在原图坐标系做：框超出页图 (W,H) 即越界（PAPER_SPEC 第 6 节）。
            if bbox[0] < 0 or bbox[1] < 0 or bbox[2] > size[0] or bbox[3] > size[1] or bbox_area(bbox) <= 0:
                oob += 1
            cover = correspondence_row(bbox, size, grid, model_size)
            for i, value in enumerate(cover):
                if value > coverage[i]:
                    coverage[i] = value
        audits.append(
            PageAudit(
                doc_id=doc_id,
                page_id=page_id,
                width=size[0],
                height=size[1],
                num_regions=len(rows),
                oob_regions=oob,
                coverage_mean=sum(coverage) / len(coverage),
            )
        )
    total_regions = sum(a.num_regions for a in audits)
    oob_total = sum(a.oob_regions for a in audits)
    zero_pages = [a.page_id for a in audits if a.coverage_mean <= 0.0]
    report = AuditReport(
        model_size=model_size,
        grid=grid,
        patch_pixels=model_size // grid,
        pages_audited=len(audits),
        total_regions=total_regions,
        out_of_bounds_regions=oob_total,
        out_of_bounds_ratio=oob_total / total_regions if total_regions else 0.0,
        coverage_mean=sum(a.coverage_mean for a in audits) / len(audits) if audits else 0.0,
        pages_zero_coverage=zero_pages,
        gate_oob_pass=(oob_total / total_regions < 0.01) if total_regions else False,
        gate_zero_page_pass=len(zero_pages) == 0,
        gate_all_pass=False,
    )
    report = AuditReport(**{**asdict(report), "gate_all_pass": report.gate_oob_pass and report.gate_zero_page_pass})
    return audits, report


def write_audit_json(audits: list[PageAudit], report: AuditReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "report": asdict(report),
        "pages": [asdict(a) for a in audits],
    }
    out = out_dir / "audit.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
