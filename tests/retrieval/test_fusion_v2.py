"""CPU checks for the explicit v2 alternative; no dataset or checkpoint access."""

from __future__ import annotations

import pytest
import torch
from torch.nn.functional import normalize

from layoutpatch.layout.nodes import D
from layoutpatch.retrieval.fusion.sparse_fusion import SparseLocalFusion, SparseLocalFusionV2


def test_v2_identity_initialization_and_legacy_state_dict() -> None:
    torch.manual_seed(0)
    fusion = SparseLocalFusionV2()
    patches = normalize(torch.randn(2, 8, D), dim=-1)
    nodes = normalize(torch.randn(2, 3, D), dim=-1)
    weights = torch.rand(2, 8, 3)
    raw_mass = weights.sum(-1, keepdim=True)
    weights = weights / raw_mass

    output = fusion(patches, weights, nodes, raw_mass)

    assert output.shape == patches.shape
    assert torch.allclose(output, patches, atol=1e-7)
    legacy = SparseLocalFusion()
    restored = SparseLocalFusion()
    restored.load_state_dict(legacy.state_dict(), strict=True)
    assert set(legacy.state_dict()) == set(restored.state_dict())
    assert isinstance(legacy.residual[-1], torch.nn.LayerNorm)


def test_v2_no_candidates_and_empty_or_padding_only_rows_are_unchanged() -> None:
    fusion = SparseLocalFusionV2()
    patches = torch.randn(1, 3, D)
    no_candidates = fusion(
        patches, torch.empty(1, 3, 0), torch.empty(1, 0, D), torch.zeros(1, 3, 1)
    )
    assert torch.equal(no_candidates, patches)

    with torch.no_grad():
        fusion.residual[-1].bias.fill_(0.1)
    weights = torch.tensor([[[0.0, 0.0], [0.0, 1.0], [1.0, 0.0]]])
    output = fusion(
        patches,
        weights,
        torch.randn(1, 2, D),
        weights.sum(-1, keepdim=True),
        node_mask=torch.tensor([[True, False]]),
    )
    assert torch.equal(output[:, :2], patches[:, :2])
    assert torch.isfinite(output).all()


def test_v2_stable_ties_exclude_padding_before_softmax() -> None:
    fusion = SparseLocalFusionV2(top_k=2)
    with torch.no_grad():
        fusion.value.weight.copy_(torch.eye(D))
    nodes = torch.zeros(1, 4, D)
    nodes[0, 0, 0] = 100.0
    nodes[0, 1, 1] = 1.0
    nodes[0, 2, 2] = 1.0
    nodes[0, 3, 3] = 1.0
    seen = []
    hook = fusion.residual[0].register_forward_pre_hook(lambda _module, args: seen.append(args[0]))
    try:
        fusion(
            torch.zeros(1, 1, D),
            torch.ones(1, 1, 4),
            nodes,
            torch.ones(1, 1, 1),
            node_mask=torch.tensor([[False, True, True, True]]),
        )
    finally:
        hook.remove()
    expected = (nodes[:, 1:2] + nodes[:, 2:3]) / 2
    assert torch.equal(seen[0], expected)


def test_v2_keys_are_unprojected_nodes() -> None:
    fusion = SparseLocalFusionV2(top_k=2)
    with torch.no_grad():
        fusion.value.weight.copy_(-torch.eye(D))
    patches = torch.zeros(1, 1, D)
    patches[..., 0] = 1.0
    nodes = torch.zeros(1, 2, D)
    nodes[0, 0, 0] = 1.0
    nodes[0, 1, 0] = -1.0
    seen = []
    hook = fusion.residual[0].register_forward_pre_hook(lambda _module, args: seen.append(args[0]))
    try:
        fusion(patches, torch.ones(1, 1, 2) / 2, nodes, torch.ones(1, 1, 1))
    finally:
        hook.remove()
    # Positive-key node wins attention, although its projected value is negative.
    assert seen[0][0, 0, 0] < 0


def test_v2_gate_can_distinguish_raw_mass_with_identical_normalized_weights() -> None:
    fusion = SparseLocalFusionV2()
    with torch.no_grad():
        fusion.gate.weight[0, -1] = 1.0
        fusion.residual[-1].bias[1] = 0.2
    patches = torch.zeros(1, 1, D)
    patches[..., 0] = 1.0
    nodes = torch.zeros(1, 1, D)
    weights = torch.ones(1, 1, 1)

    low = fusion(patches, weights, nodes, torch.full((1, 1, 1), 0.2))
    high = fusion(patches, weights, nodes, torch.full((1, 1, 1), 0.8))

    assert high[0, 0, 1] > low[0, 0, 1] > 0


def test_v2_small_residual_remains_small() -> None:
    fusion = SparseLocalFusionV2()
    with torch.no_grad():
        fusion.residual[-1].bias[1] = 1e-6
    patches = torch.zeros(1, 1, D)
    patches[..., 0] = 1.0
    output = fusion(
        patches, torch.ones(1, 1, 1), torch.randn(1, 1, D), torch.ones(1, 1, 1)
    )
    distance = torch.linalg.vector_norm(output - patches).item()
    assert 0 < distance < 1e-6


@pytest.mark.parametrize("kind", ["negative_weight", "negative_mass", "nan_mass", "mass_shape"])
def test_v2_rejects_invalid_spatial_inputs(kind: str) -> None:
    fusion = SparseLocalFusionV2()
    weights = torch.ones(1, 1, 1)
    mass = torch.ones(1, 1, 1)
    if kind == "negative_weight":
        weights.fill_(-1)
    elif kind == "negative_mass":
        mass.fill_(-1)
    elif kind == "nan_mass":
        mass.fill_(float("nan"))
    else:
        mass = torch.ones(1, 1)
    with pytest.raises(ValueError):
        fusion(torch.zeros(1, 1, D), weights, torch.zeros(1, 1, D), mass)
