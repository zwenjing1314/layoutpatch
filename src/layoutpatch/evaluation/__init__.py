"""Page and region metrics (M3: metrics + pipeline land; IoU metrics land in M4)."""

from __future__ import annotations

from layoutpatch.evaluation import region_labels as region_labels_module
from layoutpatch.evaluation.metrics import evaluate_metrics
from layoutpatch.evaluation.pipeline import evaluate_run
from layoutpatch.evaluation.region_labels import RegionLabel, labels_by_query

__all__ = ["RegionLabel", "evaluate_metrics", "evaluate_run", "labels_by_query", "region_labels_module"]
