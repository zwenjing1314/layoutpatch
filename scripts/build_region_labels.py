"""Build region_labels.parquet for MMDocIR evaluation (M2.5).

独立脚本：只读官方 annotations + 已有 nodes 表，只写 region_labels.parquet，
四表（documents/pages/nodes/queries）一行不改。删了 region_labels 可随时重建。
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import typer

from layoutpatch.datasets.adapters import write_region_labels
from layoutpatch.evaluation.region_labels import build_region_labels_from_annotations
from layoutpatch.paths import data_root

app = typer.Typer(help="Build region-level gold labels.")


def _bbox_key(bbox: list[float]) -> tuple[float, ...]:
    return tuple(round(float(value), 2) for value in bbox)


@app.command()
def main(
    raw_dir: str = str(data_root() / "raw" / "mmdocir_evaluation"),
    processed_dir: str = str(data_root() / "processed" / "mmdocir_evaluation"),
) -> None:
    raw = Path(raw_dir)
    out_dir = Path(processed_dir)
    annotations = [
        json.loads(line) for line in (raw / "MMDocIR_annotations.jsonl").read_text(encoding="utf-8").splitlines() if line
    ]
    nodes = pl.read_parquet(out_dir / "nodes.parquet").to_dicts()
    lookup: dict[tuple[str, str, tuple[float, ...]], str] = {}
    for row in nodes:
        bbox = row["bbox"]
        if isinstance(bbox, str):
            import json as _json

            bbox = _json.loads(bbox)
        lookup[(row["doc_id"], row["page_id"], _bbox_key(bbox or []))] = row["node_id"]
    labels = build_region_labels_from_annotations(annotations, lookup)
    out = write_region_labels(out_dir, labels)
    matched = sum(1 for label in labels if label.source == "matched")
    typer.echo(f"wrote {out}: {len(labels)} labels ({matched} matched, {len(labels) - matched} unmapped)")


if __name__ == "__main__":
    app()
