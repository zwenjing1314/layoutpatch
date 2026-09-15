"""Import and CLI smoke tests. These must pass without GPU, data, or network."""

from __future__ import annotations

from typer.testing import CliRunner

from layoutpatch import __version__
from layoutpatch.cli import app

runner = CliRunner()


class TestPackage:
    def test_version_is_semver_like(self) -> None:
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestCli:
    def test_version_command(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert "Usage" in result.output
