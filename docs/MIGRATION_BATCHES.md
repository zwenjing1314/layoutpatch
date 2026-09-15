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
[ ] src/layoutpatch/retrieval/pipeline.py  scoring.py        ← 检索管线
[ ] src/layoutpatch/retrieval/colpali.py                     ← ColPali 编码 + MaxSim + embedding cache
[ ] src/layoutpatch/evaluation/metrics.py  pipeline.py       ← 页级指标（sufficiency.py 不搬）
[ ] src/layoutpatch/cli.py                                   ← prepare/retrieve/evaluate 三命令
[ ] configs/experiments/mmdocir_colpali.yaml                 ← 正式 config
[ ] configs/experiments/mmdocir_bm25_page.yaml               ← BM25 对照
[ ] tests/test_retrieval_metrics.py  test_colpali_integration.py
[ ] （可选省 8 小时）artifacts/colpali/ embedding cache 从旧仓库复制
[ ] experiments/registry.csv + templates/experiment-record.md ← 登记体系
[ ] docs/reproduction/colpali_vidore_v1_reproduction_20260830.md ← 复现凭证
[ ] 旧 run 目录 runs/retrieval/mmdocir_colpali/20260912_221714 只读留档
```

完成判据：`./tasks.ps1 mmdocir-colpali-full`，R@5 与旧 0.8390 偏差 < 0.005；本仓库登记 EXP-001（迁移复验）。

## 批次 4：Phase 1B 缺口诊断（需要 OCR/布局数据，是新增代码的起点）

```text
[ ] src/layoutpatch/layout/nodes.py          ← TextLayoutEncoder → T [M,D]（新写，按 PAPER_SPEC 第 5 节）
[ ] src/layoutpatch/layout/correspondence.py ← W 三种定义 + 行归一化 + 空行标记（新写）
[ ] src/layoutpatch/evaluation/region_metrics.py ← IoU Hit@0.5 + Text Recall/F1 + A/B/C/D + 分层（新写）
[ ] src/layoutpatch/evaluation/audit.py      ← 坐标审计（机器门限 + 叠图）（新写）
[ ] src/layoutpatch/retrieval/layout_index.py ← BM25/结构信号检索布局节点（新写）
[ ] tests/layout/  tests/evaluation/         ← 对应单测（新写）
[ ] configs/experiments/mmdocir_layout_node_bge_m3.yaml ← 旧仓库预备 config 复制
[ ] 判据前置：先过坐标审计，再谈任何区域指标
```

完成判据：A/B/C/D 四象限产出 + 按 10 类问题类型分层表 + 10 成功/10 失败案例图；registry 登记。

## 批次 5：Phase 1C 无训练基线（三选一前先测 Snappy 传播）

```text
[ ] src/layoutpatch/retrieval/propagation.py      ← Snappy 式 patch→区域传播（新写，需先审计坐标映射）
[ ] src/layoutpatch/retrieval/region_pooling.py   ← 固定 IoU/coverage 聚合（新写）
[ ] src/layoutpatch/retrieval/region_grouping.py  ← 动态显著分组（新写，不许称 RegionRAG 复现）
[ ] configs/experiments/ 三个对应 yaml             ← 新建
[ ] tests/retrieval/ 对应单测
```

完成判据：三基线区域指标同表输出；1C 决策材料（B 类占比、Snappy 消掉比例、dev/test 趋势）齐备交导师确认。

## 批次 6：Phase 2 融合模块（只有 1C Gate 通过才解锁）

```text
[ ] src/layoutpatch/fusion/sparse_fusion.py  gate.py  fused_index.py  region_scoring.py
[ ] configs/experiments/mmdocir_fusion_*.yaml   训练/评测 config（新建）
[ ] tests/fusion/ 单测 + 一个 smoke 训练（1 query/1 doc 级别）
[ ] 训练前：MMDocIR train 标签构造规则审查（防泄漏），完成后 hyperparams_frozen.json 入 run 目录
```

完成判据：按 PAPER_SPEC 第 8 节完整评测矩阵 + 效率表与 LFRAG/ColParse 的 k+1 行同表。

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
