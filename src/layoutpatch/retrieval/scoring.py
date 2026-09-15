"""Text scoring backends for page retrieval (migrated from old repo in batch M3).

说明（新手向）：
- `tokenize`：中英文混合分词。英文按词、小写；中文按字。 query 和页面用同一套分词，
  否则两边 token 对不上，分数无意义。
- `SimpleBM25`：经典 BM25 公式。核心思想：query 里的词在某页出现越多、越稀有，
  该页分数越高；同时用 `avgdl`（平均页长）惩罚超长页面，防止长页占便宜。
- `SimpleTfidf`：TF-IDF 余弦相似度。`query` 和每页各算一个向量，算余弦夹角。
  它是 dense 模型缺席时的兜底（见 pipeline 的 `dense:tfidf_fallback`）。
- `reciprocal_rank_fusion`：RRF 融合。把 BM25 和 dense 两份排名按 `1/(k+rank)` 加权相加，
  得到 hybrid 排名。k=60 是经验常数，不调。
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", lowered)
    return tokens or [lowered.strip()] if lowered.strip() else []


class SimpleBM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(doc) for doc in docs]
        self.doc_count = len(self.tokens)
        self.avgdl = sum(len(doc) for doc in self.tokens) / max(self.doc_count, 1)
        self.df: Counter[str] = Counter()
        for doc in self.tokens:
            self.df.update(set(doc))

    def score(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        scores = []
        for doc_tokens in self.tokens:
            tf = Counter(doc_tokens)
            doc_len = len(doc_tokens)
            score = 0.0
            for token in query_tokens:
                if token not in tf:
                    continue
                df = self.df.get(token, 0)
                idf = math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
                denom = tf[token] + self.k1 * (
                    1 - self.b + self.b * doc_len / max(self.avgdl, 1e-9)
                )
                score += idf * tf[token] * (self.k1 + 1) / denom
            scores.append(score)
        return scores


class SimpleTfidf:
    def __init__(self, docs: list[str]):
        self.docs = [tokenize(doc) for doc in docs]
        self.doc_count = len(self.docs)
        self.df: Counter[str] = Counter()
        for doc in self.docs:
            self.df.update(set(doc))
        self.vectors = [self._vector(doc) for doc in self.docs]

    def _idf(self, token: str) -> float:
        return math.log((self.doc_count + 1) / (self.df.get(token, 0) + 1)) + 1

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        total = max(sum(counts.values()), 1)
        return {token: count / total * self._idf(token) for token, count in counts.items()}

    def score(self, query: str) -> list[float]:
        query_vector = self._vector(tokenize(query))
        return [cosine(query_vector, doc_vector) for doc_vector in self.vectors]


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return dict(scores)
