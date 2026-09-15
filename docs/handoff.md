# 工作交接记录（变化的进度）

> 用途：新开 Cursor 窗口时手动 `@docs/handoff.md`，让新会话接上当前进度。
> 约定：每次会话结束前更新本文件；本文件只写变化的进度，不写不变的规范（规范在 `.cursor/rules/` 与 `docs/RULES.md`）。

## 当前 Phase 与 Gate 状态

- 当前所处阶段：**M3 代码迁移完成、smoke 链路已通，下一步挂全量复验（EXP-001，约 8 小时 GPU）**，见 `docs/MIGRATION_BATCHES.md` 批次清单。
- 已完成的 Phase：M0（根目录骨架）+ M1（`uv sync --dev` 落盘 `uv.lock`；`uv run lp version` 通过；`./tasks.ps1 check` 全绿；git init 首个 commit；两份 SSOT 已覆盖）+ M2（adapters 迁移 + `lp prepare` + 全量对数 313/20395/170338/1658 验证通过）+ M2.5（官方 raw 已复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行落地，四表未动）+ M3 代码（retrieval/scoring/colpali/pipeline + evaluation/metrics/pipeline + `lp retrieve/evaluate` + 3 个 config + 2 组测试，ruff + 24 pytest 全绿；smoke 链路 9 query 已通）。
- 下一个 Gate：

```text
M2 通过条件：lp prepare 实现 + tasks.ps1 mmdocir-prepare 注册 + 全量对数 313/20395/170338/1658 + check 全绿（ruff + 15 pytest，含 M2.5 的 3 个 region_labels 测试）
M2.5 通过条件：region_labels.parquet 2638 行（2523 matched + 115 unmapped，覆盖全部 1658 query）+ 四表对数未动 + ruff 全绿
下一步任务：M3（docs/MIGRATION_BATCHES.md 批次 3）：复制 retrieval/pipeline、scoring、colpali、evaluation/metrics、cli retrieve/evaluate，实现 full 复验 R@5≈0.839
阻塞问题：无（旧仓库保持只读，不做修改）
```

## 最近 runs

| EXP | run 目录 | 关键指标一句 | 是否可用 |
| --- | --- | --- | --- |
| （无） | 新仓库还没有任何 run | 旧仓库 EXP-002（Page R@5=0.8390）是迁移后的复验基准 | 是（作为对照） |

## 配置与分支状态

- 当前分支：`master`，工作区干净，最近 commit `5f251f6`（M2.5 区域标注）
- 未提交改动：无（`data/` 产物不进 git）
- 工作中 config：`configs/datasets/mmdocir.yaml`（working）
- 最近 commit：`5f251f6`（M2.5 区域标注）

## 未解决问题

1. `.env` 尚未创建：如需切换 raw 数据位置，复制 `.env.example` 为 `.env` 并设置 `LAYOUTPATCH_MMDOCIR_EVALUATION_ROOT`；默认直接读本仓库 `data/raw/mmdocir_evaluation/`（官方三文件已复制，约 4GB，不进 git）。
2. `test_data_splits.py` 未搬运：它依赖旧仓库 `retrieval.pipeline.apply_data_split` 与 `evaluation.pipeline`，等 M3 检索/评测管线落地后再补。
3. 页图已还原到本仓库 `data/interim/mmdocir_evaluation/page_images/`（约 8GB，不进 git），ColPali 编码阶段直接复用。

## 下一步（给新会话的指令）

```text
1. M1 收尾确认：uv sync --dev → lp version → tasks.ps1 check → git init → 覆盖 THESIS_SPEC 占位（已完成）。
2. M2 数据准备：复制 datasets/adapters 与配置，实现 lp prepare 并跑 prepare 对数 313/20395/170338/1658（已完成：对数验证通过，见上）。
3. M3 代码迁移（已完成：smoke 链路已通）→ 挂全量复验 EXP-001：`./tasks.ps1 mmdocir-colpali-full`（约 8 小时 GPU，缓存签名对不上需全量重编码），判据 R@5 与旧 0.8390 偏差 < 0.005，然后登记 registry。
```

## 更新记录

| 日期 | 更新内容 |
| --- | --- |
| 2026-06-16 | M0 骨架完成：根目录 12 个条目、src 包结构、tests（参考官方 repro：conftest + markers + smoke）、docs 七篇、configs/experiments 占位、MIGRATION 重写为 M0-M6 批次清单 |
| 2026-09-15 | 第一优先级修复完成：删重复旧 skill、修正 rules 旧引用与 30 号 glob、修正 handoff/index 的 MIGRATION 引用、PAPER_SPEC 覆盖为小论文全文、GPU 测试改为函数内 importorskip；依赖保持完整未拆分 |
| 2026-09-15 | M1 完成：`uv sync --dev` 落盘 `uv.lock`、`uv run lp version` 通过、`./tasks.ps1 check` 全绿、git 首个 commit、覆盖 `THESIS_SPEC.md`；`cli.py` 补 callback 修复 typer 单命令折叠 |
| 2026-09-15 | M2 完成：adapters（demo/mmdocir）+ `lp prepare` + `tasks.ps1 mmdocir-prepare` + `configs/datasets/mmdocir.yaml` 落地；ruff + 12 pytest 全绿；全量对数 313/20395/170338/1658 验证通过（raw 经临时变量指向旧仓库，产物在本仓库 `data/`） |
| 2026-09-15 | M2.5 完成：官方 evaluation 原始三文件复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行（2523 matched + 115 unmapped，覆盖 1658 query）；ruff + 15 pytest 全绿；四表对数未动 |
