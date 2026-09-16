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

## mmdocir-prepare（已实现，批次 M2）

```powershell
./tasks.ps1 mmdocir-prepare
```

- 输入：MMDocIR evaluation 原始数据（布局见 `docs/01-quickstart.md`）
- 输出：`data/processed/mmdocir_evaluation/{documents,pages,nodes,queries}.parquet` + `page_images/`
- 检查：对数 313 / 20395 / 170338 / 1658；`tasks.ps1` 内置断言

## mmdocir-smoke（已实现，批次 M3）

```powershell
./tasks.ps1 mmdocir-smoke
```

- 输入：`configs/experiments/mmdocir_colpali_smoke.yaml`（2 文档限流）+ embedding cache
- 输出：`runs/retrieval/mmdocir_colpali_smoke/<timestamp>/` 五件套
- 检查：`torch.cuda.is_available()=True`；smoke 结果不进论文

## mmdocir-colpali-full（已实现，批次 M3，EXP-001）

```powershell
./tasks.ps1 mmdocir-colpali-full
uv run lp evaluate --run runs/retrieval/mmdocir_colpali/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ `artifacts/colpali/` embedding cache
- 输出：`runs/retrieval/mmdocir_colpali/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：Page R@5 与旧仓库 EXP-002 的 0.8390 偏差 < 0.005 → 迁移验收通过；
  签名命中则复用缓存，不命中 GPU 重算并覆盖写回

## phase1b-audit（已实现，批次 M4，坐标审计硬 Gate）

```powershell
uv run python scripts/run_phase1b_audit.py            # 全量机器门限 + 20 张叠图
uv run python scripts/run_phase1b_audit.py --limit-pages 50   # 快速试扫
```

- 输入：`data/processed/mmdocir_evaluation/nodes.parquet` + `data/interim/mmdocir_evaluation/page_images/`
- 输出：`artifacts/audit/mmdocir_evaluation/audit.json`（机器门限数值）+
  `artifacts/audit/mmdocir_evaluation/overlays/*.jpg`（≥20 张 patch 网格+布局框叠图）
- 检查（`docs/PAPER_SPEC.md` 第 6 节）：越界率 < 1%；无页级覆盖为 0 的异常页；
  人工抽查叠图回答"表格线/栏边界是否对齐"，任何一页不通过 → 停工修数据链。
  人工判读口径（2026-09-16 已固定）：看彩色框围没围住真实文字/表格
  （红=表格/橙=段落/绿=图），不看框边压没压蓝色网格线；
  页顶小字/页底文字/页码未被框住属官方标注稀疏，不是错位（用户已确认 `2021700463_p69` 通过）。

## phase1b-abcd（已实现，批次 M4，EXP-002）

```powershell
uv run python -c "from layoutpatch.evaluation.region_diagnosis import diagnose; d = diagnose(k=5); print(d.a_page_hit_region_hit, d.b_page_hit_region_miss, d.c_page_miss_region_hit, d.d_page_miss_region_miss)"
```

- 输入：EXP-001 run 的 `predictions.parquet`（Top-5）+ `nodes.parquet`（页内候选框）+ `region_labels.parquet`（2638 行 gold 区域）
- 输出：`artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`
- 检查（`docs/PAPER_SPEC.md` 第 7.3 节）：A 页中区中 / B 页中区不中 / C 页不中区中 / D 都不中；
  当前值 A=1345/B=45/C=0/D=268，B 占页命中 3.24%；IoU 口径 `bbox_iou`≥0.5（0.3/0.5/0.7 敏感性 0.8154/0.8112/0.8100）；
  与 EXP-001 差 1 题为 gold 页口径差异（`mmdocir_01342`）；记录页 `experiments/2026-09-16-exp-002-abcd-diagnosis.md` + registry 第二行
