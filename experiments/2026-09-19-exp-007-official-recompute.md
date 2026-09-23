# EXP-007 官方口径重算：冻结输入上的 L1/L2/L3 三层表（只重算，不改 Gate）

## 1. 实验目的

- 一句话：把 EXP-001 冻结页排序与 EXP-006 冻结 Top-1 选框，放到 MMDocIR 官方 `recall_layout` 口径下重算一遍，产出 L1/L2/L3 三层表，与旧 IoU 数双轨并列。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 5 关门后重算；本次只出数，不改任何 Gate、不冻新阈值、不判进 2-R 还是收缩（见第 11 节）。

## 2. 环境

- 运行环境：本机有 GPU（RTX 3080Ti 12GB）；但本次重算为纯 CPU 只读脚本（bbox 交集几何计算，不加载任何模型），无 GPU 调用、无视觉重编码、无训练。
- 官方源码唯一事实来源：`C:/Users/WenJing/Documents/WorkTransfer/MMDocIR/metric_eval.py`（`calculate_overlap_score` + `recall_layout` + `top_k_indices` 语义逐行移植，见脚本头部注释）。

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split；query 全集 1658，gold 共 2638 行。
- 审计字段（只描述数据来源，不当官方口径下的训练/评测分组）：行级精确查户口 `matched 2523 / unmapped 115`；题级 `1598（含 both 2：mmdocir_00036/00491）/ unmapped_only 60`。官方 `recall_layout` 不要求精确相等，同一 gold 可被多候选累加给分，因此 `matched/unmapped` 只作诊断分层，不作“可用/不可用”二分。
- 对账单（冻结）：`2638=2523+115`（行级）；`1598+60=1658`（题级）；`1343A+45B+2A纯unmapped命中+255D matched+13D unmapped_only=1658`（IoU 口径类级，辅助）；`47=45B+2A`（页命中级 unmapped 口径）；零面积单列 `mmdocir_00700 [300,100,300,450]`（1 行 1 题，全零，按官方 `gt_area==0→0.0`，不进训练分母）。
- 冻结输入（只读，不重编码）：
  - 页排序：`runs/retrieval/mmdocir_colpali/20260916_134144/predictions.parquet`（EXP-001，30112 hits）
  - 选框：`artifacts/baselines/mmdocir_1c/phase1c_picks.json`（EXP-006，1388 题逐题 Top-1 pick；group 三档为自组框 None，本次只评 5 个固定候选法）
  - gold：`data/processed/mmdocir_evaluation/region_labels.parquet`
  - 候选：`data/processed/mmdocir_evaluation/nodes.parquet`（170338 行）

## 4. 配置文件

- 无新 config；单脚本：`scripts/run_phase1c_official_recompute.py`（EXP-007 runner；官方函数 verbatim port + L1/L2/L3 + union-clipped 敏感性 + 旧 IoU 原样附录）。

## 5. 运行命令

```powershell
uv run python scripts/run_phase1c_official_recompute.py
```

- 约 16.3 秒；输出 `artifacts/baselines/mmdocir_1c_official/exp007_official_recompute.json`。
- `./tasks.ps1 check` 原样（2026-09-19 EXP-007 提交前实跑）：ruff 全过 + 44 pytest 全绿（`check: all green`）。

## 6. 代码 commit

- commit：`225792a`（EXP-007 入库）+ 本轮修订另起 commit；JSON 产物在 `artifacts/` 本地（不进 git），路径记入 registry。
- 是否干净：以提交时 `git status --short` 为准；他人未提交改动本轮不碰、不入库。
- 禁令确认：未新建 `fusion/` 子包，未写 `train_fusion.py`，无可训练参数；evaluation gold 只用于打分。

## 7. 输出目录

- `artifacts/baselines/mmdocir_1c_official/exp007_official_recompute.json`（L1/L2/L3 + 旧 IoU 附录 + elapsed_s=16.3）

## 8. 关键指标（JSON 原样抄）

### 8.1 L1 页级（冻结 EXP-001，文档内范围，官方 top_k 排序语义）

