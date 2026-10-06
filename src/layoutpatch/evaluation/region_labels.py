"""Region-level gold labels for MMDocIR evaluation (M2.5, new code, no old-repo reuse).

背景（新手向）：M2 的四表里 `queries` 有 1658 行，其中 1598 行有 `evidence_node_ids`，
60 行是空的；`evidence_bboxes` 全空。1B/1C 的区域评测（IoU Hit@0.5）需要每个 query
的 gold 框坐标，而官方 `layout_mapping` 里 2638 个框中有 115 个在 nodes 表里找不到
对应节点（bbox 四舍五入到 2 位小数后仍对不上；模块注释猜测多为大框如 [10,13,1180,800]，
仅为成因猜测，不作结论；真正面积分布以 EXP-005 直方图 `strat_area_hist.json/png` 为准）。
本模块把“能对上节点的 2523 个框”和“对不上但真实存在的 115 个框”统一成一份
`region_labels.parquet`，评测时直接读它，不再依赖 `evidence_node_ids` 是否为空。

字段约定（评测 SSOT，M4 直接使用）：
- query_id / doc_id / page_id：定位到哪次查询、哪份文档、哪一页；
- node_id：能对上 nodes 表时填真实 node_id，对不上时填空字符串；
- bbox：原图绝对像素 [x1,y1,x2,y2]，与官方 annotations 一致；
- page_size：同页 `page_size` [W,H]，三用途指引见 EXP-006 §3（Snappy 缩 448 / 面积归一分箱 / 防刷分母）；本字段冻结只读；
- source：matched（对上节点）或 unmapped（官方有框但 nodes 无对应）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from layoutpatch.paths import data_root


@dataclass(frozen=True)
class RegionLabel:
    query_id: str
    doc_id: str
    page_id: str
    node_id: str
    bbox: list[float]
    page_size: list[float]
    source: str


def _page_id(doc_id: str, index: int) -> str:
    return f"{doc_id}_p{index}"


def _bbox_key(bbox: list[float]) -> tuple[float, ...]:
    return tuple(round(float(value), 2) for value in bbox)


def build_region_labels_from_annotations(
    annotations: list[dict[str, Any]],
    node_lookup: dict[tuple[str, str, tuple[float, ...]], str],
    *,
    doc_id_normalizer: Callable[[str], str] | None = None,
) -> list[RegionLabel]:
    """纯函数：输入官方 annotations + 节点 lookup，输出 region 标注列表。

    与磁盘解耦，单元测试用 demo 级小数据即可覆盖 matched / unmapped / 无框三种分支。
    默认保留历史 Path.stem 规则；新版本适配器必须传入其自身的文档 ID 规则。
    """
    labels: list[RegionLabel] = []
    query_index = 0
    for item in annotations:
        doc_id = (
            Path(item["doc_name"]).stem
            if doc_id_normalizer is None
            else doc_id_normalizer(item["doc_name"])
        )
        for question in item.get("questions", []):
            query_id = f"mmdocir_{query_index:05d}"
            query_index += 1
            for mapping in question.get("layout_mapping", []):
                page = _page_id(doc_id, int(mapping["page"]))
                bbox = [float(value) for value in mapping["bbox"]]
                node_id = node_lookup.get((doc_id, page, _bbox_key(bbox)), "")
                labels.append(
                    RegionLabel(
                        query_id=query_id,
                        doc_id=doc_id,
                        page_id=page,
                        node_id=node_id,
                        bbox=bbox,
                        page_size=[float(value) for value in mapping.get("page_size", [])],
                        source="matched" if node_id else "unmapped",
                    )
                )
    return labels


def read_region_labels(processed_dir: Path | None = None) -> list[RegionLabel]:
    """读已落盘的 region_labels.parquet，供 M4 评测使用。"""
    root = processed_dir or (data_root() / "processed" / "mmdocir_evaluation")
    rows = pl.read_parquet(root / "region_labels.parquet").to_dicts()
    return [RegionLabel(**row) for row in rows]


def labels_by_query(labels: list[RegionLabel]) -> dict[str, list[RegionLabel]]:
    """按 query_id 分组；无框 query 自然不在结果中，不进区域分母。"""
    grouped: dict[str, list[RegionLabel]] = {}
    for label in labels:
        grouped.setdefault(label.query_id, []).append(label)
    return grouped


def bbox_iou(left: list[float], right: list[float]) -> float:
    """IoU（交并比）：两个框重叠面积 / 总面积，评测命中判定的基础函数。"""
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - inter
    return inter / union if union > 0 else 0.0


def scale_bbox_to_model(bbox: list[float], page_size: list[float], model_size: int = 448) -> list[float]:
    """Snappy 式坐标缩放：原图像素 → 448 模型坐标（PAPER_SPEC 5.6 节公式）。"""
    width, height = page_size
    x1, y1, x2, y2 = bbox
    return [x1 * model_size / width, y1 * model_size / height, x2 * model_size / width, y2 * model_size / height]
