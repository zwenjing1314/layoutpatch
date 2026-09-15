"""Shared fixtures.

Adopted from the colpali-official-repro conventions:
- markers (`slow`, `gpu`) declared in pyproject; gpu tests auto-skip when the
  extra/torch or a CUDA device is unavailable, so bare `pytest` stays green;
- session-scoped fixtures for expensive resources;
- no network in unit tests (fail loudly instead of silently downloading).
"""

from __future__ import annotations

import pytest


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip gpu-marked tests instead of erroring when torch/CUDA is missing."""
    if _cuda_available():
        return
    skip_gpu = pytest.mark.skip(reason="requires the colpali extra and a CUDA device")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly instead of silently downloading models/datasets in tests."""
    import socket

    def _blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is forbidden in unit tests; use local fixtures")

    monkeypatch.setattr(socket, "create_connection", _blocked)
