# 方法型小论文继续推进方案审计

不是训练。不读 `test_eval` 内容。不混训 DUDE。不改 2-R / fusion 权重。不用 evaluation gold 当训练标签。不编码新页。不把论文改成失败分析稿。

本轮本地提交：`f946a1d`（未推远程）。

## 0. 一句话

仓库里没有独立区域监督。要继续做**方法型**小论文，唯一推荐是：先在 `train_fit` 上补少量独立框标注，再训面积去偏的候选框排序头。不要同时开 query 条件 MIL。

## 1. 只读数据源

### 1.1 `train_fit` / `train_dev` 字段

池文件只存身份，不含答案框：

- `experiments/s2_splits/train_fit_ids.jsonl`：`domain`、`line_index`、`query_id`、`doc_names`、`normalized_query`
- `experiments/s2_splits/train_dev_ids.jsonl`：同上

题文件（7 域 jsonl 各读首行，未读 `test_eval`）：

| 文件 | 题字段 | 正/负页字段 |
| --- | --- | --- |
| ArxivQA / DUDE / MP-DocVQA / SciQAG / SlideVQA / TAT-DQA | `query_id`, `query`, `domain`, `positive_passages`, `negative_passages` | `doc_name`, `page_id` |
| Wiki-ss | 同上但无 `domain` | `doc_name`, `page_id` |

页文件（7 域 `*_filter.parquet` 各 1 页）：列 `file_name`, `page`, `domain`, `image`, `page_size`, `layouts`。`layouts` 只有 `bbox`, `type`。无 OCR 字符串，无答案框。

`split_proof.json`：`train_fit` / `train_dev` 的 `with_layout_gold=0`。

### 1.2 仓库内是否另有区域监督

| 来源 | 是否可用作训练标签 |
| --- | --- |
| 训练 jsonl 正负页 | 只有页级，已用于 2-R 和 fusion，未超过 `geom:area` |
| 训练 parquet 框 | 版式候选，不是问题证据 |
| `data/processed/mmdocir_evaluation/region_labels.parquet` | evaluation gold，只许评测 |
| `dev_eval` 415 题 | 有布局 gold，只许评测 |
| 训练侧 OCR / 答案区域 / 问题到框 | 无 |

### 1.3 外部公开标注

MMDocIR train 官方接口本身就没有框级 gold。DocVQA / InfographicsVQA 等公开集可能有答案框，但本仓库没有这些训练标签，使用它们需要新数据、新编码，本轮禁止。DUDE 混训本轮禁止。因此：**当前可合法、可立即使用的独立区域标签 = 0。**

### 1.4 `test_eval` 边界（未打开内容）

- 路径存在：`experiments/s2_splits/test_eval_ids.jsonl`
- 大小：135880 字节
- 权限：只记 id，不打分；本文件未读其中题单
- 训练禁止引用该池的文档、问句、gold

## 2. 两条方法路线

### A. query-conditioned MIL / attention

页级正负已经知道「哪一页对」，不知道「哪一个框对」。MIL（多实例学习）把正页看成一包框，用 query 给框加权。

| 项 | 内容 |
| --- | --- |
| 输入 | 已有 Q、P、布局框坐标/类型。文本仍为零。 |
| 输出 | 每框一个分数。不改离线 `P'`。页序仍冻结 ColPali。 |
| 监督 | 仅正页包分 > 负页包分。 |
| 去面积捷径 | 不用原始面积特征；不用「只取最大 4 框」；按面积分桶采负框；检查 attention 是否塌成最大框。 |
| 代码 / 缓存 | 新打分头 + 新 task。不编码新页。不覆盖现有 checkpoint。须改 C3（不再是 query-independent 文档侧融合）。 |
| 最小规模 | ArxivQA `train_fit` 9241 / `train_dev` 1592，一次 `dev_eval`。 |
| 成功概率 | 低。同一套页级标签已让线性头和 fusion 失败。官方 Area 偏爱大框。 |
| 主要风险 | 学到的仍是页级匹配，不是框定位；即使涨也可能是面积捷径；投稿须改 C-b/C3 叙事，接近 Argus 而不是当前主线。 |

投稿底线：有可训练参数和独立页级数据，但 **C-c 尚未成立**，且与 C3 冲突。值得投入：**否（作为下一唯一实验）**。实现成本低，失败风险高。

### B. 独立区域监督（先补少量标注）

