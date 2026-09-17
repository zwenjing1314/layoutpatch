# 工作交接记录（变化的进度）

> 用途：新开 Cursor 窗口时手动 `@docs/handoff.md`，让新会话接上当前进度。
> 约定：每次会话结束前更新本文件；本文件只写变化的进度，不写不变的规范（规范在 `.cursor/rules/` 与 `docs/RULES.md`）。
> 配套必读：`docs/MIGRATION_BATCHES.md`（批次清单）→ `docs/00-index.md`（SSOT 导航）→ `docs/PAPER_SPEC.md`（小论文执行规范）。

## 一句话总览（给新窗口的第一段）

- 项目：LayoutPatch（布局约束的文档侧 patch 融合），旧仓库 `mmdoc-evidence-rag` 迁移而来，保持只读，永不修改。
- 目标：ColPali 页级已达 R@5=0.8390，在此之上长出页内区域定位能力，约束见 `docs/PAPER_SPEC.md` 第 5 节（单次编码/不裁剪/MaxSim 接口不动）。
- 关键结论速记：EXP-001 复验通过（R@5=0.8390 逐位一致）→ 叠图曾因"页号差一"全错，已修（`c7a817c`）→ 机器审计 Gate 通过（越界 1/170338）→ EXP-002 A/B/C/D 首次诊断：B 类仅 3.24%（45/1390），Top-K 内 C=0 为定义性结果（区域命中要求页命中，不许写成发现） → EXP-003 BGE-M3（R@5=0.7750）/ EXP-004 Hybrid（R@5=0.7883）补齐第 7.2 节四基准 → EXP-005 关门：B=45/45 全 unmapped_only，可寻址 B 双分母均为 0.0（离 10% 线低 10pp）；oracle 页命中内 96.76%/全量 96.50%；自匹配 5 题 IoU 全 1.0（候选召回上限非排序能力；B 是 oracle 未中 58 题真子集；unmapped_only 有 2 题 both-A 反例） → EXP-006 实测 1C：1343A Top-1 最高 0.3187，45B 固定五档消解全 0.0，不进 Phase 2 转收缩。
- 当前位置：`docs/MIGRATION_BATCHES.md` 批次 5 已跑完（Phase 1C，`docs/PAPER_SPEC.md` 第 7.4 节三基线 + P25/P50/P75，registry 为 EXP-006）；下一步是与导师按 11.2/11.3 共判收缩（B1/B2）。

## 当前 Phase 与 Gate 状态

- 当前所处阶段：**M5（Phase 1C 三无训练基线，迁移批次清单批次 5）已跑完**；见 `docs/MIGRATION_BATCHES.md` 批次清单与小论文执行规范 `docs/PAPER_SPEC.md` 第 7.4 节。**第 7.2 节四基准已齐**：ColPali R@5=0.8390（EXP-001）/ BM25 R@5=0.7521（20260915_215504）/ BGE-M3 R@5=0.7750（EXP-003）/ Hybrid R@5=0.7883（EXP-004）。**EXP-005（2026-09-17，关门）**：交叉表 matched 题 1598（A=1343/B=0/D=255）+ unmapped_only 题 60（A=2/B=45/D=13）；可寻址 B=0，双分母 0/1390=0.0、0/1598=0.0，离 10% 线各低 10pp；oracle 页命中内 1345/1390=96.76%、全量 1600/1658=96.50%，框缺口 45/58；自匹配 5 题 IoU 全 1.0（候选召回上限非排序能力；B 是 oracle 未中 58 题真子集；2 题 both-A 反例）；分层 18 行 + 极值 20 + 中间态 10；面积/覆盖直方图已落盘。**EXP-006（2026-09-17，1C 实测）**：1343A Top-1 最高 0.3187（fixed:iou_mass）/ Snappy-iou 0.2621 / max/mean ~0.10 / group ≤0.1035；45B Snappy/固定五档消解全 0.0（group 碰框 0.6889/0.3556/0.0889 虚高不计）；B 占比 3.24% 且可寻址 0 → 不进 Phase 2，转 11.3 收缩。
- 已完成的 Phase 与 2026-09-16 当天关键事件：
  - M0/M1/M2/M2.5 全部完成（环境、四表 313/20395/170338/1658、`region_labels.parquet` 2638 行）。
  - M3 完成并加固：旧缓存 20395 个 `.pt` 拷入后按**选项 A（用户亲批）**全删、从零重编码 run `20260916_134144`（约 52 分钟，最早 13:42:28、最晚 14:34:58），七指标与旧仓逐位一致（R@5=0.838962605548854），顶替作废的 `20260916_105545`。
  - M4 前半完成：`correspondence.py`（Snappy 公式 + W cover/行归一化/`row_normalize`）+ 单元测试 `tests/layout/test_correspondence.py`；`audit.py`（原图坐标越界判定）+ `audit_overlays.py`（32×32 网格 + 布局框叠图）+ `scripts/run_phase1b_audit.py`（已登记 `docs/02-commands.md` 的 `phase1b-audit`）。
  - M4 关键 bug 与修复：叠图曾错页（`_page_image_for` 写了 `-1` 偏移，把框画到前一页），文本判别法双文档验证（IBM 直配 779 对差一 3；arXiv 直配 135 对差一 0）证 layouts 页号与页图序号同义，已修（`c7a817c`），`audit.json` 重算：20261 页/170338 区域/越界 1/零覆盖 0/Gate 全过。
  - EXP-002 完成（`45af9c0`）：正式 `region_metrics.bbox_iou` + `region_diagnosis.py` + `tests/evaluation/test_region_metrics.py`，`artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`：A=1345、B=45、C=0、D=268；B 占页命中 3.24%；IoU 敏感性 0.3/0.5/0.7 = 0.8154/0.8112/0.8100；与 EXP-001 的 1 题差因 gold 页口径不同（`mmdocir_01342`：evidence 页 p182 进 Top-5，region_labels 框在 p149）。
