"""Legacy fusion and an explicit v2 alternative (PAPER_SPEC 5.4/5.5).

Empty rows of W stay zero and bypass softmax. No background token is used.
Historical runs use SparseLocalFusion; the v2 class has no trained checkpoint.
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


class SparseLocalFusionV2(nn.Module):
    """Explicit alternative; legacy experiments continue using SparseLocalFusion.

    ``weights`` supplies the spatial attention bias, usually row-normalized.
    ``raw_cover_mass`` is supplied separately as the sum of the original cover
    weights. Overlapping regions can make it exceed one; it is not union coverage.
    ``node_mask`` excludes padding independently of its stored weights.
    """

    def __init__(self, top_k: int = TOP_K) -> None:
        super().__init__()
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        self.top_k = top_k
        self.value = nn.Linear(D, D, bias=False)
        self.residual = nn.Sequential(
            nn.LayerNorm(D),
            nn.Linear(D, 2 * D),
            nn.GELU(),
            nn.Linear(2 * D, D),
        )
        nn.init.zeros_(self.residual[-1].weight)
        nn.init.zeros_(self.residual[-1].bias)
        self.gate = nn.Linear(2 * D + 1, 1)
        nn.init.zeros_(self.gate.weight)
        nn.init.constant_(self.gate.bias, GATE_BIAS)

    def forward(
        self,
        patches: torch.Tensor,
        weights: torch.Tensor,
        nodes: torch.Tensor,
        raw_cover_mass: torch.Tensor,
        *,
        node_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if patches.ndim != 3 or patches.shape[-1] != D:
            raise ValueError("patches must have shape [B, N, 128]")
        batch, num_patches, _ = patches.shape
        if nodes.ndim != 3 or nodes.shape[0] != batch or nodes.shape[-1] != D:
            raise ValueError("nodes must have shape [B, M, 128]")
        num_regions = nodes.shape[1]
        if weights.shape != (batch, num_patches, num_regions):
            raise ValueError("weights must have shape [B, N, M]")
        if raw_cover_mass.shape != (batch, num_patches, 1):
            raise ValueError("raw_cover_mass must have shape [B, N, 1]")
        for name, tensor in (
            ("patches", patches),
            ("weights", weights),
            ("nodes", nodes),
            ("raw_cover_mass", raw_cover_mass),
        ):
            if not tensor.is_floating_point() or not bool(torch.isfinite(tensor).all()):
                raise ValueError(f"{name} must contain finite floating-point values")
            if tensor.device != patches.device:
                raise ValueError("all inputs must be on the same device")
        if bool((weights < 0).any()) or bool((raw_cover_mass < 0).any()):
            raise ValueError("weights and raw_cover_mass must be nonnegative")
        if node_mask is not None and (
            node_mask.shape != (batch, num_regions)
            or node_mask.dtype != torch.bool
            or node_mask.device != patches.device
        ):
            raise ValueError("node_mask must be boolean [B, M] on the input device")
        if num_regions == 0:
            return patches

        spatial = weights if node_mask is None else weights.masked_fill(~node_mask[:, None, :], 0.0)
        k = min(self.top_k, num_regions)
        # Stable sorting breaks equal spatial weights by original region index.
        chosen = torch.argsort(spatial, dim=-1, descending=True, stable=True)[..., :k]
        chosen_w = torch.gather(spatial, -1, chosen)
        valid = chosen_w > 0
        expanded = nodes.unsqueeze(1).expand(-1, num_patches, -1, -1)
        keys = torch.gather(expanded, 2, chosen.unsqueeze(-1).expand(-1, -1, -1, D))
        values = self.value(keys)
        scores = torch.einsum("bnd,bnkd->bnk", patches, keys) / (D**0.5)
        scores = scores + torch.log(chosen_w + 1e-6)
        scores = scores.masked_fill(~valid, float("-inf"))
        empty = ~valid.any(dim=-1)
        # Empty rows use safe logits and zero attention, then bypass the update.
        scores = scores.masked_fill(empty.unsqueeze(-1), 0.0)
        attention = torch.softmax(scores, dim=-1)
        attention = torch.where(valid, attention, torch.zeros_like(attention))
        delta = torch.einsum("bnk,bnkd->bnd", attention, values)
        gate = torch.sigmoid(self.gate(torch.cat((patches, delta, raw_cover_mass), dim=-1)))
        updated = torch.nn.functional.normalize(patches + gate * self.residual(delta), dim=-1)
        return torch.where(empty.unsqueeze(-1), patches, updated)
