"""EXP-014：冻结 A/B/C 正式比较，仅一次 source_dev 评测阶段。"""
from __future__ import annotations

import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["HF_HUB_OFFLINE"] = "1"

import polars as pl  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402

from layoutpatch.evaluation.localization import (  # noqa: E402
    mcnemar_exact,
    question_macro,
    rank_candidates,
    unit_metrics,
)
from layoutpatch.evaluation.region_metrics import bbox_iou  # noqa: E402
from layoutpatch.retrieval.colpali import _source_signature  # noqa: E402
from layoutpatch.retrieval.colpali_layout import split_page_embedding  # noqa: E402
from layoutpatch.retrieval.route_v2_exp1 import (  # noqa: E402
    EarlyStopping,
    assert_dev_ready,
    finite,
    macro_summary,
    memory_guard,
    paired_statistics,
    select_units,
    train_epoch,
)
from layoutpatch.retrieval.route_v2_query_cache import file_sha256  # noqa: E402
from layoutpatch.retrieval.route_v2_scoring import (  # noqa: E402
    PatchAdapter,
    area_scores,
    patch_iou_matrix,
    patch_scores,
    region_scores,
)

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "configs/experiments/route_v2_exp1.yaml"


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def capture_code(out):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=REPO)
    (out / "workspace.patch").write_bytes(diff)
    paths = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO).decode().split("\0")
    hashes = {}
    for name in sorted(set(paths) - {""}):
        path = REPO / name
        if path.is_file():
            hashes[name] = file_sha256(path)
            # 保存实际执行代码（包含本轮未提交文件），无需加载或运行其他脚本。
            if name.startswith(("src/", "scripts/")) and path.suffix == ".py":
                target = out / "code" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
    write_json(out / "workspace_files.json", hashes)
    return {"commit": commit, "workspace_patch_sha256": file_sha256(out / "workspace.patch"),
            "workspace_files_sha256": file_sha256(out / "workspace_files.json")}


def check_inputs(receipt):
    if not receipt["passed"]:
        raise ValueError("verification receipt failed")
    for name, expected in receipt["input_sha256"].items():
        if file_sha256(REPO / name) != expected:
            raise ValueError(f"input hash mismatch: {name}")


class Inputs:
    def __init__(self, config):
        self.config = config
        root = REPO / config["regions"]
        self.units = pl.read_parquet(root / "units.parquet").to_dicts()
        self.queries = torch.load(REPO / config["query_cache"], map_location="cpu", weights_only=True)["embeddings"]
        self.candidates = {}
        for c in pl.read_parquet(root / "candidates.parquet").to_dicts():
            self.candidates.setdefault((c["doc_id"], c["page"]), []).append(c)
        self.pages = {}
        self.geometry = {}
        self.page_paths = {r["page_id"]: Path(r["page_image_path"]) for r in pl.read_parquet(
            REPO / "data/processed/mmdocir_evaluation/pages.parquet", columns=["page_id", "page_image_path"]).to_dicts()}

    def item(self, u):
        pid = u["page_cache_id"]
        if pid not in self.pages:
            payload = torch.load(REPO / self.config["page_cache"] / f"{pid}.pt", map_location="cpu", weights_only=True)
            if payload["source_signature"] != _source_signature(self.page_paths[pid], "vidore/colpali"):
                raise ValueError(f"page signature mismatch: {pid}")
            p, _ = split_page_embedding(payload["embedding"].float())
            finite(p, "cached patches")
            self.pages[pid] = p
        pos, ignore = torch.zeros(1024, dtype=torch.bool), torch.zeros(1024, dtype=torch.bool)
        pos[u["patch_pos_idx"]] = True
        ignore[u["patch_ignore_idx"]] = True
        return {"query": self.queries[u["query_id"]].float(), "patches": self.pages[pid], "pos": pos, "neg": ~(pos | ignore)}

    def boxes(self, u):
        c = self.candidates.get((u["doc_id"], u["page"]), [])
        return [r["bbox"] for r in c], [r["layout_id"] for r in c]

    def iou(self, u):
        key = (u["doc_id"], u["page"], tuple(u["page_size"]))
        if key not in self.geometry:
            self.geometry[key] = patch_iou_matrix(self.boxes(u)[0], u["page_size"])
        return self.geometry[key]