- 下一个 Gate：

```text
批次 4 已关（PAPER_SPEC 第 7.3 节）：主表 EXP-002 + 关门 EXP-005（交叉表/双分母 0.0/oracle/直方图/30 张案例/自匹配 5 题）均已登记 registry；叠图判读口径：看彩色框围没围住真实文字/表格（红=表格/橙=段落/绿=图，黄粗框=gold），不看框边压没压网格线；顶部小字/底部文字/页码未框属官方稀疏（p69 已确认通过）；EXP-002-S1 记录页恢复留档标 SUPERSEDED，registry 保留两行；matplotlib 由 scipy/sklearn 间接引入已锁 uv.lock，主依赖未回填（见 EXP-005 第 8.5 节声明）。
第 7.2 节已关（2026-09-17）：EXP-003（run 20260917_113452，CPU 约 13.4 分钟）+ EXP-004（run 20260917_115238，CPU 约 13.5 分钟）已登记 registry 第三四行。
批次 5 已跑完（Phase 1C，PAPER_SPEC 第 5.6/7.4 节，EXP-006）：新建 propagation.py / region_pooling.py / region_grouping.py + scripts/run_phase1c.py + tests/retrieval/test_phase1c.py（含 Snappy max/mean/iou 三聚合 + P25/P50/P75 敏感性；`./tasks.ps1 phase1c-smoke/baselines` 对齐）；1343A Top-1 最高 0.3187，45B 固定五档消解全 0.0；决策材料交导师按 11.2/11.3 判收缩（B1/B2）。
批次 6（Phase 2）禁令重申：未过 1C Gate 不得新建 fusion/ 子包与训练代码、不写 train_fusion.py；训练前须用户+导师双确认。
阻塞问题：无（旧仓库保持只读，不做修改；GPU 当前空闲）
```

## 最近 runs（本地产物，不进 git）

