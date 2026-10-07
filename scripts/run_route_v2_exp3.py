"""EXP-016：九次从头训练完成后统一dev评分；只复用既有预测。"""
from __future__ import annotations

import contextlib
import json
import math
import statistics
import subprocess
import time
from datetime import datetime
from functools import partial

import polars as pl
import torch
import yaml
from run_route_v2_exp1 import (
    REPO,
    Inputs,
    check_inputs,
    evaluate,
    summarize,
    train_seed,
    write_json,
)
from verify_route_v2_exp2 import SHARED, check_predictions, verify

from layoutpatch.evaluation.localization import mcnemar_exact, question_macro
from layoutpatch.retrieval.route_v2_attribution import (
    VARIANTS,
    assert_all_selected,
    attribution_statistics,
    averaged_questions,
    make_variant,
)
from layoutpatch.retrieval.route_v2_exp1 import EarlyStopping, finite, select_units
from layoutpatch.retrieval.route_v2_layout import LayoutInputs
from layoutpatch.retrieval.route_v2_query_cache import file_sha256

CONFIG = REPO / "configs/experiments/route_v2_exp3_attribution.yaml"


def load_config():
    spec = yaml.safe_load(CONFIG.read_text("utf-8"))
    base_path = REPO / spec["base_config"]
    if file_sha256(base_path) != spec["base_config_sha256"]:
        raise ValueError("EXP-015 frozen config identity mismatch")
    base = yaml.safe_load(base_path.read_text("utf-8"))
    cfg = {**base, **spec}
    for key in SHARED:
        if cfg[key] != base[key]:
            raise ValueError(f"EXP-015 budget changed: {key}")
    if list(spec["variants"]) != list(VARIANTS) or cfg["seeds"] != [0, 1, 2] or cfg["max_epochs"] != 30:
        raise ValueError("variant/seed/epoch declaration mismatch")
    if cfg["maximum_training_runs"] != 9 or spec["comparisons"] != [f"D-{v}" for v in VARIANTS]:
        raise ValueError("training/comparison family changed")
    if cfg["status"] != "frozen" or cfg["bootstrap"]["iterations"] != 2000 or cfg["bootstrap"]["seed"] != 0:
        raise ValueError("configuration not frozen")
    expected_inputs = {"D-no-text": "text", "D-no-coord": "coords"}
    if spec["variants"]["C-wide"]["hidden"] != 1062:
        raise ValueError("C-wide hidden width changed")
    if any(spec["variants"][k]["zero_input"] != v for k, v in expected_inputs.items()):
        raise ValueError("ablation definition changed")
    multiple = cfg["multiple_comparisons"]
    if multiple["family_size"] != 3 or multiple["family_alpha"] != .05 or not math.isclose(multiple["individual_confidence"], 1 - .05 / 3):
        raise ValueError("multiple comparison definition changed")
    for name in VARIANTS:
        count = sum(p.numel() for p in make_variant(name).parameters() if p.requires_grad)
        if count != cfg["variants"][name]["trainable_parameters"]:
            raise ValueError("trainable parameter mismatch")
        if name == "C-wide" and abs(count / base["trainable_parameters"] - 1) > .01:
            raise ValueError("C-wide capacity mismatch")
    return cfg, base


def check_saved_methods(rows, dev, candidates, labels):
    expected = {"A", "B", *(f"{v}_seed_{s}" for v in labels for s in (0, 1, 2))}
    if {r["method"] for r in rows} != expected or len(rows) != len(expected) * len(dev):
        raise ValueError("saved method/row denominator mismatch")
    methods = {m: [r for r in rows if r["method"] == m] for m in expected}
    for label in labels:
        # 复用原候选/分母/排序/指标回验，只在临时副本中映射方法名。
        temporary = methods["A"] + methods["B"]
        temporary += [{**r, "method": f"C_seed_{s}"} for s in (0, 1, 2) for r in methods[f"{label}_seed_{s}"]]
        check_predictions(temporary, dev, candidates)
    return methods


