from __future__ import annotations

from layoutpatch.io import read_records, write_records
from layoutpatch.schemas import DocumentRecord, QueryRecord, RetrievalHit


def test_schema_roundtrip_parquet(tmp_path):
    path = tmp_path / "documents.parquet"
    records = [
        DocumentRecord(
            doc_id="doc1",
            dataset="demo",
            title="Demo",
            language="zh",
            metadata={"source": "unit-test"},
        )
    ]
    write_records(path, records)

    loaded = read_records(path, DocumentRecord)

    assert loaded[0].doc_id == "doc1"
    assert loaded[0].metadata["source"] == "unit-test"


def test_query_defaults_are_lists():
    query = QueryRecord(query_id="q1", dataset="demo", doc_id="doc1", question="收入是多少？")

    assert query.evidence_page_ids == []
    assert query.evidence_node_ids == []
    assert query.is_answerable is True


def test_retrieval_hit_metadata_roundtrip(tmp_path):
    path = tmp_path / "hits.parquet"
    records = [
        RetrievalHit(
            query_id="q1",
            rank=1,
            score=1.0,
            doc_id="doc1",
            page_id="doc1_p1",
            node_id="doc1_p1_n1",
            retriever="unit",
            metadata={"coverage_slots": ["metric:营业收入"], "page_rank": 1},
        )
    ]
    write_records(path, records)

    loaded = read_records(path, RetrievalHit)

    assert loaded[0].metadata["coverage_slots"] == ["metric:营业收入"]
    assert loaded[0].metadata["page_rank"] == 1