| EXP | run 目录 | 关键指标一句 | 是否可用 |
| --- | --- | --- | --- |
| EXP-001 | `runs/retrieval/mmdocir_colpali/20260916_134144`（作废：`20260916_105545`、`20260916_125129`、`20260915_215535` 均已删半成品或被顶替） | Phase 1A ColPali full（本机从零重编码约 52 分钟）：R@5=0.8390 与旧仓逐位一致；predictions 30112 行/1658 query | 是（当前唯一有效 1B 分母） |
| EXP-002 | `artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`（静态诊断，无 run 目录） | Phase 1B A/B/C/D：A=1345 B=45 C=0 D=268；B 占页命中 3.24%；Top-K 内 C=0 为定义性结果（区域命中要求页命中） | 是（1B 主表；口径修正见 EXP-005） |
| EXP-003 | `runs/retrieval/mmdocir_bge_m3_page/20260917_113452` | Phase 1A BGE-M3 dense（CPU 约 13.4 分钟）：R@5=0.7750/R@1=0.4783/MRR=0.6118；actual_retrievers=dense:BAAI/bge-m3 无降级 | 是（文本 dense 基线） |
| EXP-004 | `runs/retrieval/mmdocir_hybrid_page/20260917_115238` | Phase 1A Hybrid RRF k=60（CPU 约 13.5 分钟）：R@5=0.7883 高于 BM25/BGE 单路，低于 ColPali | 是（融合对照基线） |
| EXP-005 | `artifacts/diagnosis/mmdocir_evaluation/crosstab.json` + `addressability.json` + `oracle.json` + `strat_*_hist.png/json` + `overlays_cases/`（20）+ `overlays_cases_mid/`（10） | Phase 1B 关门：B=45/45 unmapped_only；可寻址 B 双分母 0.0（离 10% 线低 10pp）；oracle 页命中内 96.76%/全量 96.50%；自匹配 5 题全 1.0（召回上限非排序能力；B 是 58 真子集；2 both-A 反例） | 是（第 7.3 节关门证据；30 张待抽查） |
| EXP-006 | `artifacts/baselines/mmdocir_1c/phase1c.json`（全量 1343A/45B，约 225 秒）+ `phase1c_smoke.json`（冒烟 10A/0B） | Phase 1C 实测：A Top-1 最高 0.3187（fixed:iou_mass）；B 固定五档消解全 0.0（group 碰框虚高不计）；不进 Phase 2 转收缩 | 是（第 7.4 节决策材料；B 分母严格 45） |

## 配置与分支状态

- 当前分支：`master`，最新 `45af9c0 feat(phase1b): abcd gap diagnosis with formal region IoU metric`；工作区改动见下。
- 未提交改动：本轮只改文档（`handoff.md`、`MIGRATION_BATCHES.md`、`02-commands.md`、`00-index.md`、`CHANGELOG.md`），代码与产物无改动；`data/`（约 12GB）/`artifacts/`/`runs/` 产物不进 git。
- 工作中 config：`configs/experiments/mmdocir_colpali.yaml`（EXP-001 冻结基线）、`configs/experiments/mmdocir_bm25_page.yaml`（BM25 对照 run `20260915_215504`，R@5=0.7521）、`configs/experiments/mmdocir_bge_m3_page.yaml`（EXP-003 新建已跑）+ `configs/experiments/mmdocir_hybrid_page.yaml`（EXP-004 新建已跑）。
- 最近 commits：`45af9c0`（EXP-002 诊断）← `c7a817c`（叠图页号修复）← `dfd2ab2`（审计机器门限）← `ffd11d0`（数据路径隔离）← `883dd41`（规则 4.4 后台执行+指令透明）。

## 实验讲解规则（新窗口必读，docs/RULES.md 第 0.2 节）

- 只要回复涉及实验，必须按小白模式展开：白话目标 → 输入是什么 → 处理逻辑 → 输出落在哪 → 怎么验证对错 → 失败会怎样 → 对应哪个文档哪一节。
- 首次出现缩写必须写全称出处（如"迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 4，对应小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节 Phase 1B"），之后才可用"批次 4/Phase 1B"。
- 每次回复的操作步骤后另附「本轮指令说明」：逐条贴本轮实际命令原文 + 一句话作用；未跑命令写"本轮未执行任何命令"。
- 实验五问模板（Phase 1A 四基准 / 坐标审计 / A/B/C/D / 1C 三基线 / Phase 2 训练动机）见 `docs/02-commands.md` 各节"判据"行。

## 数据链地图（新窗口查数用）

