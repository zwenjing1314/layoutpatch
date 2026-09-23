# Phase 2-R 训练泄漏审查（前置门槛，缺一即停）

> 状态：部分完成。eval 侧已落盘；train 侧本地无数据，2-R 训练保持禁止。

## 1. eval 侧（已完成，2026-09-22）

- eval 313 文档清单：`experiments/eval313_doc_ids.txt`（313 行，来自 `documents.parquet`）。
- 训练标签现状：MMDocIR train（6878 文档 / 73k+ query / 仅部分有布局标签）本地**不存在**（`data/raw` 仅有 `mmdocir_evaluation`），官方仓库（已搬迁为 `MMDocIR_research/`）`dataset/` 下也只有 eval 三件（annotations.jsonl + layouts.parquet + pages.parquet）。

## 2. train 侧（待办，训练解禁的前置条件）

按 `docs/PAPER_SPEC.md` 第 5.7 节清单，获取 train 数据后必须逐项落盘，任一不满足即停：

```text
[ ] 布局标签来源与缺失率（MinerU/人工比例；3/7 子集无布局标签即不可训 2-R）
[ ] train 6878 与 eval313 doc_id 交集必须为 0（用本文件的 eval313_doc_ids.txt 对撞）
[ ] train/eval query 文本归一化后完全相同条数 >0 即剔除并记录
[ ] page/layout 图像 md5 级复用审（复用即停）
[ ] evaluation gold 永不进训练；dev/test 划分先于训练冻结
```

## 3. 结论

2-R 训练（含重排头）在此文件第 2 节全勾选前**保持禁止**；阈值冻结（`2026-09-22-threshold-proposal.md`）同样未完成，两禁令叠加。
