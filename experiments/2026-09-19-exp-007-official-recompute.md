# EXP-007 官方口径重算：冻结输入上的 L1/L2/L3 三层表（只重算，不改 Gate）

## 1. 实验目的

- 一句话：把 EXP-001 冻结页排序与 EXP-006 冻结 Top-1 选框，放到 MMDocIR 官方 `recall_layout` 口径下重算一遍，产出 L1/L2/L3 三层表，与旧 IoU 数双轨并列。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 5 关门后重算；本次只出数，不改任何 Gate、不冻新阈值、不判进 2-R 还是收缩（见第 11 节）。

## 2. 环境

- uv `.venv`；CPU 只读重算，无 GPU、无视觉重编码、无训练。
- 官方源码唯一事实来源：`C:/Users/WenJing/Documents/WorkTransfer/MMDocIR/metric_eval.py`（`calculate_overlap_score` + `recall_layout` + `top_k_indices` 语义逐行移植，见脚本头部注释）。

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split；query 全集 1658（2638 gold 行 = 2523 matched + 115 unmapped；题级 matched 1598 含 both 2 + unmapped_only 60）。
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

- commit：待提交（本记录页随 EXP-007 入库）。
- 是否干净：提交前 `git status --short` 只允许 EXP-007 三件（脚本 + JSON + 记录页 + registry 行），其余 `a1fbcc2` 未提交改动（两份规范 working 提案）本次不入库。
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

### 8.2 L2 候选覆盖上限（全集 1658，同页全候选，无模型分数）

| 指标 | 官方原样 | union-clipped |
| --- | --- | --- |
| oracle_area_recall@1 | 0.9093 | 0.9093 |
| oracle_area_recall@5 | 1.1234 | 0.9714 |
| oracle_area_recall@10 | 1.1542 | 0.9778 |

- 口径警告：官方原样可超 1（重叠候选不去重，同一 gold 可重复计面积），@5/@10 超 1 即证据；union-clipped 截到 [0,1]，两者并列、不混称。

### 8.3 L3 实际 Top-1（冻结 EXP-006 picks；eval1388 口径 + full1658 口径双分母）

| 基线 | eval1388 official@1 | full1658 official@1 | eval1388 union@1 | full1658 union@1 | ge05_eval1388 |
| --- | --- | --- | --- | --- | --- |
| snappy:max | 0.0792 | 0.0663 | 0.0869 | 0.0727 | 111 |
| snappy:mean | 0.0786 | 0.0658 | 0.0862 | 0.0722 | 110 |
| snappy:iou | 0.2216 | 0.1855 | 0.2383 | 0.1995 | 303 |
| fixed:coverage | 0.2208 | 0.1849 | 0.2376 | 0.1989 | 302 |
| fixed:iou_mass | 0.2791 | 0.2336 | 0.3002 | 0.2513 | 383 |

- group 三档未评（自组框 None，无官方候选口径；旧 IoU 虚高数见附录，不并列）。

### 8.4 旧 IoU 数（附录原样抄，不可比，不判 Gate）

- EXP-006 1343A Top-1：fixed:iou_mass 0.3187 / snappy:iou 0.2621 / 其余见 JSON。
- EXP-006 45B 消解：Snappy/固定五档全 0.0（group 虚高不计）。
- EXP-005 A/B/C/D：A=1345/B=45/C=0/D=268（matched 1598=1343A+255D含2both归A；unmapped_only 60=45B+13D+2A纯unmapped命中）。

## 9. 错误信息

- 无。重算 16.3 秒一次通过；`mmdocir_00700` 零面积题（1 行 1 题，全零）按官方 `gt_area==0 → 0.0` 处理，单列注明（见第 10 节）。

## 10. 结果解释

- L2 高 L3 低成立：Oracle@1 官方 0.9093（union 0.9093）vs 最好冻结规则 Top-1 官方 0.2791（union 0.3002，eval1388 口径），gap 约 0.63；full1658 口径 gap 更大（0.9093 vs 0.2336）。缺口在排序不在候选（全集层面）。
- 但 L2 按题级不均匀：`oracle_official_area.json` 分层（matched 1596 clip 均值 1.0/oracle@1 0.9365；both 2 clip 1.0；unmapped_only 60 clip 0.5421/oracle@1 0.1857；ceiling<0.1 仅 9 题）。60 题候选层本身弱，2-R 训练分母须单列，不能拿全集 gap 直接当可训练性。
- `matched 1596` 与 1598 差 2 = both 2 单列所致（1596+2=1598），无丢题；以后引用写 `matched 1598 含 both 2`。
- 与上一版对比：首次官方口径 L1/L2/L3 三层表；旧 0.3187 与新 0.2791 口径不可比（单框命中率 vs 面积召回），双轨并列。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（三层表 + 双分母 + 双口径并列 + union 敏感性；判定类表述一律否）。
- 下一步：与导师冻新阈值（Oracle 下限 + gap 下限 + 分层归因），再判进 2-R 还是按 `docs/THESIS_SPEC.md` 第 11.3 节收缩；**新阈值未冻前不建 `fusion/`、不写 `train_fusion.py`，训练须学生+导师双确认；`a1fbcc2` 两份规范维持 working 提案，不转正。**
