"""Dataset preparation adapters (migrated from the old repository in batch M2).

只保留主线需要的两个入口：
- `prepare_demo`：内置 2 文档 / 3 页 / 4 节点 / 3 查询的小样例，用于冒烟验证管线，不需要任何外部数据；
- `prepare_mmdocir`：把官方 MMDocIR evaluation 原始文件（annotations jsonl + pages/layouts parquet）
  转成四张标准表 documents / pages / nodes / queries，全量应对数 313 / 20395 / 170338 / 1658。

中文年报（`cn_annual_reports`）是开题后被否的方向，永久留在旧仓库，本文件不搬运、不提供。
数据根目录统一走 `layoutpatch.paths.data_root()`（环境变量 `LAYOUTPATCH_DATA_ROOT`，默认 `./data`）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import polars as pl

from layoutpatch.io import write_processed_dataset
from layoutpatch.layout.schema import (
    TYPE_SCHEMA,
    canonical_layout_type,
    layout_type_id,
    ocr_text_with_source,
)
from layoutpatch.paths import data_root
from layoutpatch.schemas import DocumentRecord, EvidenceNode, PageRecord, QueryRecord

InputPolicy = Literal["legacy", "v2_ocr_only"]


@dataclass(frozen=True)
class PrepareResult:
    dataset: str
    processed_dir: Path
    documents: int
    pages: int
    nodes: int
    queries: int
    message: str


def prepare_dataset(
    dataset: str,
    limit_docs: int | None = None,
    output_dataset: str | None = None,
    input_policy: InputPolicy = "legacy",
) -> PrepareResult:
    """按数据集名分发：只接受 demo 与 mmdocir 主线。"""
    if dataset == "demo":
        if input_policy != "legacy":
            raise ValueError("input_policy applies only to MMDocIR")
        return prepare_demo(limit_docs=limit_docs)
    if dataset in {"mmdocir", "mmdocir_evaluation"}:
        return prepare_mmdocir(
            limit_docs=limit_docs, output_dataset=output_dataset, input_policy=input_policy
        )
    raise ValueError(f"Unknown dataset: {dataset}. Choose demo or mmdocir.")


def prepare_demo(limit_docs: int | None = None) -> PrepareResult:
    """内置小样例：2 文档 / 3 页 / 4 节点 / 3 查询，无外部依赖。"""
    dataset = "demo"
    processed_dir = data_root() / "processed" / dataset
    documents = [
        DocumentRecord(
            doc_id="demo_finance_2025",
            dataset=dataset,
            title="2025 Annual Report Demo",
            source_path="demo://finance",
            domain="annual_report",
            language="zh",
            num_pages=2,
            metadata={"company": "示例科技"},
        ),
        DocumentRecord(
            doc_id="demo_contract_001",
            dataset=dataset,
            title="Contract Review Demo",
            source_path="demo://contract",
            domain="contract",
            language="zh",
            num_pages=1,
            metadata={"contract_type": "service"},
        ),
    ]
    if limit_docs is not None:
        documents = documents[:limit_docs]
    allowed = {doc.doc_id for doc in documents}
    pages = [
        PageRecord(
            doc_id="demo_finance_2025",
            page_id="demo_finance_2025_p1",
            page_index=1,
            page_text="示例科技2025年营业收入为12.8亿元，同比增长18%。研发投入为2.1亿元。",
            metadata={"section": "主要会计数据"},
        ),
        PageRecord(
            doc_id="demo_finance_2025",
            page_id="demo_finance_2025_p2",
            page_index=2,
            page_text="现金流量表显示，经营活动产生的现金流量净额为3.4亿元。",
            metadata={"section": "现金流量"},
        ),
        PageRecord(
            doc_id="demo_contract_001",
            page_id="demo_contract_001_p1",
            page_index=1,
            page_text="本合同服务期限为2025年1月1日至2025年12月31日。付款方式为按季度支付。",
            metadata={"section": "合同条款"},
        ),
    ]
    pages = [page for page in pages if page.doc_id in allowed]
    nodes = [
        EvidenceNode(
            node_id="demo_finance_2025_p1_n1",
            doc_id="demo_finance_2025",
            page_id="demo_finance_2025_p1",
            node_type="paragraph",
            text="示例科技2025年营业收入为12.8亿元，同比增长18%。",
            reading_order=1,
            source="demo",
            confidence=1.0,
        ),
        EvidenceNode(
            node_id="demo_finance_2025_p1_n2",
            doc_id="demo_finance_2025",
            page_id="demo_finance_2025_p1",
            node_type="table",
            bbox=[80, 120, 520, 360],
            text="主要财务指标：营业收入12.8亿元；研发投入2.1亿元。",
            reading_order=2,
            source="demo",
            confidence=1.0,
        ),
        EvidenceNode(
            node_id="demo_finance_2025_p2_n1",
            doc_id="demo_finance_2025",
            page_id="demo_finance_2025_p2",
            node_type="paragraph",
            text="经营活动产生的现金流量净额为3.4亿元。",
            reading_order=1,
            source="demo",
            confidence=1.0,
        ),
        EvidenceNode(
            node_id="demo_contract_001_p1_n1",
            doc_id="demo_contract_001",
            page_id="demo_contract_001_p1",
            node_type="paragraph",
            text="本合同服务期限为2025年1月1日至2025年12月31日。",
            reading_order=1,
            source="demo",
            confidence=1.0,
        ),
    ]
    nodes = [node for node in nodes if node.doc_id in allowed]
    queries = [
        QueryRecord(
            query_id="demo_q1",
            dataset=dataset,
            doc_id="demo_finance_2025",
            question="示例科技2025年营业收入是多少？",
            answer="12.8亿元",
            question_type="numeric",
            evidence_page_ids=["demo_finance_2025_p1"],
            evidence_node_ids=["demo_finance_2025_p1_n1", "demo_finance_2025_p1_n2"],
        ),
        QueryRecord(
            query_id="demo_q2",
            dataset=dataset,
            doc_id="demo_finance_2025",
            question="经营活动产生的现金流量净额是多少？",
            answer="3.4亿元",
            question_type="numeric",
            evidence_page_ids=["demo_finance_2025_p2"],
            evidence_node_ids=["demo_finance_2025_p2_n1"],
        ),
        QueryRecord(
            query_id="demo_q3",
            dataset=dataset,
            doc_id="demo_contract_001",
            question="合同服务期限是什么？",
            answer="2025年1月1日至2025年12月31日",
            question_type="fact",
            evidence_page_ids=["demo_contract_001_p1"],
            evidence_node_ids=["demo_contract_001_p1_n1"],
        ),
    ]
    queries = [query for query in queries if query.doc_id in allowed]
    write_processed_dataset(processed_dir, documents, pages, nodes, queries)
    return PrepareResult(
        dataset,
        processed_dir,
        len(documents),
        len(pages),
        len(nodes),
        len(queries),
        "Demo dataset prepared.",
    )


def prepare_mmdocir(
    limit_docs: int | None = None,
    output_dataset: str | None = None,
    with_region_labels: bool = False,
    input_policy: InputPolicy = "legacy",
) -> PrepareResult:
    """MMDocIR evaluation 全量转换：313 文档 / 20395 页 / 170338 节点 / 1658 查询。

    输入是官方发布的三个原始文件（放 `data/raw/mmdocir_evaluation/`）：
    `MMDocIR_annotations.jsonl`（313 行文档，每行含 questions）、
    `MMDocIR_pages.parquet`（20395 页）、`MMDocIR_layouts.parquet`（170338 布局块）。
    页图二进制（`image_binary` 列）会还原到 `data/interim/mmdocir_evaluation/page_images/`，
    ColPali 编码阶段需要这些图片。

    `with_region_labels=True` 时额外输出 `region_labels.parquet`（M2.5）：
    官方 2638 个 layout_mapping 框全部落地（含 nodes 表对不上的 115 个 unmapped），
    四表本身一行不改，对数判据不受影响。

    默认 legacy 保留历史映射/文本回退和输出。显式 v2_ocr_only 使用共享类型表，
    仅取 ocr_text，并记录输入来源；必须指定尚不存在的新 output_dataset。
    v2 页图也写入同名的新 interim 目录，不更新历史页图或缓存。
    """
    import os

    from layoutpatch.evaluation.region_labels import build_region_labels_from_annotations

    dataset = "mmdocir_evaluation"
    if input_policy not in {"legacy", "v2_ocr_only"}:
        raise ValueError(f"Unknown input_policy: {input_policy}")
    raw_dir = Path(os.getenv("LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT", data_root() / "raw" / dataset))
    processed_name = output_dataset or dataset
    processed_dir = data_root() / "processed" / processed_name
    if input_policy == "v2_ocr_only":
        _validate_new_output_dataset(output_dataset)

    def source_doc_id(name: str) -> str:
        # A dot in an extensionless document ID is part of its identity in v2.
        return Path(name).stem if input_policy == "legacy" else name.removesuffix(".pdf")

    policy_metadata = (
        {"input_policy": input_policy, "type_schema": TYPE_SCHEMA, "text_policy": "ocr_only"}
        if input_policy == "v2_ocr_only"
        else {}
    )
    annotations_path = raw_dir / "MMDocIR_annotations.jsonl"
    pages_path = raw_dir / "MMDocIR_pages.parquet"
    layouts_path = raw_dir / "MMDocIR_layouts.parquet"
    if not all(path.exists() for path in (annotations_path, pages_path, layouts_path)):
        _write_missing_data_note(
            processed_dir,
            "MMDocIR evaluation files not found. "
            "Copy the official release into data/raw/mmdocir_evaluation/ "
            "or set LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT to that directory.",
        )
        return PrepareResult(dataset, processed_dir, 0, 0, 0, 0, "MMDocIR raw data not found.")

    annotations = [
        json.loads(line)
        for line in annotations_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if limit_docs is not None:
        annotations = annotations[:limit_docs]
    doc_ids = {source_doc_id(item["doc_name"]) for item in annotations}
    page_frame = pl.read_parquet(pages_path).with_columns(
        pl.col("doc_name").str.replace(r"\.pdf$", "").alias("doc_id")
    )
    layout_frame = pl.read_parquet(layouts_path).with_columns(
        pl.col("doc_name").str.replace(r"\.pdf$", "").alias("doc_id")
    )
    page_rows = page_frame.filter(pl.col("doc_id").is_in(doc_ids)).to_dicts()
    layout_rows = layout_frame.filter(pl.col("doc_id").is_in(doc_ids)).to_dicts()

    def page_id(doc_id: str, index: int) -> str:
        return f"{doc_id}_p{index}"

    def bbox_key(bbox: list[float]) -> tuple[float, ...]:
        return tuple(round(float(value), 2) for value in bbox)

    image_dataset = dataset if input_policy == "legacy" else processed_name
    image_dir = data_root() / "interim" / image_dataset / "page_images"
    pages = []
    for row in page_rows:
        relative_image_path = Path(str(row.get("image_path") or ""))
        if input_policy == "v2_ocr_only":
            # Names alone are not unique across documents; hash also avoids unsafe path characters.
            doc_image_key = hashlib.sha256(row["doc_id"].encode("utf-8")).hexdigest()
            extension = relative_image_path.suffix.lower()
            if extension not in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
                extension = ".img"
            image_path = image_dir / doc_image_key / f"p{int(row['passage_id'])}{extension}"
        else:
            image_path = image_dir / relative_image_path.name
        image_binary = row.get("image_binary")
        if image_binary and not image_path.exists():
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_binary)
        if input_policy == "v2_ocr_only":
            page_text, text_source = ocr_text_with_source(row)
            text_metadata = {**policy_metadata, "text_source": text_source}
        else:
            page_text = str(row.get("ocr_text") or row.get("vlm_text") or "")
            text_metadata = {}
        pages.append(
            PageRecord(
                doc_id=row["doc_id"],
                page_id=page_id(row["doc_id"], int(row["passage_id"])),
                page_index=int(row["passage_id"]) + 1,
                page_text=page_text,
                page_image_path=str(image_path) if image_path.exists() else "",
                metadata={
                    "domain": row.get("domain", ""),
                    "source_image_path": str(relative_image_path),
                    **text_metadata,
                },
            )
        )
    nodes = []
    for row in layout_rows:
        if input_policy == "v2_ocr_only":
            node_type = canonical_layout_type(row.get("type"))
            text, text_source = ocr_text_with_source(row)
            node_metadata = {
                **policy_metadata,
                "raw_type": row.get("type"),
                "layout_type_id": layout_type_id(row.get("type")),
                "text_source": text_source,
            }
        else:
            node_type = (
                "table_block" if row["type"] == "table"
                else "figure" if row["type"] == "figure"
                else "paragraph"
            )
            text = str(row.get("text") or row.get("ocr_text") or row.get("vlm_text") or "")
            node_metadata = {}
        nodes.append(EvidenceNode(
            node_id=f"{row['doc_id']}_p{row['page_id']}_l{row['layout_id']}",
            doc_id=row["doc_id"],
            page_id=page_id(row["doc_id"], int(row["page_id"])),
            node_type=node_type,
            bbox=row["bbox"],
            text=text,
            source="mmdocir",
            metadata=node_metadata,
        ))
    lookup = {
        (node.doc_id, node.page_id, bbox_key(node.bbox or [])): node.node_id for node in nodes
    }
    documents = [
        DocumentRecord(
            doc_id=doc_id,
            dataset=dataset,
            title=doc_id,
            domain=next(
                (
                    str(item.get("domain", ""))
                    for item in annotations
                    if source_doc_id(item["doc_name"]) == doc_id
                ),
                "",
            ),
            num_pages=sum(page.doc_id == doc_id for page in pages),
            metadata=policy_metadata.copy(),
        )
        for doc_id in sorted(doc_ids)
    ]
    queries = []
    for item in annotations:
        doc_id = source_doc_id(item["doc_name"])
        for question in item["questions"]:
            mappings = question.get("layout_mapping", [])
            queries.append(
                QueryRecord(
                    query_id=f"mmdocir_{len(queries):05d}",
                    dataset=dataset,
                    doc_id=doc_id,
                    question=question["Q"],
                    answer=str(question.get("A", "")),
                    question_type=str(question.get("type", "")),
                    evidence_page_ids=[
                        page_id(doc_id, int(value)) for value in question.get("page_id", [])
                    ],
                    evidence_node_ids=[
                        lookup[
                            (
                                doc_id,
                                page_id(doc_id, int(mapping["page"])),
                                bbox_key(mapping["bbox"]),
                            )
                        ]
                        for mapping in mappings
                        if (
                            doc_id,
                            page_id(doc_id, int(mapping["page"])),
                            bbox_key(mapping["bbox"]),
                        )
                        in lookup
                    ],
                    metadata={"mmdocir_layout_count": len(mappings), **policy_metadata},
                )
            )
    write_processed_dataset(processed_dir, documents, pages, nodes, queries)
    if with_region_labels:
        region_labels = build_region_labels_from_annotations(
            annotations, lookup, doc_id_normalizer=source_doc_id
        )
        write_region_labels(processed_dir, region_labels)
    return PrepareResult(
        dataset,
        processed_dir,
        len(documents),
        len(pages),
        len(nodes),
        len(queries),
        "MMDocIR evaluation dataset prepared."
        if input_policy == "legacy"
        else f"MMDocIR dataset prepared with {input_policy}; historical outputs unchanged.",
    )


def _validate_new_output_dataset(output_dataset: str | None) -> None:
    """Validate v2 destinations before opening raw data or creating any output."""
    if (
        not output_dataset
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", output_dataset) is None
        or output_dataset.casefold() in {"mmdocir", "mmdocir_evaluation"}
    ):
        raise ValueError("v2_ocr_only requires a new explicit output_dataset directory name")
    for stage in ("processed", "interim"):
        root = (data_root() / stage).resolve()
        destination = (root / output_dataset).resolve()
        if destination.parent != root:
            raise ValueError("output_dataset must stay directly inside its data directory")
        if destination.exists():
            raise FileExistsError(f"v2_ocr_only will not overwrite existing output: {destination}")


def _write_missing_data_note(processed_dir: Path, message: str) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / "README.md").write_text(message + "\n", encoding="utf-8")


def write_region_labels(processed_dir: Path, labels: list) -> Path:
    """写 region_labels.parquet：独立文件，不碰四表，删了可重建。"""
    import polars as pl

    out = processed_dir / "region_labels.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "query_id": label.query_id,
            "doc_id": label.doc_id,
            "page_id": label.page_id,
            "node_id": label.node_id,
            "bbox": label.bbox,
            "page_size": label.page_size,
            "source": label.source,
        }
        for label in labels
    ]
    pl.DataFrame(rows).write_parquet(out)
    return out
