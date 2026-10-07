"""EXP-014 的角色门、训练轮次、检查点与配对统计；沿用既有评分与指标。"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

import torch

from layoutpatch.evaluation.localization import doc_bootstrap_diff, question_macro
from layoutpatch.retrieval.route_v2_scoring import local_contrastive_loss, patch_scores


def select_units(units: list[dict], role: str, *, training: bool = False) -> list[dict]:
    if training and role != "source_train":
        raise ValueError("parameter updates only allowed on source_train")
    if role not in {"source_train", "source_val", "source_dev"}:
        raise ValueError("forbidden role")
    selected = [u for u in units if u["role"] == role and (
        u["local_loss_ready"] and not u["page_overlap_excluded"] if training else u["eval_ready"])]
    return sorted(selected, key=lambda u: u["unit_id"])


@dataclass
class EarlyStopping:
    patience: int = 5
    best: float = -math.inf
    best_epoch: int = 0
    stale: int = 0

    def observe(self, epoch: int, score: float) -> tuple[bool, bool]:
        if not math.isfinite(score):
            raise FloatingPointError("nonfinite validation metric")
        improved = score > self.best
        if improved:
            self.best, self.best_epoch, self.stale = score, epoch, 0
        else:
            self.stale += 1
        return improved, self.stale >= self.patience


def assert_dev_ready(selected: dict, seeds: list[int]) -> None:
    if set(selected) != set(seeds) or any(not selected[s].get("checkpoint") for s in seeds):
        raise ValueError("source_dev blocked until all checkpoints are selected")


def finite(tensor: torch.Tensor, label: str) -> None:
    if not bool(torch.isfinite(tensor).all()):
        raise FloatingPointError(f"nonfinite {label}")


def memory_guard(device: str, budget_gib: float) -> None:
    if device.startswith("cuda"):
        peak = max(torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved())
        if peak > budget_gib * 1024**3:
            raise RuntimeError(f"VRAM budget exceeded: {peak} bytes")


def train_epoch(module, optimizer, items, rng: random.Random, *, batch_units=4, tau=0.25,
                clip=1.0, device="cuda:0", budget_gib=12) -> dict:
    order = list(range(len(items)))
    rng.shuffle(order)
    loss_sum, norms, updates = 0.0, [], 0
    diagnostic = {"gate_sum": 0.0, "gate_count": 0, "gate_min": 1.0, "gate_max": 0.0,
                  "residual_sum": 0.0, "residual_count": 0, "residual_max": 0.0,
                  "patch_change_sum": 0.0, "patch_count": 0}
    hooks = []
    if hasattr(module, "fusion"):
        def capture_gate(_module, _args, output):
            gate = output.detach().sigmoid()
            finite(gate, "gate diagnostic")
            diagnostic["gate_sum"] += float(gate.sum())
            diagnostic["gate_count"] += gate.numel()
            diagnostic["gate_min"] = min(diagnostic["gate_min"], float(gate.min()))
            diagnostic["gate_max"] = max(diagnostic["gate_max"], float(gate.max()))

        def capture_residual(_module, _args, output):
            residual = output.detach().norm(dim=-1)
            finite(residual, "residual diagnostic")
            diagnostic["residual_sum"] += float(residual.sum())
            diagnostic["residual_count"] += residual.numel()
            diagnostic["residual_max"] = max(diagnostic["residual_max"], float(residual.max()))

        hooks = [module.fusion.gate.register_forward_hook(capture_gate),
                 module.fusion.residual.register_forward_hook(capture_residual)]
    module.train()
    for start in range(0, len(order), batch_units):
        group = order[start:start + batch_units]
        optimizer.zero_grad(set_to_none=True)
        for idx in group:
            item = items[idx]
            q, p = item["query"].to(device), item["patches"].to(device)
            pos, neg = item["pos"].to(device), item["neg"].to(device)
            finite(q, "query")
            finite(p, "patch input")
            layout = {k: v.to(device) for k, v in item["layout"].items()} if "layout" in item else None
            updated = module(p, layout) if layout is not None else module(p)
            if layout is not None:
                change = (torch.nn.functional.normalize(updated.detach(), dim=-1) - torch.nn.functional.normalize(p, dim=-1)).norm(dim=-1)
                finite(change, "patch change diagnostic")
                diagnostic["patch_change_sum"] += float(change.sum())
                diagnostic["patch_count"] += change.numel()
            s = patch_scores(q, updated)
            finite(s, "patch scores")
            loss = local_contrastive_loss(s, pos, neg, tau)
            finite(loss, "local loss")
            (loss / len(group)).backward()
            loss_sum += float(loss.detach())
            memory_guard(device, budget_gib)
        for param in module.parameters():
            if param.grad is not None:
                finite(param.grad, "gradient before update")
        norm = torch.nn.utils.clip_grad_norm_(module.parameters(), clip, error_if_nonfinite=True)
        finite(norm, "gradient norm")
        norms.append(float(norm))
        optimizer.step()
        updates += 1
        for param in module.parameters():
            finite(param, "parameter after update")
        for state in optimizer.state.values():
            for value in state.values():
                if isinstance(value, torch.Tensor):
                    finite(value, "optimizer state")
        memory_guard(device, budget_gib)
    for hook in hooks:
        hook.remove()
    diagnostics = {} if not hooks else {
        "gate_mean": diagnostic["gate_sum"] / diagnostic["gate_count"],
        "gate_min": diagnostic["gate_min"], "gate_max": diagnostic["gate_max"],
        "residual_mlp_l2_mean": diagnostic["residual_sum"] / diagnostic["residual_count"],
        "residual_mlp_l2_max": diagnostic["residual_max"],
        "normalized_patch_change_mean": diagnostic["patch_change_sum"] / diagnostic["patch_count"],
    }
    return {"loss": loss_sum / len(items), "updates": updates, "gradient_norm_min": min(norms),
            "gradient_norm_max": max(norms), "nonzero_updates": sum(n > 0 for n in norms),
            "nonfinite": 0, **diagnostics}


def macro_summary(rows: list[dict], keys: list[str]) -> dict:
    if not rows:
        return {"questions": 0, "units": 0, "metrics": {}}
    metrics = {k: statistics.mean(question_macro(rows, k).values()) for k in keys}
    return {"questions": len({r["query_id"] for r in rows}), "units": len(rows), "metrics": metrics}


def paired_statistics(seed_scores: list[dict], baseline: dict, area: dict, doc_of: dict,
                      *, iterations=2000, seed=0) -> dict:
    if len(seed_scores) != 3 or any(set(s) != set(baseline) for s in seed_scores) or set(area) != set(baseline):
        raise ValueError("three seeds and identical question IDs required")
    averaged = {q: statistics.mean(s[q] for s in seed_scores) for q in sorted(baseline)}
    individual = [statistics.mean(s.values()) for s in seed_scores]
    cb = doc_bootstrap_diff(averaged, baseline, doc_of, iterations=iterations, seed=seed)
    ca = doc_bootstrap_diff(averaged, area, doc_of, iterations=iterations, seed=seed)
    return {"C_mean": statistics.mean(individual), "C_std": statistics.stdev(individual),
            "C_minus_B": cb, "C_minus_A": ca,
            "advance": cb["mean_diff"] >= 0.01 and cb["ci95_low"] > 0}
