# 命令手册（SSOT）

> Status: working | Scope: 全仓命令 | SSOT: 是
> 本篇是命令唯一真理源。其他文档只允许引用，不许重复写长命令。
> 约定：所有命令在项目根目录执行；Windows 用 `./tasks.ps1 <task>`；所有任务共用 uv `.venv`。
> 每条格式固定为：命令 / 输入 / 输出 / 检查。新任务先在这里登记，再在 `tasks.ps1` 实现。

## check（质量门，已实现）

```powershell
./tasks.ps1 check
```

- 输入：`src/` + `tests/`
- 输出：终端结果；无产物
- 检查：ruff 与 pytest 全绿（合入 `main` 的最低条件，见 `docs/RULES.md` 7.1 节）

## version（冒烟，已实现）

```powershell
uv run lp version
```

- 输入：无
- 输出：`layoutpatch 0.1.0`
- 检查：环境搭建后第一条验证命令（不需要 GPU / 数据 / 网络）

## mmdocir-prepare（未实现，Phase M1 登记）

```powershell
./tasks.ps1 mmdocir-prepare
```

- 输入：MMDocIR evaluation 原始数据（布局见 `docs/01-quickstart.md`）
- 输出：`data/processed/mmdocir_evaluation/{documents,pages,nodes,queries}.parquet` + `page_images/`
- 检查：对数 313 / 20395 / 170338 / 1658；`tasks.ps1` 内置断言

## mmdocir-smoke（未实现，Phase M2 登记）

```powershell
./tasks.ps1 mmdocir-smoke
```

- 输入：`configs/experiments/mmdocir__phase1a__colpali.yaml`（限流版）+ embedding cache
- 输出：`runs/retrieval/mmdocir__phase1a__colpali_smoke/<timestamp>/` 五件套
- 检查：`torch.cuda.is_available()=True`；smoke 结果不进论文

## mmdocir-colpali-full（未实现，Phase M2 登记，EXP 复验）

```powershell
./tasks.ps1 mmdocir-colpali-full
```

- 输入：全量 parquet + `artifacts/colpali/` embedding cache（可从旧仓库复制）
- 输出：`runs/retrieval/mmdocir__phase1a__colpali/<timestamp>/` 五件套
- 检查：Page R@5 与旧仓库 EXP-002 的 0.8390 偏差 < 0.005 → 迁移验收通过
