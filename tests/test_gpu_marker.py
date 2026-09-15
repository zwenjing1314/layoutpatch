"""Marker registration sanity: gpu tests skip cleanly without CUDA.

Mirrors the colpali-official-repro convention of one focused test per
infrastructural concern, so CI failures point at the mechanism directly.
"""

from __future__ import annotations

import pytest
import torch


@pytest.mark.gpu
def test_gpu_marker_skips_without_cuda() -> None:
    assert torch.cuda.is_available()
