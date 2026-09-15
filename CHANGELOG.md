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
- `docs/THESIS_SPEC.md` 由占位替换为大论文研究路线全文（来源旧仓库 `THESIS_RESEARCH_ROUTE_DRAFT.md`，适配 `PAPER_SPEC.md` 引用）。
- `src/layoutpatch/cli.py` 补 `@app.callback()`，修复 typer 0.27 单命令折叠导致 `uv run lp version` 被当成多余参数的问题。
- `uv.lock` 首次生成（`uv sync --dev`，224 个包），`uv run lp version` 与 `./tasks.ps1 check`（ruff + 12 个 pytest）已验证通过。
- M2 数据准备落地：`src/layoutpatch/{schemas,io,paths}.py` 迁移、`src/layoutpatch/datasets/adapters.py`（仅 demo/mmdocir 主线，不含中文年报）、`lp prepare` 命令、`tasks.ps1 mmdocir-prepare`、`configs/datasets/mmdocir.yaml`、`tests/test_schemas_io.py` + `tests/datasets/test_adapters.py`；全量 prepare 对数 313/20395/170338/1658 已验证。
- M2.5 区域标注落地：官方 evaluation 原始数据复制到本仓库 `data/raw/mmdocir_evaluation/`（不进 git）；新增 `src/layoutpatch/evaluation/region_labels.py`（IoU/坐标缩放/分组函数）、`scripts/build_region_labels.py`（独立脚本）、`adapters.prepare_mmdocir(with_region_labels=True)` 开关、`tests/evaluation/test_region_labels.py`（解耦测试）；`region_labels.parquet` 共 2638 行（2523 matched + 115 unmapped，覆盖 1658 个 query），四表对数未动。
