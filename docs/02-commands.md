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

## route-v2-identity（外部源固定 + 身份审计四步，task）

```powershell
./tasks.ps1 route-v2-identity
```

- 输入/输出：依次执行下列四步（底层等价，备查）；某步产物已存在则跳过，不覆盖。全程不打分、不训练。
- 检查：`artifacts/route_v2_data/verification_v1/verification_report.json` 的 `decision_counts`；`internal_identity_v1.json` 的 `confirmed_doc_groups`。约 3–5 分钟（首次含约 133MB 下载）。

### 底层等价（备查）1/4：acquire（固定外部测试源，仅作身份审计）

```powershell
uv run --offline --no-sync python scripts/acquire_route_v2_external.py
```

- 输入：官方HF `Yuwh07/SciEGQA-Bench` revision `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`；脚本联网获取README、JSONL和PDF.tar（共约133MB），uv不安装依赖。
- 输出：`data/raw/sciegqa_bench/<revision>/` 与SHA256回执；不读取输出题目/答案/gold、不打分、不下载1.1GB Images.tar或模型。
- 检查：固定文件大小和校验和一致；已存在源仅复核不覆盖。网络失败保留.part供诊断。身份核查不等于数据许可证已经确认。

### 底层等价（备查）2/4：identity（固定阈值的身份/近重复检查）

```powershell
uv run --offline --no-sync python scripts/audit_route_v2_identity.py
```

- 输入：MMDocIR原annotations/pages（包括已批准重定用途的旧test身份）、固定SciEGQA标注/PDF；仅程序处理题目、OCR、图像用于去重，不输出答案/gold或计算模型分数。
- 输出：`artifacts/route_v2_data/identity_v1/`，阈值策略、页指纹、overlap_report；报告输入SHA256、每层匹配、隔离文档和限制。
- 检查：80篇外部/313篇本地页面覆盖完整；文档ID、问题近重复、全页文本5-gram Jaccard、64bit pHash+缩略图RMSE交叉核查。匹配文档仅从MMDocIR训练/开发侧隔离，外部题集不删。首次约数分钟；无训练、无额外模型编码；旧文件只读。

### 底层等价（备查）3/4：verify（内容复核，不评模型）

```powershell
uv run --offline --no-sync python scripts/verify_route_v2_candidates.py
```

- 输入：第一阶段候选及原始页/PDF；用正文、160像素前景图、标题复核低分辨率图像候选。
- 输出：`artifacts/route_v2_data/verification_v1/`；约1分钟，未知候选保守隔离。
- 检查：候选不等于重复；确认/模板误报/未知分别列出，输入绑定SHA256。结果仍须结合本地去重和最终split验证。

## route-v2-data（数据角色、坐标门、区域单元与监督可视化，task）

```powershell
./tasks.ps1 route-v2-data
```

- 输入：MMDocIR evaluation 原始 annotations/layouts、processed pages、页向量缓存、旧 s2_splits 清单（只读）与 route-v2-identity 产物。不写题目/答案原文。
- 输出（已存在则跳过，不覆盖）：
  1. `experiments/route_v2_splits/data-roles-v1/`：四角色 ID、`split_proof.json`、`identity_inputs.json`（进 git，只含 ID）；
  2. `artifacts/route_v2_data/coordinate_audit_v1.json`：token 布局、页框比例、框-墨迹召回、缓存签名；
  3. `artifacts/route_v2_data/regions_v1/`：`units.parquet`、`candidates.parquet`、`questions.parquet`、`audit.json`；
  4. `artifacts/route_v2_data/regions_v1/supervision_viz/`：8 张固定样本叠图 + `index.json`。
- 检查：`split_proof.json` 的 `pairwise_document_intersections` 全空、`identity_units_crossing_roles` 为空；`coordinate_audit_v1.json` 的 `passed`；`audit.json` 各角色 `units_local_loss_ready`。约 3–6 分钟，CPU。
- 底层等价（备查）：`uv run --offline --no-sync python scripts/{build_route_v2_split,audit_route_v2_coordinates,build_route_v2_regions,render_route_v2_supervision}.py`，按此顺序。

## route-v2-smoke（管线可学习性验证，task；不是效果实验）

```powershell
./tasks.ps1 route-v2-smoke
```

- 输入：上一步全部产物 + `artifacts/route_v2_data/query_cache_v1/source_queries.pt`（非隔离来源题的问题向量，至少含固定 16 题；格式见脚本 `QUERY_SCHEMA`。截至 2026-10-04 不存在，生成需另行批准）。
- 输出：`artifacts/route_v2_smoke/<timestamp>/preconditions.json`；全部前置通过时另有 `adapter.pt`、`smoke_result.json`。
- 检查：前置失败时退出码 2、不训练、不替换输入。通过时看 `smoke_result.json` 的 loss、grad_norm、`mean_gap`、`nonfinite_steps`。CPU，预计数分钟。smoke 结果永不进论文。

## route-v2-data-tests（身份与划分合成检查）

```powershell
uv run --offline --no-sync ruff check scripts/acquire_route_v2_external.py scripts/audit_route_v2_identity.py scripts/verify_route_v2_candidates.py src/layoutpatch/datasets/route_v2_split.py tests/datasets/test_route_v2_split.py tests/datasets/test_identity_verification.py
uv run --offline --no-sync pytest tests/datasets/test_route_v2_split.py tests/datasets/test_identity_verification.py
```

