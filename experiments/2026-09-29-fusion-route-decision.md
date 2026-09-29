# 替代网络路线可行性审计

不是训练。不读 `test_eval` 内容。不混训 DUDE。不改当前 fusion。不扩大训练集。不改冻结划分、指标或 `ranker.pt`。

依据：`docs/PAPER_SPEC.md` 第 2.3b、2.4、5.7、7.5、9.1、11 节；`experiments/2026-09-29-fusion-failure-audit.md`；`experiments/2026-09-24-s2-train-audit.md`；`experiments/s2_splits/split_proof.json`。

## 0. 一句话

训练集只有页级正页/负页，没有问题到框的对应标签。当前 fusion 和 2-R 都已经用过这套弱监督，并且都没有超过 `geom:area`。因此：**不建议再训当前 fusion；独立框监督排序现在做不了；小论文按 2.3b 应重定方法。** 若还要再做一次学习实验，只能换成 query 条件的框包 MIL，而且必须先改 C3 叙事。

## 1. 训练集到底有什么

只读 `train_fit` / `train_dev` 用到的 ArxivQA 源，以及已有缓存是否存在。没有打开 `test_eval_ids.jsonl` 的题单内容，没有打分。

### 1.1 jsonl 题（`ArxivQA_train.jsonl`）

字段只有：`query_id`、`query`、`domain`、`positive_passages`、`negative_passages`。

正页/负页各 1 条，条目只有 `doc_name`、`page_id`。前 200 题没有 `y_c`、`coverage`、`gold_bbox`、`evidence_bboxes` 这类框答案字段。

官方 `train_dataset.py` 的口径（已写在 S2 审计）：每题 1 问 + 2 页，无框级 gold。

### 1.2 parquet 页（`ArxivQA_filter.parquet`）

列：`file_name`、`page`、`domain`、`image`、`page_size`、`layouts`。

`layouts` 一项只有 `bbox` 和 `type`。抽 200 页：OCR 字符串数为 0。类型有 `text` / `title` / `table` / `image` / `interline_equation`。

这些框是版式解析候选，不是「这个问题的证据框」。不能当 `G`，因此不能构造

```text
y(c) = Area(c ∩ G) / Area(G)
```

### 1.3 划分与泄漏

| 池 | 题数 | 有布局 gold |
| --- | ---: | ---: |
| train_fit | 57062（ArxivQA 有框子集 9241） | 0 |
| train_dev | 5400（ArxivQA 有框子集 1592） | 0 |
| dev_eval | 415 | 415 |
| test_eval | 1243 | 1243；本轮只确认文件存在，未读内容、未打分 |

`split_proof.json`：`train_fit` / `train_dev` 的 `with_layout_gold=0`。四池文档交集空。`exclusion_proof.json`：剔除后文档名交集空、问句交集空，md5 复用 0。evaluation gold 只在 `dev_eval` 评测，不许进训练。

现有泄漏风险：文本/文档重叠已剔除。剩余风险只有「以后误用 evaluation gold 造 `y(c)`」。当前代码路径没有这样做。

### 1.4 缓存

- 页向量 P：`artifacts/colpali/mmdocir_train/vidore_colpali/`，ArxivQA 训练页已有。
- query：`fit_queries.pt`（9241）、`dev_queries.pt`（1592）、`dev_eval_queries.pt`（415）。
- 框文本：训练 parquet 无 OCR，BGE 框向量为 0，不是文本监督。
- 无框级 `y(c)` 缓存。

### 1.5 结论表

| 问 | 答 |
| --- | --- |
| 是否只有正页/负页？ | 是。监督只有同文档 1 正页 + 1 负页。 |
| 是否有问题与框的对应标签？ | 否。 |
| 是否有页面级答案区域 / OCR 文本 / 其他独立监督？ | 否。有候选框坐标和类型，无答案区域，无 OCR 字符串，无答案字段。 |
| 独立框级标签？ | 无。 |
| evaluation gold 泄漏？ | 已剔除文本/文档重叠；gold 框未进训练。不要用 gold 补标签。 |

## 2. 规范约束（决定哪条路能投稿）

第 2.3b：可投稿需要可学习模块 + 三指标同报。**若 2-R 与全融合 dev 皆不涨，小论文判方法失败，必须重定方法或换路线，不许拿 B1/B2 顶替投稿。** 现状正是这一条：2-R 未超过 `geom:area`，融合 Area@1/5 低于 `geom:area`。

第 5.7 / 7.5：规定的区域监督是独立训练集上的 `y(c)`。train 侧没有 `G`，这条现在执行不了。

C3：`P_fused` 必须 query-independent、离线算好。query 条件打分不是当前 C-b 主线，而是换路线（更接近 Argus 的部署取舍）。

第 11：无独立训练数据又要用 gold 训练 → 即停。复杂融合不如固定聚合 → 即停。当前 fusion 已经不如面积规则。

## 3. 三条路线

### 路线 A. 只有页级标签时的 query-conditioned MIL / attention

**判定：可作为备选。** 不是现在就训。

这是什么：不再改离线 `P→P'`。冻结 ColPali 页向量，用 query 去给**这一页上每个候选框**打分。正页被看成一包框（bag），负页是另一包。MIL（多实例学习）的意思是：只知道整页对/错，不知道哪一个框对，让模型自己在包内加权。

