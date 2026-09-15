"""Pydantic-settings based configuration (single source for env overrides)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAYOUTPATCH_", env_file=".env", extra="ignore")

    data_root: Path = Path("./data")
    artifact_root: Path = Path("./artifacts")
    runs_root: Path = Path("./runs")


def get_settings() -> Settings:
    return Settings()
