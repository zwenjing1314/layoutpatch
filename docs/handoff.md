# 工作交接记录（变化的进度）

> 用途：新开 Cursor 窗口时手动 `@docs/handoff.md`，让新会话接上当前进度。
> 约定：每次会话结束前更新本文件；本文件只写变化的进度，不写不变的规范（规范在 `.cursor/rules/` 与 `docs/RULES.md`）。

## 当前 Phase 与 Gate 状态

- 当前所处阶段：**M1 已完成（环境与规范），下一步 M2（数据准备：adapters + prepare 对数）**，见 `docs/MIGRATION_BATCHES.md` 批次清单。
- 已完成的 Phase：M0（根目录骨架）+ M1（`uv sync --dev` 落盘 `uv.lock`；`uv run lp version` 通过；`./tasks.ps1 check` ruff+5 pytest 全绿；git init 首个 commit `88a47ce`；两份 SSOT 已覆盖）。
- 下一个 Gate：

```text
M1 通过条件：uv sync --dev 成功 + ./tasks.ps1 check 三绿 + git init 首个 commit + 单一 skill（layoutpatch-research）引用正确 + `docs/PAPER_SPEC.md` 从占位替换为小论文执行规范
下一步任务：M1 清单逐项执行（docs/MIGRATION_BATCHES.md）
阻塞问题：无（旧仓库保持只读，不做修改）
```

## 最近 runs

| EXP | run 目录 | 关键指标一句 | 是否可用 |
| --- | --- | --- | --- |
| （无） | 新仓库还没有任何 run | 旧仓库 EXP-002（Page R@5=0.8390）是迁移后的复验基准 | 是（作为对照） |

## 配置与分支状态

- 当前分支：未 init（M1 第一步 `git init` + 首个 commit 包含全部骨架）
- 未提交改动：全仓库均为 M0 新文件，待 git 管理
- 工作中 config：无（configs/ 下只有 README，首批 yaml 在 M2 复制）
- 最近 commit：无

## 未解决问题

1. 本仓库 `.cursor/rules/` 与唯一 skill 已就位（旧引用已清理），剩余工作是执行 `uv sync` + `check` + `git init`。
2. `docs/THESIS_SPEC.md` 仍是占位文件，后续用旧仓库大论文规范全文覆盖（`docs/PAPER_SPEC.md` 已于 2026-09-15 覆盖为小论文执行规范）。
3. 数据目录布局待 M2 核对（`LAYOUTPATCH_DATA_ROOT` 环境变量在 `.env` 中设置）。

## 下一步（给新会话的指令）

```text
1. 执行 docs/MIGRATION_BATCHES.md 的 M1 批：uv sync --dev → lp version → tasks.ps1 check → git init → 修正 .cursor 引用 → 覆盖 PAPER_SPEC 占位。
2. M1 验收后进入 M2：复制 datasets/adapters 与配置，实现 lp prepare 并跑 prepare 对数 313/20395/170338/1658。
3. M2 复制 ColPali 与 embedding cache，实现 lp retrieve/evaluate，跑 full 复验 R@5≈0.839，登记 registry。
```

## 更新记录

| 日期 | 更新内容 |
| --- | --- |
| 2026-06-16 | M0 骨架完成：根目录 12 个条目、src 包结构、tests（参考官方 repro：conftest + markers + smoke）、docs 七篇、configs/experiments 占位、MIGRATION 重写为 M0-M6 批次清单 |
| 2026-09-15 | 第一优先级修复完成：删重复旧 skill、修正 rules 旧引用与 30 号 glob、修正 handoff/index 的 MIGRATION 引用、PAPER_SPEC 覆盖为小论文全文、GPU 测试改为函数内 importorskip；依赖保持完整未拆分 |
| 2026-09-15 | M1 完成：`uv sync --dev` 落盘 `uv.lock`、`uv run lp version` 通过、`./tasks.ps1 check` 全绿、git 首个 commit、覆盖 `THESIS_SPEC.md`；`cli.py` 补 callback 修复 typer 单命令折叠 |
