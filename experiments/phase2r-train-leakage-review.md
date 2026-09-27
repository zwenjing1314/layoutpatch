# Phase 2-R 训练泄漏审查（前置门槛，缺一即停）

> 状态：文本泄漏已剔除；md5 复用数为 0；dev/test id 已冻结。训练仍禁止。本页不是开训许可。

## 1. eval 侧（已完成，2026-09-22）

- eval 313 文档清单：`experiments/eval313_doc_ids.txt`（313 行，来自 `documents.parquet`）。
- 训练数据已到本地：`data/raw/mmdocir_train/hf_hub/`（7 域 jsonl + 7 域页图 parquet）。旧句「本地无数据」作废。

## 2. train 侧（2026-09-26 回填）

归一化规则（两边同一套，写在 `experiments/s2_exclusion/text_overlap_summary.json`）：

- 文档名：取文件名主干，只去掉结尾的 `.pdf`（不区分大小写）。
- 问句：转小写，只删普通空格和制表符。

```text
[x] 布局标签来源与缺失率
    证据：experiments/2026-09-24-s2-train-audit.md 第 3 节。
    train 无框级 gold，layouts 只是候选框。2-R 不能用 evaluation gold 造 y(c)。
[x] 文档名交集已剔除
    重叠清单：experiments/s2_exclusion/overlap_doc_names.txt（24 行）。
    剔除后交集为空：experiments/s2_exclusion/exclusion_proof.json 的 doc_intersection_after。
[x] 问句交集已剔除
    重叠清单：experiments/s2_exclusion/overlap_queries.json（38 个归一化问句，对应 47 条 train 题）。
    剔除后交集为空：exclusion_proof.json 的 query_intersection_after。
[x] 页图 md5 复用审已完成，复用数 = 0，未触发停工
    证据：experiments/s2_exclusion/md5_reuse.json。
    评测 20395 页、训练 67845 页，空字节都是 0，原始图片字节 md5 对撞命中 0。
    eval 内部 20395 页对 20275 个 md5，120 页是评测集内部重复，不是 train 复用，不触发停工。
[x] evaluation gold 未进训练输入；dev/test 划分已冻结
    id：experiments/s2_splits/。规则：experiments/2026-09-26-dev-test-split-frozen.md。
    冻结不是开训许可。不许用 evaluation gold 构造 y(c)。
```

## 3. 剔除结果（不是训练许可）

并集 = 24 个重叠文档的全部 train 题 + 38 句重叠问句的全部 train 题 + md5 命中。md5 命中为 0，没有并入新题。

| | 题数 | 文档数 |
| --- | ---: | ---: |
| 剔除前 | 65319 | 30913 |
| 剔除 | 118 | 24 |
| 剔除后 | 65201 | 30889 |

118 = 文档命中 87 + 问句命中 47 − 两边都命中 16。保留清单是 `experiments/s2_exclusion/kept_train_ids.jsonl`，剔除清单是 `excluded_train_ids.jsonl`。

## 4. 结论

阈值已在 `experiments/2026-09-22-threshold-frozen.md` 冻结，不再构成禁令。dev/test 划分已冻结（`experiments/2026-09-26-dev-test-split-frozen.md`）。训练禁令仍在：本轮没有批准开训。禁止建 `fusion/`、写 `train_fusion.py`、用 evaluation gold 构造 `y(c)`、用 `T_oracle≥0.5` 过滤 train。
