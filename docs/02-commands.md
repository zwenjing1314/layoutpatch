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

## mmdocir-bge-m3-full（已实现，批次 M3，EXP-003）

```powershell
./tasks.ps1 mmdocir-bge-m3-full
uv run lp evaluate --run runs/retrieval/mmdocir_bge_m3_page/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ 本地 `BAAI/bge-m3`（`local_files_only=True` 可加载）
- 输出：`runs/retrieval/mmdocir_bge_m3_page/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：`run_info.json` 的 `actual_retrievers` 必须含 `dense:BAAI/bge-m3` 且不含 `dense:tfidf_fallback`；`require_model: true` 下模型缺席必须报错而不是降级；登记条件见小论文执行规范 `docs/PAPER_SPEC.md` 第 7.2 节 Phase 1A（query 数=1658 五件套齐全）

## mmdocir-hybrid-full（已实现，批次 M3，EXP-004）

```powershell
./tasks.ps1 mmdocir-hybrid-full
uv run lp evaluate --run runs/retrieval/mmdocir_hybrid_page/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ 本地 `BAAI/bge-m3`（Hybrid 内 dense 分支同 EXP-003 口径）
- 输出：`runs/retrieval/mmdocir_hybrid_page/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：`run_info.json` 的 `retriever_type=hybrid_page` 且 `retriever=hybrid_page`（RRF 融合 `page_methods=[bm25,dense]`，k=60）；dense 分支同样禁 TF-IDF 降级；登记条件同第 7.2 节

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

## phase1b-stratify（已实现，批次 M4，EXP-005 关门补证）

```powershell
uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5
```

- 输入：EXP-001 run 的 `predictions.parquet`（Top-5）+ `nodes.parquet` + `region_labels.parquet`（2638 行：matched 2523 + unmapped 115；题级 matched 1598/unmapped_only 60；`page_size` 冻结只读）+ `queries.parquet`（问题类型）
- 输出：`artifacts/diagnosis/mmdocir_evaluation/` 下 `stratification.json`（分层表，`meta` 含 k/iou/面积均值定义/三分位点）+ `cases.json`（成功 10/失败 10/中间态 10 + `meta` 三档定义）+ `crosstab.json` + `addressability.json` + `oracle.json` + `strat_area_hist.png/json` + `strat_cov_hist.png/json` + `overlays_cases/*.jpg`（极值 20）+ `overlays_cases_mid/*.jpg`（中间态 10）
- 检查（小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节）：分层键=问题类型归一化/面积均值三分位/OCR 密度均值三分位；成功=A 类 IoU 最高 10；失败=B 类 IoU 最低 10；中间态=B 类多样贪心 10；C_topk=0 为定义性结果不许写成发现；记录页 `experiments/2026-09-17-exp-005-gate-closeout.md` + registry EXP-005 行

## phase1c-baselines（已实现，批次 5，EXP-006）

```powershell
./tasks.ps1 phase1c-smoke
./tasks.ps1 phase1c-baselines
```

- 输入：EXP-001 Top-5 + `nodes.parquet` + `region_labels.parquet`（冻结只读）+ 冻结 ColPali 缓存（页向量缓存-only，query 文本塔 GPU 编码）
- 输出：`artifacts/baselines/mmdocir_1c/phase1c_smoke.json`（冒烟 10A/0B）+ `phase1c.json`（全量 1343A/45B：Snappy max/mean/iou + 固定 coverage/iou_mass + 分组 P25/P50/P75）+ `phase1c_picks.json`（1388 题逐题五档 picks，供 Text 双轨）+ `phase1c_probes.json`（`run_phase1c_probes.py` 清洗探针：cuda:0，n=19 去 warmup，权重基座 5653.3MB；query 编码 mean 38.1ms；七档选框合计 243.0ms，P75 191.7ms 最贵；单页单点不可推广）
- 检查（小论文执行规范 `docs/PAPER_SPEC.md` 第 7.4 节）：A Top-1 选框准确率（最高 0.3187 fixed:iou_mass）+ B 消解率（固定五档全 0.0）；B 分母为严格 45（非 47=45B+2A）；group 的 B 碰框率虚高不计消解；`page_size` 三用途行号见 EXP-006§3；记录页 `experiments/2026-09-17-exp-006-phase1c.md` + registry EXP-006 行

## phase1b-abcd（已实现，批次 M4，EXP-002）

```powershell
uv run python -c "from layoutpatch.evaluation.region_diagnosis import diagnose; d = diagnose(k=5); print(d.a_page_hit_region_hit, d.b_page_hit_region_miss, d.c_page_miss_region_hit, d.d_page_miss_region_miss)"
```

- 输入：EXP-001 run 的 `predictions.parquet`（Top-5）+ `nodes.parquet`（页内候选框）+ `region_labels.parquet`（2638 行 gold 区域）
- 输出：`artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`
- 检查（`docs/PAPER_SPEC.md` 第 7.3 节）：A 页中区中 / B 页中区不中 / C 页不中区中 / D 都不中；
  当前值 A=1345/B=45/C=0/D=268，B 占页命中 3.24%；IoU 口径 `bbox_iou`≥0.5（0.3/0.5/0.7 敏感性 0.8154/0.8112/0.8100）；
  与 EXP-001 差 1 题为 gold 页口径差异（`mmdocir_01342`）；记录页 `experiments/2026-09-16-exp-002-abcd-diagnosis.md` + registry 第二行
