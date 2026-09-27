"""Phase 2-R training entry. Not a license to start a formal run.

Frozen design A: three feature groups, K=4 train-only, early stop 2 rounds,
batch 32. Evaluation calls the existing official recall_layout. This script
refuses to start if train patch-score or box-text caches are missing, and
refuses to read test_eval scores or build y(c).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRAIN_FIT = REPO / "experiments" / "s2_splits" / "train_fit_ids.jsonl"
TRAIN_DEV = REPO / "experiments" / "s2_splits" / "train_dev_ids.jsonl"
DEV_EVAL = REPO / "experiments" / "s2_splits" / "dev_eval_ids.jsonl"
TEST_EVAL = REPO / "experiments" / "s2_splits" / "test_eval_ids.jsonl"

PATCH_CACHE = REPO / "artifacts" / "colpali" / "mmdocir_train"
TEXT_CACHE = REPO / "artifacts" / "bge_m3" / "mmdocir_train_boxes"


def missing_before_train() -> list[str]:
    missing = []
    if not PATCH_CACHE.exists():
        missing.append("train ColPali patch-score cache")
    if not TEXT_CACHE.exists():
        missing.append("train box-text bge-m3 cache")
    return missing


def assert_no_test_eval(path: Path) -> None:
    if path.resolve() == TEST_EVAL.resolve():
        raise RuntimeError("test_eval scores are forbidden")


def assert_no_coverage_label(row: dict) -> None:
    if "y_c" in row or "coverage" in row:
        raise RuntimeError("y(c) labels are forbidden")


def main() -> int:
    missing = missing_before_train()
    if missing:
        print(json.dumps({"status": "stopped", "missing": missing}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "caches_present", "train_fit": str(TRAIN_FIT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
