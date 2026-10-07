"""EXP-016只验证输入干预、有效容量、选择门与同时比较。"""
import copy
import importlib.util
from pathlib import Path

import pytest
import torch

from layoutpatch.evaluation.localization import doc_bootstrap_diff
from layoutpatch.retrieval.route_v2_attribution import (
    VARIANTS,
    assert_all_selected,
    attribution_statistics,
    make_variant,
)
from layoutpatch.retrieval.route_v2_layout import LayoutPatchD, page_layout
from layoutpatch.retrieval.route_v2_scoring import local_contrastive_loss, patch_scores


def layout():
    rows = [{"layout_id": 1, "type": "text", "bbox": [20, 0, 224, 224], "page_size": [448, 448]},
            {"layout_id": 2, "type": "table", "bbox": [224, 0, 448, 224], "page_size": [448, 448]}]
    return page_layout(rows, torch.randn(2, 1024))


@pytest.mark.parametrize("name,field", [("D-no-text", "text"), ("D-no-coord", "coords")])
def test_only_declared_node_input_is_zeroed_without_mutating_cache(name, field):
    torch.manual_seed(9)
    module, original = make_variant(name), LayoutPatchD()
    with torch.no_grad():
        module.fusion.residual[-1].weight.normal_(std=.03)
    original.load_state_dict(module.state_dict())
    data = layout()
    snapshot = {k: v.clone() for k, v in data.items()}
    page = torch.randn(1031, 128)
    observed = {}

    def capture_nodes(_module, args):
        observed["text"], observed["coords"], observed["types"], observed["mask"] = args

    def capture_fusion(_module, args, kwargs):
        observed["W_attn"], observed["cover_mass"] = args[1], args[3]
        observed["fusion_mask"] = kwargs["node_mask"]

    module.nodes.register_forward_pre_hook(capture_nodes)
    module.fusion.register_forward_pre_hook(capture_fusion, with_kwargs=True)
    output = module.forward_page(page, data)
    expected = original.forward_page(page, {**data, field: torch.zeros_like(data[field])})
    assert torch.equal(output, expected)
    assert not torch.equal(output[:1024], original.forward_page(page, data)[:1024])
    assert torch.count_nonzero(observed[field]) == 0
    for key in ("text", "coords", "types", "mask", "W_attn", "cover_mass"):
        if key != field:
            assert torch.equal(observed[key][0], snapshot[key])
    assert torch.equal(observed["fusion_mask"][0], data["mask"])
    assert all(torch.equal(data[k], snapshot[k]) for k in data)
    assert torch.equal(output[1024:], page[1024:])
    assert torch.equal(output[:1024][data["cover_mass"].squeeze(-1) == 0], page[:1024][data["cover_mass"].squeeze(-1) == 0])
    changed = {**data, field: torch.randn_like(data[field]) * 100}
    assert torch.equal(output, module.forward_page(page, changed))


def test_wide_capacity_is_nearest_and_all_parameters_learn():
    torch.manual_seed(3)
    module = make_variant("C-wide")
    count = sum(p.numel() for p in module.parameters())
    assert count == 273318 and abs(count / 273410 - 1) <= .01
    assert all(abs(count - 273410) < abs(257 * h + 384 - 273410) for h in (1061, 1063))
    p, q = torch.randn(1024, 128), torch.randn(12, 128)
    assert torch.allclose(patch_scores(q, module(p)), patch_scores(q, p), atol=1e-6)
    pos = torch.zeros(1024, dtype=torch.bool)
    pos[:40] = True
    optimizer = torch.optim.AdamW(module.parameters(), lr=.001)
    for _ in range(2):
        optimizer.zero_grad()
        loss = local_contrastive_loss(patch_scores(q, module(p)), pos, ~pos)
        loss.backward()
        optimizer.step()
    assert all(param.grad is not None and torch.isfinite(param.grad).all() and param.grad.norm() > 0 for param in module.parameters())


def test_all_nine_selections_required():
    choices = {name: {s: {"checkpoint": f"{s}.pt"} for s in (0, 1, 2)} for name in VARIANTS}
    assert_all_selected(choices, [0, 1, 2])
    for name in VARIANTS:
        broken = copy.deepcopy(choices)
        del broken[name][2]
        with pytest.raises(ValueError, match="all checkpoints"):
            assert_all_selected(broken, [0, 1, 2])
    with pytest.raises(ValueError, match="three variants"):
        assert_all_selected({"C-wide": choices["C-wide"]}, [0, 1, 2])


def test_document_bootstrap_preserves_old_intervals_and_corrects_entire_family():
    reference = {f"q{i}": (i % 3) / 2 for i in range(30)}
    docs = {f"q{i}": f"doc{i // 3}" for i in range(30)}
    values = {name: {q: v * factor for q, v in reference.items()} for name, factor in zip(VARIANTS, [.5, 1., 1.5], strict=True)}
    result = attribution_statistics(reference, values, docs)
    assert list(result) == [f"D-{v}" for v in VARIANTS]
    for name in VARIANTS:
        expected = doc_bootstrap_diff(reference, values[name], docs)
        actual = result[f"D-{name}"]
        assert all(actual[k] == v for k, v in expected.items())
        assert actual["bonferroni_ci_low"] <= actual["ci95_low"] <= actual["ci95_high"] <= actual["bonferroni_ci_high"]
        assert actual["documents"] == 10 and actual["queries"] == 30
    assert result["D-C-wide"]["adjusted_positive"]
    assert not result["D-D-no-text"]["adjusted_positive"]
    assert result["D-D-no-coord"]["adjusted_negative"]
    with pytest.raises(ValueError, match="three prespecified"):
        attribution_statistics(reference, {"C-wide": values["C-wide"]}, docs)
    del values["D-no-text"]["q0"]
    with pytest.raises(ValueError, match="denominator"):
        attribution_statistics(reference, values, docs)


def test_frozen_config_inherits_exact_budget_and_saved_predictions_reject_mismatch(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("exp16_runner", scripts / "run_route_v2_exp3.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    config, baseline = runner.load_config()
    assert all(config[k] == baseline[k] for k in runner.SHARED)
    assert config["maximum_training_runs"] == 9
    with pytest.raises(ValueError, match="denominator"):
        runner.check_saved_methods([], [], {}, ("C", "D"))