def aggregate(methods, dev, cfg):
    summaries = {m: summarize(rows) for m, rows in methods.items()}
    means = {}
    for label in ("C", "D", *VARIANTS):
        means[label] = {}
        for subset in ("all", "M_ge_2"):
            first = summaries[f"{label}_seed_0"][subset]
            means[label][subset] = {"questions": first["questions"], "units": first["units"],
                "metrics": {k: statistics.mean(summaries[f"{label}_seed_{s}"][subset]["metrics"][k] for s in cfg["seeds"]) for k in first["metrics"]},
                "std": {k: statistics.stdev(summaries[f"{label}_seed_{s}"][subset]["metrics"][k] for s in cfg["seeds"]) for k in first["metrics"]}}
    reference = averaged_questions(methods, "D", cfg["seeds"])
    contrasts = {v: averaged_questions(methods, v, cfg["seeds"]) for v in VARIANTS}
    paired = attribution_statistics(reference, contrasts, {u["query_id"]: u["doc_id"] for u in dev})
    auxiliary = {f"D-{v}": {str(s): mcnemar_exact(
        {r["unit_id"]: r["hit1@0.5"] for r in methods[f"D_seed_{s}"]},
        {r["unit_id"]: r["hit1@0.5"] for r in methods[f"{v}_seed_{s}"]}) for s in cfg["seeds"]} for v in VARIANTS}
    return {"role": "source_dev", "methods": summaries, "seed_aggregates": means, "paired": paired,
            "multiple_comparisons": cfg["multiple_comparisons"], "mcnemar_each_seed": auxiliary,
            "mcnemar_note": "unit auxiliary ignores document dependence; not used for contribution decisions",
            "top5_D_minus_variant": {v: {k: means["D"]["all"]["metrics"][k] - means[v]["all"]["metrics"][k]
                                         for k in cfg["report_top5_differences"]} for v in VARIANTS},
            "claim": cfg["source_dev_claim"]}