def score_unit(data, u, method, module, device):
    boxes, ids = data.boxes(u)
    if method == "A":
        scores = torch.tensor(area_scores(boxes), dtype=torch.float32)
    else:
        item = data.item(u)
        patches = item["patches"].to(device)
        if module is not None:
            layout = {k: v.to(device) for k, v in item["layout"].items()} if "layout" in item else None
            patches = module(patches, layout) if layout is not None else module(patches)
        scores_patch = patch_scores(item["query"].to(device), patches)
        finite(scores_patch, "evaluation patch scores")
        scores = region_scores(scores_patch, data.iou(u).to(device)).cpu()
    # 既有空覆盖候选的 -inf 是排序哨兵，不是数值运算异常。
    allowed = data.iou(u).sum(-1) == 0
    if bool(torch.isnan(scores).any()) or bool(torch.isposinf(scores).any()) or bool((torch.isneginf(scores) & ~allowed).any()):
        raise FloatingPointError(f"invalid candidate scores: {u['unit_id']}")
    ranked = rank_candidates(scores.tolist(), ids)
    return ranked, scores, boxes, ids


def evaluate(data, units, method, module, device, *, full):
    rows = []
    if module is not None:
        module.eval()
    with torch.no_grad():
        for u in units:
            order, scores, boxes, ids = score_unit(data, u, method, module, device)
            ranked_boxes = [boxes[i] for i in order]
            if full:
                metrics = unit_metrics(ranked_boxes, u["gold_boxes"], u["page_size"])
            else:
                metrics = {"hit1@0.5": float(bool(order) and max(bbox_iou(ranked_boxes[0], g) for g in u["gold_boxes"]) >= 0.5)}
            if not all(math.isfinite(v) for v in metrics.values()):
                raise FloatingPointError("nonfinite evaluation metrics")
            rows.append({"query_id": u["query_id"], "doc_id": u["doc_id"], "unit_id": u["unit_id"],
                         "role": u["role"], "method": method, "candidate_count": len(boxes),
                         "page_overlap_excluded": u["page_overlap_excluded"],
                         "ranked_layout_ids": [ids[i] for i in order],
                         "ranked_scores": [float(scores[i]) if torch.isfinite(scores[i]) else None for i in order],
                         **metrics})
            memory_guard(device, 12)
    return rows


def summarize(rows):
    metadata = {"query_id", "doc_id", "unit_id", "role", "method", "candidate_count", "page_overlap_excluded", "ranked_layout_ids", "ranked_scores"}
    keys = [k for k in rows[0] if k not in metadata]
    out = {"all": macro_summary(rows, keys),
           "M_ge_2": macro_summary([r for r in rows if r["candidate_count"] >= 2], keys),
           "empty_units": sum(r["candidate_count"] == 0 for r in rows),
           "page_overlap_excluded_eval_units": sum(r["page_overlap_excluded"] for r in rows)}
    out["area_quantiles_unit"] = {}
    for key in ("top1_area_frac", "top1_to_gold_area"):
        quantiles = torch.tensor([r[key] for r in rows], dtype=torch.float64).quantile(torch.tensor([0, .05, .25, .5, .75, .95, 1], dtype=torch.float64)).tolist()
        out["area_quantiles_unit"][key] = dict(zip(["min", "p05", "p25", "p50", "p75", "p95", "max"], quantiles, strict=True))
    return out


