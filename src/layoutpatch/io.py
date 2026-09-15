"""Parquet/JSON IO helpers (migrated from the old repository in batch M2).

读写规则（新手向）：
- `write_records`：把一串 Pydantic 对象（例如多条 DocumentRecord）变成表格并存成 parquet 文件；
- `read_records`：把 parquet 读回 Pydantic 对象列表；
- `write_processed_dataset`：一次写 documents/pages/nodes/queries 四张表；
- JSON 列（metadata、bbox、证据 id 列表等）在存盘时转成字符串，读回时再解析，保证表格列类型稳定。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import polars as pl
from pydantic import BaseModel

from layoutpatch.schemas import (
    DocumentRecord,
    EvidenceNode,
    PageRecord,
    QueryRecord,
    RetrievalHit,
)

T = TypeVar("T", bound=BaseModel)

JSON_COLUMNS = {
    "metadata",
    "bbox",
    "evidence_page_ids",
    "evidence_node_ids",
    "evidence_bboxes",
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _jsonify(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _unjsonify(key: str, value: Any) -> Any:
    if key in JSON_COLUMNS and isinstance(value, str) and value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def write_records(path: Path, records: list[BaseModel]) -> None:
    """把 Pydantic 对象列表写成一张 parquet 表。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        rows.append({key: _jsonify(value) for key, value in record.model_dump(mode="json").items()})
    pl.DataFrame(rows).write_parquet(path)


def read_records(path: Path, model: type[T]) -> list[T]:
    """把 parquet 表读回 Pydantic 对象列表；文件缺失时直接报错。"""
    if not path.exists():
        raise FileNotFoundError(f"Missing required table: {path}")
    rows = pl.read_parquet(path).to_dicts()
    cleaned = [{key: _unjsonify(key, value) for key, value in row.items()} for row in rows]
    return [model(**row) for row in cleaned]


def write_processed_dataset(
    processed_dir: Path,
    documents: list[DocumentRecord],
    pages: list[PageRecord],
    nodes: list[EvidenceNode],
    queries: list[QueryRecord],
) -> None:
    """一次写四张标准表：documents / pages / nodes / queries。」"""
    write_records(processed_dir / "documents.parquet", documents)
    write_records(processed_dir / "pages.parquet", pages)
    write_records(processed_dir / "nodes.parquet", nodes)
    write_records(processed_dir / "queries.parquet", queries)


def read_processed_dataset(
    processed_dir: Path,
) -> tuple[list[DocumentRecord], list[PageRecord], list[EvidenceNode], list[QueryRecord]]:
    """一次读回四张标准表。"""
    return (
        read_records(processed_dir / "documents.parquet", DocumentRecord),
        read_records(processed_dir / "pages.parquet", PageRecord),
        read_records(processed_dir / "nodes.parquet", EvidenceNode),
        read_records(processed_dir / "queries.parquet", QueryRecord),
    )


def write_hits(path: Path, hits: list[RetrievalHit]) -> None:
    write_records(path, hits)


def read_hits(path: Path) -> list[RetrievalHit]:
    return read_records(path, RetrievalHit)
