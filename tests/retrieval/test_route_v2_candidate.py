"""唯一 E 候选排序头的定向合成测试。"""

import copy

import pytest
import torch

from layoutpatch.evaluation.localization import rank_candidates
from layoutpatch.retrieval.route_v2_candidate import (
    EXPECTED_PARAMETERS,
    CandidateRankerE,
    candidate_supervision,
    frozen_candidate_features,
    multi_positive_candidate_loss,
    trainable_parameter_count,
    training_filter_audit,
)


def example():
    torch.manual_seed(7)
    query = torch.randn(5, 128)
    query[-1].zero_()
    patches = torch.randn(8, 128)
    w_raw = torch.zeros(8, 4)
    w_raw[:4, 0] = 1
    w_raw[4:, 1] = 0.5
    w_raw[:, 3] = 100  # padding 的非零权重必须被忽略。
    mask = torch.tensor([True, True, True, False])
    features = frozen_candidate_features(query, patches, w_raw, mask)
    coords = torch.rand(4, 6)
    types = torch.tensor([1, 3, 5, 2])
    score_b = torch.tensor([0.2, 0.1, -0.4, 9.0])
    return features, coords, types, score_b


def score(module, data):
    features, coords, types, score_b = data
    return module(
        features["x"],
        features["visual"],
        coords,
        types,
        features["candidate_mask"],
        features["nonempty_w"],
        score_b,
    )


def test_parameter_count_and_zero_init_equal_B_scores_and_stable_ranking():
    module = CandidateRankerE()
    data = example()
    scores = score(module, data)
    assert trainable_parameter_count(module) == EXPECTED_PARAMETERS == 272_593
    assert torch.equal(scores[:3], data[-1][:3])
    assert torch.isneginf(scores[3])
    ids = [8, 2, 5]
    tied = [0.4, 0.4, 0.4]
    assert rank_candidates(tied, ids) == [1, 2, 0]
    assert rank_candidates(scores[:3].tolist(), ids) == rank_candidates(
        data[-1][:3].tolist(), ids
    )


def test_multi_positive_loss_and_units_without_both_classes_are_rejected():
    scores = torch.tensor([1.0, 0.5, -0.5], requires_grad=True)
    positive = torch.tensor([True, True, False])
    negative = torch.tensor([False, False, True])
    loss = multi_positive_candidate_loss(scores, positive, negative, tau=0.25)
    expected = torch.logsumexp(scores / 0.25, 0) - torch.logsumexp(
        scores[:2] / 0.25, 0
    )
    assert float(loss.detach()) == pytest.approx(float(expected.detach()))
    loss.backward()
    assert bool(torch.isfinite(scores.grad).all())
    for pos, neg in (
        (torch.zeros(3, dtype=torch.bool), torch.ones(3, dtype=torch.bool)),
        (torch.ones(3, dtype=torch.bool), torch.zeros(3, dtype=torch.bool)),
    ):
        with pytest.raises(ValueError, match="at least one positive and one negative"):
            multi_positive_candidate_loss(scores.detach(), pos, neg)


def test_empty_W_padding_and_text_are_isolated_from_E():
    module = CandidateRankerE()
    data = example()
    features, coords, types, score_b = data
    assert features["nonempty_w"].tolist() == [True, True, False, False]
    assert torch.equal(features["visual"][2:], torch.zeros_like(features["visual"][2:]))
    with torch.no_grad():
        module.mlp[-1].weight.normal_(std=0.02)
        module.mlp[-1].bias.fill_(0.1)
    before = score(module, data)
    changed_padding = (
        features,
        coords.clone(),
        types.clone(),
        score_b.clone(),
    )
    changed_padding[1][3] = 100
    changed_padding[2][3] = 5
    changed_padding[3][3] = -100
    after = score(module, changed_padding)
    assert torch.equal(before[:3], after[:3])
    assert before[2] == score_b[2]  # 空 W 候选不使用学习修正。
    assert torch.isneginf(before[3])


def test_gradient_and_parameters_update_after_zero_initialization():
    module = CandidateRankerE()
    before = copy.deepcopy(module.state_dict())
    data = example()
    positive = torch.tensor([True, False, False, False])
    negative = torch.tensor([False, True, True, False])
    optimizer = torch.optim.AdamW(module.parameters(), lr=0.001)
    upstream_seen = False
    for step in range(3):
        optimizer.zero_grad(set_to_none=True)
        loss = multi_positive_candidate_loss(score(module, data), positive, negative)
        loss.backward()
        gradients = {
            name: float(parameter.grad.norm())
            for name, parameter in module.named_parameters()
            if parameter.grad is not None
        }
        assert gradients["mlp.2.weight"] > 0
        assert all(torch.isfinite(parameter.grad).all() for parameter in module.parameters())
        if step > 0:
            upstream_seen |= gradients["coord_proj.weight"] > 0
            upstream_seen |= gradients["type_emb.weight"] > 0
            upstream_seen |= gradients["mlp.0.weight"] > 0
        optimizer.step()
    assert upstream_seen
    assert any(not torch.equal(value, before[name]) for name, value in module.state_dict().items())


def test_supervision_filter_is_D_subset_and_reports_exclusions():
    units = [
        {
            "unit_id": name,
            "role": role,
            "local_loss_ready": ready,
            "page_overlap_excluded": excluded,
            "gold_boxes": [[0, 0, 10, 10]],
        }
        for name, role, ready, excluded in (
            ("ok", "source_train", True, False),
            ("no-pos", "source_train", True, False),
            ("no-neg", "source_train", True, False),
            ("old-filter", "source_train", False, False),
            ("external", "external_test", True, False),
        )
    ]
    boxes = {
        "ok": [[0, 0, 10, 10], [20, 20, 30, 30]],
        "no-pos": [[20, 20, 30, 30]],
        "no-neg": [[0, 0, 10, 10]],
    }
    nonempty = {name: torch.ones(len(value), dtype=torch.bool) for name, value in boxes.items()}
    selected, audit = training_filter_audit(units, boxes, nonempty)
    assert selected == ["ok"]
    assert audit["original_D_training_units"] == 3
    assert audit["E_trainable_units"] == audit["D_E_intersection_units"] == 1
    assert audit["exclusion_reasons_exclusive"] == {
        "no_negative_candidate": 1,
        "no_positive_candidate_iou_ge_0.5": 1,
    }
    positive, negative = candidate_supervision(
        boxes["ok"], units[0]["gold_boxes"], threshold=0.5
    )
    assert positive.tolist() == [True, False]
    assert negative.tolist() == [False, True]
