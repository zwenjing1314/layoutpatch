"""Route-v2 differentiable scoring, fixed region aggregation and local supervision.

All methods share one interface (definitions: PAPER_SPEC section 8.1):
- patches are the image-first rows of the cached page tensor, L2-normalized in float32;
- patch score keeps every valid query token (no pooling): ``s_j = max_i <q_i, p_j>``.
  The page MaxSim ``sum_i max_j <q_i, p_j>`` is unchanged by this view;
- fixed, untrained region score (Snappy Eq. 10 form, no percentile filter):
  ``r(c) = sum_j IoU(patch_j, c) s_j / sum_j IoU(patch_j, c)``;
- local loss (RegionRAG Eq. 3, tau=0.25, over ``s_j`` instead of a pooled query):
  ``L = -log(sum_{P+} exp(s/tau) / sum_{P+ ∪ P-} exp(s/tau))``; ignored patches excluded.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import torch
from torch import nn
from torch.nn.functional import normalize

from layoutpatch.layout.correspondence import GRID, clamp_bbox, patch_bbox, scale_bbox_to_model

LOCAL_TAU = 0.25
_CELLS = torch.tensor([patch_bbox(i) for i in range(GRID * GRID)], dtype=torch.float32)


def valid_query(query: torch.Tensor) -> torch.Tensor:
    """Float32, L2-normalized query rows; all-zero (masked padding) rows are dropped."""
    q = query.float()
    keep = q.norm(dim=-1) > 1e-6
    if not bool(keep.any()):
        raise ValueError("query has no nonzero token rows")
    return normalize(q[keep], dim=-1)


def patch_scores(query: torch.Tensor, patches: torch.Tensor) -> torch.Tensor:
    """Per-patch MaxSim term over valid query tokens; ``patches`` is [1024, D]."""
    if patches.shape[0] != GRID * GRID:
        raise ValueError(f"expected {GRID * GRID} patch rows, got {tuple(patches.shape)}")
    return (valid_query(query) @ normalize(patches.float(), dim=-1).T).amax(dim=0)


def patch_iou_matrix(boxes: Sequence[Sequence[float]], page_size: Sequence[float]) -> torch.Tensor:
    """IoU between each candidate (page frame) and each 14px model patch: [M, 1024]."""
    if not boxes:
        return torch.zeros(0, GRID * GRID)
    size = [float(v) for v in page_size]
    scaled = torch.tensor(
        [clamp_bbox(scale_bbox_to_model([float(v) for v in b], size)) for b in boxes],
        dtype=torch.float32,
    )
    c = _CELLS
    w = (torch.minimum(scaled[:, None, 2], c[None, :, 2]) - torch.maximum(scaled[:, None, 0], c[None, :, 0])).clamp_min(0)
    h = (torch.minimum(scaled[:, None, 3], c[None, :, 3]) - torch.maximum(scaled[:, None, 1], c[None, :, 1])).clamp_min(0)
    inter = w * h
    box_area = ((scaled[:, 2] - scaled[:, 0]) * (scaled[:, 3] - scaled[:, 1])).clamp_min(0)
    cell_area = (c[:, 2] - c[:, 0]) * (c[:, 3] - c[:, 1])
    union = box_area[:, None] + cell_area[None, :] - inter
    return torch.where(union > 0, inter / union.clamp_min(1e-9), torch.zeros_like(inter))


def region_scores(scores: torch.Tensor, iou: torch.Tensor) -> torch.Tensor:
    """IoU-normalized patch mean per candidate; candidates touching no patch get -inf."""
    mass = iou.sum(dim=-1)
    mean = (iou @ scores) / mass.clamp_min(1e-12)
    return torch.where(mass > 0, mean, torch.full_like(mean, -math.inf))


def area_scores(boxes: Sequence[Sequence[float]]) -> list[float]:
    """Area-descending baseline score (page frame); ties are broken by the ranker."""
    return [max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) for b in boxes]


class PatchAdapter(nn.Module):
    """Learnable no-layout control: ``P' = normalize(P + W2 GELU(W1 LN(P)))``.

    ``W2`` is zero-initialized, so before training it reproduces the frozen baseline.
    It sees only patch vectors: no text, type, coordinates or W.
    """

    def __init__(self, dim: int = 128, hidden: int = 256) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, hidden), nn.GELU(), nn.Linear(hidden, dim))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, patches: torch.Tensor) -> torch.Tensor:
        x = normalize(patches.float(), dim=-1)
        return normalize(x + self.net(x), dim=-1)


def local_contrastive_loss(
    scores: torch.Tensor, pos: torch.Tensor, neg: torch.Tensor, tau: float = LOCAL_TAU
) -> torch.Tensor:
    if pos.dtype != torch.bool or neg.dtype != torch.bool or bool((pos & neg).any()):
        raise ValueError("pos/neg must be disjoint boolean masks")
    if not bool(pos.any()) or not bool(neg.any()):
        raise ValueError("local loss needs at least one positive and one negative patch")
    logits = scores / tau
    return torch.logsumexp(logits[pos | neg], 0) - torch.logsumexp(logits[pos], 0)


def separation(scores: torch.Tensor, pos: torch.Tensor, neg: torch.Tensor) -> dict[str, float]:
    s = scores.detach()
    both = pos | neg
    top = int(torch.nonzero(both).flatten()[s[both].argmax()])
    return {
        "mean_gap": float(s[pos].mean() - s[neg].mean()),
        "max_gap": float(s[pos].max() - s[neg].max()),
        "top_patch_positive": float(bool(pos[top])),
    }


def train_local_steps(
    module: nn.Module,
    items: Sequence[dict[str, Any]],
    *,
    steps: int,
    lr: float,
    tau: float = LOCAL_TAU,
    log_every: int = 10,
) -> dict[str, Any]:
    """Full-batch AdamW on mean local loss; each item has query/patches/pos/neg tensors."""
    if steps < 1 or not items:
        raise ValueError("need steps >= 1 and at least one item")
    optimizer = torch.optim.AdamW(module.parameters(), lr=lr)

    def evaluate() -> tuple[torch.Tensor, dict[str, float]]:
        losses, gaps = [], []
        for item in items:
            s = patch_scores(item["query"], module(item["patches"]))
            if not bool(torch.isfinite(s).all()):
                raise FloatingPointError("nonfinite patch scores; stopped before optimizer update")
            losses.append(local_contrastive_loss(s, item["pos"], item["neg"], tau))
            gaps.append(separation(s, item["pos"], item["neg"]))
        mean_gap = {k: sum(g[k] for g in gaps) / len(gaps) for k in gaps[0]}
        return torch.stack(losses).mean(), mean_gap

    initial_parameters = [p.detach().clone() for p in module.parameters()]
    for item in items:
        if not all(bool(torch.isfinite(item[k]).all()) for k in ("query", "patches")):
            raise FloatingPointError("nonfinite input; stopped before optimizer update")
    log: list[dict[str, float]] = []
    grad_norms = []
    nonfinite = 0
    for step in range(steps):
        loss, gaps = evaluate()
        if not bool(torch.isfinite(loss)):
            raise FloatingPointError(f"nonfinite loss at step {step}; no optimizer update")
        optimizer.zero_grad()
        loss.backward()
        grads = [p.grad for p in module.parameters() if p.grad is not None]
        grad_norm = float(torch.linalg.vector_norm(torch.stack([g.norm() for g in grads]))) if grads else 0.0
        value = float(loss.detach())
        if not math.isfinite(grad_norm) or not all(bool(torch.isfinite(g).all()) for g in grads):
            raise FloatingPointError(f"nonfinite gradient at step {step}; no optimizer update")
        grad_norms.append(grad_norm)
        if step % log_every == 0:
            log.append({"step": float(step), "loss": value, "grad_norm": grad_norm, **gaps})
        optimizer.step()
        if not all(bool(torch.isfinite(p).all()) for p in module.parameters()):
            raise FloatingPointError(f"nonfinite parameters after step {step}; stopped")
        if not all(bool(torch.isfinite(v).all()) for state in optimizer.state.values()
                   for v in state.values() if isinstance(v, torch.Tensor)):
            raise FloatingPointError(f"nonfinite optimizer state after step {step}; stopped")
    with torch.no_grad():
        final_loss, final_gaps = evaluate()
    if not bool(torch.isfinite(final_loss)):
        raise FloatingPointError("nonfinite final loss")
    parameter_delta = float(torch.linalg.vector_norm(torch.stack([
        (p.detach() - before).norm() for p, before in zip(module.parameters(), initial_parameters, strict=True)
    ])))
    return {
        "steps_completed": steps,
        "gradient_norm_min": min(grad_norms),
        "gradient_norm_max": max(grad_norms),
        "gradient_nonzero_steps": sum(g > 0 for g in grad_norms),
        "gradients_all_finite": True,
        "parameters_changed": parameter_delta > 0,
        "parameter_delta_l2": parameter_delta,
        "log": log,
        "initial": log[0],
        "final": {"step": float(steps), "loss": float(final_loss), **final_gaps},
        "nonfinite_steps": nonfinite,
        "trainable_parameters": sum(p.numel() for p in module.parameters() if p.requires_grad),
    }
