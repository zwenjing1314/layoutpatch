# A/B 40 题验收、独立一致性与无训练排序诊断

不是训练。不是扩到 400 题。不是开训许可。未读 `dev_eval` / `test_eval` / evaluation gold。未改冻结划分、候选框、指标或任何 `ranker.pt`。未自动裁定人工标签。未加载视觉编码器。未编码新页。

## 1. A/B 验收结果

集合都对上：A、B 各 40 题，`sample_id` 与 `arxivqa_pilot_manifest.jsonl` 1:1，无重复/漏题/额外题，协议全部 `region-ann-v1`，候选 `box_id` 合法。格式检查**都未通过**。人工标签未改。manifest 未写入。旧 `labels_annotator_A.jsonl` 未覆盖。

| 标注者 | 集合 | 格式 | labeled | pending | skipped | SHA-256 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A | 通过 | 失败 | 37 | 2 | 1 | `acfb7bf62b41334db7fa92c03f81bdbf7af86d08af76077955cb69d637b888a5`（与上次验收相同，复用归档） |
| B | 通过 | 失败 | 38 | 1 | 1 | `7209e3bf497c80cf8dc2f142af68df2d32c7c7dfaadf8c161fb57cc1a26fb964`（本轮按字节新归档） |

A 阻塞：`ann-0378`、`ann-0380` 仍是 `pending`，但 `cover_ok/no_candidate/cross_box=false`，协议要求 pending 保持 null。

B 阻塞：

- `ann-0317`：`label_status=pending`，却填了 `chosen_box_ids=[0,2,3]` 和 `cover_levels`。
- `ann-0373`：`skipped` + `no_candidate=true`，但 `cross_box=true`；协议要求 skipped 时 `cross_box=false`。

A 的 `ann-0158` 是 skipped / 无候选。B 的 `ann-0373` 想标无候选，但字段自相矛盾。多个独立充分框未强制 `cross_box=true`，这符合 v1。

## 2. 独立一致性（裁定前）

校准题确认：`ann-0004`（协议登记）、`ann-0018`（题目含 Figure (A) descending part，即“图A下降段”）。没有其他可确认编号的共同讨论题，不猜。校准题保留在数据中，**不进独立一致率分母**。

| 口径 | 题数 | 题号 |
| --- | ---: | --- |
| 总题数 | 40 | pilot 全表 |
| 校准题 | 2 | ann-0004, ann-0018 |
| 任一方 pending | 3 | ann-0317, ann-0378, ann-0380 |
| 可比较 | 35 | 其余；pending 不当负例 |
| 双方空集（Jaccard 不计满分） | 0 | 无 |

- Jaccard 分母 = 35（双方都非空或一方有框一方确认无候选；双方空集 0 题）。
- 均值 Jaccard = 0.8357142857142859。
- 完全一致率 = 26/35 = 0.7428571428571429。
- `no_candidate` 一致率 = 33/35 = 0.9428571428571428。
- `cover_ok` 分歧 2；`cross_box` 分歧 1。
- 共同选择框的 full/partial：40 框中 38 一致。

计划稿内部门槛 Jaccard≥0.8 只是质检线，不是正确率证明。均值刚过 0.8，完全一致率只有 26/35，且校准题 `ann-0018` 选了完全不同的框（A=图框0，B=正文框1）。

## 3. 必须人工复核的题

不取交集或并集当 gold。优先：

1. 无候选分歧：`ann-0158`（A 无候选，B 选 1）、`ann-0373`（A 选 0，B 想标无候选且字段非法）。
2. pending 字段非法：`ann-0317`（B）、`ann-0378`/`ann-0380`（A pending，B 已选 0）。
3. 图 vs 正文替代证据：校准题 `ann-0018`；可比较题 `ann-0133`、`ann-0150`、`ann-0160`、`ann-0234`、`ann-0328`、`ann-0357`、`ann-0395`。
4. 协议风险（大框/图注/正文）：大量一致题备注都写“候选过粗，含图+图注”。这不是单题错误，是候选粒度和“直接证据”口径问题。
5. A 备注导出残留：`ann-0234`、`ann-0365`。A `ann-0108` 缺 cover_levels（协议允许空，需确认是否故意）。A `ann-0395` 备注写联合，同时有 full 且 `cross_box=false`。

完整表：`experiments/region_annotation/archive/2026-09-30_ab_diagnosis/disagreement_review.md`。

## 4. 面积规则剩余排序空间

分母是该标注者非 pending 题；校准题单列。不隐藏困难题。

| 统计 | A 非校准 36 | A 校准 2 | A labeled∧cover_ok 37 | B 非校准 37 | B 校准 2 | B labeled∧cover_ok 38 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 候选合计 / 正框合计 | 266 / 52 | 13 / 4 | 276 / 56 | 266 / 47 | 13 / 3 | 277 / 50 |
| 平均正框比例 | 0.328 | 0.298 | 0.335 | 0.299 | 0.226 | 0.303 |
| 全部候选都是正框 | 5 | 0 | 5 | 5 | 0 | 5 |
| 无同页负框 | 6 | 0 | 5 | 6 | 0 | 5 |
| 最大框是正框 | 31 | 2 | 33 | 31 | 0 | 31 |
| 面积 Top-1 覆盖全部正框 | 19 | 1 | 20 | 24 | 0 | 24 |
| 面积 Top-3 覆盖全部正框 | 27 | 1 | 28 | 30 | 1 | 31 |

