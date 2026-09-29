"""Minimal local fusion (PAPER_SPEC 5.4/5.5). Shape smoke only; not trained.

Empty rows of W stay zero and bypass softmax. No background token is used.
"""

from __future__ import annotations

import torch
from torch import nn

from layoutpatch.layout.nodes import D

TOP_K = 4
GATE_BIAS = -3.0


class SparseLocalFusion(nn.Module):
    """Fuse each patch with at most four valid layout nodes."""

    def __init__(self, top_k: int = TOP_K) -> None:
        super().__init__()
        self.top_k = top_k
        self.value = nn.Linear(D, D, bias=False)
        self.residual = nn.Sequential(
            nn.Linear(D, 2 * D),
            nn.GELU(),
            nn.Linear(2 * D, D),
            nn.LayerNorm(D),
        )
        last = self.residual[2]
        if not isinstance(last, nn.Linear):
            raise TypeError("residual output layer must be Linear")
        nn.init.zeros_(last.weight)
        nn.init.zeros_(last.bias)
        self.gate = nn.Linear(2 * D + 1, 1)
        nn.init.zeros_(self.gate.weight)
        nn.init.constant_(self.gate.bias, GATE_BIAS)

    def forward(self, patches: torch.Tensor, weights: torch.Tensor, nodes: torch.Tensor) -> torch.Tensor:
        if patches.shape[-1] != D or nodes.shape[-1] != D:
            raise ValueError("P and T must both use D=128")
        batch, num_patches, _ = patches.shape
        num_regions = nodes.shape[1]
        k = min(self.top_k, num_regions)
        safe = torch.where(weights > 0, weights, torch.zeros_like(weights))
        chosen = torch.topk(safe, k=k, dim=-1).indices
        chosen_w = torch.gather(weights, -1, chosen)
        valid = chosen_w > 0
        gathered = nodes.unsqueeze(1).expand(-1, num_patches, -1, -1)
        gathered = torch.gather(gathered, 2, chosen.unsqueeze(-1).expand(-1, -1, -1, D))
        values = self.value(gathered)
        scores = torch.einsum("bnd,bnkd->bnk", patches, values) / (D**0.5)
        scores = scores + torch.log(chosen_w.clamp_min(0) + 1e-6)
        scores = scores.masked_fill(~valid, float("-inf"))
        empty = ~valid.any(dim=-1)
        scores = scores.masked_fill(empty.unsqueeze(-1), 0.0)
        attention = torch.softmax(scores, dim=-1)
        attention = torch.where(valid, attention, torch.zeros_like(attention))
        delta = torch.einsum("bnk,bnkd->bnd", attention, values)
        coverage = weights.clamp_min(0).sum(dim=-1, keepdim=True)
        gate = torch.sigmoid(self.gate(torch.cat((patches, delta, coverage), dim=-1)))
        residual = self.residual(delta)
        updated = patches + gate * residual
        updated = torch.nn.functional.normalize(updated, dim=-1)
        keep = empty.unsqueeze(-1)
        return torch.where(keep, patches, updated)