```text
data/raw/mmdocir_evaluation/                  官方三文件（约 4GB，不进 git）
data/interim/mmdocir_evaluation/page_images/  20395 张 jpg（约 8GB，不进 git）
data/processed/mmdocir_evaluation/            documents 313 / pages 20395 / nodes 170338 / queries 1658 + region_labels 2638（matched 2523/unmapped 115；题级 matched 1598/unmapped_only 60）
全局 HF 缓存 C:/Users/WenJing/.cache/huggingface/hub/   BGE-M3（models--BAAI--bge-m3，旧仓 robocopy，全局复用；ColPali 同在此）
artifacts/colpali/mmdocir_evaluation/vidore_colpali/  20395 个 .pt（本机 52 分钟重编码，min 265634/max 267497/零字节 0）
artifacts/audit/mmdocir_evaluation/           audit.json（20261 页/170338 区域/越界 1）+ overlays/ 20 张叠图（已修页号）
artifacts/diagnosis/mmdocir_evaluation/       abcd_diagnosis.json（EXP-002）+ EXP-005 十件（stratification/cases/crosstab/addressability/oracle/strat_*_hist.png+json/overlays_cases+mid 30 张）
artifacts/baselines/mmdocir_1c/                 phase1c.json（EXP-006 全量 1343A/45B）+ phase1c_smoke.json（冒烟 10A/0B）
runs/retrieval/mmdocir_colpali/20260916_134144/  EXP-001 五件套（唯一有效；latest 指向它）
runs/retrieval/mmdocir_bm25_page/20260915_215504/  BM25 五件套（R@5=0.7521，同口径对照）
runs/retrieval/mmdocir_bge_m3_page/20260917_113452/  EXP-003 五件套（R@5=0.7750）
runs/retrieval/mmdocir_hybrid_page/20260917_115238/  EXP-004 五件套（R@5=0.7883）
```

## 未解决问题

1. ~~Phase 1A 四基准缺 BGE-M3 dense 与 Hybrid~~已关（2026-09-17，EXP-003/EXP-004）：四基准同表为 ColPali R@5=0.8390 / Hybrid R@5=0.7883 / BGE-M3 R@5=0.7750 / BM25 R@5=0.7521（同 query 集 1658、同文档内范围、同 Top-20、同脚本）。
2. ColPali 库选型：当前 `colpali-engine>=0.3.0`（已废弃但仍可用于原始复现；`colpali-official-repro/README.md` 推荐新路用 Sentence Transformers v6 + `-hf` 模型）。结论：Phase 1A 基线不动库，Sentence Transformers 仅作未来可选新实验，不替换 `vidore/colpali` 的 0.8390。
3. 坐标审计判读口径：已固定为"框围内容、不看网格"，用户已按此口径确认 p69 通过；其余 19 张待抽查（建议表格页优先看 `NYSE_IBM_2020_p126`、`ACTIVISIONBLIZZARD_2019_10K_p113`）。EXP-005 的 30 张案例图（`overlays_cases/` 20 + `overlays_cases_mid/` 10，黄粗框=gold）待用户按同口径抽查，重点看 `M_mmdocir_00522`（IoU 0.4036、仅 2 候选）黄框内是否有文字但框偏小/偏大。
4. 134 页无官方布局节点（占 0.66%）：属官方标注稀疏，页图与缓存正常，检索可用；区域审计分母天然排除，不影响结论。
5. 1C 已跑完（EXP-006 实测）：1343A Top-1 最高 0.3187（fixed:iou_mass），Snappy-iou 0.2621；45B Snappy/固定五档消解全 0.0（group 碰框虚高不计）；B 占比 3.24% 且可寻址 0 → 不进 Phase 2，转 11.3 收缩（B1 效率/B2 失败学）。禁令：未过 1C Gate 不建 `fusion/` 子包、不写 `train_fusion.py`。

## 下一步（给新会话的指令，按序执行）

