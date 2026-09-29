"""Random-tensor shape tests. No evaluation data and no gold files."""

from __future__ import annotations

import torch

from layoutpatch.layout.nodes import D, TextLayoutEncoder
from layoutpatch.retrieval.fusion.sparse_fusion import GATE_BIAS, SparseLocalFusion


def test_random_forward_keeps_shape() -> None:
    torch.manual_seed(0)
    encoder = TextLayoutEncoder(text_dim=32, num_types=4)
    fusion = SparseLocalFusion()
    text = torch.randn(2, 3, 32)
    text[0, 2].zero_()
    coords = torch.rand(2, 3, 6)
    types = torch.tensor([[1, 2, 0], [0, 1, 3]])
    valid = torch.tensor([[1, 1, 0], [1, 0, 1]], dtype=torch.bool)
    nodes = encoder(text, coords, types, valid)
    patches = torch.randn(2, 8, D)
    weights = torch.rand(2, 8, 3)
    out = fusion(patches, weights, nodes)
    assert out.shape == patches.shape
    assert torch.isfinite(out).all()


def test_empty_rows_keep_original_patches() -> None:
    fusion = SparseLocalFusion()
    patches = torch.randn(1, 4, D)
    nodes = torch.randn(1, 2, D)
    weights = torch.zeros(1, 4, 2)
    weights[0, 1, 0] = 0.5
    out = fusion(patches, weights, nodes)
    assert torch.allclose(out[0, 0], patches[0, 0])
    assert torch.allclose(out[0, 2:], patches[0, 2:])


def test_fewer_than_four_regions_has_no_nan() -> None:
    fusion = SparseLocalFusion()
    patches = torch.randn(1, 5, D)
    nodes = torch.randn(1, 2, D)
    weights = torch.tensor([[[0.2, 0.0], [0.0, 0.7], [0.1, 0.3], [0.0, 0.0], [0.4, 0.0]]])
    out = fusion(patches, weights, nodes)
    assert torch.isfinite(out).all()


def test_initial_gate_and_zero_residual() -> None:
    fusion = SparseLocalFusion()
    patches = torch.randn(1, 2, D)
    nodes = torch.randn(1, 1, D)
    weights = torch.ones(1, 2, 1)
    with torch.no_grad():
        delta = fusion.value(nodes).expand(1, 2, 1, D)
        delta = torch.softmax(torch.zeros(1, 2, 1), dim=-1).unsqueeze(-1) * delta
        delta = delta.squeeze(2)
        coverage = weights.sum(-1, keepdim=True)
        gate = torch.sigmoid(fusion.gate(torch.cat((patches, delta, coverage), dim=-1)))
    expected = torch.sigmoid(torch.tensor(GATE_BIAS, dtype=gate.dtype))
    assert torch.allclose(gate, torch.full_like(gate, float(expected)), atol=1e-4)
    last = fusion.residual[2]
    assert isinstance(last, torch.nn.Linear)
    assert torch.count_nonzero(last.weight) == 0
    assert torch.count_nonzero(last.bias) == 0


def test_parameter_count_is_finite() -> None:
    encoder = TextLayoutEncoder(text_dim=32, num_types=4)
    fusion = SparseLocalFusion()
    count = sum(p.numel() for p in encoder.parameters()) + sum(p.numel() for p in fusion.parameters())
    assert count == 146178
