"""Layout package: patch-region correspondence (M4, PAPER_SPEC sections 5.3/6)."""

from __future__ import annotations

from layoutpatch.layout.correspondence import (
    CorrespondenceResult,
    correspondence_row,
    patch_bbox,
    row_normalize,
    scale_bbox_to_model,
    stack_correspondence,
)
from layoutpatch.layout.nodes import COORD_DIM, UNK_TYPE_ID, D, TextLayoutEncoder

__all__ = [
    "COORD_DIM",
    "CorrespondenceResult",
    "D",
    "TextLayoutEncoder",
    "UNK_TYPE_ID",
    "correspondence_row",
    "patch_bbox",
    "row_normalize",
    "scale_bbox_to_model",
    "stack_correspondence",
]
