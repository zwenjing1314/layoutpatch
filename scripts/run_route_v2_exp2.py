"""EXP-015正式入口（本轮不执行）；复用EXP-014训练/评分，基线只读已存预测。"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime

import polars as pl
import torch
import yaml
from run_route_v2_exp1 import (
    REPO,
    Inputs,
    capture_code,
    check_inputs,
    evaluate,
    summarize,
    train_seed,
    write_json,
)

from layoutpatch.evaluation.localization import doc_bootstrap_diff, mcnemar_exact, question_macro
from layoutpatch.retrieval.route_v2_exp1 import assert_dev_ready, select_units
from layoutpatch.retrieval.route_v2_layout import LayoutInputs, LayoutPatchD
from layoutpatch.retrieval.route_v2_query_cache import file_sha256


def main():
    config_path = REPO / "configs/experiments/route_v2_exp2_D.yaml"
    cfg = yaml.safe_load(config_path.read_text("utf-8"))
    out = REPO / cfg["output"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    info = {"status": "started", "external_test_opened": False}
    try:
        print(f"run_dir: {out}", flush=True)
        write_json(out / "config.json", cfg)
        info.update(capture_code(out))
        baseline = REPO / cfg["baseline_run"]
        receipt = json.loads((baseline / "input_verification.json").read_text("utf-8"))
        check_inputs(receipt)
        write_json(out / "input_verification.json", receipt)
        preflight = json.loads((REPO / cfg["preflight"]).read_text("utf-8"))
        if not preflight["passed"] or cfg["status"] != "frozen":
            raise ValueError("preflight/config not frozen")
        info["preflight_sha256"] = file_sha256(REPO / cfg["preflight"])
        check_inputs(preflight)
        write_json(out / "D_input_verification.json", preflight)
        # 缺dev节点时在训练前停止，不能用train/val节点或全零文本替代。
        dev_manifest = REPO / cfg["node_cache_dev"] / "manifest.json"
        if not dev_manifest.exists():
            raise FileNotFoundError("EXP-015 requires separately authorized source_dev node cache before formal execution")
        dm = json.loads(dev_manifest.read_text("utf-8"))
        tm = json.loads((REPO / cfg["node_cache_train_val"] / "manifest.json").read_text("utf-8"))
        if dm["encoding"] != tm["encoding"] or dm["identity"] != tm["identity"] or any(r["role"] != "source_dev" for r in dm["pages"]):
            raise ValueError("development node cache identity/rule mismatch")
        info["dev_node_manifest_sha256"] = file_sha256(dev_manifest)
        info["baseline_predictions_sha256"] = file_sha256(baseline / "predictions.parquet")
        info["config_sha256"] = file_sha256(config_path)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        base = Inputs(cfg)
        data = LayoutInputs(base, REPO / cfg["node_cache_train_val"], cfg["node_manifest_sha256"])
        dev_data = LayoutInputs(base, REPO / cfg["node_cache_dev"], info["dev_node_manifest_sha256"])
        dev = select_units(base.units, "source_dev")
        # 在参数更新前验证所有需要的缓存和页面签名，dev不调用评分。
        for role, loader, training in (("source_train", data, True), ("source_val", data, False), ("source_dev", dev_data, False)):
            for unit in select_units(base.units, role, training=training):
                loader.item(unit)
        selected = {s: train_seed(data, cfg, s, out, module_factory=LayoutPatchD, method_name="D") for s in cfg["seeds"]}
        assert_dev_ready(selected, cfg["seeds"])
        for choice in selected.values():
            if file_sha256(out / choice["checkpoint"]) != choice["checkpoint_sha256"]:
                raise ValueError("D checkpoint identity mismatch")
        write_json(out / "checkpoint_selection.json", selected)
        write_json(out / "source_dev_started.json", {"selected": selected, "time": datetime.now().isoformat()})
        prior = pl.read_parquet(baseline / "predictions.parquet").to_dicts()
        expected_ids = {u["unit_id"] for u in dev}
        methods = {m: [r for r in prior if r["method"] == m] for m in ("A", "B", "C_seed_0", "C_seed_1", "C_seed_2")}
        for rows in methods.values():
            if {r["unit_id"] for r in rows} != expected_ids or len(rows) != len(dev):
                raise ValueError("baseline unit denominator mismatch")
        efficiency = {}
        for s in cfg["seeds"]:
            payload = torch.load(out / selected[s]["checkpoint"], map_location="cpu", weights_only=True)
            module = LayoutPatchD().to(cfg["device"])
            module.load_state_dict(payload["state_dict"])
            t = time.perf_counter()
            methods[f"D_seed_{s}"] = evaluate(dev_data, dev, f"D_seed_{s}", module, cfg["device"], full=True)
            efficiency[str(s)] = {"scoring_seconds": time.perf_counter() - t,
                                  "parameters": sum(p.numel() for p in module.parameters()),
                                  "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                                  "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
            print(json.dumps({"seed": s, "dev_scoring_completed": True, "seconds": efficiency[str(s)]["scoring_seconds"]}), flush=True)
        all_rows = [r for rows in methods.values() for r in rows]
        pl.DataFrame(all_rows).write_parquet(out / "predictions.parquet")
        question_rows = [{"method": method, "query_id": q, "hit1@0.5": score}
                         for method, rows in methods.items() for q, score in question_macro(rows, "hit1@0.5").items()]
        pl.DataFrame(question_rows).write_parquet(out / "question_scores.parquet")
        summaries = {m: summarize(rows) for m, rows in methods.items()}
        keys = summaries["D_seed_0"]["all"]["metrics"]
        means = {}
        for label in ("C", "D"):
            means[label] = {}
            for subset in ("all", "M_ge_2"):
                means[label][subset] = {"questions": summaries[f"{label}_seed_0"][subset]["questions"],
                                        "units": summaries[f"{label}_seed_0"][subset]["units"],
                                        "metrics": {k: statistics.mean(summaries[f"{label}_seed_{s}"][subset]["metrics"][k] for s in cfg["seeds"]) for k in keys},
                                        "std": {k: statistics.stdev(summaries[f"{label}_seed_{s}"][subset]["metrics"][k] for s in cfg["seeds"]) for k in keys}}
        def averaged(label):
            qs = [question_macro(methods[f"{label}_seed_{s}"], "hit1@0.5") for s in cfg["seeds"]]
            return {q: statistics.mean(v[q] for v in qs) for q in qs[0]}
        d, c = averaged("D"), averaged("C")
        docs = {u["query_id"]: u["doc_id"] for u in dev}
        paired = {f"D-{m}": doc_bootstrap_diff(d, values, docs, iterations=2000, seed=0)
                  for m, values in (("C", c), ("A", question_macro(methods["A"], "hit1@0.5")), ("B", question_macro(methods["B"], "hit1@0.5")))}
        auxiliary = {str(s): mcnemar_exact({r["unit_id"]: r["hit1@0.5"] for r in methods[f"D_seed_{s}"]},
                                         {r["unit_id"]: r["hit1@0.5"] for r in methods[f"C_seed_{s}"]}) for s in cfg["seeds"]}
        metrics = {"role": "source_dev", "methods": summaries, "seed_aggregates": means, "paired": paired,
                   "advance": paired["D-C"]["mean_diff"] >= .01 and paired["D-C"]["ci95_low"] > 0,
                   "top5_D_minus_C": {k: means["D"]["all"]["metrics"][k] - means["C"]["all"]["metrics"][k] for k in cfg["report_top5_differences"]},
                   "mcnemar_each_seed_D_C": auxiliary, "mcnemar_note": "unit auxiliary ignores document dependence",
                   "seeds": selected, "efficiency": efficiency, "text_encoding_receipt": tm["run_info"]}
        write_json(out / "metrics.json", metrics)
        (out / "summary.md").write_text("# EXP-015\n\n仅新的开发比较，不是独立测试或新颖性证明。\n\n" + json.dumps({"paired": paired, "top5_D_minus_C": metrics["top5_D_minus_C"]}, ensure_ascii=False, indent=2), "utf-8")
        check_inputs(receipt)
        check_inputs(preflight)
        if file_sha256(config_path) != info["config_sha256"]:
            raise ValueError("config changed")
        info["status"] = "completed"
        info["seeds"] = selected
        info["torch"] = str(torch.__version__)
        info["cuda"] = torch.version.cuda
        info["gpu"] = torch.cuda.get_device_name()
        info["trainable_parameters"] = {"D": 273410, "C": 66176}
    except Exception as exc:
        info["status"] = "failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - start
        write_json(out / "run_info.json", info)
        print(json.dumps({"run_dir": str(out), "status": info["status"], "elapsed_seconds": info["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
