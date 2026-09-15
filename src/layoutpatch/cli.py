"""lp command line entry (typer).

M3 registers retrieve + evaluate next to prepare. Keep each command thin;
logic lives in retrieval.pipeline / evaluation.pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from layoutpatch.paths import resolve_project_path

app = typer.Typer(help="LayoutPatch experiment CLI.", no_args_is_help=True)
console = Console()


@app.callback()
def _callback() -> None:
    """Keep multi-command behaviour so `lp version` stays a subcommand."""


@app.command("version")
def version() -> None:
    """Print the package version."""
    from layoutpatch import __version__

    typer.echo(f"layoutpatch {__version__}")


@app.command("prepare")
def prepare(
    dataset: Annotated[str, typer.Option(help="Dataset name: demo or mmdocir.")] = "demo",
    limit_docs: Annotated[
        int | None, typer.Option(help="Optional document limit for quick experiments.")
    ] = None,
    output_dataset: Annotated[
        str | None,
        typer.Option(
            help="Optional processed-directory name; use a separate name for smoke data."
        ),
    ] = None,
) -> None:
    """Prepare raw data into standard parquet tables."""
    from layoutpatch.datasets import prepare_dataset

    result = prepare_dataset(dataset, limit_docs=limit_docs, output_dataset=output_dataset)
    table = Table(title="Prepare Result")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("dataset", result.dataset)
    table.add_row("processed_dir", str(result.processed_dir))
    table.add_row("documents", str(result.documents))
    table.add_row("pages", str(result.pages))
    table.add_row("nodes", str(result.nodes))
    table.add_row("queries", str(result.queries))
    table.add_row("message", result.message)
    console.print(table)
    if result.documents == 0:
        console.print("[yellow]No usable data was prepared. For a smoke test, run:[/yellow]")
        console.print("[bold]uv run lp prepare --dataset demo[/bold]")


@app.command("retrieve")
def retrieve(
    config: Annotated[Path, typer.Option(help="Experiment config path.")] = ...,
    split: Annotated[
        str | None,
        typer.Option(help="Optional data split override, for example train, dev, or test."),
    ] = None,
) -> None:
    """Run retrieval for an experiment config."""
    from layoutpatch.retrieval import run_retrieval

    config_path = resolve_project_path(config)
    try:
        run_dir = run_retrieval(config_path, split_name=split)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("[yellow]If raw data is not ready, run the demo flow first:[/yellow]")
        console.print("[bold]uv run lp prepare --dataset demo[/bold]")
        console.print("[bold]uv run lp retrieve --config configs/experiments/demo_bm25_page.yaml[/bold]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Retrieval run written to:[/green] {run_dir}")


@app.command("evaluate")
def evaluate(
    run: Annotated[
        Path, typer.Option(help="Run directory, for example runs/retrieval/demo_bm25_page/latest.")
    ] = ...,
) -> None:
    """Evaluate a retrieval run."""
    from layoutpatch.evaluation import evaluate_run

    run_path = resolve_project_path(run)
    metrics = evaluate_run(run_path)
    table = Table(title="Evaluation Metrics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in metrics.items():
        table.add_row(key, f"{value:.4f}")
    console.print(table)


if __name__ == "__main__":
    app()
