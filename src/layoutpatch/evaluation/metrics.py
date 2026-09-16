"""Page-level evaluation metrics (migrated from old repo in batch M3).

说明（新手向）：
- 页级指标只看 `evidence_page_ids`：`page_recall@k` 是 gold 页进没进 Top-K 的比例；
  `mrr` / `ndcg@k` 还考虑排名越靠前越好。1A 复验就看这三个，判据是 R@5≈0.839。
- `region_hit@5` 是占位诊断：旧仓库的 region 指标是节点精确匹配
  （`hit.node_id in gold_nodes`），不是 `PAPER_SPEC` 第 8 节要的 IoU≥0.5 判定；
  真正的 IoU 评测在 1B/1C 写 `region_metrics.py`，这里只保留旧逻辑做回归对照。
- `ndcg_at_k` 与旧仓库逐行一致（含 `target_count` 取 node 数或 page 数的分支），
  这是 EXP-001 复验能对上旧 0.6932/0.7231 的前提。已知口径限制：多 gold 页的 query
  在节点数小于页命中数时，dcg 分子可能超过 idcg，小样本下 ndcg 会略大于 1（旧仓库同病）。
  正式的 IoU 区域口径在 1B 的 `region_metrics.py` 里另立，本文件不改公式只做回归对照。
- `evaluate_metrics` 的 region 四件套（`region_gold_queries` / `region_mrr` /
  `region_ndcg@5` / `region_ndcg@10`）只在 hits 带 `node_id` 时才输出，
  页级 run 不带 node，自然没有这四个键——这是有意设计，不是 bug。
"""

from __future__ import annotations

import math

from layoutpatch.schemas import QueryRecord, RetrievalHit


def group_hits(hits: list[RetrievalHit]) -> dict[str, list[RetrievalHit]]:
    grouped: dict[str, list[RetrievalHit]] = {}
    for hit in sorted(hits, key=lambda item: (item.query_id, item.rank)):
        grouped.setdefault(hit.query_id, []).append(hit)
    return grouped


def page_recall_at_k(queries: list[QueryRecord], hits: list[RetrievalHit], k: int) -> float:
    grouped = group_hits(hits)
    total = 0
    correct = 0
    for query in queries:
        if not query.evidence_page_ids:
            continue
        total += 1
        predicted = {hit.page_id for hit in grouped.get(query.query_id, [])[:k]}
        if predicted.intersection(query.evidence_page_ids):
            correct += 1
    return correct / total if total else 0.0


def hit_matches_target(query: QueryRecord, hit: RetrievalHit) -> bool:
    if hit.node_id and query.evidence_node_ids:
        return hit.node_id in set(query.evidence_node_ids)
    return hit.page_id in set(query.evidence_page_ids)


def mrr(queries: list[QueryRecord], hits: list[RetrievalHit]) -> float:
    grouped = group_hits(hits)
    total = 0
    score = 0.0
    for query in queries:
        if not query.evidence_page_ids and not query.evidence_node_ids:
            continue
        total += 1
        for hit in grouped.get(query.query_id, []):
            if hit_matches_target(query, hit):
                score += 1 / hit.rank
                break
    return score / total if total else 0.0


def ndcg_at_k(queries: list[QueryRecord], hits: list[RetrievalHit], k: int) -> float:
    grouped = group_hits(hits)
    total = 0
    score = 0.0
    for query in queries:
        if not query.evidence_page_ids and not query.evidence_node_ids:
            continue
        total += 1
        dcg = 0.0
        for hit in grouped.get(query.query_id, [])[:k]:
            relevance = 1 if hit_matches_target(query, hit) else 0
            dcg += relevance / math.log2(hit.rank + 1)
        target_count = (
            len(query.evidence_node_ids)
            if any(hit.node_id for hit in grouped.get(query.query_id, [])[:k])
            and query.evidence_node_ids
            else len(query.evidence_page_ids)
        )
        ideal_hits = min(target_count, k)
        idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        score += dcg / idcg if idcg else 0.0
    return score / total if total else 0.0


def region_hit_at_k(queries: list[QueryRecord], hits: list[RetrievalHit], k: int) -> float:
    grouped = group_hits(hits)
    total = 0
    correct = 0
    for query in queries:
        if not query.evidence_node_ids:
            continue
        total += 1
        predicted = {hit.node_id for hit in grouped.get(query.query_id, [])[:k] if hit.node_id}
        if predicted.intersection(query.evidence_node_ids):
            correct += 1
    return correct / total if total else 0.0


def region_mrr(queries: list[QueryRecord], hits: list[RetrievalHit]) -> float:
    """MRR over queries with an exact layout-node gold annotation."""
    grouped = group_hits(hits)
    total = 0
    score = 0.0
    for query in queries:
        if not query.evidence_node_ids:
            continue
        total += 1
        gold_nodes = set(query.evidence_node_ids)
        for hit in grouped.get(query.query_id, []):
            if hit.node_id in gold_nodes:
                score += 1 / hit.rank
                break
    return score / total if total else 0.0


def region_ndcg_at_k(queries: list[QueryRecord], hits: list[RetrievalHit], k: int) -> float:
    """nDCG over queries with an exact layout-node gold annotation."""
    grouped = group_hits(hits)
    total = 0
    score = 0.0
    for query in queries:
        if not query.evidence_node_ids:
            continue
        total += 1
        gold_nodes = set(query.evidence_node_ids)
        dcg = sum(
            (1 / math.log2(hit.rank + 1))
            for hit in grouped.get(query.query_id, [])[:k]
            if hit.node_id in gold_nodes
        )
        ideal_hits = min(len(gold_nodes), k)
        idcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        score += dcg / idcg if idcg else 0.0
    return score / total if total else 0.0


def evaluate_metrics(queries: list[QueryRecord], hits: list[RetrievalHit]) -> dict[str, float]:
    metrics = {
        "page_recall@1": page_recall_at_k(queries, hits, 1),
        "page_recall@5": page_recall_at_k(queries, hits, 5),
        "page_recall@10": page_recall_at_k(queries, hits, 10),
        "mrr": mrr(queries, hits),
        "ndcg@5": ndcg_at_k(queries, hits, 5),
        "ndcg@10": ndcg_at_k(queries, hits, 10),
        "region_hit@5": region_hit_at_k(queries, hits, 5),
    }
    if any(hit.node_id for hit in hits):
        metrics.update(
            {
                "region_gold_queries": float(sum(bool(query.evidence_node_ids) for query in queries)),
                "region_mrr": region_mrr(queries, hits),
                "region_ndcg@5": region_ndcg_at_k(queries, hits, 5),
                "region_ndcg@10": region_ndcg_at_k(queries, hits, 10),
            }
        )
    return metrics
