"""EXP-018：唯一 E 三 seed 训练与一次事后外部补充比较。"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import polars as pl  # noqa: E402
import run_route_v2_external as external_runner  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402
from run_route_v2_exp1 import REPO, Inputs, summarize  # noqa: E402

from layoutpatch.evaluation.external_localization import (  # noqa: E402
    aggregate_seed_summaries,
    averaged_question_scores,
    compute_analytical_results,
    summarize_rows,
    validate_prediction_metrics,
)
from layoutpatch.evaluation.localization import (  # noqa: E402
    doc_bootstrap_diff,
    question_macro,
    rank_candidates,
    unit_metrics,
)
from layoutpatch.evaluation.region_metrics import bbox_iou  # noqa: E402
from layoutpatch.retrieval.route_v2_candidate import (  # noqa: E402
    EXPECTED_PARAMETERS,
    CandidateRankerE,
    candidate_supervision,
    frozen_candidate_features,
    multi_positive_candidate_loss,
    trainable_parameter_count,
    training_filter_audit,
)
from layoutpatch.retrieval.route_v2_exp1 import (  # noqa: E402
    EarlyStopping,
    finite,
    memory_guard,
    select_units,
)
from layoutpatch.retrieval.route_v2_layout import LayoutInputs  # noqa: E402
from layoutpatch.retrieval.route_v2_query_cache import file_sha256  # noqa: E402
from layoutpatch.retrieval.route_v2_scoring import (  # noqa: E402
    patch_scores,
    region_scores,
)

CONFIG = REPO / "configs/experiments/route_v2_E_supplement_v1.yaml"
TRAIN_CODE = (
    "scripts/run_route_v2_E_supplement.py",
    "src/layoutpatch/retrieval/route_v2_candidate.py",
    "src/layoutpatch/retrieval/route_v2_scoring.py",
    "src/layoutpatch/retrieval/route_v2_exp1.py",
    "src/layoutpatch/retrieval/route_v2_layout.py",
    "src/layoutpatch/layout/nodes.py",
    "src/layoutpatch/evaluation/localization.py",
    "configs/experiments/route_v2_E_supplement_v1.yaml",
)
EXTERNAL_CODE = TRAIN_CODE + (
    "scripts/run_route_v2_external.py",
    "src/layoutpatch/evaluation/external_localization.py",
)


def write_json(path: Path, value: object, *, exclusive: bool = True) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load_config() -> tuple[dict, dict]:
    spec = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if (
        spec.get("experiment_id") != "EXP-018"
        or spec.get("status") != "frozen"
        or spec.get("method") != "E"
    ):
        raise ValueError("EXP-018 E config is not frozen")
    base_path = REPO / spec["base_config"]
    if file_sha256(base_path) != spec["base_config_sha256"]:
        raise ValueError("frozen D config identity mismatch")
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    shared = (
        "seeds",
        "max_epochs",
        "optimizer",
        "units_per_update",
        "clip_max_norm",
        "device",
        "dtype",
        "mixed_precision",
        "scheduler",
        "tf32",
        "deterministic_algorithms",
        "vram_budget_gib",
    )
    for key in shared:
        if spec[key] != base[key]:
            raise ValueError(f"E changed frozen D budget: {key}")
    if spec["loss"]["tau"] != base["tau"] or spec["early_stopping"] != base["early_stopping"]:
        raise ValueError("E changed frozen D loss temperature or early stopping")
    architecture = spec["architecture"]
    module = CandidateRankerE()
    if (
        architecture["trainable_parameters"] != EXPECTED_PARAMETERS
        or trainable_parameter_count(module) != EXPECTED_PARAMETERS
        or architecture["mlp"] != "Linear_384_680_GELU_Linear_680_1"
    ):
        raise ValueError("E architecture or parameter count changed")
    if spec["seeds"] != [0, 1, 2] or spec["max_epochs"] != 30:
        raise ValueError("E seed or epoch budget changed")
    if spec["evaluation"]["source_dev"] != "forbidden_not_needed_this_round":
        raise ValueError("source_dev must remain closed")
    if spec["additional_variants"] != "forbidden":
        raise ValueError("a second E variant is forbidden")
    external = spec["external"]
    source_files = {
        external["source_config"]: external["source_config_sha256"],
        f"{external['source_run']}/predictions.parquet": external[
            "source_predictions_sha256"
        ],
        f"{external['source_run']}/metrics.json": external["source_metrics_sha256"],
        f"{external['source_run']}/run_info.json": external[
            "source_run_info_sha256"
        ],
        f"{external['source_run']}/result_verification.json": external[
            "source_verification_sha256"
        ],
    }
    for name, digest in source_files.items():
        if file_sha256(REPO / name) != digest:
            raise ValueError(f"frozen external source changed: {name}")
    return {**base, **spec}, spec


def capture_identity(out: Path, names: tuple[str, ...]) -> dict:
    hashes = {}
    for name in names:
        source = REPO / name
        target = out / "code" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        hashes[name] = file_sha256(source)
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", *names],
        cwd=REPO,
        capture_output=True,
        check=False,
    ).stdout
    (out / "workspace.patch").write_bytes(diff)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    write_json(out / "code_identity.json", hashes)
    return {
        "git_commit": commit or "unknown",
        "code_sha256": hashes,
        "workspace_patch_sha256": file_sha256(out / "workspace.patch"),
    }


def prepared_item(data, unit: dict) -> dict:
    item = data.item(unit)
    boxes, layout_ids = data.boxes(unit)
    if layout_ids != sorted(layout_ids) or len(set(layout_ids)) != len(layout_ids):
        raise ValueError(f"candidate IDs are not stable and unique: {unit['unit_id']}")
    layout = item["layout"]
    if layout["mask"].shape != (len(boxes),) or not bool(layout["mask"].all()):
        raise ValueError("stored candidates must be real nodes; padding is only an interface rule")
    features = frozen_candidate_features(
        item["query"], item["patches"], layout["W_raw"], layout["mask"]
    )
    patch = patch_scores(item["query"], item["patches"])
    finite(patch, "frozen B patch score")
    score_b = region_scores(patch, data.iou(unit))
    allowed = ~features["nonempty_w"]
    if (
        bool(torch.isnan(score_b).any())
        or bool(torch.isposinf(score_b).any())
        or bool((torch.isneginf(score_b) & ~allowed).any())
    ):
        raise FloatingPointError(f"invalid frozen B score: {unit['unit_id']}")
    positive, negative = candidate_supervision(boxes, unit["gold_boxes"])
    active = features["nonempty_w"] & features["candidate_mask"]
    return {
        "unit": unit,
        "boxes": boxes,
        "layout_ids": layout_ids,
        "x": features["x"],
        "visual": features["visual"],
        "coords": layout["coords"].float(),
        "types": layout["types"].long(),
        "candidate_mask": features["candidate_mask"],
        "nonempty_w": features["nonempty_w"],
        "score_b": score_b.detach(),
        "positive": positive & active,
        "negative": negative & active,
    }


def move_item(item: dict, device: str) -> dict[str, torch.Tensor]:
    keys = (
        "x",
        "visual",
        "coords",
        "types",
        "candidate_mask",
        "nonempty_w",
        "score_b",
        "positive",
        "negative",
    )
    return {key: item[key].to(device) for key in keys}


def e_scores(module: CandidateRankerE, item: dict, device: str) -> torch.Tensor:
    value = move_item(item, device)
    return module(
        value["x"],
        value["visual"],
        value["coords"],
        value["types"],
        value["candidate_mask"],
        value["nonempty_w"],
        value["score_b"],
    )


def evaluate_items(
    module: CandidateRankerE,
    items: list[dict],
    method: str,
    device: str,
    *,
    full: bool,
) -> list[dict]:
    module.eval()
    rows = []
    with torch.no_grad():
        for item in items:
            scores = e_scores(module, item, device).cpu()
            unit = item["unit"]
            order = rank_candidates(scores.tolist(), item["layout_ids"])
            ranked_boxes = [item["boxes"][index] for index in order]
            if full:
                metrics = unit_metrics(ranked_boxes, unit["gold_boxes"], unit["page_size"])
            else:
                hit = bool(order) and max(
                    bbox_iou(ranked_boxes[0], gold)
                    for gold in unit["gold_boxes"]
                ) >= 0.5
                metrics = {"hit1@0.5": float(hit)}
            if not all(math.isfinite(value) for value in metrics.values()):
                raise FloatingPointError("nonfinite E evaluation metric")
            rows.append(
                {
                    "query_id": unit["query_id"],
                    "doc_id": unit["doc_id"],
                    "unit_id": unit["unit_id"],
                    "role": unit["role"],
                    "method": method,
                    "candidate_count": len(item["boxes"]),
                    "page_overlap_excluded": unit["page_overlap_excluded"],
                    "ranked_layout_ids": [item["layout_ids"][index] for index in order],
                    "ranked_scores": [
                        float(scores[index]) if torch.isfinite(scores[index]) else None
                        for index in order
                    ],
                    **metrics,
                }
            )
            memory_guard(device, 12)
    return rows


def train_epoch_e(
    module: CandidateRankerE,
    optimizer: torch.optim.Optimizer,
    items: list[dict],
    rng: random.Random,
    cfg: dict,
) -> dict:
    order = list(range(len(items)))
    rng.shuffle(order)
    module.train()
    losses: list[float] = []
    norms: list[float] = []
    corrections: list[float] = []
    updates = 0
    batch_units = cfg["units_per_update"]
    for start in range(0, len(order), batch_units):
        group = order[start : start + batch_units]
        optimizer.zero_grad(set_to_none=True)
        for index in group:
            item = items[index]
            value = move_item(item, cfg["device"])
            scores = module(
                value["x"],
                value["visual"],
                value["coords"],
                value["types"],
                value["candidate_mask"],
                value["nonempty_w"],
                value["score_b"],
            )
            loss = multi_positive_candidate_loss(
                scores,
                value["positive"],
                value["negative"],
                tau=cfg["loss"]["tau"],
            )
            finite(loss, "E candidate loss")
            (loss / len(group)).backward()
            losses.append(float(loss.detach()))
            active = value["positive"] | value["negative"]
            corrections.append(float((scores[active] - value["score_b"][active]).abs().mean()))
            memory_guard(cfg["device"], cfg["vram_budget_gib"])
        for parameter in module.parameters():
            if parameter.grad is not None:
                finite(parameter.grad, "E gradient before update")
        norm = torch.nn.utils.clip_grad_norm_(
            module.parameters(), cfg["clip_max_norm"], error_if_nonfinite=True
        )
        finite(norm, "E gradient norm")
        norms.append(float(norm))
        optimizer.step()
        updates += 1
        for parameter in module.parameters():
            finite(parameter, "E parameter after update")
        for state in optimizer.state.values():
            for value in state.values():
                if isinstance(value, torch.Tensor):
                    finite(value, "E optimizer state")
        memory_guard(cfg["device"], cfg["vram_budget_gib"])
    return {
        "loss": statistics.mean(losses),
        "updates": updates,
        "gradient_norm_min": min(norms),
        "gradient_norm_max": max(norms),
        "nonzero_updates": sum(value > 0 for value in norms),
        "mean_abs_score_correction": statistics.mean(corrections),
        "nonfinite": 0,
    }


def zero_equivalence(
    module: CandidateRankerE,
    items: list[dict],
    device: str,
    atol: float,
) -> dict:
    maximum = 0.0
    module.eval()
    with torch.no_grad():
        for item in items:
            actual = e_scores(module, item, device).cpu()
            expected = torch.where(
                item["candidate_mask"],
                item["score_b"],
                torch.full_like(item["score_b"], -math.inf),
            )
            valid = torch.isfinite(expected)
            if not torch.equal(torch.isfinite(actual), valid):
                raise ValueError("zero-initialized E/B finite masks differ")
            if bool(valid.any()):
                difference = float((actual[valid] - expected[valid]).abs().max())
                maximum = max(maximum, difference)
                if difference > atol:
                    raise ValueError("zero-initialized E candidate scores differ from B")
            if rank_candidates(actual.tolist(), item["layout_ids"]) != rank_candidates(
                expected.tolist(), item["layout_ids"]
            ):
                raise ValueError("zero-initialized E ranking differs from B")
    return {
        "passed": True,
        "units": len(items),
        "max_abs_difference": maximum,
        "scores_equal": True,
        "rankings_equal": True,
    }


def train_seed(
    cfg: dict,
    seed: int,
    train: list[dict],
    val: list[dict],
    equivalence_items: list[dict],
    out: Path,
) -> dict:
    torch.manual_seed(seed)
    rng = random.Random(seed)
    module = CandidateRankerE().to(cfg["device"])
    receipt = zero_equivalence(
        module, equivalence_items, cfg["device"], cfg["zero_init_score_atol"]
    )
    write_json(out / f"seed_{seed}_initial_equivalence.json", receipt)
    settings = cfg["optimizer"]
    optimizer = torch.optim.AdamW(
        module.parameters(),
        lr=settings["lr"],
        weight_decay=settings["weight_decay"],
        betas=tuple(settings["betas"]),
        eps=settings["eps"],
    )
    stopper = EarlyStopping(cfg["early_stopping"]["patience"])
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    training_seconds = 0.0
    val_seconds = 0.0
    best_path = None
    for epoch in range(1, cfg["max_epochs"] + 1):
        torch.cuda.synchronize()
        epoch_started = time.perf_counter()
        log = train_epoch_e(module, optimizer, train, rng, cfg)
        torch.cuda.synchronize()
        log["training_seconds"] = time.perf_counter() - epoch_started
        training_seconds += log["training_seconds"]
        val_started = time.perf_counter()
        val_rows = evaluate_items(
            module, val, f"E_seed_{seed}", cfg["device"], full=False
        )
        score = statistics.mean(question_macro(val_rows, "hit1@0.5").values())
        current_val_seconds = time.perf_counter() - val_started
        val_seconds += current_val_seconds
        improved, stop = stopper.observe(epoch, score)
        if improved:
            best_path = out / f"seed_{seed}_epoch_{epoch:02d}.pt"
            torch.save(
                {
                    "seed": seed,
                    "epoch": epoch,
                    "val_score": score,
                    "state_dict": {
                        name: value.detach().cpu()
                        for name, value in module.state_dict().items()
                    },
                },
                best_path,
            )
        log.update(
            {
                "seed": seed,
                "epoch": epoch,
                "val_hit1@0.5": score,
                "val_seconds": current_val_seconds,
                "improved": improved,
                "stale": stopper.stale,
                "best_epoch": stopper.best_epoch,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            }
        )
        write_json(out / f"seed_{seed}_epoch_{epoch:02d}.json", log)
        with (out / "training_curves.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(log, allow_nan=False) + "\n")
        print(json.dumps(log), flush=True)
        if stop:
            break
    if best_path is None:
        raise RuntimeError("source_val did not select an E checkpoint")
    result = {
        "seed": seed,
        "epochs": epoch,
        "best_epoch": stopper.best_epoch,
        "best_val": stopper.best,
        "selection_role": "source_val",
        "checkpoint": str(best_path.relative_to(out)),
        "checkpoint_sha256": file_sha256(best_path),
        "training_seconds": training_seconds,
        "source_val_seconds": val_seconds,
        "train_val_seconds": time.perf_counter() - started,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
    }
    write_json(out / f"seed_{seed}_selection.json", result)
    return result


def prepare_training_inputs(cfg: dict) -> tuple[list[dict], list[dict], dict, dict]:
    base = Inputs(cfg)
    data = LayoutInputs(
        base,
        REPO / cfg["node_cache_train_val"],
        cfg["node_manifest_sha256"],
    )
    d_units = select_units(base.units, "source_train", training=True)
    val_units = select_units(base.units, "source_val")
    if (
        len(d_units) != cfg["supervision"]["expected_original_D_training_units"]
        or len(val_units) != cfg["evaluation"]["source_val_expected_units"]
        or len({unit["query_id"] for unit in val_units})
        != cfg["evaluation"]["source_val_expected_questions"]
    ):
        raise ValueError("frozen D train or source_val denominator changed")
    prepared_train = [prepared_item(data, unit) for unit in d_units]
    prepared_val = [prepared_item(data, unit) for unit in val_units]
    boxes = {item["unit"]["unit_id"]: item["boxes"] for item in prepared_train}
    nonempty = {
        item["unit"]["unit_id"]: item["nonempty_w"] for item in prepared_train
    }
    selected_ids, audit = training_filter_audit(base.units, boxes, nonempty)
    by_id = {item["unit"]["unit_id"]: item for item in prepared_train}
    selected = [by_id[unit_id] for unit_id in selected_ids]
    if not selected:
        raise ValueError("E has no trainable units")
    identity = {
        "split_proof": file_sha256(REPO / cfg["split"] / "split_proof.json"),
        "regions_units": file_sha256(REPO / cfg["regions"] / "units.parquet"),
        "regions_candidates": file_sha256(REPO / cfg["regions"] / "candidates.parquet"),
        "query_cache": file_sha256(REPO / cfg["query_cache"]),
        "node_manifest": file_sha256(
            REPO / cfg["node_cache_train_val"] / "manifest.json"
        ),
        "consumed_layout_fields": ["coords", "types", "mask", "W_raw"],
        "forbidden_layout_fields": ["text"],
        "source_dev_opened": False,
        "external_labels_opened": False,
    }
    return selected, prepared_val, audit, identity


def verify_training_selections(run: Path, selections: dict, cfg: dict) -> int:
    if set(map(int, selections)) != set(cfg["seeds"]):
        raise ValueError("three E selections required")
    epochs = 0
    for raw_seed, choice in selections.items():
        seed = int(raw_seed)
        stopper = EarlyStopping(cfg["early_stopping"]["patience"])
        stopped = False
        for epoch in range(1, choice["epochs"] + 1):
            log = json.loads(
                (run / "weights" / f"seed_{seed}_epoch_{epoch:02d}.json").read_text(
                    encoding="utf-8"
                )
            )
            improved, stopped = stopper.observe(epoch, log["val_hit1@0.5"])
            if (
                improved != log["improved"]
                or log["nonfinite"]
                or log["nonzero_updates"] != log["updates"]
            ):
                raise ValueError("saved E training log failed verification")
            if max(log["peak_allocated_bytes"], log["peak_reserved_bytes"]) > (
                cfg["vram_budget_gib"] * 1024**3
            ):
                raise RuntimeError("saved E VRAM exceeds budget")
            if stopped and epoch != choice["epochs"]:
                raise ValueError("E training continued after early stop")
        if choice["epochs"] > cfg["max_epochs"] or (
            choice["epochs"] < cfg["max_epochs"] and not stopped
        ):
            raise ValueError("E epoch budget or early stopping mismatch")
        if (stopper.best_epoch, stopper.best) != (
            choice["best_epoch"],
            choice["best_val"],
        ):
            raise ValueError("selected E checkpoint is not source_val best")
        checkpoint = run / "weights" / choice["checkpoint"]
        if file_sha256(checkpoint) != choice["checkpoint_sha256"]:
            raise ValueError("E checkpoint hash mismatch")
        payload = torch.load(checkpoint, weights_only=True, map_location="cpu")
        if (payload["seed"], payload["epoch"], payload["val_score"]) != (
            seed,
            stopper.best_epoch,
            stopper.best,
        ):
            raise ValueError("E checkpoint payload mismatch")
        epochs += choice["epochs"]
    return epochs


def find_run(root: Path, spec: dict, *, completed_only: bool) -> Path | None:
    if not root.is_dir():
        return None
    completed = []
    blocked = []
    for run in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        try:
            saved = json.loads((run / "config.json").read_text(encoding="utf-8"))
            info = json.loads((run / "run_info.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if saved != spec:
            continue
        if info.get("status") == "completed":
            completed.append(run)
        else:
            blocked.append(run)
    if len(completed) > 1:
        raise ValueError("multiple completed runs exist for the same frozen E config")
    if not completed and blocked and completed_only:
        raise RuntimeError("prior E run is incomplete/failed; automatic retry is forbidden")
    return completed[0] if completed else None


def matching_incomplete_runs(root: Path, spec: dict) -> list[Path]:
    """Return same-config runs that did not reach completed status."""
    if not root.is_dir():
        return []
    matches = []
    for run in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        try:
            saved = json.loads((run / "config.json").read_text(encoding="utf-8"))
            info = json.loads((run / "run_info.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if saved == spec and info.get("status") != "completed":
            matches.append(run)
    return matches


def expected_gbk_minus_failure(error: object) -> bool:
    """Accept only the known Windows console failure after saved-result verification."""
    if not isinstance(error, str):
        return False
    prefix = "UnicodeEncodeError: 'gbk' codec can't encode character '\\u2212' in position "
    suffix = ": illegal multibyte sequence"
    if not error.startswith(prefix) or not error.endswith(suffix):
        return False
    position = error[len(prefix) : -len(suffix)]
    return position.isdigit()


def recover_verified_external_run(root: Path, cfg: dict, spec: dict) -> Path | None:
    """Publish a verified console-print failure without loading weights or rescoring."""
    incomplete = matching_incomplete_runs(root, spec)
    if not incomplete:
        return None
    if len(incomplete) != 1:
        raise RuntimeError("external recovery requires exactly one incomplete matching run")
    failed = incomplete[0]
    failure = json.loads((failed / "failure.json").read_text(encoding="utf-8"))
    failed_info = json.loads((failed / "run_info.json").read_text(encoding="utf-8"))
    if (
        failure.get("status") != "failed"
        or failed_info.get("status") != "failed"
        or failure.get("error") != failed_info.get("error")
        or not expected_gbk_minus_failure(failure.get("error"))
    ):
        raise RuntimeError("incomplete external run is not the approved GBK minus failure")
    saved_verification = json.loads(
        (failed / "result_verification.json").read_text(encoding="utf-8")
    )
    if (
        saved_verification.get("passed") is not True
        or saved_verification.get("model_scoring_reexecuted") is not False
    ):
        raise RuntimeError("failed external run lacks a passed saved-result verification")
    ext_cfg = external_runner.load_config()
    recomputed = verify_external_saved(failed, cfg, ext_cfg)
    for key, value in recomputed.items():
        if key != "seconds" and saved_verification.get(key) != value:
            raise ValueError(f"failed external verification receipt changed: {key}")

    out = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    completed_info = dict(failed_info)
    completed_info.pop("error", None)
    try:
        copied_files = (
            "config.json",
            "metrics.json",
            "predictions.parquet",
            "question_scores.parquet",
            "preflight.json",
            "code_identity.json",
            "workspace.patch",
        )
        source_hashes = {}
        for name in copied_files:
            source = failed / name
            source_hashes[name] = file_sha256(source)
            shutil.copy2(source, out / name)
        shutil.copytree(failed / "code", out / "code")
        summary = (failed / "summary.md").read_text(encoding="utf-8")
        (out / "summary.md").write_text(summary.replace("−", "-"), encoding="utf-8")
        verification = verify_external_saved(out, cfg, ext_cfg)
        verification.update(
            {
                "recovered_from_verified_console_failure": str(
                    failed.relative_to(REPO)
                ).replace("\\", "/"),
                "failed_result_verification_passed": True,
                "checkpoint_loaded_during_recovery": False,
                "model_scoring_reexecuted": False,
            }
        )
        write_json(out / "result_verification.json", verification)
        recovery = {
            "status": "completed",
            "accepted_error": failure["error"],
            "source_run": str(failed.relative_to(REPO)).replace("\\", "/"),
            "source_artifact_sha256": source_hashes,
            "saved_statistics_recomputed": True,
            "checkpoint_loaded": False,
            "model_scoring_reexecuted": False,
            "recovery_code_sha256": file_sha256(Path(__file__)),
        }
        write_json(out / "recovery.json", recovery)
        recovery_seconds = time.perf_counter() - started
        completed_info.update(
            {
                "status": "completed",
                "recovered_from": recovery["source_run"],
                "recovery_reason": "verified_post_save_gbk_console_minus_failure",
                "checkpoint_loaded_during_recovery": False,
                "model_scoring_reexecuted": False,
                "original_failed_elapsed_seconds": failed_info.get("elapsed_seconds"),
                "recovery_seconds": recovery_seconds,
                "elapsed_seconds": (failed_info.get("elapsed_seconds") or 0)
                + recovery_seconds,
                "result_verification": verification,
            }
        )
        write_json(out / "run_info.json", completed_info)
        print(
            json.dumps(
                {
                    "status": "recovered",
                    "run_dir": str(out),
                    "source_run": str(failed),
                    "model_scoring_reexecuted": False,
                    "checkpoint_loaded": False,
                    "predictions": verification["predictions"],
                    "question_rows": verification["question_rows"],
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        return out
    except Exception as exc:
        completed_info.update(
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "checkpoint_loaded_during_recovery": False,
                "model_scoring_reexecuted": False,
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
        write_json(out / "failure.json", completed_info)
        write_json(out / "run_info.json", completed_info)
        raise


def run_training() -> Path:
    cfg, spec = load_config()
    root = REPO / spec["training_output"]
    previous = find_run(root, spec, completed_only=True)
    if previous is not None:
        selections = json.loads(
            (previous / "checkpoint_selection.json").read_text(encoding="utf-8")
        )
        verify_training_selections(previous, selections, cfg)
        print(json.dumps({"status": "reused", "run_dir": str(previous)}), flush=True)
        return previous
    out = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    (out / "weights").mkdir()
    started = time.perf_counter()
    info = {
        "status": "started",
        "source_dev_opened": False,
        "external_labels_opened": False,
        "training_runs": 0,
    }
    try:
        print(f"run_dir: {out}", flush=True)
        write_json(out / "config.json", spec)
        info.update(capture_identity(out, TRAIN_CODE))
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable for formal E training")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        train, val, audit, input_identity = prepare_training_inputs(cfg)
        write_json(out / "training_filter_audit.json", audit)
        write_json(out / "input_identity.json", input_identity)
        equivalence_items = train + val
        selections = {}
        for seed in cfg["seeds"]:
            with (out / "weights" / f"seed_{seed}_stdout.log").open(
                "x", encoding="utf-8"
            ) as stream, contextlib.redirect_stdout(stream):
                selections[str(seed)] = train_seed(
                    cfg,
                    seed,
                    train,
                    val,
                    equivalence_items,
                    out / "weights",
                )
            info["training_runs"] += 1
            print(
                f"E seed={seed} completed; epochs={selections[str(seed)]['epochs']}; "
                f"best={selections[str(seed)]['best_epoch']}",
                flush=True,
            )
        epochs = verify_training_selections(out, selections, cfg)
        write_json(out / "checkpoint_selection.json", selections)
        methods = {}
        efficiency = {}
        for seed in cfg["seeds"]:
            choice = selections[str(seed)]
            payload = torch.load(
                out / "weights" / choice["checkpoint"],
                weights_only=True,
                map_location="cpu",
            )
            module = CandidateRankerE().to(cfg["device"])
            module.load_state_dict(payload["state_dict"], strict=True)
            rows = evaluate_items(
                module, val, f"E_seed_{seed}", cfg["device"], full=True
            )
            methods[f"E_seed_{seed}"] = rows
            efficiency[f"E_seed_{seed}"] = choice
            del module, payload
        rows = [row for name in sorted(methods) for row in methods[name]]
        pl.DataFrame(rows).write_parquet(out / "predictions.parquet")
        summaries = {name: summarize(value) for name, value in methods.items()}
        first = summaries["E_seed_0"]
        aggregate = {}
        for subset in ("all", "M_ge_2"):
            keys = first[subset]["metrics"]
            aggregate[subset] = {
                "questions": first[subset]["questions"],
                "units": first[subset]["units"],
                "metrics": {
                    key: statistics.mean(
                        summaries[f"E_seed_{seed}"][subset]["metrics"][key]
                        for seed in cfg["seeds"]
                    )
                    for key in keys
                },
                "std": {
                    key: statistics.stdev(
                        summaries[f"E_seed_{seed}"][subset]["metrics"][key]
                        for seed in cfg["seeds"]
                    )
                    for key in keys
                },
            }
        metrics = {
            "schema": "route-v2-E-training-supplement-v1",
            "result_role": "post-hoc_supplementary",
            "training_filter": audit,
            "trainable_parameters": EXPECTED_PARAMETERS,
            "source_val_methods": summaries,
            "source_val_seed_aggregate": aggregate,
            "selections": selections,
            "efficiency": efficiency,
            "source_dev_scored": False,
            "external_scored": False,
        }
        write_json(out / "metrics.json", metrics)
        verification = {
            "passed": True,
            "seeds": cfg["seeds"],
            "training_runs": 3,
            "epochs": epochs,
            "checkpoints_selected_by_source_val": True,
            "source_dev_scored": False,
            "predictions": len(rows),
            "trainable_parameters": EXPECTED_PARAMETERS,
            "training_filter_closes": audit["original_D_training_units"]
            == audit["E_trainable_units"] + audit["excluded_units"],
        }
        write_json(out / "result_verification.json", verification)
        lines = [
            "# EXP-018 E training",
            "",
            "Post-hoc supplementary；只训练唯一 E，不评分 source_dev。",
            "",
            "|seed|epochs|best epoch|source_val hit1@0.5|training seconds|peak reserved bytes|",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for seed in cfg["seeds"]:
            choice = selections[str(seed)]
            hit = summaries[f"E_seed_{seed}"]["all"]["metrics"]["hit1@0.5"]
            lines.append(
                f"|{seed}|{choice['epochs']}|{choice['best_epoch']}|{hit:.10f}|"
                f"{choice['training_seconds']:.3f}|{choice['peak_reserved_bytes']}|"
            )
        lines += [
            "",
            f"原 D 训练 unit：{audit['original_D_training_units']}；"
            f"E 可训练 unit：{audit['E_trainable_units']}。",
            "",
            "E 与 D 使用同一标注来源，但不是同粒度标签或完全相同训练集。",
        ]
        (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, digest in info["code_sha256"].items():
            if file_sha256(REPO / name) != digest:
                raise ValueError(f"code/config changed during E training: {name}")
        info.update(
            {
                "status": "completed",
                "python": sys.version,
                "torch": str(torch.__version__),
                "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(),
                "training_runs": 3,
                "epochs": epochs,
                "peak_reserved_bytes": max(
                    choice["peak_reserved_bytes"] for choice in selections.values()
                ),
            }
        )
        print("formal E training completed and verified", flush=True)
        return out
    except Exception as exc:
        info.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "run_info.json", info, exclusive=False)
        print(
            json.dumps(
                {
                    "status": info["status"],
                    "elapsed_seconds": info["elapsed_seconds"],
                    "run_dir": str(out),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


def run_check() -> Path:
    _, spec = load_config()
    root = REPO / spec["check_output"]
    out = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(123)
    query = torch.randn(6, 128)
    query[-1].zero_()
    patches = torch.randn(16, 128)
    w_raw = torch.zeros(16, 4)
    w_raw[:8, 0] = 1
    w_raw[8:, 1] = 1
    w_raw[:, 2] = 0.2
    mask = torch.tensor([True, True, True, False])
    features = frozen_candidate_features(query, patches, w_raw, mask)
    coords = torch.rand(4, 6)
    types = torch.tensor([1, 3, 4, 5])
    score_b = torch.tensor([0.3, 0.2, 0.1, 100.0])
    positive = torch.tensor([True, True, False, False])
    negative = torch.tensor([False, False, True, False])
    module = CandidateRankerE()
    before = {name: value.detach().clone() for name, value in module.state_dict().items()}
    initial = module(
        features["x"],
        features["visual"],
        coords,
        types,
        features["candidate_mask"],
        features["nonempty_w"],
        score_b,
    )
    if not torch.equal(initial[:3], score_b[:3]) or not torch.isneginf(initial[3]):
        raise ValueError("small check zero equivalence failed")
    optimizer = torch.optim.AdamW(module.parameters(), lr=0.001, weight_decay=0.01)
    gradients = []
    losses = []
    for _ in range(3):
        optimizer.zero_grad(set_to_none=True)
        scores = module(
            features["x"],
            features["visual"],
            coords,
            types,
            features["candidate_mask"],
            features["nonempty_w"],
            score_b,
        )
        loss = multi_positive_candidate_loss(scores, positive, negative, tau=0.25)
        loss.backward()
        grad = float(
            torch.linalg.vector_norm(
                torch.stack(
                    [
                        parameter.grad.norm()
                        for parameter in module.parameters()
                        if parameter.grad is not None
                    ]
                )
            )
        )
        if not math.isfinite(grad) or grad <= 0:
            raise FloatingPointError("small check gradient is invalid")
        gradients.append(grad)
        losses.append(float(loss.detach()))
        optimizer.step()
    changed = any(
        not torch.equal(value, before[name]) for name, value in module.state_dict().items()
    )
    result = {
        "passed": changed,
        "purpose": "implementation_only_not_hyperparameter_or_seed_selection",
        "trainable_parameters": trainable_parameter_count(module),
        "zero_scores_equal_B": True,
        "zero_ranking_equal_B": rank_candidates(initial.tolist(), [1, 2, 3, 4])
        == rank_candidates([0.3, 0.2, 0.1, -math.inf], [1, 2, 3, 4]),
        "multi_positive_count": 2,
        "negative_count": 1,
        "empty_W_finite": bool(torch.isfinite(features["visual"]).all()),
        "padding_score_is_negative_infinity": bool(torch.isneginf(initial[3])),
        "gradient_norms": gradients,
        "losses": losses,
        "parameters_changed": changed,
        "steps": 3,
    }
    write_json(out / "check.json", result)
    print(json.dumps({"out": str(out), **result}, ensure_ascii=False), flush=True)
    return out


def load_training_run(cfg: dict, spec: dict) -> tuple[Path, dict]:
    run = find_run(REPO / spec["training_output"], spec, completed_only=True)
    if run is None:
        raise FileNotFoundError("completed E training run not found")
    selections = json.loads(
        (run / "checkpoint_selection.json").read_text(encoding="utf-8")
    )
    verify_training_selections(run, selections, cfg)
    return run, selections


def external_e_rows(
    data: external_runner.ExternalInputs,
    module: CandidateRankerE,
    method: str,
    device: str,
) -> list[dict]:
    module.eval()
    rows = []
    with torch.no_grad():
        for unit in data.units:
            boxes, layout_ids = data.boxes(unit)
            item = data.item(unit, layout=True)
            layout = item["layout"]
            if not bool(layout["mask"].all()):
                raise ValueError("external stored candidates unexpectedly contain padding")
            features = frozen_candidate_features(
                item["query"].to(device),
                item["patches"].to(device),
                layout["W_raw"].to(device),
                layout["mask"].to(device),
            )
            patch = patch_scores(item["query"].to(device), item["patches"].to(device))
            score_b = region_scores(patch, data.iou(unit).to(device))
            scores = module(
                features["x"],
                features["visual"],
                layout["coords"].to(device),
                layout["types"].to(device),
                features["candidate_mask"],
                features["nonempty_w"],
                score_b,
            ).cpu()
            order = rank_candidates(scores.tolist(), layout_ids)
            ranked_boxes = [boxes[index] for index in order]
            metrics = unit_metrics(ranked_boxes, unit["gold_boxes"], unit["page_size"])
            if not all(math.isfinite(value) for value in metrics.values()):
                raise FloatingPointError("nonfinite external E metric")
            rows.append(
                {
                    "query_id": unit["query_id"],
                    "doc_id": unit["doc_id"],
                    "page_id": unit["page_id"],
                    "unit_id": unit["unit_id"],
                    "role": unit["role"],
                    "method": method,
                    "candidate_count": len(boxes),
                    "page_overlap_excluded": False,
                    "ranked_layout_ids": [layout_ids[index] for index in order],
                    "ranked_scores": [
                        float(scores[index]) if torch.isfinite(scores[index]) else None
                        for index in order
                    ],
                    **metrics,
                }
            )
            memory_guard(device, 12)
    return rows


def supplementary_analysis(methods: dict[str, list[dict]], units: list[dict], cfg: dict) -> dict:
    seeds = cfg["seeds"]
    summaries = {name: summarize_rows(rows) for name, rows in methods.items()}
    e_aggregate = aggregate_seed_summaries(summaries, "E", seeds)
    reference = averaged_question_scores(methods, "D-no-text", seeds)
    e_questions = averaged_question_scores(methods, "E", seeds)
    doc_of = {unit["query_id"]: unit["doc_id"] for unit in units}
    paired = doc_bootstrap_diff(
        reference,
        e_questions,
        doc_of,
        iterations=cfg["statistics"]["bootstrap"]["iterations"],
        seed=cfg["statistics"]["bootstrap"]["seed"],
    )
    old_aggregates = {
        name: aggregate_seed_summaries(summaries, name, seeds)
        for name in ("C", "C-wide", "D", "D-no-text")
    }
    e_hit = e_aggregate["all"]["metrics"]["hit1@0.5"]
    positions = {
        "E-A": e_hit - summaries["A"]["all"]["metrics"]["hit1@0.5"],
        "E-B": e_hit - summaries["B"]["all"]["metrics"]["hit1@0.5"],
        "E-C-wide": e_hit
        - old_aggregates["C-wide"]["all"]["metrics"]["hit1@0.5"],
    }
    top5_keys = cfg["statistics"]["top5_differences"]
    top5 = {
        key: old_aggregates["D-no-text"]["all"]["metrics"][key]
        - e_aggregate["all"]["metrics"][key]
        for key in top5_keys
    }
    top5_by_seed = {
        str(seed): {
            key: summaries[f"D-no-text_seed_{seed}"]["all"]["metrics"][key]
            - summaries[f"E_seed_{seed}"]["all"]["metrics"][key]
            for key in top5_keys
        }
        for seed in seeds
    }
    return {
        "schema": "route-v2-E-external-supplement-v1",
        "result_role": "post-hoc_supplementary",
        "E_methods": {f"E_seed_{seed}": summaries[f"E_seed_{seed}"] for seed in seeds},
        "E_seed_aggregate": e_aggregate,
        "display_original_methods": {
            "A": summaries["A"],
            "B": summaries["B"],
            "C-wide": old_aggregates["C-wide"],
            "D-no-text": old_aggregates["D-no-text"],
        },
        "primary_supplementary": {"D-no-text-E": paired},
        "multiple_comparison_correction": "none_single_post_hoc_supplementary_comparison",
        "numerical_position_not_primary_comparisons": positions,
        "top5_D_no_text_minus_E": top5,
        "top5_D_no_text_minus_E_by_seed": top5_by_seed,
        "claim_limit": (
            "only compares D-no-text with this one concrete direct-ranking E; "
            "interval crossing zero is not equivalence"
        ),
    }


def analytical_equal(actual: object, expected: object, path: str = "value") -> None:
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"{path} keys differ")
        for key in actual:
            analytical_equal(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path} lengths differ")
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            analytical_equal(left, right, f"{path}[{index}]")
    elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if not math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{path} differs")
    elif actual != expected:
        raise ValueError(f"{path} differs")


def verify_external_saved(run: Path, cfg: dict, ext_cfg: dict) -> dict:
    started = time.perf_counter()
    saved = external_runner.SavedInputs(ext_cfg)
    units = {unit["unit_id"]: unit for unit in saved.units}
    rows = pl.read_parquet(run / "predictions.parquet").to_dicts()
    methods: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        unit = units.get(row["unit_id"])
        if unit is None:
            raise ValueError("supplementary prediction unit identity mismatch")
        boxes, layout_ids = saved.boxes(unit)
        ranked = row["ranked_layout_ids"]
        if len(ranked) != len(layout_ids) or set(ranked) != set(layout_ids):
            raise ValueError("supplementary candidate permutation mismatch")
        lookup = dict(zip(layout_ids, boxes, strict=True))
        validate_prediction_metrics(
            row,
            [lookup[layout_id] for layout_id in ranked],
            unit["gold_boxes"],
            unit["page_size"],
        )
        methods[row["method"]].append(row)
    source_path = REPO / cfg["external"]["source_run"] / "predictions.parquet"
    source_rows = pl.read_parquet(source_path).to_dicts()
    source_methods = {row["method"] for row in source_rows}
    copied = [row for row in rows if row["method"] in source_methods]
    if copied != source_rows:
        raise ValueError("original external predictions were not copied exactly")
    expected_methods = source_methods | {f"E_seed_{seed}" for seed in cfg["seeds"]}
    if set(methods) != expected_methods:
        raise ValueError("supplementary method set mismatch")
    analysis = supplementary_analysis(dict(methods), saved.units, cfg)
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    analytical_equal(analysis, metrics["supplementary"])
    expected_questions = external_runner.question_rows(dict(methods))
    actual_questions = pl.read_parquet(run / "question_scores.parquet").to_dicts()
    analytical_equal(actual_questions, expected_questions, "question_scores")
    return {
        "passed": True,
        "predictions": len(rows),
        "question_rows": len(actual_questions),
        "methods": len(methods),
        "units_per_method": len(saved.units),
        "original_prediction_rows_exactly_reused": len(source_rows),
        "E_prediction_rows": len(rows) - len(source_rows),
        "unit_metrics_recomputed": True,
        "supplementary_statistics_recomputed": True,
        "model_scoring_reexecuted": False,
        "seconds": time.perf_counter() - started,
    }


def run_external() -> Path:
    cfg, spec = load_config()
    root = REPO / spec["external_output"]
    previous = find_run(root, spec, completed_only=False)
    if previous is not None:
        ext_cfg = external_runner.load_config()
        verification = verify_external_saved(previous, cfg, ext_cfg)
        print(
            json.dumps(
                {"status": "reused", "run_dir": str(previous), **verification},
                ensure_ascii=True,
            ),
            flush=True,
        )
        return previous
    recovered = recover_verified_external_run(root, cfg, spec)
    if recovered is not None:
        return recovered
    training_run, selections = load_training_run(cfg, spec)
    out = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    info = {
        "status": "started",
        "training": False,
        "old_model_rescoring": False,
        "visual_reencoding": False,
        "page_retrieval": False,
        "E_scoring_started": False,
        "training_run": str(training_run.relative_to(REPO)).replace("\\", "/"),
    }
    try:
        write_json(out / "config.json", spec)
        info.update(capture_identity(out, EXTERNAL_CODE))
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable for E external scoring")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        ext_cfg = external_runner.load_config()
        if file_sha256(external_runner.CONFIG) != spec["external"]["source_config_sha256"]:
            raise ValueError("external config changed after E freeze")
        candidates, page_sizes = external_runner.load_candidates(ext_cfg)
        units = external_runner.build_units(ext_cfg, page_sizes)
        cache_manifest, cache_receipt = external_runner.validate_cache(
            ext_cfg, candidates, units
        )
        preflight = {
            "status": "ready",
            "denominators": spec["external"]["denominators"],
            "encoding_manifest_sha256": cache_receipt["manifest_sha256"],
            "model_identities": cache_manifest["model_identities"],
            "E_checkpoints": {
                seed: selections[str(seed)]["checkpoint_sha256"]
                for seed in cfg["seeds"]
            },
            "old_predictions_sha256": file_sha256(
                REPO / spec["external"]["source_run"] / "predictions.parquet"
            ),
            "old_model_rescoring": False,
            "visual_reencoding": False,
        }
        write_json(out / "preflight.json", preflight)
        source_run = REPO / spec["external"]["source_run"]
        source_rows = pl.read_parquet(source_run / "predictions.parquet").to_dicts()
        original_methods: dict[str, list[dict]] = defaultdict(list)
        for row in source_rows:
            original_methods[row["method"]].append(row)
        original_analysis = compute_analytical_results(original_methods, units, ext_cfg)
        original_metrics = json.loads(
            (source_run / "metrics.json").read_text(encoding="utf-8")
        )
        analytical_equal(
            original_analysis,
            original_metrics["analytical"],
            "original_analytical",
        )
        data = external_runner.ExternalInputs(ext_cfg)
        methods = dict(original_methods)
        efficiency = {}
        peak = 0
        info["E_scoring_started"] = True
        for seed in cfg["seeds"]:
            choice = selections[str(seed)]
            checkpoint = training_run / "weights" / choice["checkpoint"]
            payload = torch.load(checkpoint, weights_only=True, map_location="cpu")
            module = CandidateRankerE().to(cfg["device"])
            module.load_state_dict(payload["state_dict"], strict=True)
            torch.cuda.reset_peak_memory_stats()
            scoring_started = time.perf_counter()
            method = f"E_seed_{seed}"
            methods[method] = external_e_rows(data, module, method, cfg["device"])
            efficiency[method] = {
                "scoring_seconds": time.perf_counter() - scoring_started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "trainable_parameters": trainable_parameter_count(module),
                "checkpoint": str(checkpoint.relative_to(REPO)).replace("\\", "/"),
                "checkpoint_sha256": choice["checkpoint_sha256"],
                "model_passes": 1,
            }
            peak = max(
                peak,
                efficiency[method]["peak_allocated_bytes"],
                efficiency[method]["peak_reserved_bytes"],
            )
            print(
                json.dumps(
                    {
                        "method": method,
                        "seconds": efficiency[method]["scoring_seconds"],
                        "peak_reserved_bytes": efficiency[method][
                            "peak_reserved_bytes"
                        ],
                    }
                ),
                flush=True,
            )
            del module, payload
            torch.cuda.empty_cache()
        predictions = source_rows + [
            row
            for method in (f"E_seed_{seed}" for seed in cfg["seeds"])
            for row in methods[method]
        ]
        pl.DataFrame(predictions).write_parquet(out / "predictions.parquet")
        questions = external_runner.question_rows(methods)
        pl.DataFrame(questions).write_parquet(out / "question_scores.parquet")
        supplementary = supplementary_analysis(methods, units, cfg)
        metrics = {
            "schema": "route-v2-E-external-supplement-v1",
            "result_role": "post-hoc_supplementary",
            "denominators": spec["external"]["denominators"],
            "original_analytical_recomputed_unchanged": original_analysis,
            "supplementary": supplementary,
            "efficiency": efficiency,
            "E_model_scoring_passes": 3,
            "old_model_scoring_passes": 0,
            "visual_encoding_passes": 0,
            "peak_vram_bytes": peak,
            "vram_budget_bytes": cfg["vram_budget_gib"] * 1024**3,
            "source_predictions": spec["external"]["source_run"]
            + "/predictions.parquet",
            "source_predictions_sha256": spec["external"][
                "source_predictions_sha256"
            ],
        }
        write_json(out / "metrics.json", metrics)
        verification = verify_external_saved(out, cfg, ext_cfg)
        write_json(out / "result_verification.json", verification)
        e = supplementary["E_seed_aggregate"]["all"]
        d = supplementary["display_original_methods"]["D-no-text"]["all"]
        paired = supplementary["primary_supplementary"]["D-no-text-E"]
        lines = [
            "# EXP-018 E external supplement",
            "",
            "Post-hoc supplementary；给定正确页定位，不改写 EXP-017 确认性比较。",
            "",
            "|方法|hit1@0.5|seed std|cov@5|gold recall@5|area sum@5|",
            "|---|---:|---:|---:|---:|---:|",
            f"|D-no-text|{d['metrics']['hit1@0.5']:.10f}|"
            f"{d['std']['hit1@0.5']:.10f}|{d['metrics']['cov@5']:.10f}|"
            f"{d['metrics']['gold_recall@5@0.5']:.10f}|"
            f"{d['metrics']['area_sum@5']:.10f}|",
            f"|E|{e['metrics']['hit1@0.5']:.10f}|{e['std']['hit1@0.5']:.10f}|"
            f"{e['metrics']['cov@5']:.10f}|"
            f"{e['metrics']['gold_recall@5@0.5']:.10f}|"
            f"{e['metrics']['area_sum@5']:.10f}|",
            "",
            f"D-no-text-E Top-1={paired['mean_diff']:.10f}; "
            f"95% CI=[{paired['ci95_low']:.10f},{paired['ci95_high']:.10f}]。",
            "",
            "该比较只回答 D-no-text 是否胜过这一个具体直接排序方案；"
            "区间跨零时不能写等效。",
        ]
        (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, digest in info["code_sha256"].items():
            if file_sha256(REPO / name) != digest:
                raise ValueError(f"code/config changed during E external scoring: {name}")
        cfg_external = spec["external"]
        source_hashes = {
            "predictions.parquet": cfg_external["source_predictions_sha256"],
            "metrics.json": cfg_external["source_metrics_sha256"],
            "run_info.json": cfg_external["source_run_info_sha256"],
            "result_verification.json": cfg_external["source_verification_sha256"],
        }
        for name, digest in source_hashes.items():
            if file_sha256(source_run / name) != digest:
                raise ValueError(f"old external artifact changed during E scoring: {name}")
        info.update(
            {
                "status": "completed",
                "python": sys.version,
                "torch": str(torch.__version__),
                "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(),
                "predictions": len(predictions),
                "question_rows": len(questions),
                "peak_vram_bytes": peak,
                "result_verification": verification,
            }
        )
        print("\n".join(lines[4:]), flush=True)
        return out
    except Exception as exc:
        info.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_json(out / "failure.json", info)
        raise
    finally:
        info["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "run_info.json", info, exclusive=False)
        print(
            json.dumps(
                {
                    "status": info["status"],
                    "elapsed_seconds": info["elapsed_seconds"],
                    "run_dir": str(out),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


def verify_external() -> None:
    cfg, spec = load_config()
    run = find_run(REPO / spec["external_output"], spec, completed_only=True)
    if run is None:
        raise FileNotFoundError("completed E external supplement not found")
    verification = verify_external_saved(run, cfg, external_runner.load_config())
    training_run = find_run(
        REPO / spec["training_output"], spec, completed_only=True
    )
    if training_run is None:
        raise FileNotFoundError("completed E training run not found")
    training_metrics = json.loads(
        (training_run / "metrics.json").read_text(encoding="utf-8")
    )
    training_verification = json.loads(
        (training_run / "result_verification.json").read_text(encoding="utf-8")
    )
    training_run_info = json.loads(
        (training_run / "run_info.json").read_text(encoding="utf-8")
    )
    external_metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    external_run_info = json.loads((run / "run_info.json").read_text(encoding="utf-8"))
    recovery_receipt = json.loads((run / "recovery.json").read_text(encoding="utf-8"))
    supplementary = external_metrics["supplementary"]
    report = {
        "run_dir": str(run),
        **verification,
        "training_run": str(training_run),
        "training_predictions": training_verification["predictions"],
        "training_elapsed_seconds": training_run_info["elapsed_seconds"],
        "training_environment": {
            key: training_run_info.get(key)
            for key in ("git_commit", "python", "torch", "cuda", "gpu")
        },
        "training_metrics": {
            "training_filter": training_metrics["training_filter"],
            "trainable_parameters": training_metrics["trainable_parameters"],
            "source_val_hit1_by_seed": {
                name: value["all"]["metrics"]["hit1@0.5"]
                for name, value in training_metrics["source_val_methods"].items()
            },
            "source_val_hit1_aggregate": {
                "mean": training_metrics["source_val_seed_aggregate"]["all"][
                    "metrics"
                ]["hit1@0.5"],
                "std": training_metrics["source_val_seed_aggregate"]["all"][
                    "std"
                ]["hit1@0.5"],
            },
            "selections": training_metrics["selections"],
            "source_dev_scored": training_metrics["source_dev_scored"],
            "external_scored": training_metrics["external_scored"],
        },
        "external_elapsed_seconds_including_recovery": external_run_info[
            "elapsed_seconds"
        ],
        "recovery": {
            "accepted_error": recovery_receipt["accepted_error"],
            "source_run": recovery_receipt["source_run"],
            "checkpoint_loaded": recovery_receipt["checkpoint_loaded"],
            "model_scoring_reexecuted": recovery_receipt[
                "model_scoring_reexecuted"
            ],
            "recovery_seconds": external_run_info["recovery_seconds"],
        },
        "external_metrics": {
            "denominators": external_metrics["denominators"],
            "E_all_metrics_by_seed": {
                name: value["all"]["metrics"]
                for name, value in supplementary["E_methods"].items()
            },
            "E_all_seed_aggregate": supplementary["E_seed_aggregate"]["all"],
            "display_top1": {
                name: value["all"]["metrics"]["hit1@0.5"]
                for name, value in supplementary["display_original_methods"].items()
            },
            "primary_supplementary": supplementary["primary_supplementary"],
            "numerical_position_not_primary_comparisons": supplementary[
                "numerical_position_not_primary_comparisons"
            ],
            "top5_D_no_text_minus_E": supplementary[
                "top5_D_no_text_minus_E"
            ],
            "top5_D_no_text_minus_E_by_seed": supplementary[
                "top5_D_no_text_minus_E_by_seed"
            ],
            "claim_limit": supplementary["claim_limit"],
            "efficiency": external_metrics["efficiency"],
            "E_model_scoring_passes": external_metrics["E_model_scoring_passes"],
            "old_model_scoring_passes": external_metrics[
                "old_model_scoring_passes"
            ],
            "visual_encoding_passes": external_metrics["visual_encoding_passes"],
            "peak_vram_bytes": external_metrics["peak_vram_bytes"],
        },
    }
    print(json.dumps(report, ensure_ascii=True), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("check", "train", "external", "verify"))
    args = parser.parse_args()
    if args.mode == "check":
        run_check()
    elif args.mode == "train":
        run_training()
    elif args.mode == "external":
        run_external()
    else:
        verify_external()


if __name__ == "__main__":
    main()
