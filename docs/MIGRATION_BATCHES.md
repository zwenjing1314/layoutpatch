# 迁移批次清单（旧仓库 mmdoc-evidence-rag → LayoutPatch，按小论文实验推进分批）

> Status: working | 用途：每完成一个实验阶段，搬运对应批次；每批自带"完成判据"，判据不绿不进下一批。
> 与 `docs/MIGRATION.md`（旧仓库版总清单）的关系：本文件是执行版，按时间顺序切片；两处冲突以本文为准。
> 纪律：每批只搬列出的文件；发现"顺手也想搬"的东西，先登记到本文"待定区"，经确认再入批。

## 批次 0：环境与质量门（已由骨架完成，此批只剩执行）

```text
[x] pyproject.toml            包名 layoutpatch，CLI=lp，锁版本与 cu130 源继承旧仓库
[x] .python-version           3.11
[x] .gitignore                data/ artifacts/ runs/ tmp/ 永不进 git
[x] .env.example              HF_HOME=artifacts/hf_cache
[x] tasks.ps1                 check / env-verify / mmdocir-prepare / mmdocir-colpali-full / evaluate
[x] src/layoutpatch/__init__.py
[x] tests/conftest.py         gpu 标记自动跳过（借 colpali-official-repro 方案）
[x] tests/test_package.py  tests/test_gpu_marker.py
[ ] git init + 首个 commit（本批文件全部入库）
```

完成判据：`./tasks.ps1 check` 三绿；`./tasks.ps1 env-verify` 输出 CUDA True。

## 批次 1：规范文档（先立规矩，再搬代码）

```text
[ ] docs/THESIS_SPEC.md      ← 旧 docs/THESIS_RESEARCH_ROUTE_DRAFT.md 全文覆盖占位，改内部引用
[ ] docs/PAPER_SPEC.md       ← 旧 docs/SMALL_PAPER_DEV_SPEC.md 全文覆盖占位，mmdocrag→layoutpatch
[ ] docs/01-quickstart.md    ← 旧同名，改 uv 命令与数据根路径说明
[ ] docs/02-commands.md      ← 旧同名，改 mdr→lp、任务名与本仓库 tasks.ps1 对齐
[ ] docs/03-glossary.md      ← 旧同名直接复制
[ ] .cursor/skills/mmdoc-evidence-research/ ← 旧仓库 .cursor/skills/ 整目录复制
[ ] 复制后全库 grep "mmdocrag|mdr "，清零残留引用
```

完成判据：`docs/00-index.md` 六类信息表指向全部存在；grep 残留为 0。

## 批次 2：数据准备（跑通 prepare 才算接上数据源）

```text
[x] src/layoutpatch/config.py  paths.py  schemas.py  io.py   ← 骨架四件，改包名（已完成）
[x] src/layoutpatch/datasets/adapters.py                     ← MMDocIR prepare（对数逻辑原样，仅 demo/mmdocir 主线，不含中文年报）
[x] configs/datasets/mmdocir.yaml                            ← 变量改为 LAYOUTPATCH_*
[x] configs/README.md                                        ← 只登记本仓库实际存在的 config
[x] tests/test_schemas_io.py                                 ← 旧测试直搬改包名（test_data_splits.py 待 M3 管线落地后补）
[x] tests/datasets/test_adapters.py                          ← 参照 repro 风格按模块建子目录（新写）
[x] M2.5 region_labels：官方 evaluation 原始三文件复制到本仓库 data/raw/；src/layoutpatch/evaluation/region_labels.py + scripts/build_region_labels.py + adapters with_region_labels 开关 + tests/evaluation/test_region_labels.py；region_labels.parquet 2638 行（2523 matched + 115 unmapped），四表对数未动
```

完成判据：`./tasks.ps1 mmdocir-prepare` 对数 313/20395/170338/1658。

## 批次 3：Phase 1A 复验（页级 baseline 搬运与重跑）

