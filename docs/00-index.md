# 00-index（全仓导航 SSOT）

> Status: working | Scope: 全仓 | SSOT: 是
> 新增/修改任何 SSOT 文档，必须同步更新本表状态行。迁移完成前 Status 保持 working。

## 六类信息去哪找

| 信息类型 | 位置 | SSOT |
| --- | --- | --- |
| 代码 | `src/layoutpatch/` `tests/` `scripts/` | - |
| 配置 | `configs/`（注册表 `configs/README.md`） | `configs/README.md` |
| 数据与运行产物 | `data/` `artifacts/` `runs/`（不进 git） | - |
| 稳定规范 | `docs/` 下各 SSOT | 见下行 |
| 一次性记录 | `experiments/` | `experiments/registry.csv`（M2 起填充） |
| 当前进度 | `docs/handoff.md` | `docs/handoff.md` |

## 入门（按顺序读）

1. `docs/01-quickstart.md`（working, SSOT）：环境 + 数据准备
2. `docs/02-commands.md`（working, SSOT）：命令唯一入口（含 `phase1b-audit` 坐标审计命令）
3. `docs/RULES.md`（stable, SSOT）：开发规范十条铁律 + 0.2 实验小白讲解 + 4.4 指令透明后台执行

## 现行研究

- `docs/THESIS_SPEC.md`（stable）：大论文边界——2026-09-15 已用旧仓全文覆盖
- `docs/PAPER_SPEC.md`（stable）：小论文执行——2026-09-15 已用旧仓全文覆盖
- `docs/handoff.md`（working）：当前批次、阻塞问题、下一步指令
- `docs/paper-progress.md`（working）：小论文进度叙事。2026-09-27 起，执行令以 `docs/handoff.md` 置顶节为准。
- `docs/paper-draft-notes.md`（working）：小论文章节素材。数字以 registry 和证明文件为准，不替代 `docs/PAPER_SPEC.md`。
- `docs/MIGRATION_BATCHES.md`（working）：M0-M6 分批迁移清单（批次 = 实验阶段）

## 实验过程

- `experiments/registry.csv`：注册表（EXP-001~013 + FUSION-ARXIVQA + EXP-002-S1 + EXP-007-S1 + THR-B + S2-AUDIT + SPLIT-FROZEN）。2-R 缺口证明：`experiments/s2_splits/phase2r_gap_proof.json`。第一次正式融合：`experiments/2026-09-29-fusion-arxivqa.md`。
- S2 剔除清单（2026-09-26，已落盘，未开训）：`experiments/s2_exclusion/` + `experiments/phase2r-train-leakage-review.md`。划分已冻结：`experiments/2026-09-26-dev-test-split-frozen.md` + `experiments/s2_splits/`。冻结不是开训许可。
- `experiments/templates/experiment-record.md`：11 段模板（M2 迁入）
- 关门加固（2026-09-18，全部入库）：`experiments/2026-09-17-eff-b1.md`（B1 效率表 8 行 + 探针清洗 + k+1 页码表号）+ `experiments/2026-09-17-b2-taxonomy-draft.md`（B2 四数并列三类）+ `experiments/2026-09-18-advisor-decision-pack.md`（决策包三问只摆数）+ `scripts/run_text_dual.py`（Text 双轨）+ `scripts/run_phase1c_probes.py`（清洗探针）+ `scripts/run_phase1c.py`（存逐题 picks）

## 文献

- `docs/literature/`：逐篇阅读笔记（M6 迁入）
- `docs/30-literature/README.md`：一句话五问表（M6 迁入）

## 状态图例

`stable` 长期有效少改；`working` 正在写；`placeholder` 占位待覆盖；`frozen` 冻结只增版本；`archived` 只读。

## 迁移状态

- 本项目由 `mmdoc-evidence-rag` 迁移而来，执行清单 `docs/MIGRATION_BATCHES.md`。
- 当前进度：M0–M5 已完成（见下方长段，数字以 registry 为准）。2026-09-27 现行状态不在这段里：S2 泄漏已剔除，四池与 2-R 设计已冻结，训练未开始，下一步只编 `train_fit` 的 ArxivQA。读 `docs/handoff.md` 置顶节，不要只读本段。
- 分支基线：`master` 已推到 `09911d5`（S2 划分、2-R 设计与进度页）。`447460f` 是更早的 1C 关门点，不再是最新。`./tasks.ps1 check` 在 2-R 骨架合入时为 ruff + 50 pytest。
- M3 全量复验（EXP-001，R@5=0.8390）已通过。本文件 Status 仍保持 working，因为迁移清单批次 6 未关。