| 指标 | 值 |
| --- | --- |
| page_recall@1 | 0.5724 |
| page_recall@5 | 0.8384 |
| page_recall@10 | 0.9041 |

### 8.2 L2 候选覆盖上限（同页全候选，无模型分数）

| 分母 | 指标 | 官方原样 | union-clipped |
| --- | --- | --- | --- |
| 全集 1658（天花板 headline） | oracle_area_recall@1 | 0.9093 | 0.9093 |
| 全集 1658 | oracle_area_recall@5 | 1.1234 | 0.9714 |
| 全集 1658 | oracle_area_recall@10 | 1.1542 | 0.9778 |
| 对齐 1390（与 L3 同分母，算 gap 用这行） | oracle_area_recall@1 | 0.9136 | 0.9136 |
| 对齐 1390 | oracle_area_recall@5 | 1.1345 | 0.9724 |
| 对齐 1390 | oracle_area_recall@10 | 1.1670 | 0.9787 |

- 对齐 1390 = 1388 冻结 picks + 2 回填（`mmdocir_00520/00672`，同冻结方法，`phase1c_picks_backfill_2.json`）= 页命中全集；“1343A/45B”只是来源名，A/B 标签不参与任何官方口径计算。
- L2-full 与 L2-eval1390 只差 0.004，说明页未命中题不改变“候选充足”的全集结论；但算 Oracle−实际 gap 必须用对齐行。
- 口径警告：官方原样可超 1（重叠候选不去重，同一 gold 可重复计面积），@5/@10 超 1 即证据；union-clipped 截到 [0,1]，两者并列、不混称。

### 8.3 L3 实际 Top-1（冻结 picks + 2 回填；eval1390 主分母 + full1658 参考分母）

读表方法：**行 = 5 种无训练选框规则**（每题各选 1 个框，见下）；**列 = 同一规则在两种分母、两种口径下的平均面积召回 + ≥0.5 题数**。`eval1390` 是 picks 实际覆盖的 1390 题 = 1388 冻结 + 2 回填（页命中全集；A/B 只是来源名）；`full1658` 把剩下 268 题（页未中 D）按 0 计入，仅作参考，判 gap 以 eval1390列为准（与 L2 对齐行同分母）。

1658 与 1390 差值构成（2026-09-22 逐题核对，已验证 `picks ⊆ 页命中集`）：

```text
1658 全集 = 1390 页命中 + 268 页未中(D)
1390 页命中 = 1388 冻结 picks + 2 回填(mmdocir_00520/00672，同冻结方法；回填前 EXP-006 建集时被旧口径漏掉)
268 无 picks = 268 D（页未中，区域分天然 0）
```

各实验用的数据（口径声明）：EXP-001 页检索用全集 1658；EXP-006 选框原只在 1388 上有 picks，本轮回填 2 题后 = 页命中全集 1390；EXP-007 的 L1 用全集、L2 出全集 headline + 对齐 1390 两行、L3 主列 eval1390 + 参考列 full1658（268 按 0 计，**不是**官方指标，仅看稀释幅度）。

5 种规则（EXP-006 原样，无训练，共用同一份冻结 patch 分；详见 `experiments/2026-09-17-exp-006-phase1c.md` 与 `src/layoutpatch/retrieval/propagation.py` / `region_pooling.py`）：

```text
共同底座：冻结 ColPali 算 query 对整页的匹配，1024 个 patch 每个得一个分（分高 = 这块小格子与问题相关）。
snappy:max：每个候选框看压住它的 patch，取最热那一个的分。毛病：大框容易含一个热点，白占便宜。
snappy:mean：取压住它的 patch 的平均分。毛病：大框被大量冷 patch 稀释。
snappy:iou：按 patch 与框的 IoU 加权平均。比上面两个均衡，但仍偏向大框。
fixed:coverage：权重 = 相交面积 / 框面积（“这个框里有多大比例是热的”）。偏向紧致小框。
fixed:iou_mass：权重 = 相交面积 / 并集面积。大小框都不偏不倚，所以五档里最高（0.2787）。
group P25/P50/P75：不从候选里选，自己把热 patch 连成片画框（自组框，无 node_id），官方口径下无候选身份，本次未评；旧 IoU 虚高数见附录。
```

