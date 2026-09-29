# train_fit 独立区域标注方案（设计稿，不是开标许可）

不是训练。不是人工标注启动。不读 `test_eval` 内容。不用 evaluation gold。不改四池 id。不改 `recall_layout`。不改任何 `ranker.pt` / `fusion.pt`。不启动 A 路线 query-conditioned MIL。不编码新页。

本页把 `experiments/2026-09-29-method-route-decision.md` 的 B 路线落成可执行协议。清单和空模板在 `experiments/region_annotation/`。400 行全部 `label_status=pending`，没有 `chosen_box_ids`。

## 0. 一句话

要继续做方法型小论文，必须先给 ArxivQA `train_fit` 补独立框监督。本轮只冻结「点哪些候选框、抽哪些题、怎么质检、训什么、何时停」。还没有标签，不能开训。

## 1. 为什么要标

小论文执行规范 `docs/PAPER_SPEC.md`：

- 第 2.3b：可投稿需要可学习模块 + 三指标同报。2-R 与无条件 fusion 的 `dev_eval` 都没有同时超过 `geom:area`。
- 第 2.4：必须有独立训练数据，不许用 evaluation gold。
- 第 5.7：`L = λ_page L_page + λ_region L_region + λ_distill L_distill`。`L_region` 的正样本必须来自独立训练框标注。
- 第 7.5：evaluation gold 永不进训练。
- 第 8：主指标仍是官方 `recall_layout` Area@K；IoU@0.5 辅助；页级 R@5 同口径。
- 第 11：无独立训练数据又要用 gold 训练即停；dev 不涨不进 test。

现状：`split_proof.json` 里 `train_fit` / `train_dev` 的 `with_layout_gold=0`。训练 jsonl 只有 1 正页 + 1 负页。parquet `layouts` 只有 `bbox` 和 `type`，没有 OCR 字符串，没有答案框。因此当前合法区域标签 = 0。

## 2. 标注对象

只标问题对应的**正页候选框**。负页只保留身份，不点选。

来源限制：

- 只从 ArxivQA `train_fit` 抽。
- 正页和负页都已有 ColPali 页缓存。
- 正页至少 1 个 layout 候选。
- 同一正页只留 1 题（`line_index` 最小），避免一页重复劳动。
- 不打开 `experiments/s2_splits/test_eval_ids.jsonl`。
- 不读 `data/processed/mmdocir_evaluation/region_labels.parquet`。
- 标注界面不得展示 `dev_eval` / `test_eval` 文档、问句或 gold 框。

候选框定义：该正页 parquet `layouts` 的下标 `box_id`，从 0 起，顺序与文件中列表一致。不新画框。训练和评测都走同一套 MinerU 候选，和官方 `recall_layout` 一致。

## 3. 每题要标什么

主值是**多个正框 ID**，不是单个 ID，也不是把 evaluation 式覆盖分抄进来。

| 字段 | 谁填 | 含义 |
| --- | --- | --- |
| `sample_id` | 清单 | 题号，如 `ann-0001` |
| `chosen_box_ids` | 人 | 正页上盖住答案证据的候选下标，可多选，可空 |
| `cover_levels` | 人，可选 | 只给已选框：`full` 或 `partial`。未选框隐式 `none` |
| `cover_ok` | 人 | 已选框合在一起是否盖住答题所需证据 |
| `no_candidate` | 人 | 现有候选都盖不住证据 |
| `cross_box` | 人 | 证据跨多个已选框 |
| `note` | 人 | 短备注，不进训练 |
| `annotator_id` | 系统 | 标注者代号，不是账号密钥 |
| `protocol_version` | 系统 | `region-ann-v0` |
| `labeled_at` | 系统 | UTC 时间 |
| `label_status` | 系统 | `pending` / `labeled` / `skipped` / `adjudicated` |

空模板：`experiments/region_annotation/label_template.jsonl`。字段约束：`experiments/region_annotation/label_schema.json`。

### 3.1 允许多框

允许。一题可以点 1 个或多个候选。官方 Area 允许跨框累加，训练标签也允许多正框。

### 3.2 答案跨多个框

点上所有必要框，`cross_box=true`。不要为了省事只点最大框。不要把无关大框一起点上「凑覆盖」。

### 3.3 没有合适候选

