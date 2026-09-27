# S2 审计：train 数据清点 + 泄漏 5 项 + 标签审计（2026-09-24）

> 状态：审计完成，泄漏已剔除。证据：`experiments/s2_exclusion/exclusion_proof.json`。训练仍禁止。划分已冻结，见 `experiments/2026-09-26-dev-test-split-frozen.md`。

## 1. 清点（data/raw/mmdocir_train/hf_hub）

- 来源：`MMDocIR/MMDocIR_Train_Dataset`（镜像 `hf-mirror.com`），见 `DATASET_CARD.txt`。
- jsonl（7 域，TOP1_NEG 命名，parquet 侧 DUDE_long 对应 DUDE_train.jsonl）：
  ArxivQA 10838 / DUDE 2715 / MP-DocVQA 6122 / SciQAG 4496 / SlideVQA 11606 / TAT-DQA 14249 / Wiki-ss 15293，合计 65319 题。
- parquet（7 域，页图 + page_size + layouts）：67845 页。文档数有两套口径，差 2050，不是两批文档：
  - 32963：页图 `file_name` 原文字符串去重。同一个文档如果一页写成 `foo.pdf`、另一页写成 `foo`，会算成两个。
  - 30913：去掉结尾 `.pdf` 之后的文档名去重。jsonl 问句里的 `doc_name` 用同一规则去重也是 30913，两边文档集合相同。
  - 2050 = 32963 − 30913，全部来自这层后缀重复，不是漏掉的文档。剔除和泄漏对撞用 30913 这一套。
  页均框：ArxivQA 8.0 / DUDE 7.9 / MP-DocVQA 7.9 / SciQAG 10.5 / SlideVQA 4.6 / TAT-DQA 9.4 / Wiki-ss 15.7；0 框页存在（除 SciQAG/Wiki-ss 外各域有）。
- 官方 `train_dataset.py`：每步返回 1 问 + 2 页（1 正页 + 1 负页），只用 `doc_name + page_id`，**无框级 gold**。

## 2. 泄漏 5 项

1. train/doc 与 eval/313 文档名交集：24 个文档。已剔除，不是待剔除。证据：`experiments/s2_exclusion/exclusion_proof.json`。
2. query 文本（小写、只删空格和制表符）交集：38 句。已剔除。eval 去重问句是 1631，不是 1632。旧数 1632 没有对应的漏剔问句；同一规则重算是 1658 题、12 组重复、多出 27 行，1658 − 27 = 1631。重复组在 `experiments/s2_exclusion/eval_duplicate_queries.json`。最大一组是 `What is the title of the document?`，跨 10 个文档。旧数多 1，是把跨文档重复少算了一条，不是少掉某一句。
3. 标签构造规则：jsonl 只有页级正负（同文档内 top1 负例），无框监督；`layouts` 为附带候选框，不能当 gold。
4. 硬负例：同文档内页（`negative_passages` 与正例同 `doc_name`），与 eval 文档内检索范围一致，无跨文档泄漏便利。
5. evaluation gold 隔离：本审计只读 eval 的 doc_id/question 作交集比对，未将 eval 框标签拷入任何训练输入。

## 3. 标签审计（2-R 可用性）

- 直接框监督：无。`y(c)=Area(c∩G)/Area(G)` 在 train 侧无 G 可用，**不可直接构造**。
- 可用监督尚未批准：页级弱监督和框先验只是候选，不是已批准 loss。
- 不可用：0 框页（SlideVQA 等）只能出页级对、无框排序对，自动落入 B2 口径，不进 2-R 训练。
- 结论：train 侧没有框级强监督，全融合所需标签不存在。2-R 是否可练，留到划分方案下一轮讨论。本文件不批准开训。

## 4. 剔除状态

用户已认可剔除证据。并集已落盘：剔除前 65319 题 / 30913 文档，剔除 118 题，剔除后 65201 题 / 30889 文档。训练仍禁止。本文件不批准开训，不冻结 dev/test 划分。