含义：多数题最大框已经是正框，但面积 Top-1 **没有**覆盖全部正框（A 20/37，B 24/38）。因此仍有多正框/漏选大框的排序空间。全部候选都为正的 5 题两边相同：`ann-0066`、`ann-0104`、`ann-0119`、`ann-0163`、`ann-0310`；这些题没有同页负框，不能当对比学习负例。pilot 文档切分仍是 `annot_fit` 33 / `annot_val` 7，但 pending 和字段错误会再吃掉可用题，当前不能把 33/7 当成训练分母。

## 5. 无训练语义对照

诊断指标，不是官方 Area。禁止与 0.4673 / 0.7727 比较。
分母：`labeled ∧ cover_ok=true ∧ 已选框非空 ∧ line_index 能映射到 fit_queries.pt`。
映射按 9241 条 boxed `train_fit` 顺序，不是 9246 条仅有页缓存的行；query 文本和正页身份已核对。A 分母 37，B 分母 38，缓存缺口 0。未加载编码器。

公式：Hit@K = 任一正框进入 Top-K；Recall@K = |Top-K ∩ 正框| / |正框|；MRR = 第一个正框名次的倒数。full/partial 不改成面积权重。

| 方法 | 标签 | n | Hit@1 | Hit@3 | Recall@1 | Recall@3 | MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 面积降序 | A | 37 | 0.8919 | 1.0000 | 0.6937 | 0.8919 | 0.9369 |
| fixed:iou_mass | A | 37 | 0.5135 | 0.7838 | 0.4099 | 0.6441 | 0.6719 |
| 框内 patch MaxSim | A | 37 | 0.5946 | 0.9189 | 0.5045 | 0.7838 | 0.7643 |
| 面积降序 | B | 38 | 0.8158 | 1.0000 | 0.7149 | 0.9167 | 0.8991 |
| fixed:iou_mass | B | 38 | 0.4474 | 0.7105 | 0.3904 | 0.6491 | 0.6170 |
| 框内 patch MaxSim | B | 38 | 0.5263 | 0.8684 | 0.4825 | 0.8114 | 0.7113 |

相对面积的 Hit@1 胜/平/负：

- A / iou_mass：0 / 20 / 14（另有 3 题只在 MRR 上输）
- A / region_maxsim：2 / 20 / 13（2 题 MRR 输）
- B / iou_mass：0 / 18 / 14（6 题 MRR 输）
- B / region_maxsim：3 / 18 / 14（3 题 MRR 输）

“面积选错、语义选对”（Hit@1）可复核样本：`ann-0098`、`ann-0389`（A 与 B 的 region_maxsim）；B 另有 `ann-0234`。iou_mass 校正后没有这类样本。双方完全一致的 26 题补充：面积 Hit@1=0.8846，region_maxsim=0.6154，iou_mass=0.5000。这是选择偏差子集，不能代表困难题。

40 题波动很大。当前冻结 ColPali 语义聚合整体弱于面积，不能据此说路线必然可行或不可行。

## 6. 唯一下一步

**先修标签/协议。**

理由：集合齐了，但格式未过；3 题 pending 不能当负例；无候选和“图/正文/大框”分歧正好打在 v1 口径上；独立 Jaccard 均值刚过内部门槛，完全一致率只有 26/35；校准题 `ann-0018` 完全不一致。面积规则仍强，现有无训练语义对照没有稳定优势。此时扩到 400 或开训，只会放大协议噪声。

不建议现在做极小监督验证。若以后标签修好，方案只能是：沿用 `annot_fit/annot_val` 文档切分，先重数实际可用题（现在清单 33/7，不是训练分母）；只训一个轻量框打分头，对照面积降序；冻结 ColPali；CPU 可跑完；早停看 annot_val 的 Hit@1/MRR，不看 official Area，不碰 `dev_eval`/`test_eval`。40 题只能测可学习性，不能证明投稿效果。本轮不做。

过程记录仍缺：A/B 的模型名、提示词、原始回复、人工改动日志。协议允许 A=DeepSeek、B=Gemini，但不能倒推本次实际使用情况。

## 7. 产物路径

- A 归档（复用）：`experiments/region_annotation/archive/2026-09-30_annotator_A_v1/`
- B 归档（新建）：`experiments/region_annotation/archive/2026-09-30_annotator_B_v1/`
- 独立副本：`experiments/region_annotation/labels_annotator_A_v1.jsonl`、`labels_annotator_B_v1.jsonl`
- 诊断：`experiments/region_annotation/archive/2026-09-30_ab_diagnosis/diagnosis.json`
- 一致率：`.../agreement.json`
- 分歧表：`.../disagreement_review.md`
- 本报告：`experiments/2026-09-30-region-ann-ab-diagnosis.md`

Downloads 原文件保留。未训练。未读评测 gold。
