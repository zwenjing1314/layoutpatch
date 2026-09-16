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

__all__ = [
    "CorrespondenceResult",
    "correspondence_row",
    "patch_bbox",
    "row_normalize",
    "scale_bbox_to_model",
    "stack_correspondence",
]