def train_seed(data, config, seed, out, *, module_factory=None, method_name="C"):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    module = (module_factory() if module_factory is not None else PatchAdapter(hidden=config["hidden"])).to(config["device"])
    train = select_units(data.units, "source_train", training=True)
    val = select_units(data.units, "source_val")
    items = [data.item(u) for u in train]
    # 每个seed独立检查全体train/val的初始C与B评分；不访问dev评分。
    max_difference = 0.0
    with torch.no_grad():
        for u in train + val:
            _, b, _, _ = score_unit(data, u, "B", None, config["device"])
            _, c, _, _ = score_unit(data, u, "C", module, config["device"])
            valid = torch.isfinite(b)
            if not torch.equal(valid, torch.isfinite(c)) or not torch.allclose(b[valid], c[valid], atol=config["zero_init_score_atol"], rtol=0):
                raise ValueError("zero-initialized C differs from B")
            if bool(valid.any()):
                max_difference = max(max_difference, float((b[valid] - c[valid]).abs().max()))
    write_json(out / f"seed_{seed}_initial_equivalence.json", {"passed": True, "units": len(train) + len(val), "max_abs_difference": max_difference})
    opt = config["optimizer"]
    optimizer = torch.optim.AdamW(module.parameters(), lr=opt["lr"], weight_decay=opt["weight_decay"], betas=tuple(opt["betas"]), eps=opt["eps"])
    stopper = EarlyStopping(config["early_stopping"]["patience"])
    torch.cuda.reset_peak_memory_stats()
    started, training_seconds = time.perf_counter(), 0.0
    best_path = None
    for epoch in range(1, config["max_epochs"] + 1):
        torch.cuda.synchronize()
        t = time.perf_counter()
        log = train_epoch(module, optimizer, items, rng, batch_units=config["units_per_update"], tau=config["tau"], clip=config["clip_max_norm"], device=config["device"], budget_gib=config["vram_budget_gib"])
        torch.cuda.synchronize()
        log["training_seconds"] = time.perf_counter() - t
        training_seconds += log["training_seconds"]
        t = time.perf_counter()
        val_rows = evaluate(data, val, method_name, module, config["device"], full=False)
        score = statistics.mean(question_macro(val_rows, "hit1@0.5").values())
        improved, stop = stopper.observe(epoch, score)
        if improved:
            best_path = out / f"seed_{seed}_epoch_{epoch:02d}.pt"
            torch.save({"seed": seed, "epoch": epoch, "val_score": score,
                        "state_dict": {k: v.detach().cpu() for k, v in module.state_dict().items()}}, best_path)
        log.update({"seed": seed, "epoch": epoch, "val_hit1@0.5": score, "val_seconds": time.perf_counter() - t,
                    "improved": improved, "stale": stopper.stale, "best_epoch": stopper.best_epoch,
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()})
        write_json(out / f"seed_{seed}_epoch_{epoch:02d}.json", log)
        with (out / "training_curves.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log) + "\n")
        print(json.dumps(log), flush=True)
        if stop:
            break
    result = {"seed": seed, "epochs": epoch, "best_epoch": stopper.best_epoch, "best_val": stopper.best,
              "checkpoint": str(best_path.relative_to(out)), "checkpoint_sha256": file_sha256(best_path),
              "training_seconds": training_seconds, "train_val_seconds": time.perf_counter() - started,
              "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
    write_json(out / f"seed_{seed}_selection.json", result)
    return result


def main():
    started = time.perf_counter()
    config = yaml.safe_load(CONFIG.read_text("utf-8"))
    out = REPO / config["output"] / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    print(f"run_dir: {out}", flush=True)
    info = {"status": "started", "external_test_opened": False, "source_dev_evaluation_started": False}
    try:
        write_json(out / "config.json", config)
        info.update(capture_code(out))
        info["config_sha256"] = file_sha256(CONFIG)
        info["verification_sha256"] = file_sha256(REPO / config["verification"])
        receipt = json.loads((REPO / config["verification"]).read_text("utf-8"))
        write_json(out / "input_verification.json", receipt)
        check_inputs(receipt)
        if not torch.cuda.is_available():
            raise RuntimeError("required CUDA device unavailable")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        info.update({"python": sys.version, "torch": str(torch.__version__), "cuda": torch.version.cuda,
                     "gpu": torch.cuda.get_device_name(), "seeds": {}, "deterministic_algorithms": True,
                     "tf32": False, "roles": receipt["roles"]})
        data = Inputs(config)
        selected = {}
        for seed in config["seeds"]:
            selected[seed] = train_seed(data, config, seed, out)
            info["seeds"][str(seed)] = selected[seed]
        assert_dev_ready(selected, config["seeds"])
        for value in selected.values():
            if file_sha256(out / value["checkpoint"]) != value["checkpoint_sha256"]:
                raise ValueError("selected checkpoint identity mismatch")
        write_json(out / "checkpoint_selection.json", selected)
        # dev访问标记只能创建一次，全部checkpoint确定后才评分。
        write_json(out / "source_dev_started.json", {"started": datetime.now().isoformat(), "selected": selected})
        info["source_dev_evaluation_started"] = True
        dev = select_units(data.units, "source_dev")
        predictions, summaries, by_method = [], {}, {}
        evaluation_seconds = {}
        for method in ["A", "B", *[f"C_seed_{s}" for s in config["seeds"]]]:
            module = None
            if method.startswith("C_"):
                seed = int(method.rsplit("_", 1)[1])
                checkpoint = torch.load(out / selected[seed]["checkpoint"], weights_only=True, map_location="cpu")
                module = PatchAdapter(hidden=config["hidden"]).to(config["device"])
                module.load_state_dict(checkpoint["state_dict"])
            t = time.perf_counter()
            rows = evaluate(data, dev, method, module, config["device"], full=True)
            evaluation_seconds[method] = time.perf_counter() - t
            predictions.extend(rows)
            by_method[method] = rows
            summaries[method] = summarize(rows)
            print(json.dumps({"method": method, "dev_hit1@0.5": summaries[method]["all"]["metrics"]["hit1@0.5"], "seconds": evaluation_seconds[method]}), flush=True)
        pl.DataFrame(predictions).write_parquet(out / "predictions.parquet")
        question_rows = []
        for method, rows in by_method.items():
            for q, score in question_macro(rows, "hit1@0.5").items():
                question_rows.append({"method": method, "query_id": q, "hit1@0.5": score})
        pl.DataFrame(question_rows).write_parquet(out / "question_scores.parquet")
        doc_of = {u["query_id"]: u["doc_id"] for u in dev}
        stats = paired_statistics([question_macro(by_method[f"C_seed_{s}"], "hit1@0.5") for s in config["seeds"]],
                                  question_macro(by_method["B"], "hit1@0.5"), question_macro(by_method["A"], "hit1@0.5"), doc_of,
                                  iterations=config["bootstrap"]["iterations"], seed=config["bootstrap"]["seed"])
        mcnemar = {str(s): mcnemar_exact({r["unit_id"]: r["hit1@0.5"] for r in by_method[f"C_seed_{s}"]},
                                       {r["unit_id"]: r["hit1@0.5"] for r in by_method["B"]}) for s in config["seeds"]}
        c_mean = {}
        for subset in ("all", "M_ge_2"):
            keys = summaries["C_seed_0"][subset]["metrics"]
            c_mean[subset] = {"questions": summaries["C_seed_0"][subset]["questions"], "units": summaries["C_seed_0"][subset]["units"],
                              "metrics": {k: statistics.mean(summaries[f"C_seed_{s}"][subset]["metrics"][k] for s in config["seeds"]) for k in keys},
                              "std": {k: statistics.stdev(summaries[f"C_seed_{s}"][subset]["metrics"][k] for s in config["seeds"]) for k in keys}}
        summaries["C_mean"] = c_mean
        metrics = {"schema": "route-v2-exp1-v1", "role": "source_dev", "methods": summaries, "paired": stats,
                   "mcnemar_each_seed_vs_B": mcnemar, "mcnemar_limitation": "unit-level auxiliary; ignores within-document dependence",
                   "seeds": list(selected.values()), "evaluation_seconds": evaluation_seconds,
                   "conclusion": "达到本轮推进标准" if stats["advance"] else "未达到本轮推进标准"}
        write_json(out / "metrics.json", metrics)
        # 结束时再核验输入与配置未变化，不更新任何源产物。
        check_inputs(receipt)
        if file_sha256(CONFIG) != info["config_sha256"]:
            raise ValueError("frozen config changed during execution")
        info["status"] = "completed"
        lines = ["# EXP-014 route-v2-exp1", "", "仅source_dev开发结果；未运行外部测试，未验证D创新或页级保持。", "", metrics["conclusion"], "", "|方法|Top-1 IoU Hit@0.5|", "|---|---|"]
        for method, summary in summaries.items():
            lines.append(f"|{method}|{summary['all']['metrics']['hit1@0.5']:.10f}|")
        lines += ["", f"C−B: {stats['C_minus_B']}", f"C−A: {stats['C_minus_A']}", "", "source_val原始375题中news_combined占137题；不重划分。", "完整主辅指标、随机期望、Oracle、M≥2和面积分位数见metrics.json。"]
        (out / "summary.md").write_text("\n".join(lines) + "\n", "utf-8")
    except Exception as exc:
        info["status"] = "failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "run_info.json", info)
        print(json.dumps({"run_dir": str(out), "status": info["status"], "elapsed_seconds": info["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
