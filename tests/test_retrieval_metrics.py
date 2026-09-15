"""Page retrieval + metrics tests (migrated in batch M3, scoped to 1A page level).

说明（新手向）：这些测试只用 demo 级小数据（几条 query、几页），验证三件事：
1. BM25/TF-IDF 把含关键词的页面排前面（检索器的基本功）；
2. dense 在模型缺席时显式降级为 TF-IDF（`LAYOUTPATCH_DISABLE_SENTENCE_TRANSFORMERS=1`
   强制走降级分支），而不是静默失败；
3. 页级指标公式正确（recall/mrr/ndcg），且 region 指标在 hits 无 node_id 时不输出。
旧仓库 `test_retrieval_metrics.py` 里 hybrid/region/evidence_set/oracle 用例不搬，
那是 1B 之后或旧方向的，本轮 1A 用不上。
"""

from __future__ import annotations

from layoutpatch.evaluation.metrics import evaluate_metrics, mrr, ndcg_at_k, page_recall_at_k
from layoutpatch.retrieval.pipeline import retrieve_pages, score_texts_with_backend
from layoutpatch.retrieval.scoring import SimpleBM25, SimpleTfidf, reciprocal_rank_fusion
from layoutpatch.schemas import PageRecord, QueryRecord, RetrievalHit


def test_bm25_ranks_matching_document_first():
    scorer = SimpleBM25(["营业收入为12.8亿元", "合同服务期限为一年"])
    scores = scorer.score("营业收入是多少")

    assert scores[0] > scores[1]


def test_tfidf_ranks_matching_document_first():
    scorer = SimpleTfidf(["现金流量净额为3.4亿元", "付款方式为按季度支付"])
    scores = scorer.score("现金流量净额")

    assert scores[0] > scores[1]


def test_dense_fallback_backend_is_explicit(monkeypatch):
    monkeypatch.setenv("LAYOUTPATCH_DISABLE_SENTENCE_TRANSFORMERS", "1")

    result = score_texts_with_backend(
        ["营业收入是多少"], ["营业收入 100 元", "普通说明"], "dense", "BAAI/bge-m3"
    )

    assert result.backend == "dense:tfidf_fallback"
    assert result.scores[0][0] > result.scores[0][1]


def test_rrf_combines_rankings():
    scores = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])

    assert scores["b"] > scores["c"]


def test_page_metrics_on_demo_hits():
    queries = [
        QueryRecord(
            query_id="q1",
            dataset="demo",
            doc_id="doc1",
            question="营业收入是多少？",
            evidence_page_ids=["p1"],
        )
    ]
    hits = [
        RetrievalHit(
            query_id="q1", rank=1, score=2.0, doc_id="doc1", page_id="p1", retriever="unit"
        ),
        RetrievalHit(
            query_id="q1", rank=2, score=1.0, doc_id="doc1", page_id="p2", retriever="unit"
        ),
    ]

    assert page_recall_at_k(queries, hits, 1) == 1.0
    assert mrr(queries, hits) == 1.0
    assert ndcg_at_k(queries, hits, 5) == 1.0


def test_page_only_run_has_no_region_keys():
    queries = [
        QueryRecord(
            query_id="q1",
            dataset="demo",
            doc_id="doc1",
            question="营业收入是多少？",
            evidence_page_ids=["p1"],
        )
    ]
    hits = [
        RetrievalHit(
            query_id="q1", rank=1, score=2.0, doc_id="doc1", page_id="p1", retriever="unit"
        )
    ]

    metrics = evaluate_metrics(queries, hits)

    assert metrics["page_recall@5"] == 1.0
    assert metrics["region_hit@5"] == 0.0
    assert "region_mrr" not in metrics


def test_retrieve_pages_document_scope_filters_pages():
    pages = [
        PageRecord(doc_id="d1", page_id="d1_p1", page_index=1, page_text="营业收入增长"),
        PageRecord(doc_id="d1", page_id="d1_p2", page_index=2, page_text="无关内容说明"),
        PageRecord(doc_id="d2", page_id="d2_p1", page_index=1, page_text="营业收入增长"),
    ]
    queries = [
        QueryRecord(query_id="q1", dataset="demo", doc_id="d1", question="营业收入"),
        QueryRecord(query_id="q2", dataset="demo", doc_id="d2", question="营业收入"),
    ]

    hits = retrieve_pages(queries, pages, method="bm25", top_k=2, search_scope="document")
    by_query = {query.query_id: [hit.page_id for hit in hits if hit.query_id == query.query_id] for query in queries}

    assert set(by_query["q1"]) <= {"d1_p1", "d1_p2"}
    assert by_query["q2"] == ["d2_p1"]
