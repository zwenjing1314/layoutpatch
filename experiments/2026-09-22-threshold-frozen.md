# 阈值冻结（frozen，导师已定 B）

> 状态：frozen。导师 2026-09-24 回复"B可以"。以本文件为准，提案页维持 proposal 历史状态。
> 生效：2-R 训练集筛选只执行 T_oracle；gap 只观察不设线。训练仍须 S2（train 数据 + 泄漏 5 项）完成后才解禁。

- T_oracle：2-R 训练集只收 union-oracle@1 ≥ 0.5 的页命中题（覆盖 eval1390 的 93.31%；低于此线者自动落入 B2 诊断，不进训练）。
- gap：Oracle@1 − L3最好@1（当前 0.9136−0.2787=0.63）只观察，2-R 跑完看 dev 涨幅再定，不作门槛。
- 依据数全部来自 EXP-007 对齐表（eval1390 口径），见 `experiments/2026-09-22-threshold-proposal.md`。
- 签字：导师（2026-09-24）+ 用户转达；落盘人 agent。
