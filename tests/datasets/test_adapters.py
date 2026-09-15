"""MMDocIR prepare adapter tests (batch M2).

覆盖三件事（新手向）：
1. demo 样例不依赖外部数据，随时可跑，断言 2 文档 / 3 页 / 4 节点 / 3 查询；
2. mmdocir 入口在原始数据缺失时不崩溃，而是写 README 说明并返回 0 计数；
3. 未知数据集名直接报错，防止拼写错误静默跑错数据。
"""

from __future__ import annotations

import pytest

from layoutpatch.datasets import prepare_dataset, prepare_demo


def test_demo_counts() -> None:
    result = prepare_demo()

    assert (result.documents, result.pages, result.nodes, result.queries) == (2, 3, 4, 3)


def test_demo_limit_docs_filters_children() -> None:
    result = prepare_demo(limit_docs=1)

    assert result.documents == 1
    assert result.pages == 2
    assert result.nodes == 3
    assert result.queries == 2


def test_mmdocir_missing_raw_data_returns_zero_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAYOUTPATCH_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT", str(tmp_path / "empty-raw"))

    result = prepare_dataset("mmdocir")

    assert (result.documents, result.pages, result.nodes, result.queries) == (0, 0, 0, 0)
    assert (tmp_path / "data" / "processed" / "mmdocir_evaluation" / "README.md").exists()


def test_unknown_dataset_raises() -> None:
    with pytest.raises(ValueError, match="Unknown dataset"):
        prepare_dataset("cn_annual_reports")
