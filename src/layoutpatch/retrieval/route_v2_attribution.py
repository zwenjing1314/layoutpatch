"""EXP-016固定输入消融与三项同时比较；不改变原D。"""
from __future__ import annotations

import random
import statistics

import torch

from layoutpatch.evaluation.localization import doc_bootstrap_diff, question_macro
from layoutpatch.retrieval.route_v2_exp1 import assert_dev_ready
from layoutpatch.retrieval.route_v2_layout import LayoutPatchD
from layoutpatch.retrieval.route_v2_scoring import PatchAdapter

VARIANTS = ("C-wide", "D-no-text", "D-no-coord")


class InputAblatedD(LayoutPatchD):
    def __init__(self, zero_input: str):
        super().__init__()
        if zero_input not in {"text", "coords"}:
            raise ValueError("only text or explicit coordinates may be ablated")
        self.zero_input = zero_input

    def forward(self, patches, layout):
        # 新字典避免改写共享页面缓存；几何权重和节点mask保持原对象。
        inputs = {**layout, self.zero_input: torch.zeros_like(layout[self.zero_input])}
        return super().forward(patches, inputs)


def make_variant(name: str):
    if name == "C-wide":
        return PatchAdapter(hidden=1062)
    if name == "D-no-text":
        return InputAblatedD("text")
    if name == "D-no-coord":
        return InputAblatedD("coords")
    raise ValueError(f"unregistered variant: {name}")


def assert_all_selected(selected, seeds):
    if set(selected) != set(VARIANTS):
        raise ValueError("all three variants required before source_dev")
    for choices in selected.values():
        assert_dev_ready(choices, seeds)


def averaged_questions(methods, label, seeds):
    values = [question_macro(methods[f"{label}_seed_{s}"], "hit1@0.5") for s in seeds]
    if any(set(v) != set(values[0]) for v in values):
        raise ValueError("seed question denominator mismatch")
    return {q: statistics.mean(v[q] for v in values) for q in sorted(values[0])}


def attribution_statistics(reference, variants, doc_of, *, iterations=2000, seed=0):
    if set(variants) != set(VARIANTS) or not reference:
        raise ValueError("three prespecified comparisons required")
    if any(set(values) != set(reference) for values in variants.values()):
        raise ValueError("paired question denominator mismatch")
    by_doc = {}
    for q in sorted(reference):
        by_doc.setdefault(doc_of[q], []).append(q)
    docs = sorted(by_doc)
    rng = random.Random(seed)
    samples = {name: [] for name in VARIANTS}
    # 三项复用同一组文档抽样，题内三seed先平均，绝不将seed视作独立样本。
    for _ in range(iterations):
        questions = [q for doc in (rng.choice(docs) for _ in docs) for q in by_doc[doc]]
        for name in VARIANTS:
            samples[name].append(sum(reference[q] - variants[name][q] for q in questions) / len(questions))
    tail = .05 / (2 * len(VARIANTS))
    result = {}
    for name in VARIANTS:
        values = sorted(samples[name])
        raw = doc_bootstrap_diff(reference, variants[name], doc_of, iterations=iterations, seed=seed)
        # 保证补充统计使用原95%区间完全相同的重采样与分位数规则。
        if raw["ci95_low"] != values[int(.025 * iterations)] or raw["ci95_high"] != values[int(.975 * iterations)]:
            raise ValueError("bootstrap resampling differs from existing protocol")
        low, high = values[int(tail * iterations)], values[min(iterations - 1, int((1 - tail) * iterations))]
        result[f"D-{name}"] = {**raw, "bonferroni_ci_low": low, "bonferroni_ci_high": high,
                               "adjusted_positive": low > 0, "adjusted_negative": high < 0}
    return result
