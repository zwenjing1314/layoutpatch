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
2. `docs/02-commands.md`（working, SSOT）：命令唯一入口
3. `docs/RULES.md`（stable, SSOT）：开发规范十条铁律

## 现行研究

- `docs/THESIS_SPEC.md`（placeholder）：大论文边界——M1 用旧仓全文覆盖
- `docs/PAPER_SPEC.md`（placeholder）：小论文执行——M1 用旧仓全文覆盖
- `docs/handoff.md`（working）：当前批次、阻塞问题、下一步指令
- `docs/MIGRATION_BATCHES.md`（working）：M0-M6 分批迁移清单（批次 = 实验阶段）

## 实验过程

- `experiments/registry.csv`：注册表（M2 从旧仓迁入 EXP-001/002 两行）
- `experiments/templates/experiment-record.md`：11 段模板（M2 迁入）

## 文献

- `docs/literature/`：逐篇阅读笔记（M6 迁入）
- `docs/30-literature/README.md`：一句话五问表（M6 迁入）

## 状态图例

`stable` 长期有效少改；`working` 正在写；`placeholder` 占位待覆盖；`frozen` 冻结只增版本；`archived` 只读。

## 迁移状态

- 本项目由 `mmdoc-evidence-rag` 迁移而来，执行清单 `docs/MIGRATION_BATCHES.md`。
- 当前进度：M0 完成；旧仓保持只读。
- M2 验收（R@5 复验通过）后本文件 Status 改 `stable`。
