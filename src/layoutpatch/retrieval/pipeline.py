"""Page-level retrieval pipeline (migrated from old repo in batch M3, scoped to 1A).

说明（新手向）：
- `run_retrieval`：一次检索实验的总入口。读 config → 读四表 → 选检索器 → 写 run 目录
  （predictions.parquet + config.json + run_info.json）。run 目录名带时间戳，不可变；
  重跑生成新目录，这就是“五件套”里的三件（剩下两件 metrics.json/summary.md 由 evaluate 补）。
- search_scope（检索范围）：`document` 表示每个 query 只在自己文档的页里找
  （MMDocIR 的 1A 复验用这个）；`corpus` 表示全库 20395 页一起找。
  旧仓库 config 写 `document`，本仓库保持原样以保证复验可比。
- 本文件只支持三页级检索器：`bm25_page`（本轮对照）、`dense_page`（本轮对照，
  模型缺席时显式降级为 `dense:tfidf_fallback` 并记录在 hit 的 retriever 字段）、
  `colpali_page`（本轮主角）。旧仓库的 hybrid/region/evidence_set/oracle 分支
  是开题中文年报方向或 1B 之后才用的，本轮不搬（见 MIGRATION_BATCHES 不进清单）。
- `apply_data_split`：按文档级 split 切片。本轮 1A 全量复验不用 split（config 里不写
  `data_split` 即走全量），函数保留是为了 M3 的测试与将来 dev/test 划分。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from layoutpatch.io import read_processed_dataset, write_hits
from layoutpatch.paths import artifacts_dir, data_root, runs_dir
from layoutpatch.retrieval.colpali import retrieve_colpali_pages
from layoutpatch.retrieval.scoring import SimpleBM25, SimpleTfidf, reciprocal_rank_fusion
from layoutpatch.schemas import EvidenceNode, PageRecord, QueryRecord, RetrievalHit

SEARCH_SCOPE_CORPUS = "corpus"
SEARCH_SCOPE_DOCUMENT = "document"
_SENTENCE_TRANSFORMER_CACHE: dict[str, Any] = {}
_ACTIVE_RETRIEVAL_STARTED_AT: float | None = None


def log_retrieval(message: str) -> None:
    """Print progress immediately so long-running CPU retrieval is observable."""
    if _ACTIVE_RETRIEVAL_STARTED_AT is None:
        print(f"[lp] {message}", flush=True)
        return
    elapsed = time.monotonic() - _ACTIVE_RETRIEVAL_STARTED_AT
    print(
        f"[lp] {message} | experiment_elapsed={elapsed:.1f}s ({format_elapsed(elapsed)})",
        flush=True,
    )


def format_elapsed(seconds: float) -> str:
    """Format an elapsed duration for quick reading in long terminal runs."""
    hours, remainder = divmod(max(0.0, seconds), 3600)
    minutes, seconds_remainder = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds_remainder:04.1f}"


def progress_interval(total: int) -> int:
    """Emit about 20 updates, while still reporting small experiments per document."""
    return max(1, min(10, total // 20))


def progress_timing(index: int, total: int, started_at: float) -> str:
    elapsed = time.monotonic() - started_at
    if index <= 1:
        return f"elapsed {elapsed:.1f}s; estimating remaining time after this document."
    average_per_document = elapsed / (index - 1)
    remaining = average_per_document * (total - index + 1)
    return f"elapsed {elapsed:.1f}s; estimated remaining {remaining:.1f}s."


@dataclass(frozen=True)
class ScoreResult:
    scores: list[list[float]]
    backend: str


def run_retrieval(config_path: Path, split_name: str | None = None) -> Path:
    global _ACTIVE_RETRIEVAL_STARTED_AT
    started_at = time.monotonic()
    _ACTIVE_RETRIEVAL_STARTED_AT = started_at
    config = load_config(config_path)
    dataset = str(config["dataset"])
    processed_dataset = str(config.get("processed_dataset", dataset))
    retriever = config.get("retriever", {})
    retriever_type = str(retriever.get("type", "bm25_page"))
    experiment_name = str(config.get("experiment_name", f"{dataset}_{retriever_type}"))
    processed_dir = data_root() / "processed" / processed_dataset
    documents, pages, nodes, queries = read_processed_dataset(processed_dir)
    documents, pages, nodes, queries, split_info, split_manifest = apply_data_split(
        config, dataset, documents, pages, nodes, queries, split_name
    )
    output_root = resolve_project_path(config.get("output_dir", f"runs/retrieval/{experiment_name}"))
    if split_info is not None:
        output_root = output_root / str(split_info["name"])
    run_dir = output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    search_scope = normalize_search_scope(retriever)
    log_retrieval(
        f"Starting {experiment_name}: {len(queries)} queries, {len(pages)} pages, "
        f"scope={search_scope}, retriever={retriever_type}."
    )

    if retriever_type == "bm25_page":
        hits = retrieve_pages(
            queries, pages, method="bm25", top_k=max_top_k(retriever), search_scope=search_scope
        )
    elif retriever_type == "dense_page":
        hits = retrieve_pages(
            queries,
            pages,
            method="dense",
            top_k=max_top_k(retriever),
            encoder=str(retriever.get("encoder", "BAAI/bge-m3")),
            search_scope=search_scope,
            require_dense_model=require_dense_model(retriever),
            dense_batch_size=dense_batch_size(retriever),
            dense_max_seq_length=dense_max_seq_length(retriever),
        )
    elif retriever_type == "colpali_page":
        hits = retrieve_colpali_pages(
            dataset,
            queries,
            pages,
            top_k=max_top_k(retriever),
            config=retriever,
            search_scope=search_scope,
        )
    else:
        raise ValueError(
            f"Unsupported retriever type: {retriever_type}. "
            "M3 supports bm25_page, dense_page, colpali_page."
        )

    log_retrieval(
        f"Retrieval finished: {len(hits)} hits generated in {time.monotonic() - started_at:.1f}s. "
        "Writing result files..."
    )

    write_hits(run_dir / "predictions.parquet", hits)
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if split_manifest is not None:
        shutil.copy2(split_manifest, run_dir / "data_split.yaml")
    (run_dir / "run_info.json").write_text(
        json.dumps(
            {
                "experiment_name": experiment_name,
                "dataset": dataset,
                "processed_dataset": processed_dataset,
                "retriever_type": retriever_type,
                "hits": len(hits),
                "actual_retrievers": sorted({hit.retriever for hit in hits}),
                "data_split": split_info,
                "data_counts": {
                    "documents": len(documents),
                    "pages": len(pages),
                    "nodes": len(nodes),
                    "queries": len(queries),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    update_latest(output_root, run_dir)
    log_retrieval(f"Results are ready in {run_dir}.")
    _ACTIVE_RETRIEVAL_STARTED_AT = None
    return run_dir


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return expand_env(raw)


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        expanded = value
        for key, env_value in os.environ.items():
            expanded = expanded.replace("${" + key + "}", env_value)
        expanded = expanded.replace("${LAYOUTPATCH_DATA_ROOT}", str(data_root()))
        expanded = expanded.replace("${LAYOUTPATCH_RUNS_ROOT}", str(runs_dir()))
        expanded = expanded.replace("${LAYOUTPATCH_ARTIFACT_ROOT}", str(artifacts_dir()))
        return expanded
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    return value


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def apply_data_split(
    config: dict[str, Any],
    dataset: str,
    documents: list[Any],
    pages: list[PageRecord],
    nodes: list[EvidenceNode],
    queries: list[QueryRecord],
    split_override: str | None = None,
) -> tuple[
    list[Any],
    list[PageRecord],
    list[EvidenceNode],
    list[QueryRecord],
    dict[str, Any] | None,
    Path | None,
]:
    """Filter a processed dataset by the immutable document-level split manifest."""
    split_config = config.get("data_split")
    if not split_config:
        if split_override is not None:
            raise ValueError("`--split` requires a `data_split.manifest` in the experiment config.")
        return documents, pages, nodes, queries, None, None

    manifest_value = split_config.get("manifest")
    if not manifest_value:
        raise ValueError("`data_split.manifest` is required when data_split is configured.")
    manifest_path = resolve_project_path(manifest_value)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing data split manifest: {manifest_path}")
    manifest = load_config(manifest_path)
    if str(manifest.get("dataset", "")) != dataset:
        raise ValueError(
            f"Split manifest dataset `{manifest.get('dataset')}` does not match experiment dataset `{dataset}`."
        )
    split_name = str(split_override or split_config.get("name", ""))
    split_docs = manifest.get("splits", {})
    if split_name not in split_docs:
        raise ValueError(f"Unknown data split `{split_name}`. Available: {sorted(split_docs)}.")

    available_doc_ids = {document.doc_id for document in documents}
    declared_doc_ids: list[str] = []
    for name in split_docs:
        declared_doc_ids.extend(split_docs[name])
    if set(declared_doc_ids) != available_doc_ids:
        missing = sorted(available_doc_ids - set(declared_doc_ids))
        unknown = sorted(set(declared_doc_ids) - available_doc_ids)
        raise ValueError(
            f"Split manifest does not match processed documents. Missing={missing}; unknown={unknown}."
        )

    selected_doc_ids = set(split_docs[split_name])
    filtered_documents = [document for document in documents if document.doc_id in selected_doc_ids]
    filtered_pages = [page for page in pages if page.doc_id in selected_doc_ids]
    filtered_nodes = [node for node in nodes if node.doc_id in selected_doc_ids]
    filtered_queries = [query for query in queries if query.doc_id in selected_doc_ids]
    if not filtered_queries:
        raise ValueError(f"Data split `{split_name}` contains no queries.")

    manifest_hash = sha256(manifest_path.read_bytes()).hexdigest()
    project_path = Path.cwd()
    try:
        manifest_reference = str(manifest_path.relative_to(project_path))
    except ValueError:
        manifest_reference = str(manifest_path)
    split_info = {
        "name": split_name,
        "manifest": manifest_reference,
        "manifest_sha256": manifest_hash,
        "test_status": manifest.get("test_status"),
        "qa_source": manifest.get("qa_source"),
        "qa_source_sha256": manifest.get("qa_source_sha256"),
        "document_count": len(filtered_documents),
        "page_count": len(filtered_pages),
        "node_count": len(filtered_nodes),
        "query_count": len(filtered_queries),
    }
    return (
        filtered_documents,
        filtered_pages,
        filtered_nodes,
        filtered_queries,
        split_info,
        manifest_path,
    )


def max_top_k(retriever: dict[str, Any]) -> int:
    value = retriever.get("top_k", 10)
    if isinstance(value, list):
        return max(int(item) for item in value)
    return int(value)


def normalize_search_scope(retriever: dict[str, Any]) -> str:
    scope = str(retriever.get("search_scope", retriever.get("scope", SEARCH_SCOPE_CORPUS))).lower()
    if scope in {"doc", "same_doc", "in_document", SEARCH_SCOPE_DOCUMENT}:
        return SEARCH_SCOPE_DOCUMENT
    if scope in {"all", "global", SEARCH_SCOPE_CORPUS}:
        return SEARCH_SCOPE_CORPUS
    raise ValueError(f"Unsupported search_scope: {scope}. Use 'corpus' or 'document'.")


def require_dense_model(retriever: dict[str, Any]) -> bool:
    return bool(retriever.get("require_model", retriever.get("require_dense_model", False)))


def dense_batch_size(retriever: dict[str, Any]) -> int:
    return int(retriever.get("dense_batch_size", os.getenv("LAYOUTPATCH_DENSE_BATCH_SIZE", 8)))


def dense_max_seq_length(retriever: dict[str, Any]) -> int | None:
    value = retriever.get("dense_max_seq_length", os.getenv("LAYOUTPATCH_DENSE_MAX_SEQ_LENGTH"))
    if value in {None, ""}:
        return None
    return int(value)


def page_fusion_methods(retriever: dict[str, Any]) -> list[str]:
    methods = retriever.get("page_methods", ["bm25", "dense"])
    if isinstance(methods, str):
        return [methods]
    return [str(method) for method in methods]


def group_queries_by_doc(queries: list[QueryRecord]) -> dict[str, list[QueryRecord]]:
    grouped: dict[str, list[QueryRecord]] = {}
    for query in queries:
        grouped.setdefault(query.doc_id, []).append(query)
    return grouped


def group_pages_by_doc(pages: list[PageRecord]) -> dict[str, list[PageRecord]]:
    grouped: dict[str, list[PageRecord]] = {}
    for page in pages:
        grouped.setdefault(page.doc_id, []).append(page)
    return grouped


def group_nodes_by_doc(nodes: list[EvidenceNode]) -> dict[str, list[EvidenceNode]]:
    grouped: dict[str, list[EvidenceNode]] = {}
    for node in nodes:
        grouped.setdefault(node.doc_id, []).append(node)
    return grouped


def retrieve_pages(
    queries: list[QueryRecord],
    pages: list[PageRecord],
    method: str,
    top_k: int,
    encoder: str | None = None,
    search_scope: str = SEARCH_SCOPE_CORPUS,
    require_dense_model: bool = False,
    dense_batch_size: int = 8,
    dense_max_seq_length: int | None = None,
) -> list[RetrievalHit]:
    search_scope = normalize_search_scope({"search_scope": search_scope})
    if search_scope == SEARCH_SCOPE_DOCUMENT:
        pages_by_doc = group_pages_by_doc(pages)
        hits: list[RetrievalHit] = []
        queries_by_doc = group_queries_by_doc(queries)
        total_documents = len(queries_by_doc)
        started_at = time.monotonic()
        interval = progress_interval(total_documents)
        for index, (doc_id, doc_queries) in enumerate(queries_by_doc.items(), start=1):
            if index == 1 or index % interval == 0 or index == total_documents:
                log_retrieval(
                    f"Page retrieval: document {index}/{total_documents}; "
                    f"{len(doc_queries)} queries, {len(pages_by_doc.get(doc_id, []))} pages; "
                    f"{progress_timing(index, total_documents, started_at)}"
                )
            doc_hits = retrieve_pages(
                doc_queries,
                pages_by_doc.get(doc_id, []),
                method,
                top_k,
                encoder,
                require_dense_model=require_dense_model,
                dense_batch_size=dense_batch_size,
                dense_max_seq_length=dense_max_seq_length,
            )
            hits.extend(doc_hits)
        return hits

    docs = [page.page_text or page.ocr_text or page.page_id for page in pages]
    score_result = score_texts_with_backend(
        [query.question for query in queries],
        docs,
        method,
        encoder,
        require_dense_model,
        dense_batch_size,
        dense_max_seq_length,
    )
    hits: list[RetrievalHit] = []
    for query, scores in zip(queries, score_result.scores, strict=True):
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        for rank, (index, score) in enumerate(ranked, start=1):
            page = pages[index]
            hits.append(
                RetrievalHit(
                    query_id=query.query_id,
                    rank=rank,
                    score=float(score),
                    doc_id=page.doc_id,
                    page_id=page.page_id,
                    text=page.page_text or page.ocr_text,
                    retriever=score_result.backend,
                )
            )
    return hits


def retrieve_hybrid_pages(
    queries: list[QueryRecord],
    pages: list[PageRecord],
    retriever: dict[str, Any],
) -> list[RetrievalHit]:
    top_k = int(retriever.get("page_top_k", max_top_k(retriever)))
    candidate_top_k = int(retriever.get("candidate_top_k", max(top_k, 20)))
    search_scope = normalize_search_scope(retriever)
    if search_scope == SEARCH_SCOPE_DOCUMENT:
        pages_by_doc = group_pages_by_doc(pages)
        hits: list[RetrievalHit] = []
        queries_by_doc = group_queries_by_doc(queries)
        total_documents = len(queries_by_doc)
        started_at = time.monotonic()
        interval = progress_interval(total_documents)
        for index, (doc_id, doc_queries) in enumerate(queries_by_doc.items(), start=1):
            if index == 1 or index % interval == 0 or index == total_documents:
                log_retrieval(
                    f"Hybrid page retrieval: document {index}/{total_documents}; "
                    f"{len(doc_queries)} queries, {len(pages_by_doc.get(doc_id, []))} pages; "
                    f"{progress_timing(index, total_documents, started_at)}"
                )
            doc_hits = retrieve_hybrid_pages(
                doc_queries,
                pages_by_doc.get(doc_id, []),
                {**retriever, "search_scope": SEARCH_SCOPE_CORPUS},
            )
            hits.extend(doc_hits)
        return hits

    encoder = str(retriever.get("encoder", "BAAI/bge-m3"))
    method_hits = [
        retrieve_pages(
            queries,
            pages,
            method=method,
            top_k=candidate_top_k,
            encoder=encoder,
            search_scope=SEARCH_SCOPE_CORPUS,
            require_dense_model=require_dense_model(retriever),
            dense_batch_size=dense_batch_size(retriever),
            dense_max_seq_length=dense_max_seq_length(retriever),
        )
        for method in page_fusion_methods(retriever)
    ]
    page_by_id = {page.page_id: page for page in pages}
    final_hits: list[RetrievalHit] = []
    for query in queries:
        rankings = [
            [hit.page_id for hit in hits if hit.query_id == query.query_id] for hits in method_hits
        ]
        fused = reciprocal_rank_fusion([ranking for ranking in rankings if ranking])
        ranked_page_ids = sorted(fused, key=fused.get, reverse=True)[:top_k]
        for rank, page_id in enumerate(ranked_page_ids, start=1):
            page = page_by_id[page_id]
            final_hits.append(
                RetrievalHit(
                    query_id=query.query_id,
                    rank=rank,
                    score=float(fused[page_id]),
                    doc_id=page.doc_id,
                    page_id=page.page_id,
                    text=page.page_text or page.ocr_text,
                    retriever="hybrid_page",
                )
            )
    return final_hits


def score_texts(
    queries: list[str],
    docs: list[str],
    method: str,
    encoder: str | None = None,
) -> list[list[float]]:
    return score_texts_with_backend(queries, docs, method, encoder).scores


def score_texts_with_backend(
    queries: list[str],
    docs: list[str],
    method: str,
    encoder: str | None = None,
    require_model: bool = False,
    batch_size: int = 8,
    max_seq_length: int | None = None,
) -> ScoreResult:
    if method == "bm25":
        bm25 = SimpleBM25(docs)
        return ScoreResult([bm25.score(query) for query in queries], "bm25")
    if method == "dense":
        model_scores = try_sentence_transformer_scores(
            queries, docs, encoder, batch_size=batch_size, max_seq_length=max_seq_length
        )
        if model_scores is not None:
            return model_scores
        if require_model:
            model_name = encoder or "BAAI/bge-m3"
            raise RuntimeError(
                f"Dense retrieval requires local SentenceTransformer model `{model_name}`, "
                "but it could not be loaded. Download/cache the model first, or set "
                "`require_model: false` to allow TF-IDF fallback."
            )
        tfidf = SimpleTfidf(docs)
        return ScoreResult([tfidf.score(query) for query in queries], "dense:tfidf_fallback")
    tfidf = SimpleTfidf(docs)
    return ScoreResult([tfidf.score(query) for query in queries], "tfidf")


def try_sentence_transformer_scores(
    queries: list[str],
    docs: list[str],
    encoder: str | None,
    batch_size: int = 8,
    max_seq_length: int | None = None,
) -> ScoreResult | None:
    if os.getenv("LAYOUTPATCH_DISABLE_SENTENCE_TRANSFORMERS", "0") == "1":
        return None
    try:
        from sentence_transformers.util import cos_sim

        model_name = encoder or "BAAI/bge-m3"
        model = get_sentence_transformer(model_name, max_seq_length=max_seq_length)
        query_embeddings = model.encode(
            queries, batch_size=batch_size, show_progress_bar=False, convert_to_tensor=True
        )
        doc_embeddings = model.encode(
            docs, batch_size=batch_size, show_progress_bar=False, convert_to_tensor=True
        )
        scores = cos_sim(query_embeddings, doc_embeddings)
        return ScoreResult(scores.tolist(), f"dense:{model_name}")
    except Exception:
        return None


def get_sentence_transformer(model_name: str, max_seq_length: int | None = None) -> Any:
    cache_key = f"{model_name}\0{max_seq_length}"
    if cache_key in _SENTENCE_TRANSFORMER_CACHE:
        return _SENTENCE_TRANSFORMER_CACHE[cache_key]
    from sentence_transformers import SentenceTransformer

    log_retrieval(f"Loading sentence encoder `{model_name}` from local cache...")
    started_at = time.monotonic()
    model = SentenceTransformer(model_name, local_files_only=True)
    if max_seq_length:
        model.max_seq_length = max_seq_length
    _SENTENCE_TRANSFORMER_CACHE[cache_key] = model
    log_retrieval(f"Sentence encoder is ready in {time.monotonic() - started_at:.1f}s.")
    return model


def update_latest(output_root: Path, run_dir: Path) -> None:
    latest = output_root / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
        latest.symlink_to(run_dir.name, target_is_directory=True)
    except OSError:
        (output_root / "latest.txt").write_text(str(run_dir), encoding="utf-8")
