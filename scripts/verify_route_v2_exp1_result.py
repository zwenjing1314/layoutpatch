"""只读复核EXP-014已保存预测、早停选择和统计，不执行模型评分。"""
import json
from pathlib import Path

import polars as pl
import torch

from layoutpatch.evaluation.localization import question_macro
from layoutpatch.retrieval.route_v2_exp1 import EarlyStopping, paired_statistics
from layoutpatch.retrieval.route_v2_query_cache import file_sha256

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "runs/retrieval/route_v2_exp1/20261006_162042"


def read(name):
    return json.loads((RUN / name).read_text("utf-8"))


def main():
    config, metrics, info = read("config.json"), read("metrics.json"), read("run_info.json")
    assert info["status"] == "completed"
    assert file_sha256(REPO / "configs/experiments/route_v2_exp1.yaml") == info["config_sha256"]
    curves = [json.loads(line) for line in (RUN / "training_curves.jsonl").read_text("utf-8").splitlines()]
    for s in metrics["seeds"]:
        logs = [r for r in curves if r["seed"] == s["seed"]]
        stopper = EarlyStopping(5)
        for log in logs:
            improved, stop = stopper.observe(log["epoch"], log["val_hit1@0.5"])
            assert improved == log["improved"]
            assert log["updates"] == 251 and log["nonfinite"] == 0
            assert log["nonzero_updates"] == 251
            if stop:
                assert log is logs[-1]
        assert stopper.best_epoch == s["best_epoch"] and stopper.best == s["best_val"]
        assert len(logs) == s["epochs"] and (stopper.stale == 5 or len(logs) == 30)
        assert file_sha256(RUN / s["checkpoint"]) == s["checkpoint_sha256"]
        payload = torch.load(RUN / s["checkpoint"], map_location="cpu", weights_only=True)
        assert payload["epoch"] == s["best_epoch"] and payload["seed"] == s["seed"]
        assert all(bool(torch.isfinite(v).all()) for v in payload["state_dict"].values())
        assert (RUN / s["checkpoint"]).stat().st_mtime_ns < (RUN / "source_dev_started.json").stat().st_mtime_ns
    rows = pl.read_parquet(RUN / "predictions.parquet").to_dicts()
    grouped = {m: [r for r in rows if r["method"] == m] for m in ("A", "B", "C_seed_0", "C_seed_1", "C_seed_2")}
    reference = {r["unit_id"]: set(r["ranked_layout_ids"]) for r in grouped["B"]}
    for method, values in grouped.items():
        assert len(values) == len(reference) == 545
        assert {r["unit_id"]: set(r["ranked_layout_ids"]) for r in values} == reference
        assert all(r["role"] == "source_dev" for r in values)
        q = question_macro(values, "hit1@0.5")
        assert len(q) == 412
        actual = sum(q.values()) / len(q)
        assert abs(actual - metrics["methods"][method]["all"]["metrics"]["hit1@0.5"]) < 1e-12
    expected = paired_statistics([question_macro(grouped[f"C_seed_{s}"], "hit1@0.5") for s in config["seeds"]],
                                 question_macro(grouped["B"], "hit1@0.5"), question_macro(grouped["A"], "hit1@0.5"),
                                 {r["query_id"]: r["doc_id"] for r in grouped["B"]})
    assert expected == metrics["paired"]
    print(json.dumps({"passed": True, "run_dir": str(RUN), "prediction_rows": len(rows),
                      "questions_per_method": 412, "units_per_method": 545, "epoch_logs": len(curves),
                      "paired_statistics_match": True, "checkpoint_selection_match": True,
                      "source_dev_not_rescored": True}, indent=2))


if __name__ == "__main__":
    main()
