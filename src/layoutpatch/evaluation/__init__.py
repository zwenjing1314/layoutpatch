"""Page and region metrics (M2.5: region_labels export; full metrics land in M3)."""

from __future__ import annotations

from layoutpatch.evaluation import region_labels as region_labels_module
from layoutpatch.evaluation.region_labels import RegionLabel, labels_by_query

__all__ = ["RegionLabel", "labels_by_query", "region_labels_module"]
