"""lp command line entry (typer).

Status: scaffold. Subcommands register here as migration phases land:
M1 prepare, M2 retrieve, M3 evaluate. Keep each command thin; logic goes
into the corresponding package module.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="LayoutPatch experiment CLI.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the package version."""
    from layoutpatch import __version__

    typer.echo(f"layoutpatch {__version__}")


if __name__ == "__main__":
    app()
