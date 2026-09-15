"""Canonical path helpers derived from Settings. All IO goes through these."""

from __future__ import annotations

from pathlib import Path

from layoutpatch.config import Settings, get_settings


def processed_dir(settings: Settings | None = None) -> Path:
    return _resolve(settings).data_root / "processed"


def artifacts_dir(settings: Settings | None = None) -> Path:
    return _resolve(settings).artifact_root


def runs_dir(settings: Settings | None = None) -> Path:
    return _resolve(settings).runs_root


def _resolve(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()