def capture_identity(out):
    names = ["scripts/run_route_v2_exp3.py", "scripts/run_route_v2_exp1.py", "scripts/verify_route_v2_exp2.py",
             "src/layoutpatch/retrieval/route_v2_attribution.py", "src/layoutpatch/retrieval/route_v2_layout.py",
             "src/layoutpatch/retrieval/route_v2_exp1.py", "src/layoutpatch/retrieval/route_v2_scoring.py",
             "src/layoutpatch/retrieval/colpali_layout.py", "src/layoutpatch/retrieval/route_v2_query_cache.py",
             "src/layoutpatch/retrieval/fusion/sparse_fusion.py", "src/layoutpatch/layout/nodes.py",
             "src/layoutpatch/layout/correspondence.py", "src/layoutpatch/layout/schema.py",
             "src/layoutpatch/evaluation/localization.py", "src/layoutpatch/evaluation/region_metrics.py",
             "configs/experiments/route_v2_exp3_attribution.yaml", "configs/experiments/route_v2_exp2_D.yaml"]
    hashes = {}
    for name in names:
        source = REPO / name
        target = out / "code" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        hashes[name] = file_sha256(source)
    write_json(out / "code_identity.json", hashes)
    (out / "workspace.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=REPO))
    return {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "code_sha256": hashes, "workspace_patch_sha256": file_sha256(out / "workspace.patch")}


def verify_selections(out, selected):
    total_epochs = 0
    for variant, choices in selected.items():
        for seed, choice in choices.items():
            stopper = EarlyStopping(5)
            folder = out / variant
            for epoch in range(1, choice["epochs"] + 1):
                log = json.loads((folder / f"seed_{seed}_epoch_{epoch:02d}.json").read_text("utf-8"))
                improved, stop = stopper.observe(epoch, log["val_hit1@0.5"])
                if improved != log["improved"] or log["nonfinite"] or log["nonzero_updates"] != log["updates"]:
                    raise ValueError("training log verification failed")
                if max(log["peak_allocated_bytes"], log["peak_reserved_bytes"]) > 12 * 1024**3:
                    raise RuntimeError("saved VRAM exceeds budget")
                if stop and epoch != choice["epochs"]:
                    raise ValueError("training continued after early stop")
            if choice["epochs"] > 30 or (choice["epochs"] < 30 and not stop):
                raise ValueError("epoch budget/early stopping mismatch")
            if (stopper.best_epoch, stopper.best) != (choice["best_epoch"], choice["best_val"]):
                raise ValueError("selected checkpoint not val best")
            checkpoint = folder / choice["checkpoint"]
            if file_sha256(checkpoint) != choice["checkpoint_sha256"]:
                raise ValueError("checkpoint hash mismatch")
            payload = torch.load(checkpoint, weights_only=True, map_location="cpu")
            if (payload["seed"], payload["epoch"], payload["val_score"]) != (seed, stopper.best_epoch, stopper.best):
                raise ValueError("checkpoint payload mismatch")
            total_epochs += choice["epochs"]
    return total_epochs


def main():
    # 输出位置只由新配置决定；配置校验失败也保留失败回执。
    spec = yaml.safe_load(CONFIG.read_text("utf-8"))
    out = REPO / spec["output"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    info = {"status": "started", "external_test_opened": False, "source_dev_evaluation_started": False}
    try:
        print(f"run_dir: {out}", flush=True)
        cfg, base_cfg = load_config()
        write_json(out / "config.json", cfg)
        info.update(capture_identity(out))
        reference = REPO / cfg["reference_run"]
        old_info = json.loads((reference / "run_info.json").read_text("utf-8"))
        old_cfg = json.loads((reference / "config.json").read_text("utf-8"))
        if old_info["status"] != "completed" or old_cfg != base_cfg or old_info["config_sha256"] != cfg["base_config_sha256"]:
            raise ValueError("reference D run/config mismatch")
        receipts = [json.loads((reference / name).read_text("utf-8")) for name in ("input_verification.json", "D_input_verification.json")]
        for receipt in receipts:
            check_inputs(receipt)
        preflight = verify(REPO, base_cfg)
        receipts.append(preflight)
        write_json(out / "input_verification.json", preflight)
        info["reference_sha256"] = {name: file_sha256(reference / name) for name in
                                    ("config.json", "run_info.json", "metrics.json", "predictions.parquet", "checkpoint_selection.json")}
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        base = Inputs(cfg)
        data = LayoutInputs(base, REPO / cfg["node_cache_train_val"], cfg["node_manifest_sha256"])
        dev_data = LayoutInputs(base, REPO / cfg["node_cache_dev"], cfg["dev_node_manifest_sha256"])
        dev = select_units(base.units, "source_dev")
        candidates = {key: {c["layout_id"]: c for c in rows} for key, rows in base.candidates.items()}
        prior = pl.read_parquet(reference / "predictions.parquet").to_dicts()
        methods = check_saved_methods(prior, dev, candidates, ("C", "D"))
        prior_metrics = json.loads((reference / "metrics.json").read_text("utf-8"))
        if any(summarize(rows) != prior_metrics["methods"][name] for name, rows in methods.items()):
            raise ValueError("reference saved summaries mismatch")
        for role, loader, training in (("source_train", data, True), ("source_val", data, False), ("source_dev", dev_data, False)):
            for unit in select_units(base.units, role, training=training):
                item = loader.item(unit)
                finite(item["query"], "cached query")
                for tensor in item["layout"].values():
                    finite(tensor, "cached layout")
        print("preflight passed; 9 fresh training runs; source_dev scoring blocked until all selections", flush=True)
        selected = {}
        for name in VARIANTS:
            folder = out / name
            folder.mkdir()
            selected[name] = {}
            loader = base if name == "C-wide" else data
            for seed in cfg["seeds"]:
                with (folder / f"seed_{seed}_stdout.log").open("x", encoding="utf-8") as log, contextlib.redirect_stdout(log):
                    selected[name][seed] = train_seed(loader, cfg, seed, folder, module_factory=partial(make_variant, name), method_name=name)
                print(f"training completed: {name} seed={seed} epochs={selected[name][seed]['epochs']} best={selected[name][seed]['best_epoch']}", flush=True)
        assert_all_selected(selected, cfg["seeds"])
        epochs = verify_selections(out, selected)
        write_json(out / "checkpoint_selection.json", selected)
        write_json(out / "source_dev_started.json", {"time": datetime.now().isoformat(), "selected": selected})
        info["source_dev_evaluation_started"] = True
        efficiency = {}
        for name in VARIANTS:
            for seed in cfg["seeds"]:
                choice = selected[name][seed]
                module = make_variant(name).to(cfg["device"])
                payload = torch.load(out / name / choice["checkpoint"], weights_only=True, map_location="cpu")
                module.load_state_dict(payload["state_dict"])
                t = time.perf_counter()
                method = f"{name}_seed_{seed}"
                methods[method] = evaluate(base if name == "C-wide" else dev_data, dev, method, module, cfg["device"], full=True)
                efficiency[method] = {"scoring_seconds": time.perf_counter() - t, "trainable_parameters": sum(p.numel() for p in module.parameters()), **choice}
                del module, payload
        rows = [row for name in sorted(methods) for row in methods[name]]
        pl.DataFrame(rows).write_parquet(out / "predictions.parquet")
        qrows = [{"method": name, "query_id": q, "hit1@0.5": value} for name in sorted(methods)
                 for q, value in question_macro(methods[name], "hit1@0.5").items()]
        pl.DataFrame(qrows).write_parquet(out / "question_scores.parquet")
        metrics = aggregate(methods, dev, cfg)
        metrics.update({"selections": selected, "efficiency": efficiency})
        write_json(out / "metrics.json", metrics)
        saved = check_saved_methods(pl.read_parquet(out / "predictions.parquet").to_dicts(), dev, candidates, ("C", "D", *VARIANTS))
        if any(saved[name] != methods[name] for name in methods):
            raise ValueError("saved predictions changed")
        if aggregate(saved, dev, cfg) != {k: v for k, v in metrics.items() if k not in {"selections", "efficiency"}}:
            raise ValueError("saved statistics mismatch")
        if pl.read_parquet(out / "question_scores.parquet").to_dicts() != qrows:
            raise ValueError("saved question scores mismatch")
        if any(saved[name] != [r for r in prior if r["method"] == name] for name in prior_metrics["methods"]):
            raise ValueError("ABCD predictions changed")
        for receipt in receipts:
            check_inputs(receipt)
        for name, digest in info["reference_sha256"].items():
            if file_sha256(reference / name) != digest:
                raise ValueError("reference artifact changed")
        for name, digest in info["code_sha256"].items():
            if file_sha256(REPO / name) != digest:
                raise ValueError("code/config changed during run")
        write_json(out / "result_verification.json", {"passed": True, "predictions": len(rows), "question_rows": len(qrows),
                   "training_runs": 9, "epochs": epochs, "ABCD_predictions_unchanged": True,
                   "checkpoint_selection_verified": True, "paired_statistics_verified": True, "source_dev_model_passes": 1})
        lines = ["# EXP-016", "", "仅开发归因证据；三项同时解释，不证明外部泛化或新颖性。", "",
                 "|方法|主指标均值|样本标准差|Cov@5|gold召回@5|", "|---|---:|---:|---:|---:|"]
        for name, value in metrics["seed_aggregates"].items():
            m, sd = value["all"]["metrics"], value["all"]["std"]
            lines.append(f"|{name}|{m['hit1@0.5']:.10f}|{sd['hit1@0.5']:.10f}|{m['cov@5']:.10f}|{m['gold_recall@5@0.5']:.10f}|")
        lines += ["", "三项配对统计原文：", "", json.dumps(metrics["paired"], ensure_ascii=False, indent=2)]
        (out / "summary.md").write_text("\n".join(lines) + "\n", "utf-8")
        info.update({"status": "completed", "torch": str(torch.__version__), "cuda": torch.version.cuda,
                     "gpu": torch.cuda.get_device_name(), "training_runs": 9, "epochs": epochs})
        print("saved result verification passed; ABCD unchanged; all three comparisons retained", flush=True)
        print("\n".join(lines[4:11]), flush=True)
        for name, stat in metrics["paired"].items():
            print(f"{name}: delta={stat['mean_diff']:.10f}; CI95=[{stat['ci95_low']:.10f},{stat['ci95_high']:.10f}]; Bonferroni=[{stat['bonferroni_ci_low']:.10f},{stat['bonferroni_ci_high']:.10f}]", flush=True)
    except Exception as exc:
        info.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "run_info.json", info)
        print(f"status={info['status']}; seconds={info['elapsed_seconds']:.1f}; run_dir={out}", flush=True)


if __name__ == "__main__":
    main()