当前没有现成 `G`。evaluation gold 不许当训练标签。因此要在 **训练池文档** 上新标「这个问题对应哪些候选框」。

**标注对象：** 只从 ArxivQA `train_fit` 里已有页缓存、且正页至少 1 框的题中抽。不用 `dev_eval` / `test_eval` 文档，不用 evaluation 313。

**每题字段：**

```text
query_id, doc_name, page_id,
chosen_box_ids,          # 在该页 layouts 候选上多选
cover_ok,                # 候选是否盖住证据；否则记 no_candidate
optional_note            # 短备注，不进训练
```

优先点选已有候选框，不新画框。这样训练和评测都走同一套 MinerU 候选，和官方 `recall_layout` 一致。

**切分：** 标注集内部 80% 拟合、20% 区域早停，全部落在 `train_fit` 文档。`train_dev` 仍只做页级早停。`dev_eval` 只在标注协议冻结后判一次涨跌。`test_eval` 仍不读。

**防泄漏：** 标注名单与 `eval313_doc_ids.txt` 文档名交集必须为空（训练池剔除后本应为空，标注脚本再断言一次）。禁止打开 `test_eval_ids.jsonl` 选题。

**最小规模：** 400 题（正页点选）。其中 80 题双人复标。理由：少于约 200 题很难稳定超过面积规则；超过 800 题未先过小规模 Gate 则浪费。400 是一次可完成、足够判 `geom:area` 的下限。

**训练目标 / 网络：**

```text
y(c) = 1 若候选被点选，否则 0
      或软标签：点选框与其余框的覆盖互不借用 evaluation gold
```

冻结 ColPali `P`。输入：query 与框内 patch 的 `fixed:iou_mass` 分、坐标、类型。**不把原始框面积当作可学特征。** 输出：全体候选排序。loss：listwise / pairwise，面积分桶负采样。这是 PAPER_SPEC 5.7 的 `L_region` 最小实现，不是再训 fusion。

**强基线：** `geom:area`、最大框、`fixed:iou_mass`。同一 401 题、同一 `recall_layout`。

**质量检查：** 双人 80 题的框集合 IoU≥0.5 一致率；一致率 < 0.8 则停标、修指南。记录标注协议、seed、题单路径。

投稿底线：独立标注满足 2.4「独立训练数据、不用 evaluation gold」。若 `dev_eval` 超过 `geom:area` 且页级不掉，C-b2 + C-c 才可能成立。实现成本中（人工），失败风险中（标注噪声、Area 仍偏大框）。值得投入：**是，作为唯一下一实验。**

## 3. 比较

| | A MIL | B 独立标注 |
| --- | --- | --- |
| 2.3b / 2.4 | 结构可写，但缺能涨的区域监督；改 C3 | 监督对齐 5.7；不改 C3 |
| 成本 | 低，已有缓存 | 中，约 400 题点选 |
| 失败风险 | 高（已失败两次的同一监督） | 中（新信号，仍须打过面积规则） |
| 现在是否投入 | 不 | 是 |

## 4. 唯一推荐

**B。先补少量独立标注，再做面积去偏的候选框排序。**

不存在可用独立区域标签，所以不能直接开监督训练。不推荐先做 A：页级弱监督已经在 2-R 和 fusion 上失败，再换 MIL 仍是同一标签。不要两条一起做。

## 5. 最小下一实验（现在不执行，需批准标注）

```text
数据：ArxivQA train_fit 已缓存正页；标注 400 题点选候选框；内部 320/80。
      不用 test_eval，不用 evaluation gold，不混 DUDE，不编码新页。
网络：冻结 P；query + 框 patch 分 + 坐标/类型 → 框分。无面积特征。
loss：listwise/pairwise + 面积分桶负采样。页级保持项可选，权重预先固定。
基线：geom:area、最大框、fixed:iou_mass。
dev 成功：Area@1 > 0.46726432578302896 且 Area@5 > 0.7726699451254816
         且页级 R@5 相对 0.8939759036144578 变化在 ±0.3pp 内。
失败即停：标注一致率 < 0.8，或一次 dev_eval 未过上述线 → 不扩标注、不训 fusion、不读 test_eval。
```

未批准标注前，不是开训许可。

## 6. 本轮未做

未训练。未读 `test_eval` 内容。未改权重。未开始标注。本地提交未推远程。