```text
[x] src/layoutpatch/retrieval/pipeline.py  scoring.py        ← 检索管线（仅 bm25/dense/colpali/hybrid 四页级分支，region/evidence_set/oracle 不搬）
[x] src/layoutpatch/retrieval/colpali.py                     ← ColPali 编码 + MaxSim + embedding cache（包名/日志前缀改为 layoutpatch/lp，MPS 分支删除）
[x] src/layoutpatch/evaluation/metrics.py  pipeline.py       ← 页级指标（sufficiency.py 不搬）
[x] src/layoutpatch/cli.py                                   ← retrieve/evaluate 命令已注册（prepare 保留）
[x] configs/experiments/mmdocir_colpali.yaml                 ← 正式 config（原样）
[x] configs/experiments/mmdocir_bm25_page.yaml               ← BM25 对照（原样）
[x] configs/experiments/mmdocir_colpali_smoke.yaml           ← smoke config（2 文档限流）
[x] tests/test_retrieval_metrics.py  test_colpali_integration.py  ← 页级用例（旧方向分支不搬）
[x] artifacts/colpali/ embedding cache 20395 个 .pt 已复制（签名含旧绝对路径 → 判失效，EXP-001 改为本机全量重编码）
[x] experiments/registry.csv + experiments/2026-09-16-exp-001-colpali-full.md ← EXP-001 已登记（首行）
[x] docs/reproduction/colpali_vidore_v1_reproduction_20260830.md ← 复现凭证（从旧仓库迁入）
[x] 旧 run 目录 runs/retrieval/mmdocir_colpali/20260912_221714 只读留档（旧仓库不动；新仓库 EXP-001=20260916_105545 作对照）
```

完成判据：`./tasks.ps1 mmdocir-colpali-full`，R@5=0.8390 与旧 0.8390 偏差 0.0000 < 0.005；本仓库登记 EXP-001（迁移复验）。**批次 3 完成（2026-09-16）。** 补充（2026-09-17）：`mmdocir_bge_m3_page.yaml`（EXP-003，R@5=0.7750，run 20260917_113452）与 `mmdocir_hybrid_page.yaml`（EXP-004，R@5=0.7883，run 20260917_115238）已跑完登记，第 7.2 节四基准同表为 ColPali 0.8390 / Hybrid 0.7883 / BGE-M3 0.7750 / BM25 0.7521（同 1658 query、同文档内范围、同 Top-20、同脚本）。

## 批次 4：Phase 1B 缺口诊断（需要 OCR/布局数据，是新增代码的起点）

```text
[x] src/layoutpatch/layout/correspondence.py ← W cover 定义 + 行归一化 + 空行标记（新写，已完成 2026-09-16；fill/iou 候选未实现，按 PAPER_SPEC dev 定一种）
[x] src/layoutpatch/evaluation/audit.py      ← 坐标审计（机器门限 + 叠图）（新写，已完成 2026-09-16；关键修复 c7a817c：去掉页号 -1 偏移，文本判别法双文档验证 layouts 页号与页图序号同义）
[x] src/layoutpatch/evaluation/audit_overlays.py + scripts/run_phase1b_audit.py ← 叠图链路（已登记 02-commands 的 phase1b-audit；判读口径：框围内容不看网格；用户已确认 p69 通过）
[x] src/layoutpatch/evaluation/region_metrics.py ← 正式 bbox IoU（新写，已完成 2026-09-16，EXP-002 用 IoU≥0.5）
[x] src/layoutpatch/evaluation/region_diagnosis.py ← A/B/C/D 静态诊断（新写，已完成 2026-09-16；EXP-002：A=1345/B=45/C=0/D=268，B 占页命中 3.24%）
[x] artifacts/audit/mmdocir_evaluation/audit.json ← 机器门限（20261 页/170338 区域/越界 1/零覆盖 0/Gate 全过）
[x] artifacts/audit/mmdocir_evaluation/overlays/  ← 20 张叠图（已修页号重生成）
[x] artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json + experiments/2026-09-16-exp-002-abcd-diagnosis.md ← EXP-002 已登记（45af9c0）
[ ] src/layoutpatch/layout/nodes.py          ← TextLayoutEncoder → T [M,D]（未动；Phase 2 前再写，当前诊断不需要 T）
[ ] src/layoutpatch/retrieval/layout_index.py ← BM25/结构信号检索布局节点（未动）
[ ] configs/experiments/mmdocir_layout_node_bge_m3.yaml ← 旧仓库预备 config 复制（未动，随 EXP-003/004 一起补）
[x] 分层表（问题类型归一化 12 组/面积均值三分位/OCR 密度均值三分位）+ 10 成功/10 失败 + 10 中间态案例图（第 7.3 节，EXP-005 已完成 2026-09-17：`scripts/run_phase1b_stratify.py` 统一脚本 + `stratification.json`（meta 冻结 k/iou/面积均值定义/三分位点）18 行 + `cases.json`（meta 三档定义）+ `crosstab/addressability/oracle.json` + `strat_*_hist.png/json` + `overlays_cases/` 20 张 + `overlays_cases_mid/` 10 张；结论：B=45/45 unmapped_only，可寻址双分母 0.0，离 10% 线低 10pp；Top-K 内 C=0 为定义性结果；oracle 页命中内 96.76%/全量 96.50%）
[ ] 判据前置：先过坐标审计，再谈任何区域指标（已过：机器 Gate + p69 人工确认；其余 19 张待抽查；EXP-005 的 30 张案例图待用户同口径抽查，重点 `M_mmdocir_00522`）
```

