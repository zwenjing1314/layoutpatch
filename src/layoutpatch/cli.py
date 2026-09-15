"""lp command line entry (typer).

Status: scaffold. Subcommands register here as migration phases land:
M2 prepare, M3 retrieve, M4 evaluate. Keep each command thin; logic goes
into the corresponding package module.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

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


if __name__ == "__main__":
    app()
