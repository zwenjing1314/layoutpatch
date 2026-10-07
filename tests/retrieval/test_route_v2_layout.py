"""D组合接口、来源选择与上游梯度的合成验收。"""
import random

import torch

from layoutpatch.retrieval.route_v2_exp1 import train_epoch
from layoutpatch.retrieval.route_v2_layout import LayoutPatchD, node_text, page_layout
from layoutpatch.retrieval.route_v2_scoring import local_contrastive_loss, patch_scores


def layout():
    rows = [{"layout_id": 1, "type": "text", "bbox": [0, 0, 224, 224], "page_size": [448, 448]},
            {"layout_id": 2, "type": "table", "bbox": [224, 0, 448, 224], "page_size": [448, 448]}]
    return page_layout(rows, torch.randn(2, 1024))


def test_field_policy_no_vlm_fallback_and_geometry_alignment():
    assert node_text({"type": "text", "text": " abc ", "vlm_text": "bad"}) == ("abc", "text")
    assert node_text({"type": "image", "ocr_text": None, "vlm_text": "bad"}) == ("", "ocr_text")
    data = layout()
    assert data["types"].tolist() == [1, 3]
    assert data["coords"][0].tolist() == [0, 0, .5, .5, .5, .5]
    assert data["W_raw"][0].tolist() == [1, 0]
    assert data["W_raw"][31].tolist() == [0, 1]
    assert data["cover_mass"][800] == 0


def test_zero_initialization_empty_patch_and_prompt_preservation():
    module = LayoutPatchD()
    page = torch.randn(1031, 128)
    data = layout()
    output = module.forward_page(page, data)
    assert torch.equal(output[1024:], page[1024:])
    empty = data["cover_mass"].squeeze(-1) == 0
    assert torch.equal(output[:1024][empty], page[:1024][empty])
    query = torch.randn(13, 128)
    assert torch.allclose(patch_scores(query, output[:1024]), patch_scores(query, page[:1024]), atol=1e-6)


def test_padding_ignores_nonzero_weights_text_and_type():
    module = LayoutPatchD()
    with torch.no_grad():
        module.fusion.residual[-1].weight.normal_(std=.02)
    data = layout()
    data["mask"][1] = False
    page = torch.randn(1024, 128)
    before = module(page, data)
    data["text"][1] *= 100
    data["types"][1] = 5
    data["coords"][1] = 1
    assert torch.equal(module(page, data), before)
    assert torch.equal(before[31], page[31])


def test_upstream_receives_signal_after_zero_residual_first_step():
    torch.manual_seed(42)
    module = LayoutPatchD()
    data, p, q = layout(), torch.randn(1024, 128), torch.randn(13, 128)
    pos = torch.zeros(1024, dtype=torch.bool)
    pos[:30] = True
    optimizer = torch.optim.AdamW(module.parameters(), lr=.001)
    first = {}
    for step in range(3):
        optimizer.zero_grad()
        loss = local_contrastive_loss(patch_scores(q, module(p, data)), pos, ~pos)
        loss.backward()
        gradients = {k: float(v.grad.norm()) for k, v in module.named_parameters() if v.grad is not None}
        assert all(torch.isfinite(v.grad).all() for v in module.parameters() if v.grad is not None)
        if step == 0:
            first = gradients
            assert first["nodes.text_proj.weight"] == 0
            assert first["fusion.residual.3.weight"] > 0
        else:
            for key in ("nodes.text_proj.weight", "nodes.coord_proj.weight", "nodes.type_emb.weight", "fusion.value.weight", "fusion.gate.weight"):
                assert gradients[key] > 0
        optimizer.step()


def test_existing_epoch_interface_accepts_document_layout():
    module = LayoutPatchD()
    pos = torch.zeros(1024, dtype=torch.bool)
    pos[:30] = True
    item = {"query": torch.randn(12, 128), "patches": torch.randn(1024, 128),
            "pos": pos, "neg": ~pos, "layout": layout()}
    result = train_epoch(module, torch.optim.AdamW(module.parameters(), lr=.001),
                         [item], random.Random(0), device="cpu")
    assert result["updates"] == 1 and result["nonzero_updates"] == 1
    assert 0 < result["gate_mean"] < 1
    assert result["residual_mlp_l2_mean"] == 0
    assert result["normalized_patch_change_mean"] < 1e-6
    assert module.fusion.residual[-1].weight.abs().sum() > 0