完成判据：A/B/C/D 四象限产出 + 按 10 类问题类型分层表 + 10 成功/10 失败案例图；registry 登记。（进度：主表 EXP-002 + 关门 EXP-005 均已出；批次 4 已关，S1 记录页恢复留档标 SUPERSEDED，registry 保留两行；30 张案例图待用户抽查。）

## 批次 5：Phase 1C 无训练基线（三选一前先测 Snappy 传播）

```text
[x] src/layoutpatch/retrieval/propagation.py      ← Snappy 式 patch→区域传播（新写 2026-09-17；max/mean/iou 三聚合；MaxSim 展平修复 reshape(-1,1024).amax）
[x] src/layoutpatch/retrieval/region_pooling.py   ← 固定 IoU/coverage 聚合（新写 2026-09-17；coverage/iou_mass 双模式）
[x] src/layoutpatch/retrieval/region_grouping.py  ← 动态显著分组（新写 2026-09-17，不许称 RegionRAG 复现；四连通组框，阈值 eta 取 P25/P50/P75）
[x] scripts/run_phase1c.py                        ← 1C 跑者（新写；冒烟 --limit-docs 2 + 全量 1343A/45B；B 分母严格 45 非 47；`./tasks.ps1 phase1c-smoke/baselines` 对齐）
[x] tests/retrieval/test_phase1c.py                ← 6 单测（聚合/组框/展平/缓存布局断言 [7 prefix, 1024 patches]）
[x] artifacts/baselines/mmdocir_1c/phase1c.json    ← EXP-006 决策材料（1343A Top-1 最高 0.3187 fixed:iou_mass；45B 固定五档消解全 0.0；group 碰框虚高不计）
```

完成判据：三基线区域指标同表输出；1C 决策材料（B 类占比 3.24%、Snappy 最好消解 0/45=0.0、P25/P50/P75 敏感性、A 选框准确率）齐备交导师确认。**批次 5 已跑完（2026-09-17，EXP-006）→ 不进 Phase 2，转 11.3 收缩（B1/B2）。禁令：未过 1C Gate 不建 fusion/ 子包、不写 train_fusion.py。**

## 批次 6：Phase 2 融合模块（只有 1C Gate 通过才解锁）

```text
[ ] src/layoutpatch/fusion/sparse_fusion.py  gate.py  fused_index.py  region_scoring.py
[ ] configs/experiments/mmdocir_fusion_*.yaml   训练/评测 config（新建）
[ ] tests/fusion/ 单测 + 一个 smoke 训练（1 query/1 doc 级别）
[ ] 训练前：MMDocIR train 标签构造规则审查（防泄漏），完成后 hyperparams_frozen.json 入 run 目录
```

完成判据：按 PAPER_SPEC 第 8 节完整评测矩阵 + 效率表与 LFRAG/ColParse 的 k+1 行同表。

2026-09-27 修订：全融合 `fusion/` 仍锁定。现行先行路径是 Phase 2-R 小打分层，不是本批的 `sparse_fusion.py`。设计已冻结在 `experiments/2026-09-26-phase2r-design-frozen.md`。训练仍未开始。下一步只编码，见 `docs/handoff.md` 置顶节。不要因为本批未勾选就删除已有的 `src/layoutpatch/retrieval/rerank/`。

## 每批通用的"搬完必做"

```text
1. ./tasks.ps1 check 三绿
2. registry/记录页/handoff 三处同步
3. 本文件勾掉对应项
4. 全库 grep 旧名残留：mmdocrag / mdr / mmdoc-evidence-rag / docs/10-small-paper
```

## 明确不进新仓库（永久留在旧仓库）

```text
src/mmdocrag/evaluation/sufficiency.py     旧 evidence-set 方向
tests/test_evidence_sufficiency.py  test_cn_annual_reports_v2.py  同上
cn_annual_reports 全部 config/split/数据    被否方向
docs/90-archive/ 全部、docs/10-small-paper/、docs/paper/ 旧四篇
docs/freeze-20260912/、environment.yml
```

## 待定区（发现想搬但不在批次里的东西，先记这里）

```text
[ ] src/mmdocrag/exporting/demo.py            demo 导出，是否需要等 1A 复验后再定
[ ] tests/test_demo_smoke.py                  随 demo.py 一起决定
[ ] docs/20-experiments/mmdocir-external.md   外部实验笔记，1B 时决定是否仍有价值
```
