"""Verified token layout of cached ColPali page embeddings (route-v2).

PaliGemmaProcessor builds ``<image>*1024 <bos> <bos> Describe the image . \\n``, so a
cached ``[1031, 128]`` page tensor is image-first: rows 0..1023 are the 32x32 patches
in row-major order and rows 1024..1030 are the fixed prompt tokens. Historical code
(``propagation.patch_scores_from_vectors``, phase-2 scripts) sliced ``[7:]`` under a
prefix-first assumption; that shifts every patch index by seven. Route-v2 code must use
this module. Evidence: ``scripts/audit_route_v2_coordinates.py``.
"""

from __future__ import annotations

import torch

from layoutpatch.layout.correspondence import GRID

NUM_PATCHES = GRID * GRID
NUM_PROMPT_TOKENS = 7
PAGE_TOKENS = NUM_PATCHES + NUM_PROMPT_TOKENS
TOKEN_LAYOUT = "image-first: rows[0:1024]=row-major 32x32 patches, rows[1024:1031]=prompt"


def split_page_embedding(embedding: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Return ``(patches [1024, D], prompt [7, D])`` from one cached page tensor."""
    if embedding.ndim != 2 or embedding.shape[0] != PAGE_TOKENS:
        raise ValueError(f"expected [{PAGE_TOKENS}, D] page embedding, got {tuple(embedding.shape)}")
    return embedding[:NUM_PATCHES], embedding[NUM_PATCHES:]


def patch_index(row: int, col: int) -> int:
    """Row-major index of the patch at grid row/column (0-based)."""
    if not (0 <= row < GRID and 0 <= col < GRID):
        raise ValueError(f"patch ({row}, {col}) outside {GRID}x{GRID} grid")
    return row * GRID + col
