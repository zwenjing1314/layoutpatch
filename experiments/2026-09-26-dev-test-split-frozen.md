# 划分冻结（frozen）

> 状态：frozen。用户 2026-09-26 有条件确认方案页。本页是切分规则，不是开训许可。
> 方案页 `experiments/2026-09-26-dev-test-split-proposal.md` 保留为历史，不再执行。
> id 与证明：`experiments/s2_splits/`。

## 1. 切分规则

- seed = 42。
- 文档名先按归一化名排序，再用 `random.Random(42).shuffle` 洗牌，然后按文档比例切。
- 归一化名：去掉结尾 `.pdf`，不区分大小写。
- 训练池 30889 文档：前 90% 进 `train_fit`（27800），后 10% 进 `train_dev`（3089）。
- 评测集 313 文档：前 30% 进 `dev_eval`（93），后 70% 进 `test_eval`（220）。
- 比例是文档比例。题数偏了不改比例。

## 2. 四池计数

| 池子 | 文档数 | 题数 | 有布局 gold 的题数 |
| --- | ---: | ---: | ---: |
| train_fit | 25577 | 57062 | 0 |
| train_dev | 713 | 5400 | 0 |
| dev_eval | 93 | 415 | 415 |
| test_eval | 220 | 1243 | 1243 |

训练池题数少于 65201，是因为跨文档正负页整题剔除了 2739 题。57062 + 5400 + 2739 = 65201。这 2739 题不进 `train_fit`，也不进 `train_dev`。清单：`experiments/s2_splits/train_cross_doc_dropped.jsonl`。

四池文档名两两交集为空。训练池（含这 2739 题的文档）与评测 313 文档交集仍为空。证明：`experiments/s2_splits/split_proof.json`。

## 3. 各池用途

- `train_fit` 只学参数，标签只用训练集自带页级正负页。
- `train_dev` 只做页级早停。
- `dev_eval` 只调区域超参，并判涨跌。对照在同一子集重算，不直接拿全集 0.2787 当子集分数。
- `test_eval` 本轮只记 id，不打分。

历史全集基线 EXP-001、EXP-007-S1 不因这次划分作废。

## 4. 三句禁止

- 不用 evaluation gold 构造 `y(c)`。
- 不用 `T_oracle≥0.5` 过滤 train。
- 本页不是开训许可。不建 `fusion/`，不写 `train_fusion.py`。
