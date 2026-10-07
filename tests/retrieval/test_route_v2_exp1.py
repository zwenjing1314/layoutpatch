"""正式runner的合成协议测试，不访问真实开发集。"""
import copy
import random

import pytest
import torch

from layoutpatch.retrieval.route_v2_exp1 import (
    EarlyStopping,
    assert_dev_ready,
    macro_summary,
    paired_statistics,
    select_units,
    train_epoch,
)
from layoutpatch.retrieval.route_v2_scoring import (
    PatchAdapter,
    local_contrastive_loss,
    patch_iou_matrix,
    patch_scores,
    region_scores,
)


def test_roles_training_exclusions_and_eval_eligibility_are_separate():
    units = [{"unit_id": str(i), "role": role, "local_loss_ready": loss, "page_overlap_excluded": excluded,
              "eval_ready": ready} for i, (role, loss, excluded, ready) in enumerate([
                  ("source_train", True, False, True), ("source_train", True, True, True),
                  ("source_train", False, False, True), ("source_val", False, False, True),
                  ("source_dev", True, False, True), ("source_val", True, False, False)])]
    assert [u["unit_id"] for u in select_units(units, "source_train", training=True)] == ["0"]
    assert [u["unit_id"] for u in select_units(units, "source_val")] == ["3"]
    assert len(select_units(units, "source_train")) == 3
    with pytest.raises(ValueError, match="parameter updates"):
        select_units(units, "source_dev", training=True)
    with pytest.raises(ValueError, match="forbidden"):
        select_units(units, "quarantine")


def test_early_stopping_strict_ties_keep_earliest_checkpoint():
    stop = EarlyStopping(patience=5)
    assert stop.observe(1, 0.5) == (True, False)
    for epoch in range(2, 6):
        assert stop.observe(epoch, 0.5) == (False, False)
    assert stop.observe(6, 0.49) == (False, True)
    assert stop.best_epoch == 1
    with pytest.raises(FloatingPointError):
        stop.observe(7, float("nan"))
    stop = EarlyStopping()
    for epoch, score in enumerate([0.1, 0.2, 0.2, 0.3], 1):
        stop.observe(epoch, score)
    assert stop.best_epoch == 4 and stop.stale == 0


def test_dev_gate_requires_all_three_selected_checkpoints():
    with pytest.raises(ValueError):
        assert_dev_ready({0: {"checkpoint": "a"}, 1: {"checkpoint": "b"}}, [0, 1, 2])
    assert_dev_ready({s: {"checkpoint": str(s)} for s in range(3)}, [0, 1, 2])


def test_question_macro_not_unit_mean_and_seed_pairing_not_pseudoreplication():
    rows = [{"query_id": "q1", "score": 1.0}, {"query_id": "q1", "score": 0.0}, {"query_id": "q2", "score": 1.0}]
    assert macro_summary(rows, ["score"])["metrics"]["score"] == .75
    seeds = [{"q1": 1., "q2": 0.}, {"q1": 0., "q2": 1.}, {"q1": 1., "q2": 1.}]
    result = paired_statistics(seeds, {"q1": 0., "q2": 0.}, {"q1": 1., "q2": 1.}, {"q1": "doc", "q2": "doc"})
    assert result["C_minus_B"]["queries"] == 2
    assert result["C_minus_B"]["documents"] == 1
    assert result["C_minus_B"]["mean_diff"] == pytest.approx(2 / 3)
    assert result["C_minus_A"]["mean_diff"] == pytest.approx(-1 / 3)
    assert result["C_std"] == pytest.approx(0.28867513459481287)
    with pytest.raises(ValueError):
        paired_statistics(seeds[:2], {}, {}, {})


def items(n=5):
    pos = torch.zeros(1024, dtype=torch.bool)
    pos[:30] = True
    return [{"query": torch.randn(12, 128), "patches": torch.randn(1024, 128), "pos": pos, "neg": ~pos} for _ in range(n)]


def test_accumulation_averages_actual_tail_group_and_matches_reference():
    torch.manual_seed(8)
    model = PatchAdapter()
    reference = copy.deepcopy(model)
    data = items()
    class GradientRecorder(torch.optim.AdamW):
        def __init__(self, params):
            super().__init__(params, lr=.001, weight_decay=.01)
            self.recorded = []

        def step(self, closure=None):
            self.recorded.append([p.grad.clone() for group in self.param_groups for p in group["params"]])
            # 测试只记录梯度，固定参数排除AdamW放大微小浮点差异。

    opt = GradientRecorder(model.parameters())
    other = GradientRecorder(reference.parameters())
    result = train_epoch(model, opt, data, random.Random(0), device="cpu")
    order = list(range(5))
    random.Random(0).shuffle(order)
    for group in (order[:4], order[4:]):
        other.zero_grad(set_to_none=True)
        losses = [local_contrastive_loss(patch_scores(data[i]["query"], reference(data[i]["patches"])), data[i]["pos"], data[i]["neg"]) for i in group]
        torch.stack(losses).mean().backward()
        torch.nn.utils.clip_grad_norm_(reference.parameters(), 1., error_if_nonfinite=True)
        other.step()
    assert result["updates"] == 2 and result["nonzero_updates"] == 2
    for actual_group, expected_group in zip(opt.recorded, other.recorded, strict=True):
        for actual, expected in zip(actual_group, expected_group, strict=True):
            assert torch.allclose(actual, expected, atol=1e-7, rtol=1e-5)


def test_nan_gradient_stops_before_optimizer_step():
    model = PatchAdapter()
    before = copy.deepcopy(model.state_dict())
    model.net[-1].weight.register_hook(lambda g: torch.full_like(g, float("nan")))
    with pytest.raises(FloatingPointError, match="gradient"):
        train_epoch(model, torch.optim.AdamW(model.parameters()), items(1), random.Random(0), device="cpu")
    assert all(torch.equal(v, before[k]) for k, v in model.state_dict().items())


def test_zero_residual_region_scores_equal_frozen_propagation():
    item = items(1)[0]
    iou = patch_iou_matrix([[0, 0, 100, 100], [30, 20, 448, 448]], [448, 448])
    b = region_scores(patch_scores(item["query"], item["patches"]), iou)
    c = region_scores(patch_scores(item["query"], PatchAdapter()(item["patches"])), iou)
    assert torch.allclose(b, c, atol=1e-6, rtol=0)
