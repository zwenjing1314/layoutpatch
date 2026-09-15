from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRecord(BaseModel):
    # extra="allow" 的含义：允许额外字段（不在类定义中的字段）
    model_config = ConfigDict(extra="allow")


class DocumentRecord(StrictRecord):
    doc_id: str
    dataset: str
    title: str = ""
    source_path: str = ""
    domain: str = ""
    language: str = ""
    num_pages: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PageRecord(StrictRecord):
    doc_id: str
    page_id: str
    page_index: int
    page_text: str = ""
    page_image_path: str = ""
    ocr_text: str = ""
    width: float | None = None
    height: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceNode(StrictRecord):
    node_id: str
    doc_id: str
    page_id: str
    node_type: str = "paragraph"
    bbox: list[float] | None = None
    text: str = ""
    image_path: str = ""
    parent_id: str | None = None
    reading_order: int = 0
    source: str = ""
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryRecord(StrictRecord):
    query_id: str
    dataset: str
    doc_id: str
    question: str
    answer: str = ""
    question_type: str = ""
    evidence_page_ids: list[str] = Field(default_factory=list)
    evidence_node_ids: list[str] = Field(default_factory=list)
    evidence_bboxes: list[list[float]] = Field(default_factory=list)
    is_answerable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalHit(StrictRecord):
    query_id: str
    rank: int
    score: float
    doc_id: str
    page_id: str
    node_id: str | None = None
    node_type: str | None = None
    text: str = ""
    retriever: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalRun(StrictRecord):
    experiment_name: str
    dataset: str
    retriever_type: str
    hits: list[RetrievalHit] = Field(default_factory=list)


class EvidenceCard(StrictRecord):
    query_id: str
    evidence_id: str
    page_id: str
    node_id: str | None = None
    node_type: str | None = None
    bbox: list[float] | None = None
    text: str = ""
    score: float = 0.0
    support: Literal["unknown", "supported", "insufficient", "conflict"] = "unknown"
