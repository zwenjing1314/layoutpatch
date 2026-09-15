"""Canonical path helpers derived from Settings. All IO goes through these."""

from __future__ import annotations

from pathlib import Path

from layoutpatch.config import Settings, get_settings


def project_root() -> Path:
    return Path.cwd()


def data_root(settings: Settings | None = None) -> Path:
    return _resolve(settings).data_root.resolve()


def processed_dir(settings: Settings | None = None) -> Path:
    return data_root(settings) / "processed"


def artifacts_dir(settings: Settings | None = None) -> Path:
    return _resolve(settings).artifact_root


def runs_dir(settings: Settings | None = None) -> Path:
    return _resolve(settings).runs_root


def resolve_project_path(value: str | Path, settings: Settings | None = None) -> Path:
    del settings
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root() / path


def _resolve(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()