`no_candidate=true`，`chosen_box_ids=[]`，`cover_ok=false`，`label_status=skipped`。这类题**不算训练正样本**，只进完成率统计。禁止手画新框。禁止去 evaluation gold 里找替代框。

判定：看完全部候选后，没有任何一个框（或框的组合）盖住答题所需图/表/公式/文字。宁可标 `no_candidate`，不要猜。

### 3.4 覆盖等级怎么用

训练主损失用二值：选中 = 正框，未选 = 负框。`full` / `partial` 只用于 listwise 权重敏感性，默认 `full=1`、`partial=0.5`。这不是 `y(c)=Area(c∩G)/Area(G)`，因为本方案不画 G，也不借用 evaluation G。

### 3.5 标注者看不到评测池

操作约束，不是口号：

- 只发 `experiments/region_annotation/arxivqa_train_fit_manifest.jsonl` 里的题。
- 页面图像只从 MMDocIR train parquet 按 `pos_doc` + `pos_page` 取。
- 禁止打开 evaluation 313、`dev_eval_ids.jsonl`、`test_eval_ids.jsonl`、`region_labels.parquet`。
- 复标两人独立作答，互不看对方的 `chosen_box_ids`。

## 4. 400 题抽样依据

400 不是统计功效计算，是一次可完成、足够判 `geom:area` 的下限。

| 对照 | 数字 | 用法 |
| --- | --- | --- |
| `dev_eval` 区域分母 | 401 | 标注规模与一次判定集同量级 |
| 方法路线页 | 少于约 200 难稳过面积规则；超过 800 未过 Gate 则浪费 | `experiments/2026-09-29-method-route-decision.md` |
| 双人复标 | 80 / 400 = 20% | 先测一致率，不够再修指南 |
| 内部切分 | 320 拟合 / 80 验证 | 标注集自己做区域早停，不动冻结四池 |

本轮实际抽样（seed=42）：

- 资格池：ArxivQA `train_fit` 已缓存正负页 9246 题，4054 个不重复正页。
- 抽 400 题 = 400 正页 = 356 文档。
- 分层：版式 `layout_bin`（text / image / other）× 候选数三分位 × 最大框相对页面积三分位。
- 候选数切点：low≤5，high≥9。
- 最大框相对面积切点：low≤0.17254954011640838，high≥0.26097577077969236。
- 按层比例分配，稀有层可以为 0。
- 同一正页只留 1 题。
- 领域：本轮只标 ArxivQA。DUDE 及其他域本轮禁止混训，不进清单。文档类型按 ArxivQA 论文页处理；版式层用主导框类型代替「幻灯/表格/双栏」细类。
- 标注子集再按**正页文档**切：`annot_fit` 320 题 / 285 文档，`annot_val` 80 题 / 71 文档。文档不跨切。
- 双人 80 题：`annot_fit` 66，`annot_val` 14。

清单：`experiments/region_annotation/arxivqa_train_fit_manifest.jsonl`。计数：`experiments/region_annotation/sampling_meta.json`。

不改 `train_dev` / `dev_eval` / `test_eval`。`train_dev` 仍只做页级早停（若以后训练保留 `L_page`）。`dev_eval` 只在协议冻结且一次训练完成后判涨跌。

## 5. 质量控制

| 项 | 规则 |
| --- | --- |
| 双人比例 | 80/400 = 20%，分层抽取 |
| 主一致率 | 两套 `chosen_box_ids` 的 Jaccard ≥ 0.8，在 80 题上计算 |
| 辅一致率 | 并集框两两最大 IoU≥0.5 的集合一致率；`no_candidate` 一致率单独报 |
| 冲突 | Jaccard < 1 或 `no_candidate` 不一致 → 第三人按指南裁定，写入 `adjudicated`。裁定只改冲突题，不改抽样名单 |
| 停标 | 80 题 Jaccard 均值 < 0.8，或 `no_candidate` 比例 > 25% → 停标，修指南，不扩 400，不开训 |
| 完成率 | `labeled + skipped + adjudicated` / 400。完成率 < 0.95 不开训 |
| 训练分母 | 只收 `cover_ok=true` 且 `chosen_box_ids` 非空的题 |
| 记录 | `annotator_id`、`protocol_version=region-ann-v0`、`labeled_at`、抽样 seed=42、复标 shuffle seed=43、切分 seed=42 |

元数据另存标注 run 的 `run_info` 风格字段，不写进 evaluation `metrics.json`。

