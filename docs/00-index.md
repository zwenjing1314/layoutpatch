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
- `docs/MIGRATION_BATCHES.md`（working）：M0-M6 分批迁移清单（批次 = 实验阶段）

## 实验过程

- `experiments/registry.csv`：注册表（EXP-001~006 共 7 行：EXP-001/002/003/004/002-S1-SUPERSEDED/005/006；query_count 全 1658；EXP-006 注 Top-1 口径与 0.8112 不可比）
- `experiments/templates/experiment-record.md`：11 段模板（M2 迁入）
- 关门加固（2026-09-18，全部入库）：`experiments/2026-09-17-eff-b1.md`（B1 效率表 8 行 + 探针清洗 + k+1 页码表号）+ `experiments/2026-09-17-b2-taxonomy-draft.md`（B2 四数并列三类）+ `experiments/2026-09-18-advisor-decision-pack.md`（决策包三问只摆数）+ `scripts/run_text_dual.py`（Text 双轨）+ `scripts/run_phase1c_probes.py`（清洗探针）+ `scripts/run_phase1c.py`（存逐题 picks）

## 文献

- `docs/literature/`：逐篇阅读笔记（M6 迁入）
- `docs/30-literature/README.md`：一句话五问表（M6 迁入）

## 状态图例

`stable` 长期有效少改；`working` 正在写；`placeholder` 占位待覆盖；`frozen` 冻结只增版本；`archived` 只读。

## 迁移状态

- 本项目由 `mmdoc-evidence-rag` 迁移而来，执行清单 `docs/MIGRATION_BATCHES.md`。
- 当前进度：M0 完成，M1 环境+规范已完成（uv.lock 落盘、`check` 44 绿、两份 SSOT 已覆盖、`matplotlib` 已显式声明主依赖），M2 四表+区域标注已完成（`region_labels.parquet` 2638 行冻结只读；`page_size` 字段冻结，三用途见 EXP-006§3），M3 代码迁移+smoke+EXP-001（本机从零重编码 52 分钟，run 20260916_134144，R@5=0.8390）已完成，M4 机器审计 Gate 通过 + EXP-002 A/B/C/D 主表已出（B 占页命中 3.24%，Top-K 内 C=0 为定义性结果）+ EXP-003 BGE-M3（R@5=0.7750，run 20260917_113452）/ EXP-004 Hybrid（R@5=0.7883，run 20260917_115238）补齐第 7.2 节四基准 + EXP-005 关门（matched 1598=1343A+255D含2both归A；unmapped_only 60=45B+13D+2A纯unmapped命中；47=45B+2A；可寻址双分母 0.0；oracle 页命中内 96.76%；直方图+30 张案例；自匹配 5 题行级抽样已避开 both）+ EXP-006 实测 1C（1343A Top-1 最高 0.3187、45B 固定五档消解全 0.0，不进 Phase 2 转收缩；`phase1c_picks.json` 1388 题逐题 picks + `phase1c_probes.json` 清洗探针）+ Text 双轨方法分（n=1388 中 NaN 53/有效 1335；group 三档未跑；置零 341 格分档；双口径恒为空）+ B1/B2/决策包（`447460f`，只摆数不选择）；旧仓保持只读。
- 分支基线：`master` 最新 `447460f`，干净树，`./tasks.ps1 check` 44 绿；`docs/figures/` 白名单两张代表压缩图已入库。
- M3 全量复验（EXP-001，R@5≈0.839）通过后本文件 Status 改 `stable`。（EXP-001/EXP-002 均已通过，待本轮文档同步后改 stable。）
