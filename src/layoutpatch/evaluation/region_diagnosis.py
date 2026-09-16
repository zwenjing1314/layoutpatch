"""Phase 1B A/B/C/D gap diagnosis (PAPER_SPEC section 7.3, new code, batch 4).

四格定义（小白向，出处 docs/PAPER_SPEC.md 第 7.3 节原文）：
- A 页中区中：gold 页进了 Top-K，且页内某 gold 区域命中（本文件用 bbox IoU≥0.5 判定）。
- B 页中区不中：gold 页进了 Top-K，但页内没有任何 gold 区域命中 —— 我们的主攻缺口。
- C 页不中区中：页没进 Top-K，但"区域命中"成立 —— 说明区域信号可能强于页级排序，需解释。
- D 都不中：页没进，区域也没中。

分母：region_labels.parquet 2638 行（M2.5 产物），只统计其中有 IoU 判定意义的 query。
IoU 口径：预测区域 = gold 页内每个布局节点框，与 gold bbox 算 IoU，≥0.5 记命中
（正式口径 docs/PAPER_SPEC.md 第 8 节；本诊断用同一口径先出分布）。
页级 Top-K：用 EXP-001 run 的 predictions.parquet（colpali_page，K=5 与 R@5 判据同源）。

注意：本诊断是"页级 Top-K + gold 区域"的静态测量，不训练、不改模型。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.paths import data_root, runs_dir


@dataclass(frozen=True)
class DiagnosisResult:
    k: int
    total_queries: int  # 有 gold 区域标注的 query 数（分母）
    a_page_hit_region_hit: int
    b_page_hit_region_miss: int
    c_page_miss_region_hit: int
    d_page_miss_region_miss: int
    page_hit_rate: float
    region_hit_rate: float
    b_share_of_page_hits: float
    iou_threshold: float
    best_page_rank: dict[str, int]  # query_id -> gold 页在 Top-K 内的最小 rank
    region_hit_by_iou: dict[str, float]  # IoU 阈值敏感性 0.3/0.5/0.7


def _parse(value: object) -> list:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def load_inputs(
    run_dir: Path,
    k: int = 5,
    iou_threshold: float = 0.5,
) -> tuple[dict[str, list[tuple[str, int]]], dict[str, list[dict]], dict[str, list[dict]], dict[str, list[float]]]:
    """读 run 预测、nodes 表（页内候选框）、region_labels（gold 区域）、gold bbox。"""
    hits = pl.read_parquet(run_dir / "predictions.parquet").to_dicts()
    top_pages: dict[str, list[tuple[str, int]]] = {}
    for hit in hits:
        if hit["rank"] <= k:
            top_pages.setdefault(hit["query_id"], []).append((hit["page_id"], hit["rank"]))
    for key in top_pages:
        top_pages[key].sort(key=lambda item: item[1])

    nodes_rows = pl.read_parquet(data_root() / "processed" / "mmdocir_evaluation" / "nodes.parquet").to_dicts()
    nodes_by_page: dict[str, list[dict]] = {}
    for row in nodes_rows:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            try:
                bbox = json.loads(bbox)
            except json.JSONDecodeError:
                continue
        if isinstance(bbox, list) and len(bbox) == 4:
            nodes_by_page.setdefault(row["page_id"], []).append(
                {"node_id": row["node_id"], "bbox": [float(v) for v in bbox]}
            )

    labels = pl.read_parquet(data_root() / "processed" / "mmdocir_evaluation" / "region_labels.parquet").to_dicts()
    gold_by_query: dict[str, list[dict]] = {}
    gold_bboxes: dict[str, list[float]] = {}
    for row in labels:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            try:
                bbox = json.loads(bbox)
            except json.JSONDecodeError:
                continue
        gold_by_query.setdefault(row["query_id"], []).append(
            {"page_id": row["page_id"], "node_id": row["node_id"], "bbox": [float(v) for v in bbox]}
        )
        gold_bboxes.setdefault(row["query_id"], []).append([float(v) for v in bbox])
    return top_pages, nodes_by_page, gold_by_query, gold_bboxes


def diagnose(
    run_dir: Path | None = None,
    k: int = 5,
    iou_threshold: float = 0.5,
) -> DiagnosisResult:
    """主入口：对每个有 gold 区域的 query 归 A/B/C/D 一格。"""
    run_dir = run_dir or runs_dir() / "retrieval" / "mmdocir_colpali" / "20260916_134144"
    top_pages, nodes_by_page, gold_by_query, _ = load_inputs(run_dir, k, iou_threshold)

    a = b = c = d = 0
    best_page_rank: dict[str, int] = {}
    region_hit_at: Counter[str] = Counter()

    for query_id, golds in gold_by_query.items():
        pages = top_pages.get(query_id, [])
        gold_page_ids = {g["page_id"] for g in golds}
        hit_pages = [(pid, rank) for pid, rank in pages if pid in gold_page_ids]
        page_hit = bool(hit_pages)
        best_rank = min((rank for _, rank in hit_pages), default=0)

        region_hit = False
        if page_hit:
            for gold in golds:
                if gold["page_id"] not in {pid for pid, _ in hit_pages}:
                    continue
                for candidate in nodes_by_page.get(gold["page_id"], []):
                    iou = bbox_iou(candidate["bbox"], gold["bbox"])
                    if iou >= iou_threshold:
                        region_hit = True
                        break
                if region_hit:
                    break

        if page_hit and region_hit:
            a += 1
        elif page_hit and not region_hit:
            b += 1
        elif not page_hit and region_hit:
            c += 1
        else:
            d += 1
        if page_hit:
            best_page_rank[query_id] = best_rank
        region_hit = False
        # IoU 敏感性：0.3/0.5/0.7 三档重判
        for threshold in ("0.3", "0.5", "0.7"):
            hit = False
            for gold in golds:
                if gold["page_id"] not in {pid for pid, _ in pages}:
                    continue
                for candidate in nodes_by_page.get(gold["page_id"], []):
                    if bbox_iou(candidate["bbox"], gold["bbox"]) >= float(threshold):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                region_hit_at[threshold] += 1

    total = a + b + c + d
    page_hits = a + b
    return DiagnosisResult(
        k=k,
        total_queries=total,
        a_page_hit_region_hit=a,
        b_page_hit_region_miss=b,
        c_page_miss_region_hit=c,
        d_page_miss_region_miss=d,
        page_hit_rate=page_hits / total if total else 0.0,
        region_hit_rate=(a + c) / total if total else 0.0,
        b_share_of_page_hits=b / page_hits if page_hits else 0.0,
        iou_threshold=iou_threshold,
        best_page_rank=best_page_rank,
        region_hit_by_iou={
            t: region_hit_at[t] / total if total else 0.0 for t in ("0.3", "0.5", "0.7")
        },
    )


def write_diagnosis(result: DiagnosisResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "abcd_diagnosis.json"
    out.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return out
