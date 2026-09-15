# Changelog

格式遵循 Keep a Changelog 思想：只记面向使用者的变更，不记每日流水。

## [Unreleased]

### Added

- 项目骨架首版：`src/layoutpatch/` 包结构、`tests/`、`configs/`、`docs/`、`experiments/`、`tasks.ps1`、uv 环境三件套（`pyproject.toml` + `.python-version` + 本文件）。
- `docs/RULES.md`（开发规范十条铁律）、`docs/00-index.md`（SSOT 导航）、`docs/handoff.md`（进度交接）。
- `docs/MIGRATION_BATCHES.md`（旧仓库 `mmdoc-evidence-rag` → 本项目的分批迁移执行清单，按小论文实验阶段切片）。

### Changed

- `docs/PAPER_SPEC.md` 由占位替换为小论文执行规范全文（来源旧仓库 `SMALL_PAPER_DEV_SPEC.md`，适配 `layoutpatch` 包名与 `THESIS_SPEC.md` 引用）。
- `.cursor/rules/` 修正旧项目身份引用（旧包名/旧文档路径/`MIGRATION.md` 路径），`30-fusion-architecture.mdc` 的 glob 改为 `src/layoutpatch/`。
- 删除重复旧 skill `.cursor/skills/mmdoc-evidence-research/`，新仓库唯一研究 skill 为 `.cursor/skills/layoutpatch-research/`。
- `docs/handoff.md` 与 `docs/00-index.md` 修正为引用 `docs/MIGRATION_BATCHES.md`；M1 通过条件改为单一 skill 引用正确 + `PAPER_SPEC.md` 已覆盖。
- `tests/test_gpu_marker.py` 改为函数内 `pytest.importorskip("torch")`，基础环境（无 ColPali extra）下测试收集不再失败。
