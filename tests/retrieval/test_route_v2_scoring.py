"""Synthetic checks for the route-v2 token layout, scoring, adapter and local loss."""

from __future__ import annotations

import pytest
import torch
from torch.nn.functional import normalize

from layoutpatch.retrieval.colpali_layout import (
    NUM_PATCHES,
    PAGE_TOKENS,
    patch_index,
    split_page_embedding,
)
from layoutpatch.retrieval.route_v2_scoring import (
    PatchAdapter,
    area_scores,
    local_contrastive_loss,
    patch_iou_matrix,
    patch_scores,
    region_scores,
    train_local_steps,
)


def test_split_is_image_first_and_rejects_other_shapes():
    emb = torch.arange(PAGE_TOKENS, dtype=torch.float32)[:, None].repeat(1, 4)
    patches, prompt = split_page_embedding(emb)
    assert patches.shape == (NUM_PATCHES, 4) and prompt.shape == (7, 4)
    assert patches[0, 0] == 0 and patches[-1, 0] == NUM_PATCHES - 1 and prompt[0, 0] == NUM_PATCHES
    with pytest.raises(ValueError):
        split_page_embedding(emb[7:])
    assert patch_index(1, 0) == 32 and patch_index(31, 31) == 1023


def test_patch_scores_keep_all_valid_query_tokens_and_drop_zero_rows():
    torch.manual_seed(0)
    patches = normalize(torch.randn(NUM_PATCHES, 8), dim=-1)
    query = normalize(torch.randn(3, 8), dim=-1)
    padded = torch.cat([query, torch.zeros(2, 8)])
    expected = (query @ patches.T).amax(dim=0)
    assert torch.allclose(patch_scores(padded, patches), expected, atol=1e-6)
    with pytest.raises(ValueError):
        patch_scores(torch.zeros(2, 8), patches)


def test_region_score_is_iou_weighted_patch_mean_on_patch_grid():
    scores = torch.zeros(NUM_PATCHES)
    scores[patch_index(0, 0)] = 1.0
    page = [448.0, 448.0]
    boxes = [[0, 0, 14, 14], [0, 0, 28, 14], [100, 100, 100, 120]]
    iou = patch_iou_matrix(boxes, page)
    assert iou.shape == (3, NUM_PATCHES)
    assert iou[0, 0] == pytest.approx(1.0) and iou[0].sum() == pytest.approx(1.0)
    r = region_scores(scores, iou)
    assert r[0] == pytest.approx(1.0) and r[1] == pytest.approx(0.5)
    assert r[2] == float("-inf")
    assert area_scores([[0, 0, 2, 3], [1, 1, 1, 9]]) == [6.0, 0.0]


def test_adapter_is_identity_before_training():
    torch.manual_seed(1)
    patches = torch.randn(NUM_PATCHES, 128)
    out = PatchAdapter()(patches)
    assert torch.allclose(out, normalize(patches, dim=-1), atol=1e-6)


def test_local_loss_excludes_ignored_patches_and_requires_both_sets():
    scores = torch.tensor([2.0, 0.0, 50.0, -1.0])
    pos = torch.tensor([True, False, False, False])
    neg = torch.tensor([False, True, False, True])
    base = local_contrastive_loss(scores, pos, neg)
    scores2 = scores.clone()
    scores2[2] = -50.0  # index 2 is ignored: changing it must not change the loss
    assert torch.isclose(base, local_contrastive_loss(scores2, pos, neg))
    with pytest.raises(ValueError):
        local_contrastive_loss(scores, torch.zeros(4, dtype=torch.bool), neg)
    with pytest.raises(ValueError):
        local_contrastive_loss(scores, pos, pos)


def test_train_local_steps_learns_a_synthetic_signal():
    torch.manual_seed(2)
    marker = normalize(torch.randn(128), dim=0)  # zero-mean direction survives LayerNorm
    items = []
    for _ in range(4):
        patches = torch.randn(NUM_PATCHES, 128)
        pos = torch.zeros(NUM_PATCHES, dtype=torch.bool)
        pos[torch.randperm(NUM_PATCHES)[:20]] = True
        patches[pos] += 4.0 * marker
        items.append({"query": torch.randn(5, 128), "patches": patches, "pos": pos, "neg": ~pos})
    result = train_local_steps(PatchAdapter(), items, steps=30, lr=1e-2)
    assert result["nonfinite_steps"] == 0
    assert result["final"]["loss"] < result["initial"]["loss"]
    assert result["final"]["mean_gap"] > result["initial"]["mean_gap"]
    assert result["initial"]["grad_norm"] > 0
    assert result["parameters_changed"] and result["gradient_nonzero_steps"] == 30


@pytest.mark.parametrize("failure", ["input", "gradient"])
def test_nonfinite_stops_before_parameter_update(failure):
    module = PatchAdapter()
    initial = {k: v.clone() for k, v in module.state_dict().items()}
    pos = torch.zeros(NUM_PATCHES, dtype=torch.bool)
    pos[:20] = True
    item = {"query": torch.randn(12, 128), "patches": torch.randn(NUM_PATCHES, 128), "pos": pos, "neg": ~pos}
    if failure == "input":
        item["query"][0, 0] = float("nan")
    else:
        module.net[-1].weight.register_hook(lambda grad: torch.full_like(grad, float("inf")))
    with pytest.raises(FloatingPointError, match="nonfinite"):
        train_local_steps(module, [item], steps=2, lr=1e-3)
    assert all(torch.equal(initial[k], v) for k, v in module.state_dict().items())