- 输入：合成身份/图像/划分；不读取真实问题或gold。
- 输出：终端结果；约数秒。
- 检查：不同来源角色隔离、全局ID保持、未知证据不自动通过、图像重编码控制与正文判据。

### 底层等价（备查）4/4：internal（本地全文近重复）

```powershell
uv run --offline --no-sync ruff check scripts/audit_route_v2_internal_duplicates.py tests/datasets/test_internal_identity.py
uv run --offline --no-sync pytest tests/datasets/test_internal_identity.py
uv run --offline --no-sync python scripts/audit_route_v2_internal_duplicates.py
```

- 输入：本地20395页OCR、已生成图像指纹；不读取答案/gold。
- 输出：`artifacts/route_v2_data/internal_identity_v1.json`及阈值策略；约数分钟。
- 检查：正文三词组Jaccard、低频倒排和图像候选；区别整文档重复、多页共享、单页模板和未知。不得由单个版权页认定整文档相同；划分侧保守处理未消解重叠。

## route-v2 单元检查（CPU合成数据，不是效果实验）

```powershell
uv run --offline --no-sync pytest tests/layout/test_schema.py tests/datasets/test_input_policy.py tests/datasets/test_route_v2_split.py tests/datasets/test_route_v2_regions.py tests/evaluation/test_region_labels.py tests/evaluation/test_region_metrics.py tests/evaluation/test_page_aware_iou.py tests/evaluation/test_localization.py tests/retrieval/test_fusion_shapes.py tests/retrieval/test_fusion_v2.py tests/retrieval/test_phase1c.py tests/retrieval/test_route_v2_scoring.py
```

- 输入：上述测试的合成张量及pytest临时目录数据；现有uv环境，不同步或下载依赖。
- 输出：终端通过/失败；只写pytest临时产物，不写真实数据、权重或runs。
- 检查：类型/OCR来源、新旧输入兼容、文档/页ID一致、空patch/mask、覆盖输入、小残差及同页IoU；通过不表示效果提升，完整质量门仍为check。

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

## phase2r-arxivqa（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-arxivqa
```

- 输入：已编码的 ArxivQA `train_fit`/`train_dev` 页向量缓存；`dev_eval` id。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa/dev_eval.json`
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-dude（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-dude
```

- 输入：已编码的 DUDE `train_fit` 3330 页、`train_dev` 422 页。ColPali 与 bge 都必须非空。不读 `test_eval`。
- 输出：`artifacts/phase2r/dude/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_dude/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-arxivqa-dude（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-arxivqa-dude
```

- 输入：已有缓存里的 ArxivQA 与 DUDE `train_fit`/`train_dev` 页。缺页即停，不新编页。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa_dude/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_arxivqa_dude/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-gap-audit（只读，不训练）

```powershell
uv run python scripts/audit_phase2r_gaps.py
```

- 输入：三份冻结 `ranker.pt`、`dev_eval_region_401.txt`、当前 `region_labels.parquet`。不读 `test_eval`。
- 输出：`experiments/s2_splits/phase2r_gap_proof.json`、`phase2r_per_question.jsonl`、`phase2r_per_question_summary.json`。
- 检查：401 题单等于现行 matched 题；六个 Area 汇总数与三份旧 `metrics.json` 逐位一致。不改权重。

## phase2r-arxivqa-notext（无文本对照，不替换当前头）

```powershell
./tasks.ps1 phase2r-arxivqa-notext
```

- 输入：已有 ArxivQA 页缓存。缓存数量不是 8341 就停。不编新页。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa_notext/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_arxivqa_notext/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## fusion-arxivqa（第一次正式融合训练，ArxivQA 单域）

```powershell
./tasks.ps1 fusion-arxivqa
```

- 输入：已有 ArxivQA `train_fit`/`train_dev` 页向量与 query 缓存；训练 parquet 真实框；`dev_eval` id。不读 `test_eval`。不编码新页。不加载 ColPali。
- 输出：`artifacts/fusion/arxivqa/` 的 fusion checkpoint，以及 `runs/retrieval/mmdocir_fusion_arxivqa/<timestamp>/` 五件套。
- 检查：监督只有页级正负页；不覆盖任何 `ranker.pt`；区域分母 401，页级分母 415；未过 geom:area 则只记 dev 失败，不读 test_eval。

## region-ann-pilot（40 题本地标注流程，不训练）

```powershell
./tasks.ps1 region-ann-pilot
```

- 输入：`experiments/region_annotation/arxivqa_pilot_manifest.jsonl` + `pilot_materials/samples/*/page.png|overlay.png`。不读 `dev_eval` / `test_eval`。不改 template / manifest。不自动填框。不覆盖已有 `labels_annotator_A.jsonl` / `labels_annotator_B.jsonl`。v1 结果用独立文件，例如 `labels_annotator_A_v1.jsonl`。
- 输出：`pilot_materials/workbook.html` + `workbook.js`。人工标签由浏览器导出为独立 A/B 文件。检查可用 `uv run python scripts/region_ann_pilot.py check --annotator A|B`，或 `--labels` 指向临时/归档文件。
- 检查：40 题 PNG 都能打开；报告缺失字段、重复题目、非法/重复 `box_id`、状态冲突、无候选与选框冲突、题目元数据是否被改。`pending` 的 `cover_ok` / `no_candidate` / `cross_box` 必须为 `null`。多个独立 `full` 框允许 `cross_box=false`。浏览器不会写回仓库文件。
