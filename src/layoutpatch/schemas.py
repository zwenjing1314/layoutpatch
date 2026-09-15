"""Data schemas will be migrated from the old repository in Phase M2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def run_info(self) -> Path:
        return self.root / "run_info.json"

    @property
    def predictions(self) -> Path:
        return self.root / "predictions.parquet"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics.json"

    @property
    def summary(self) -> Path:
        return self.root / "summary.md"
