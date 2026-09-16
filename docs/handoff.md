# 工作交接记录（变化的进度）

> 用途：新开 Cursor 窗口时手动 `@docs/handoff.md`，让新会话接上当前进度。
> 约定：每次会话结束前更新本文件；本文件只写变化的进度，不写不变的规范（规范在 `.cursor/rules/` 与 `docs/RULES.md`）。

## 当前 Phase 与 Gate 状态

- 当前所处阶段：**M3 完成（EXP-001 复验通过），下一步 M4（Phase 1B 缺口诊断：坐标审计 + A/B/C/D）**，见 `docs/MIGRATION_BATCHES.md` 批次清单。
- 已完成的 Phase：M0（根目录骨架）+ M1（`uv sync --dev` 落盘 `uv.lock`；`uv run lp version` 通过；`./tasks.ps1 check` 全绿；git init 首个 commit；两份 SSOT 已覆盖）+ M2（adapters 迁移 + `lp prepare` + 全量对数 313/20395/170338/1658 验证通过）+ M2.5（官方 raw 已复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行落地，四表未动）+ M3（retrieval/scoring/colpali/pipeline + evaluation/metrics/pipeline + `lp retrieve/evaluate` + 3 个 config + 2 组测试，ruff + 25 pytest 全绿；EXP-001 复验 R@5=0.8390 与旧仓逐位一致，已登记）。
- 下一个 Gate：

```text
M3 通过条件：EXP-001 R@5=0.8390 与旧 EXP-002 偏差 0.0000 < 0.005 + 全指标逐位一致 + registry/记录页/复现凭证三件齐 + check 全绿（ruff + 25 pytest）
M4 前置（来自 PAPER_SPEC 第 6 节）：坐标审计机器门限 + ≥20 页叠图人工抽查，先过审计再谈任何区域指标
下一步任务：M4（docs/MIGRATION_BATCHES.md 批次 4）：新建 layout/nodes、correspondence、evaluation/region_metrics、audit，产出 A/B/C/D + 分层表 + 10 成功/10 失败案例图
阻塞问题：无（旧仓库保持只读，不做修改）
```

## 最近 runs

| EXP | run 目录 | 关键指标一句 | 是否可用 |
| --- | --- | --- | --- |
| EXP-001 | `runs/retrieval/mmdocir_colpali/20260916_105545` | Phase 1A ColPali full 复验：R@5=0.8390 与旧仓 EXP-002 逐位一致，可作 1B 分母 | 是（本仓库首个正式 baseline） |

## 配置与分支状态

- 当前分支：`master`，EXP-001 完成后待提交（指标回滚 + registry + 记录页 + 复现凭证 + 文档同步）
- 未提交改动：`metrics.py` ndcg 回滚、`tests/test_retrieval_metrics.py` 补回归、EXPERIMENT 与 docs 若干（见上），`data/`/`artifacts/`/`runs/` 产物不进 git
- 工作中 config：`configs/datasets/mmdocir.yaml`（working）；`configs/experiments/mmdocir_colpali.yaml`（EXP-001 冻结基线）
- 最近 commit：`bbe13ed`（EXP-001 运行头）

## 未解决问题

1. `.env` 无需创建：本仓库默认直接读 `data/raw/mmdocir_evaluation/`（官方三文件已复制，约 4GB，不进 git）。仅当 raw 数据放在其他磁盘时，才在 `.env` 里设置 `LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT` 覆盖默认路径。
2. `test_data_splits.py` 未搬运：它依赖旧仓库 `retrieval.pipeline.apply_data_split` 与 `evaluation.pipeline`，等 M3 检索/评测管线落地后再补。
3. 页图已还原到本仓库 `data/interim/mmdocir_evaluation/page_images/`（约 8GB，不进 git），ColPali 编码阶段直接复用。

## 下一步（给新会话的指令）

```text
1. M1 收尾确认：uv sync --dev → lp version → tasks.ps1 check → git init → 覆盖 THESIS_SPEC 占位（已完成）。
2. M2 数据准备：复制 datasets/adapters 与配置，实现 lp prepare 并跑 prepare 对数 313/20395/170338/1658（已完成：对数验证通过，见上）。
3. M3 检索评测（已完成：EXP-001 R@5=0.8390 与旧仓逐位一致，registry 已登记）→ 下一步 M4 Phase 1B：先过坐标审计（机器门限 + ≥20 页叠图人工抽查），再产出 A/B/C/D 缺口诊断。
```

## 更新记录

| 日期 | 更新内容 |
| --- | --- |
| 2026-06-16 | M0 骨架完成：根目录 12 个条目、src 包结构、tests（参考官方 repro：conftest + markers + smoke）、docs 七篇、configs/experiments 占位、MIGRATION 重写为 M0-M6 批次清单 |
| 2026-09-15 | 第一优先级修复完成：删重复旧 skill、修正 rules 旧引用与 30 号 glob、修正 handoff/index 的 MIGRATION 引用、PAPER_SPEC 覆盖为小论文全文、GPU 测试改为函数内 importorskip；依赖保持完整未拆分 |
| 2026-09-15 | M1 完成：`uv sync --dev` 落盘 `uv.lock`、`uv run lp version` 通过、`./tasks.ps1 check` 全绿、git 首个 commit、覆盖 `THESIS_SPEC.md`；`cli.py` 补 callback 修复 typer 单命令折叠 |
| 2026-09-15 | M2 完成：adapters（demo/mmdocir）+ `lp prepare` + `tasks.ps1 mmdocir-prepare` + `configs/datasets/mmdocir.yaml` 落地；ruff + 12 pytest 全绿；全量对数 313/20395/170338/1658 验证通过（raw 经临时变量指向旧仓库，产物在本仓库 `data/`） |
| 2026-09-15 | M2.5 完成：官方 evaluation 原始三文件复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行（2523 matched + 115 unmapped，覆盖 1658 query）；ruff + 15 pytest 全绿；四表对数未动 |
| 2026-09-16 | M3 完成：检索评测管线（bm25/dense/colpali/hybrid 页级）+ `lp retrieve/evaluate` + smoke 全绿；EXP-001 全量复验 R@5=0.8390 与旧仓逐位一致（ndcg 口径回滚为旧逐行一致 + 补回归测试）；registry 首行 + 记录页 + 复现凭证已登记；ruff + 25 pytest 全绿 |
