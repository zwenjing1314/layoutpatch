# LayoutPatch 项目

> 状态：M0 骨架已完成。下一步：M1 统一环境与规范迁移。
> 项目目标：研究布局约束的文档侧 patch 融合，用于 ColPali 页内证据区域定位。

## 现在已经有什么

本仓库目前只包含**项目骨架**，还没有复制旧仓库的实验代码、数据、模型缓存或正式实验结果：

- `src/layoutpatch/`：Python 包与 CLI 最小骨架；
- `tests/`：参考 `colpali-official-repro` 的测试组织方式，包含 smoke、GPU 自动跳过和禁网夹具；
- `docs/`：开发规范、导航、环境、命令和分批迁移清单；
- `configs/`、`experiments/`：配置与实验记录的空入口；
- `tasks.ps1`：Windows 统一任务入口，目前只真正实现 `check` 与 `help`，实验任务暂时明确报“未实现”。

## 第一次使用

请先阅读：

1. `docs/RULES.md`：项目开发规则；
2. `docs/handoff.md`：当前进度；
3. `docs/MIGRATION_BATCHES.md`：按小论文实验推进的分批迁移计划；
4. `docs/01-quickstart.md`：环境搭建；
5. `docs/02-commands.md`：命令唯一来源。

环境配置完成后，从项目根目录执行：

```powershell
uv sync --dev
uv run lp version
./tasks.ps1 check
```

## 当前不做的事

- 不复制旧项目的全部文件；
- 不复制 `data/`、`artifacts/`、`runs/`；
- 不执行 ColPali 全量实验；
- 不安装额外技术或模型；
- 不跳过 M1 直接进入数据和实验迁移。

详细顺序见 `docs/MIGRATION_BATCHES.md`。
