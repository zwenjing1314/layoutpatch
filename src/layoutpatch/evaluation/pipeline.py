"""Run evaluation: metrics.json + errors.csv + summary.md (migrated in batch M3).

说明（新手向）：
- `evaluate_run`：给定一个 run 目录，读 `predictions.parquet` + `run_info.json`，
  重算指标并写回 `metrics.json` / `errors.csv` / `summary.md`。
  这样“跑检索”和“算指标”是两步：检索只管产出预测，评测只管打分，
  复验时可以直接对比 `metrics.json`。
- `validate_run_alignment`：防呆检查。`predictions` 的 query 集合必须和当前
  processed 数据的 query 集合完全一致，否则说明 prepare 被 smoke 数据覆盖过，
  直接报错而不是给出一个看起来合理但实际错位的分数。
- `resolve_run_dir`：支持传 `latest` 快捷方式（run 目录下的软链接或 latest.txt）。
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from layoutpatch.evaluation.metrics import evaluate_metrics, group_hits
from layoutpatch.io import read_hits, read_processed_dataset
from layoutpatch.paths import data_root
from layoutpatch.retrieval.pipeline import apply_data_split
from layoutpatch.schemas import QueryRecord, RetrievalHit


def evaluate_run(run: Path) -> dict[str, float]:
    run_dir = resolve_run_dir(run)
    run_info = json.loads((run_dir / "run_info.json").read_text(encoding="utf-8"))
    hits = read_hits(run_dir / "predictions.parquet")
    queries = load_run_queries(run_dir, run_info)
    validate_run_alignment(run_dir, run_info, queries, hits)
    metrics = evaluate_metrics(queries, hits)
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_errors(run_dir / "errors.csv", queries, hits)
    write_summary(run_dir / "summary.md", run_info, metrics, queries, hits)
    return metrics


def validate_run_alignment(
    run_dir: Path,
    run_info: dict,
    queries: list[QueryRecord],
    hits: list[RetrievalHit],
) -> None:
    """Reject evaluation when the processed dataset does not match the run.

    Processed tables are shared and a smoke ``prepare`` can replace a full
    dataset.  Without this check, evaluation can silently score a run against
    the wrong query subset and still produce plausible-looking metrics.
    """
    expected_query_ids = {query.query_id for query in queries}
    predicted_query_ids = {hit.query_id for hit in hits}
    if expected_query_ids != predicted_query_ids:
        missing = sorted(expected_query_ids - predicted_query_ids)
        extra = sorted(predicted_query_ids - expected_query_ids)
        raise ValueError(
            f"Run/data mismatch for {run_dir}: processed dataset has "
            f"{len(expected_query_ids)} queries but predictions contain "
            f"{len(predicted_query_ids)} queries. "
            f"Missing predictions={missing[:5]}; unexpected predictions={extra[:5]}. "
            "Prepare the same dataset scope used by the run before evaluating."
        )

    data_counts = run_info.get("data_counts")
    if isinstance(data_counts, dict):
        recorded_queries = data_counts.get("queries")
        if recorded_queries is not None and int(recorded_queries) != len(queries):
            raise ValueError(
                f"Run/data mismatch for {run_dir}: run recorded "
                f"{recorded_queries} queries but current data has {len(queries)}."
            )


def load_run_queries(run_dir: Path, run_info: dict) -> list[QueryRecord]:
    """Load exactly the query split that produced a retrieval run."""
    dataset = str(run_info["dataset"])
    processed_dataset = str(run_info.get("processed_dataset", dataset))
    documents, pages, nodes, queries = read_processed_dataset(
        data_root() / "processed" / processed_dataset
    )
    split_info = run_info.get("data_split")
    if not split_info:
        return queries
    split_manifest = run_dir / "data_split.yaml"
    if not split_manifest.exists():
        raise FileNotFoundError(f"Missing split manifest copied with retrieval run: {split_manifest}")
    _, _, _, filtered_queries, _, _ = apply_data_split(
        {"data_split": {"manifest": str(split_manifest), "name": split_info["name"]}},
        dataset,
        documents,
        pages,
        nodes,
        queries,
    )
    return filtered_queries


def resolve_run_dir(run: Path) -> Path:
    if run.is_symlink():
        return run.resolve()
    if run.is_dir():
        return run
    latest_txt = run.parent / "latest.txt"
    if run.name == "latest" and latest_txt.exists():
        return Path(latest_txt.read_text(encoding="utf-8").strip())
    raise FileNotFoundError(f"Run directory not found: {run}")


def write_errors(path: Path, queries: list[QueryRecord], hits: list[RetrievalHit]) -> None:
    grouped = group_hits(hits)
    rows = []
    for query in queries:
        top = grouped.get(query.query_id, [])[:5]
        predicted_pages = [hit.page_id for hit in top]
        predicted_nodes = [hit.node_id for hit in top if hit.node_id]
        page_ok = bool(set(predicted_pages).intersection(query.evidence_page_ids))
        region_ok = bool(set(predicted_nodes).intersection(query.evidence_node_ids))
        if not page_ok or (query.evidence_node_ids and not region_ok):
            rows.append(
                {
                    "query_id": query.query_id,
                    "question": query.question,
                    "gold_pages": ";".join(query.evidence_page_ids),
                    "pred_pages_top5": ";".join(predicted_pages),
                    "gold_nodes": ";".join(query.evidence_node_ids),
                    "pred_nodes_top5": ";".join(predicted_nodes),
                    "page_ok": page_ok,
                    "region_ok": region_ok,
                }
            )
    pl.DataFrame(
        rows or [{"query_id": "", "question": "", "page_ok": True, "region_ok": True}]
    ).write_csv(path)


def write_summary(
    path: Path,
    run_info: dict,
    metrics: dict[str, float],
    queries: list[QueryRecord],
    hits: list[RetrievalHit],
) -> None:
    grouped = group_hits(hits)
    lines = [
        f"# {run_info['experiment_name']} Summary",
        "",
        f"- Dataset: `{run_info['dataset']}`",
        f"- Retriever: `{run_info['retriever_type']}`",
        f"- Queries: `{len(queries)}`",
        f"- Hits: `{len(hits)}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {value:.4f} |")
    lines.extend(["", "## Example Cases", ""])
    for query in queries[:5]:
        top = grouped.get(query.query_id, [])[:3]
        lines.append(f"### {query.query_id}")
        lines.append("")
        lines.append(f"- Question: {query.question}")
        lines.append(f"- Gold answer: {query.answer}")
        lines.append(f"- Gold pages: {', '.join(query.evidence_page_ids) or '-'}")
        for hit in top:
            location = hit.node_id or hit.page_id
            lines.append(
                f"- Hit {hit.rank}: `{location}` score={hit.score:.4f} text={hit.text[:120]}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