## 6. 训练目标（设计，现在不执行）

这是 PAPER_SPEC 5.7 的 `L_region` 最小实现，不是再训当前 fusion，也不是复活 EXP-009 线性头。

输入仍可用冻结 `P`、离线 `W`、布局节点 `T`（坐标 + 类型；训练 OCR 仍为空则文本为零，过投影，不当文本结果）。

**去掉原始面积特征。** 不准把框面积、相对面积当作可学列。面积只用于分桶采样。

标签：

```text
正框：chosen_box_ids
负框：同页其余候选
hard negative：同页、相对面积与某个正框落在同一分桶、但未被点选的框
no_candidate / skipped：不进 L_region
```

损失优先级：

1. listwise 或 pairwise 区域排序（正框分 > 同页负框分）。
2. 可选、权重预先固定的页级保持项 `L_page`，只比较已有正负页，不改冻结 ColPali 页序。
3. 本轮不设蒸馏新实验。

禁止：

- evaluation gold、`dev_eval` gold、`y(c)=Area(c∩G)/Area(G)` 若 G 来自评测集。
- 只取面积最大的 4 个框进损失。
- 覆盖当前 `artifacts/phase2r/*/ranker.pt` 或 `artifacts/fusion/arxivqa/fusion.pt`。
- A 路线 MIL。

新权重必须写到新目录。

## 7. 最小新实验（批准标注并完成质检之后才允许）

对照，同一 `dev_eval` 415/401、同一 gold 页、同一 `recall_layout`：

- `geom:area`：Area@1 `0.46726432578302896`，Area@5 `0.7726699451254816`，冻结 IoU 214/401。
- 最大框：与 `geom:area` 同一排序。
- `fixed:iou_mass`：Area@1 `0.28594452702337386`，Area@5 `0.7441786161356058`，冻结 IoU 130/401。

必须记录：Area@1、Area@5、IoU@0.5、页级 R@5、效率（向量数/离线/在线/显存）。只超过 `fixed:iou_mass` 不算成功。

dev 成功，三条同时：

```text
Area@1 > 0.46726432578302896
Area@5 > 0.7726699451254816
页级 R@5 相对 0.8939759036144578 变化在 ±0.3 个百分点以内
```

失败即停：不扩标注、不训 fusion、不读 `test_eval`。

## 8. 泄漏

已有冻结证明：

- 训练/评测文档名与问句交集已剔除：`experiments/s2_exclusion/exclusion_proof.json`。
- 四池文档两两交集为空，训练池对 evaluation 313 为空：`experiments/s2_splits/split_proof.json`。
- 本清单 400 题 `line_index` 都在 ArxivQA `train_fit`，不在 `train_dev`。
- 本清单完整文档名与 `experiments/eval313_doc_ids.txt` 交集为 0。
- 未打开 `test_eval_ids.jsonl`。

残留风险，必须写明：

1. `train_fit_ids.jsonl` 的 ArxivQA `doc_names` 仍是截断 stem（如 `1308`），jsonl/parquet 全名是 `1308.1101`。划分身份以 `line_index` 和冻结证明为准，不能用截断名做新的文档对撞。
2. 标注者若看到评测题，会把评测风格带进训练。靠界面隔离，不靠口头提醒。
3. 本方案不消除「官方 Area 偏爱大框」。去面积特征后，仍可能打不过 `geom:area`。那是实验失败，不是泄漏。

结论：按冻结划分，**没有新的 train_fit ↔ evaluation 文档泄漏**。截断文档名是旧口径痕迹，不是把 evaluation 放进训练集。

## 9. 本轮产物

| 文件 | 内容 |
| --- | --- |
| `experiments/2026-09-29-region-annotation-plan.md` | 本协议 |
| `experiments/region_annotation/arxivqa_train_fit_manifest.jsonl` | 400 行待标清单，无标签 |
| `experiments/region_annotation/label_schema.json` | 空 schema |
| `experiments/region_annotation/label_template.jsonl` | 一条空模板 |
| `experiments/region_annotation/sampling_meta.json` | seed、分层、切分、泄漏检查 |

未生成任何 `chosen_box_ids` 实值。未训练。未读 `test_eval`。

## 10. 现在不许做

- 不开始人工标注。
- 不训练。
- 不读、不评分 `test_eval`。
- 不把本页当成开训许可。