```text
1. 读完本文件 + docs/00-index.md + docs/MIGRATION_BATCHES.md + docs/PAPER_SPEC.md 第 6/7.2/7.3/7.4 节，再动手。
2. ~~补 Phase 1A（第 7.2 节）~~已关：EXP-003/EXP-004 已跑完登记；无需重跑（除非改 config 即开新版本）。
3. ~~补 Phase 1B 后半（第 7.3 节）~~已关（EXP-005，2026-09-17）：`./tasks.ps1 phase1b-stratify`（= `uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5`）已产分层 18 行 + 交叉表 + 双分母 0.0 + oracle + 直方图 + 极值 20/中间态 10 张 + 自匹配 5 题；registry 为 EXP-005（EXP-002-S1 恢复留档标 SUPERSEDED，registry 保留两行）。
4. ~~批次 5（Phase 1C）~~已跑完（EXP-006，2026-09-17）：`./tasks.ps1 phase1c-smoke`（冒烟 10A/0B 约 23 秒）+ `./tasks.ps1 phase1c-baselines`（全量 1343A/45B 约 225 秒）；新建 propagation.py / region_pooling.py / region_grouping.py + run_phase1c.py + test_phase1c.py；决策材料交导师按 11.2/11.3 判收缩（B1/B2）。
5. 批次 6（Phase 2）禁令重申：未过 1C Gate 不得新建 fusion/ 子包与训练代码、不写 train_fusion.py；训练前须用户+导师双确认。
```

## 更新记录

| 日期 | 更新内容 |
| --- | --- |
| 2026-06-16 | M0 骨架完成：根目录 12 个条目、src 包结构、tests（参考官方 repro：conftest + markers + smoke）、docs 七篇、configs/experiments 占位、MIGRATION 重写为 M0-M6 批次清单 |
| 2026-09-15 | 第一优先级修复完成：删重复旧 skill、修正 rules 旧引用与 30 号 glob、修正 handoff/index 的 MIGRATION 引用、PAPER_SPEC 覆盖为小论文全文、GPU 测试改为函数内 importorskip；依赖保持完整未拆分 |
| 2026-09-15 | M1 完成：`uv sync --dev` 落盘 `uv.lock`、`uv run lp version` 通过、`./tasks.ps1 check` 全绿、git 首个 commit、覆盖 `THESIS_SPEC.md`；`cli.py` 补 callback 修复 typer 单命令折叠 |
| 2026-09-15 | M2 完成：adapters（demo/mmdocir）+ `lp prepare` + `tasks.ps1 mmdocir-prepare` + `configs/datasets/mmdocir.yaml` 落地；ruff + 12 pytest 全绿；全量对数 313/20395/170338/1658 验证通过（raw 经临时变量指向旧仓库，产物在本仓库 `data/`） |
| 2026-09-15 | M2.5 完成：官方 evaluation 原始三文件复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行（2523 matched + 115 unmapped，覆盖 1658 query）；ruff + 15 pytest 全绿；四表对数未动 |
| 2026-09-16 | M3 完成：检索评测管线（bm25/dense/colpali/hybrid 页级）+ `lp retrieve/evaluate` + smoke 全绿；EXP-001 全量复验 R@5=0.8390 与旧仓逐位一致（ndcg 口径回滚为旧逐行一致 + 补回归测试）；registry 首行 + 记录页 + 复现凭证已登记；ruff + 25 pytest 全绿 |
| 2026-09-16 | 选项 A 执行：按用户批准停 12:51 编码进程、删净缓存、从零重编码 52 分钟（run 20260916_134144 顶替 105545）；`docs/RULES.md` 新增 4.4（后台执行+指令透明）与 0.2（实验小白讲解）；`configs/datasets/mmdocir.yaml` 的 raw_dir 写死仓内 |
| 2026-09-16 | M4 前半完成：`correspondence.py` + `audit.py` + 叠图链路 + 机器 Gate（越界<1%、零覆盖 0）；叠图页号差一 bug 经文本判别法定位已修（`c7a817c`）；用户确认 p69"框贴合无偏移、顶部小字/底部文字/页码未框属官方稀疏"通过 |
| 2026-09-16 | EXP-002 完成：A/B/C/D 首次诊断（A=1345/B=45/C=0/D=268；B 占页命中 3.24%；IoU 敏感性 0.3/0.5/0.7=0.8154/0.8112/0.8100；与 EXP-001 差 1 题为 gold 页口径差异）；`region_metrics.py` + 回归测试 + `experiments/2026-09-16-exp-002-abcd-diagnosis.md` 已登记（`45af9c0`）；`pytest` 36 通过 |
| 2026-09-17 | 重绘分格式论文网络框架图：`docs/figures/layoutpatch_network_framework.svg`，参考用户提供的三分格论文图风格，依据 `docs/PAPER_SPEC.md` 第 3、5、7–9 节展示总览数据流、方法组件放大图与贡献/有效性检查；SVG XML 校验通过。 |
