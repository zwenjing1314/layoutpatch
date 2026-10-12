"""冻结 P 的查询条件候选排序对照 E。"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

import torch
from torch import nn
from torch.nn.functional import normalize

from layoutpatch.evaluation.region_metrics import bbox_iou
from layoutpatch.layout.nodes import sinusoidal_coord
from layoutpatch.retrieval.route_v2_scoring import LOCAL_TAU, valid_query

DIM = 128
COORD_WIDTH = 72
NUM_TYPES = 6
HIDDEN = 680
EXPECTED_PARAMETERS = 272_593


class CandidateRankerE(nn.Module):
    """在冻结候选特征上学习 ``score_B + residual``。"""

    def __init__(self) -> None:
        super().__init__()
        self.coord_proj = nn.Linear(COORD_WIDTH, DIM)
        self.type_emb = nn.Embedding(NUM_TYPES, DIM)
        self.mlp = nn.Sequential(
            nn.Linear(3 * DIM, HIDDEN),
            nn.GELU(),
            nn.Linear(HIDDEN, 1),
        )
        nn.init.zeros_(self.mlp[-1].weight)
        nn.init.zeros_(self.mlp[-1].bias)

    def forward(
        self,
        x: torch.Tensor,
        visual: torch.Tensor,
        coords: torch.Tensor,
        type_ids: torch.Tensor,
        candidate_mask: torch.Tensor,
        nonempty_w: torch.Tensor,
        score_b: torch.Tensor,
    ) -> torch.Tensor:
        """计算候选分数；padding 为 ``-inf``，空 W 候选保留 B 分数。"""
        count = visual.shape[0]
        if (
            x.shape != (count, DIM)
            or visual.shape != (count, DIM)
            or coords.shape != (count, 6)
            or type_ids.shape != (count,)
            or candidate_mask.shape != (count,)
            or nonempty_w.shape != (count,)
            or score_b.shape != (count,)
        ):
            raise ValueError("candidate feature shapes do not match E interface")
        if candidate_mask.dtype != torch.bool or nonempty_w.dtype != torch.bool:
            raise ValueError("candidate masks must be boolean")
        if bool((nonempty_w & ~candidate_mask).any()):
            raise ValueError("nonempty W cannot belong to padding")
        layout = self.coord_proj(sinusoidal_coord(coords.float(), COORD_WIDTH))
        layout = layout + self.type_emb(type_ids.long())
        layout = layout * candidate_mask.unsqueeze(-1).to(layout.dtype)
        correction = self.mlp(torch.cat((x, visual, layout), dim=-1)).squeeze(-1)
        if not bool(torch.isfinite(correction).all()):
            raise FloatingPointError("nonfinite E correction")
        correction = correction * nonempty_w.to(correction.dtype)
        result = score_b + correction
        return torch.where(candidate_mask, result, torch.full_like(result, -math.inf))


def frozen_candidate_features(
    query: torch.Tensor,
    patches: torch.Tensor,
    w_raw: torch.Tensor,
    candidate_mask: torch.Tensor,
) -> dict[str, torch.Tensor]:
    """由冻结 Q/P 和 W_raw 计算逐维交互 x 与候选视觉表示 v。"""
    if patches.ndim != 2 or patches.shape[1] != DIM:
        raise ValueError("patches must be [N,128]")
    if w_raw.shape != (patches.shape[0], candidate_mask.numel()):
        raise ValueError("W_raw must be [N,M]")
    if candidate_mask.dtype != torch.bool:
        raise ValueError("candidate_mask must be boolean")
    if not all(bool(torch.isfinite(value).all()) for value in (query, patches, w_raw)):
        raise FloatingPointError("nonfinite frozen E input")
    if bool((w_raw < 0).any()):
        raise ValueError("W_raw must be nonnegative")
    weights = w_raw.float() * candidate_mask.unsqueeze(0).to(w_raw.dtype)
    mass = weights.sum(dim=0)
    pooled = (weights.T @ patches.float()) / mass.clamp_min(1e-12).unsqueeze(-1)
    nonempty = candidate_mask & (mass > 0)
    visual = torch.where(
        nonempty.unsqueeze(-1),
        normalize(pooled, dim=-1),
        torch.zeros_like(pooled),
    )
    q = valid_query(query)
    interaction = (q[:, None, :] * visual[None, :, :]).amax(dim=0)
    interaction = interaction * nonempty.unsqueeze(-1).to(interaction.dtype)
    if not all(bool(torch.isfinite(value).all()) for value in (visual, interaction, mass)):
        raise FloatingPointError("nonfinite frozen E feature")
    return {
        "x": interaction.detach(),
        "visual": visual.detach(),
        "candidate_mask": candidate_mask.detach(),
        "nonempty_w": nonempty.detach(),
        "w_mass": mass.detach(),
    }


def candidate_supervision(
    boxes: Sequence[Sequence[float]],
    gold_boxes: Sequence[Sequence[float]],
    *,
    threshold: float = 0.5,
) -> tuple[torch.Tensor, torch.Tensor]:
    """任一 gold 的 IoU 达阈值即为正例，其他候选为负例。"""
    if not gold_boxes or not 0 < threshold <= 1:
        raise ValueError("candidate supervision needs gold boxes and a valid threshold")
    positive = torch.tensor(
        [any(bbox_iou(box, gold) >= threshold for gold in gold_boxes) for box in boxes],
        dtype=torch.bool,
    )
    return positive, ~positive


def multi_positive_candidate_loss(
    scores: torch.Tensor,
    positive: torch.Tensor,
    negative: torch.Tensor,
    *,
    tau: float = LOCAL_TAU,
) -> torch.Tensor:
    """多正例对比损失；无正例或无负例的 unit 不得用于更新。"""
    if tau <= 0:
        raise ValueError("tau must be positive")
    if (
        positive.dtype != torch.bool
        or negative.dtype != torch.bool
        or positive.shape != scores.shape
        or negative.shape != scores.shape
        or bool((positive & negative).any())
    ):
        raise ValueError("positive/negative must be disjoint boolean score masks")
    if not bool(positive.any()) or not bool(negative.any()):
        raise ValueError("candidate loss needs at least one positive and one negative")
    active = positive | negative
    if not bool(torch.isfinite(scores[active]).all()):
        raise FloatingPointError("nonfinite active E candidate score")
    logits = scores / tau
    return torch.logsumexp(logits[active], dim=0) - torch.logsumexp(
        logits[positive], dim=0
    )


def training_filter_audit(
    units: Sequence[dict],
    boxes_by_unit: dict[str, Sequence[Sequence[float]]],
    nonempty_w_by_unit: dict[str, torch.Tensor],
    *,
    threshold: float = 0.5,
) -> tuple[list[str], dict]:
    """审计原 D 训练分母，并得到其内部可训练的 E unit。"""
    source_train = [unit for unit in units if unit["role"] == "source_train"]
    d_units = [
        unit
        for unit in source_train
        if unit["local_loss_ready"] and not unit["page_overlap_excluded"]
    ]
    reasons: Counter[str] = Counter()
    selected: list[str] = []
    empty_w_candidates = 0
    for unit in sorted(d_units, key=lambda value: value["unit_id"]):
        unit_id = unit["unit_id"]
        boxes = boxes_by_unit[unit_id]
        nonempty = nonempty_w_by_unit[unit_id].bool()
        if len(boxes) != nonempty.numel():
            raise ValueError("candidate/W denominator mismatch in training audit")
        empty_w_candidates += int((~nonempty).sum())
        if not boxes:
            reasons["no_candidates"] += 1
            continue
        positive, negative = candidate_supervision(
            boxes, unit["gold_boxes"], threshold=threshold
        )
        if not bool(positive.any()):
            reasons["no_positive_candidate_iou_ge_0.5"] += 1
        elif not bool(negative.any()):
            reasons["no_negative_candidate"] += 1
        elif not bool((positive & nonempty).any()):
            reasons["no_positive_after_empty_w_exclusion"] += 1
        elif not bool((negative & nonempty).any()):
            reasons["no_negative_after_empty_w_exclusion"] += 1
        else:
            selected.append(unit_id)
    audit = {
        "source_train_units": len(source_train),
        "original_D_training_units": len(d_units),
        "E_trainable_units": len(selected),
        "D_E_intersection_units": len(selected),
        "E_is_subset_of_D": True,
        "excluded_units": len(d_units) - len(selected),
        "exclusion_reasons_exclusive": dict(sorted(reasons.items())),
        "empty_W_candidates_in_D_units": empty_w_candidates,
        "label_relation": (
            "same_annotation_source_but_candidate_level_IoU_labels; "
            "not_the_same_label_granularity_or_identical_training_set"
        ),
    }
    if len(selected) + sum(reasons.values()) != len(d_units):
        raise ValueError("training exclusion audit does not close")
    return selected, audit


def trainable_parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)
