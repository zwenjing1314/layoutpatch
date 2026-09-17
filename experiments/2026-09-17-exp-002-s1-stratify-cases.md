# EXP-002-S1 Phase 1B 分层表 + 10 成功/10 失败案例（正式）

> SUPERSEDED by EXP-005：本页冻结留档，不可再引用数字；统一口径以 `experiments/2026-09-17-exp-005-gate-closeout.md` 为准。
> 恢复说明（2026-09-18）：本文件曾因工作区误删且从未入库（git 无历史），按不可变性要求凭上一版内容重建留档；数字以 EXP-005 统一脚本重算为准，本页仅作文档考古。

## 1. 实验目的

- 一句话：补小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节 Phase 1B 后半——分层表看 B 类缺口集中在哪，20 张案例图给人看成功长什么样、失败卡在哪。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 4；A/B/C/D 主表 EXP-002 已出，本实验只补分层与案例。

## 2. 环境

- uv `.venv`，纯 CPU 统计 + PIL 叠图（无 GPU）
- 输入四件：EXP-001 run `20260916_134144` 的 `predictions.parquet`（Top-5）、`nodes.parquet`、`region_labels.parquet`（2638 行）、`queries.parquet`（问题类型）
- 运行约 4 秒（1658 题全量判定 + 20 张叠图绘制）

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split；分母=有 gold 区域 query 1658 题（K=5，IoU≥0.5，与 EXP-002 同口径）
- 分层键（三组）：
  - 问题类型归一化：单标签取本身（`Chart/Table/Figure/Pure-text (Plain-text)/Generalized-text (Layout)/text-only/multimodal-t/multimodal-f/meta-data/una-web`），多标签并 `mixed`，空值并 `unknown`（原始 47 种组合归一化后 12 组）
  - 面积三分位：gold 框相对页面积 `bbox_area/(W*H)` 的三分位点 `0.0558/0.1742`，切 `small/medium/large`
  - OCR 密度三分位：gold 页内 nodes 框总面积占比的三分位点 `0.4305/0.5593`，切 `sparse/medium/dense`
- 案例选择：成功=A 类中 best-IoU 最高 10 题；失败=B 类中 best-IoU 最低 10 题（best-IoU=同页候选框与 gold 框的最大 IoU）

## 4. 配置文件

- 无新 config；代码 `scripts/run_phase1b_stratify.py`（旧版；已被 EXP-005 统一脚本覆盖；复用 `region_metrics.bbox_iou` 与已修页号的 `_page_image_for` 叠图链路；gold 框画黄色 6 像素粗框，布局框红=表格/橙=段落/绿=图，蓝色=32×32 网格）

## 5. 运行命令

```powershell
uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5
```

## 6. 代码 commit

- `74aa05a` 之上的工作区改动（`audit_overlays.py` 加 `gold` 黄色粗框 + 新脚本 `run_phase1b_stratify.py` + `02-commands.md` 登记 `phase1b-stratify`）
- 是否干净：否（EXP-003/004 已跑完未提交 + 本实验新产物未提交，随后一起提交）

## 7. 输出目录

- `artifacts/diagnosis/mmdocir_evaluation/stratification.json`（18 行分层；已被 EXP-005 重写并加 `meta` 冻结）
- `artifacts/diagnosis/mmdocir_evaluation/cases.json`（success 10 / failure 10 名单 + best-IoU + 页号；已被 EXP-005 重写为 10+10+10）
- `artifacts/diagnosis/mmdocir_evaluation/overlays_cases/*.jpg`（20 张，`A_<qid>_<page>.jpg` / `B_<qid>_<page>.jpg`，缺页图 0；EXP-005 保留未覆盖）

## 8. 关键指标（stratification.json 原样抄，旧版）

| 分层 | n | A | B | 页命中率 | 区域命中率 | B占页命中 |
| --- | --- | --- | --- | --- | --- | --- |
| area=large | 551 | 424 | 36 | 0.8348 | 0.7695 | 0.0783 |
| area=medium | 554 | 487 | 6 | 0.8899 | 0.8791 | 0.0122 |
| area=small | 553 | 434 | 3 | 0.7902 | 0.7848 | 0.0069 |
| density=dense | 552 | 439 | 6 | 0.8062 | 0.7953 | 0.0135 |
| density=medium | 553 | 463 | 7 | 0.8499 | 0.8373 | 0.0149 |
| density=sparse | 553 | 443 | 32 | 0.8590 | 0.8011 | 0.0674 |
| qtype=Chart | 101 | 93 | 0 | 0.9208 | 0.9208 | 0.0 |
| qtype=Figure | 170 | 126 | 13 | 0.8176 | 0.7412 | 0.0935 |
| qtype=Generalized-text (Layout) | 30 | 16 | 4 | 0.6667 | 0.5333 | 0.2 |
| qtype=Pure-text (Plain-text) | 119 | 87 | 13 | 0.8403 | 0.7311 | 0.13 |
| qtype=Table | 140 | 112 | 1 | 0.8071 | 0.8 | 0.0088 |
| qtype=meta-data | 153 | 101 | 0 | 0.6601 | 0.6601 | 0.0 |
| qtype=mixed | 217 | 177 | 13 | 0.8756 | 0.8157 | 0.0684 |
| qtype=multimodal-f | 87 | 76 | 0 | 0.8736 | 0.8736 | 0.0 |
| qtype=multimodal-t | 240 | 208 | 0 | 0.8667 | 0.8667 | 0.0 |
| qtype=text-only | 383 | 332 | 0 | 0.8668 | 0.8668 | 0.0 |
| qtype=una-web | 1 | 1 | 0 | 1.0 | 1.0 | 0.0 |
| qtype=unknown | 17 | 16 | 1 | 1.0 | 0.9412 | 0.0588 |

- 成功 10 题：`mmdocir_00000/00001/00002/00003/00004/00005/00006/00007/00009/00010`（best-IoU 全 1.0）
- 失败 10 题：`mmdocir_00102/00147/00675/00700/00116/00664/00665/00625/00082/00241`（best-IoU 0.0~0.03）

## 9. 错误信息

- 无运行错误；案例叠图缺页图 0 张。
- 口径说明：分母 1658 与 EXP-002 一致（A=1345/B=45/C=0/D=268，各分层 A+B+C+D 求和=1658）。

## 10. 结果解释（旧版口径，(frame frozen by EXP-005)）

- 支持假设：B 类缺口高度集中——大面积框占 36/45（80%）、稀疏页占 32/45（71%）；类型上纯文本 13 + Figure 13 + mixed 13 + 版式文本 4 + Table 1 + unknown 1 = 45，而 Chart/Table/text-only/multimodal 两类 B=0。说明缺口不在图表题，在"大框+纯文本/版式"组合。
- 失败归因（框缺失 vs 选错）：10 张失败案例的 gold 框 `source` 全是 `unmapped`（gold node 不在 nodes 表），同页最优 IoU 全 ≤0.03——是"框缺失"（官方布局没给该框），不是"框给了但选错"。这与 Snappy 85% 天花板口径一致：OCR/布局天花板卡住了 B 类。
- A/B/C/D：C 仍为 0（各分层 C 列全 0），页级是区域的前提成立。（该表述已被 EXP-005 修正为定义性结果，不许写成发现。）
- 与上一版对比：首次分层+案例（EXP-002 只有主表）。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否（已被 EXP-005 替代；本页仅留档，不引用数字）。
- 下一步：见 `experiments/2026-09-17-exp-005-gate-closeout.md`。