| 项 | 内容 |
| --- | --- |
| 输入 | 已有 Q、P、候选框坐标/类型。文本仍是零。不把原始面积当特征。 |
| 输出 | 每个框一个分数。不输出新的 `P'`。页序仍用冻结 ColPali。 |
| 监督 | 仅 train_fit 正页/负页。包对比：正包包分 > 负包包分。 |
| 去面积捷径 | 禁止面积特征；禁止只取最大 4 框进损失（那是 2-R 的捷径）；按面积分桶采负框；包内 attention 不能退化成「只看最大框」。 |
| 训练 / 评估 | train_fit 拟合，train_dev 早停。一次 `dev_eval`：同一 415/401、同一 `recall_layout`。对照 `geom:area` / 最大框 / `fixed:iou_mass`。 |
| 新代码 / 缓存 | 新打分头 + 新 task。不编码新页。不覆盖 `fusion.pt` / `ranker.pt`。C3 叙事要改，需先批准。 |
| 投稿底线 | 若 dev 超过 `geom:area` 且页级不掉，可尝试改写成 C-b2 变体，但不再是 C3 离线融合。第 9.1 消融仍要做。 |
| 成本 | 低。量级接近 2-R（分钟级，不加载 ColPali）。 |
| 失败风险 | **高。** 同一套页级标签已经让线性头和融合都失败。官方 Area 奖励覆盖、不惩罚大框，去面积后更难超过 `geom:area`。 |

不建议把 A 做成「再训一遍 fusion，只是加上 query」。那仍违反「文档侧离线」并且会重蹈页级 MaxSim 改表征、区域不涨。

### 路线 B. 有独立训练框标签时的候选框监督排序

**判定：不建议（当前不可行）。**

| 项 | 内容 |
| --- | --- |
| 输入 | Q、P、全体候选框。 |
| 输出 | 框排序，或回归 `y(c)`。 |
| 监督 | 必须有独立 `G`。当前 train 没有。 |
| 去面积捷径 | 去掉面积特征；面积匹配负采样；listwise / 回归覆盖分。 |
| 训练 / 评估 | 规范 5.7 的正路。dev 必须超过 `geom:area`。 |
| 新代码 / 缓存 | 框级标签文件 + 新 loss。 |
| 投稿底线 | 若标签来自独立训练标注，符合 2.4「独立训练数据」。 |
| 成本 | 标签不存在。补标是新数据，要另批。 |
| 失败风险 | 现在无法启动。用 evaluation gold 造 `y(c)` 是规范禁止，直接停。 |

### 路线 C. 没有足够监督：改研究问题或补外部标注

**判定：推荐。**

这不是再堆一个网络。2.3b 已经写明：2-R 和全融合 dev 都不涨，就判方法失败，必须重定方法或换路线。

两条子选项，都要导师点头，agent 不选：

1. **改问题 / 改叙事（无新标注）**  
   可写的事实：页级 ColPali 能找页；固定聚合弱于面积规则；页弱监督线性头和融合都没有超过面积规则；文本特征未生效；瓶颈是候选框 + Area 指标偏爱大框。  
   这是可靠负结果。但不能把 B1/B2 单独拿去投小论文。要投，必须另定可学习模块和新监督。

2. **补独立框级标注（外部，不是 evaluation gold）**  
   有了 `G` 才回到路线 B。代价高，要新技术/新数据批准。没有标注就不要假装 B 可做。

| 项 | 内容 |
| --- | --- |
| 输入 / 输出 | 暂不新增网络。 |
| 监督 | 现有数据不够支撑 PAPER_SPEC 5.7 的 `L_region`。 |
| 去面积捷径 | 论文里把 `geom:area` 升为主基线；Area 与 IoU 并列，避免把大框覆盖写成精确定位。 |
| 训练 / 评估 | 本路线本身不训练。 |
| 新代码 | 无。 |
| 投稿底线 | 维持现状则 **不满足 2.3b 方法投稿**。满足的是「方法失败、需重定」这一条。 |
| 成本 | 最低（写清证据）。补标则高。 |
| 失败风险 | 科学风险低。投稿风险是：若不换方法，小论文没有可学习增益。 |

## 4. 为什么推荐 C，而不是再训 A

1. 没有独立框标签，5.7 的 `L_region` 无法按原文执行。
2. 页级弱监督已经在打分层和 `P→P'` 上各失败一次；再换 MIL 仍是同一监督。
3. 成功线是 Area 超过 `geom:area`，而官方 Area 天然偏向最大框。去捷径和学习目标打架。
4. A 要改 C3，属于换路线，不是当前 fusion 的修补。
5. 第 11 节：无独立数据却用 gold、以及复杂融合不如规则，都该停。

A 只在导师明确同意「放弃 C3、只做一次 query 条件框包实验」时才启动。B 在有独立框标注之前不启动。

## 5. 最小下一实验（现在不执行）

现在 **不训练**。下面是若导师批准路线 A 时的最小一次实验。失败立即停，不搜超参，不混 DUDE，不读 `test_eval`。

```text
范围：只 ArxivQA train_fit 9241 / train_dev 1592。
模型：query-conditioned 框包 MIL/attention。冻结 P。不改 fusion.pt。
禁止：原始面积特征；只拿最大 K 框进损失；evaluation gold；新页编码。
早停：只看 train_dev 的页包对比，不看 test_eval。
判定：一次 dev_eval，分母 415/401，官方 recall_layout，页序冻结 ColPali。
成功：Area@1 > 0.46726432578302896 且 Area@5 > 0.7726699451254816
      且页级 R@5 相对 0.8939759036144578 变化在 ±0.3 个百分点内。
失败：立即停止扩展。转路线 C，不补 DUDE、不回调 fusion。
```

未批准前，这一段不是开训许可。

## 6. 本轮未做

未训练。未读 `test_eval` 内容。未改权重。未实现 A/B。