| 基线 | eval1390 official@1 | full1658 official@1 | eval1390 union@1 | full1658 union@1 | ge05_eval1390 |
| --- | --- | --- | --- | --- | --- |
| snappy:max | 0.0791 | 0.0663 | 0.0867 | 0.0727 | 111 |
| snappy:mean | 0.0785 | 0.0658 | 0.0861 | 0.0722 | 110 |
| snappy:iou | 0.2213 | 0.1855 | 0.2380 | 0.1995 | 303 |
| fixed:coverage | 0.2205 | 0.1849 | 0.2373 | 0.1989 | 302 |
| fixed:iou_mass | 0.2787 | 0.2336 | 0.2998 | 0.2514 | 383 |

- group 三档未评（自组框 None，无官方候选口径；旧 IoU 虚高数见附录，不并列）。
- 利弊判断：对实验**有利**的是 L2−L3 gap 在对齐分母下依然大（0.9136−0.2787≈0.63），且最好规则 fixed:iou_mass 在两口径、两分母下均为第一（0.2787/0.2336/0.2998/0.2514），排序方向一致，说明“候选充足、排序不足”不是某口径的假象；**有弊**的是 L3 均值仍低（最好 0.28），且 45 B 在官方口径下的实际分尚未单独列出（本轮只给了全集/对齐均值），2-R 的可训练分母（matched-A 高 Oracle 子集 vs 60 题弱候选）还需按 L2 分层单列，见下一步。

### 8.4 旧 IoU 数（附录原样抄，不可比，不判 Gate）

- EXP-006 1343A Top-1：fixed:iou_mass 0.3187 / snappy:iou 0.2621 / 其余见 JSON。
- EXP-006 45B 消解：Snappy/固定五档全 0.0（group 虚高不计）。
- EXP-005 A/B/C/D：A=1345/B=45/C=0/D=268（matched 1598=1343A+255D含2both归A；unmapped_only 60=45B+13D+2A纯unmapped命中）。

## 9. 错误信息

- 无。重算 16.3 秒一次通过；`mmdocir_00700` 零面积题（1 行 1 题，全零）按官方 `gt_area==0 → 0.0` 处理，单列注明（见第 10 节）。

## 10. 结果解释

- L2 高 L3 低成立（对齐分母）：Oracle@1 官方 0.9136（union 0.9136）vs 最好冻结规则 Top-1 官方 0.2787（union 0.2998，eval1390 口径），gap 约 0.63；full1658 口径 gap 更大（0.9093 vs 0.2336，仅参考）。缺口在排序不在候选（对齐分母下成立；此前版本用全集 L2 对 L3 是口径未对齐，现已修正，结论不变）。
- 但 L2 按题级不均匀：`oracle_official_area.json` 分层（matched 1596 clip 均值 1.0/oracle@1 0.9365；both 2 clip 1.0；unmapped_only 60 clip 0.5421/oracle@1 0.1857；ceiling<0.1 仅 9 题）。60 题候选层本身弱，2-R 训练分母须单列，不能拿对齐 gap 直接当可训练性；`matched/unmapped` 在此仅为诊断分层，不作官方口径下的“可用/不可用”二分。
- `matched 1596` 与 1598 差 2 = both 2 单列所致（1596+2=1598），无丢题；以后引用写 `matched 1598 含 both 2`。
- 与上一版对比：首次官方口径 L1/L2/L3 三层表；旧 0.3187 与新 0.2791 口径不可比（单框命中率 vs 面积召回），双轨并列。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（三层表 + 双分母 + 双口径并列 + union 敏感性；判定类表述一律否）。
- 下一步：与导师冻新阈值（Oracle 下限 + gap 下限 + 分层归因），再判进 2-R 还是按 `docs/THESIS_SPEC.md` 第 11.3 节收缩；**新阈值未冻前不建 `fusion/`、不写 `train_fusion.py`，训练须学生+导师双确认；`a1fbcc2` 两份规范维持 working 提案，不转正。**
