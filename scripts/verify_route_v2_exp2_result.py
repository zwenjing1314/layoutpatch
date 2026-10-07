"""只读EXP-015保存结果回验，不执行模型前向或重新训练。"""
import json
import math
import statistics
from pathlib import Path

import polars as pl
import torch

from layoutpatch.evaluation.localization import doc_bootstrap_diff, question_macro
from layoutpatch.retrieval.route_v2_exp1 import EarlyStopping
from layoutpatch.retrieval.route_v2_query_cache import file_sha256

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "runs/retrieval/route_v2_exp2_D/20261006_230924"


def read(name):
    return json.loads((RUN / name).read_text("utf-8"))


def main():
    cfg, info, metrics = read("config.json"), read("run_info.json"), read("metrics.json")
    assert info["status"] == "completed"
    assert file_sha256(REPO / "configs/experiments/route_v2_exp2_D.yaml") == info["config_sha256"]
    rows = pl.read_parquet(RUN / "predictions.parquet").to_dicts()
    prior = pl.read_parquet(REPO / cfg["baseline_predictions"]).to_dicts()
    copied = [r for r in rows if not r["method"].startswith("D_")]
    assert sorted(copied, key=lambda r: (r["method"], r["unit_id"])) == sorted(prior, key=lambda r: (r["method"], r["unit_id"]))
    groups = {m: [r for r in rows if r["method"] == m] for m in {r["method"] for r in rows}}
    expected = {r["unit_id"]: (r["query_id"], r["doc_id"], set(r["ranked_layout_ids"])) for r in groups["B"]}
    for rs in groups.values():
        assert len(rs) == 545 and len({r["query_id"] for r in rs}) == 412
        assert {r["unit_id"]: (r["query_id"], r["doc_id"], set(r["ranked_layout_ids"])) for r in rs} == expected
    logs = [json.loads(line) for line in (RUN / "training_curves.jsonl").read_text("utf-8").splitlines()]
    for seed in cfg["seeds"]:
        choice = metrics["seeds"][str(seed)]
        stopper = EarlyStopping(5)
        subset = [r for r in logs if r["seed"] == seed]
        for i, r in enumerate(subset):
            improved, stop = stopper.observe(r["epoch"], r["val_hit1@0.5"])
            assert improved == r["improved"] and r["best_epoch"] == stopper.best_epoch
            assert r["nonfinite"] == 0 and r["updates"] == 251 and r["nonzero_updates"] == 251
            assert all(math.isfinite(r[k]) for k in ("gate_mean", "residual_mlp_l2_mean", "gradient_norm_max"))
            if stop:
                assert i == len(subset) - 1
        assert len(subset) == choice["epochs"] and choice["best_epoch"] == stopper.best_epoch
        assert stopper.stale == 5 or len(subset) == 30
        p = RUN / choice["checkpoint"]
        assert file_sha256(p) == choice["checkpoint_sha256"]
        assert p.stat().st_mtime_ns < (RUN / "source_dev_started.json").stat().st_mtime_ns
        state = torch.load(p, weights_only=True, map_location="cpu")["state_dict"]
        assert all(bool(torch.isfinite(v).all()) for v in state.values())
    def mean_query(label):
        qs = [question_macro(groups[f"{label}_seed_{s}"], "hit1@0.5") for s in cfg["seeds"]]
        return {q: statistics.mean(x[q] for x in qs) for q in qs[0]}
    d = mean_query("D")
    docs = {r["query_id"]: r["doc_id"] for r in groups["B"]}
    for label, scores in (("C", mean_query("C")), ("A", question_macro(groups["A"], "hit1@0.5")), ("B", question_macro(groups["B"], "hit1@0.5"))):
        assert doc_bootstrap_diff(d, scores, docs, iterations=2000, seed=0) == metrics["paired"][f"D-{label}"]
    print(json.dumps({"passed": True, "run_dir": str(RUN), "prediction_rows": len(rows),
                      "question_rows": pl.read_parquet(RUN / "question_scores.parquet").height,
                      "epoch_logs": len(logs), "ABC_predictions_unchanged": True,
                      "checkpoint_selection_verified": True, "paired_statistics_verified": True,
                      "advance": metrics["advance"]}, indent=2))


if __name__ == "__main__":
    main()
