# Changelog

格式遵循 Keep a Changelog 思想：只记面向使用者的变更，不记每日流水。

## [Unreleased]

### Added

- EXP-016最小归因：固定C-wide隐藏1062及两个D输入置零变体，复用原训练/评分预算；九次从头训练和统一dev已完成，三项文档bootstrap及Bonferroni补充区间全报，保存预测只读复核通过、20项相关测试通过。D优于C-wide、去文本更好、显式坐标校正后证据不足，仅开发归因；原EXP-015配置与A/B/C/D预测不改，不下载模型、不外测，已停止。

- EXP-015正式执行：独立dev节点缓存补齐、原train/val哈希保留、预算与基线候选/指标兼容性前置门、冻结配置；逐epoch训练gate/残差诊断和逐题D预测。仅一次D开发比较，A/B/C复用原结果，无外测或自动调参。

- EXP-015准备：官方OCR字段来源规则、仅训练/内部验证BGE-M3节点缓存、原节点编码器+融合V2的D接口、固定16题D smoke、定向测试与缓存回验；正式D入口/唯一配置候选已准备但未执行，尚缺本轮范围外的dev节点缓存。无新依赖或模型，不改EXP-014结果。

- EXP-014 `route-v2-exp1`：冻结A/B/C三seed正式区域定位开发比较；新增只读核验和定向测试入口，保存代码/输入身份、每轮曲线、独立checkpoint、一次开发集配对统计及正式五件套。不引入依赖、布局D或外部测试。

- route-v2 问题缓存任务 `route-v2-queries`：精确映射冻结清单，离线编码非隔离来源问题，绑定模型/processor 与源文件哈希，保留 token 结构，拒绝不兼容缓存覆盖；新增 `route-v2-cache-tests`。smoke 增加非有限数值立即中止、逐步梯度与参数变化诊断、实时页面签名复核及耗时记录，不改变算法和预算。

- Cursor 项目规则 `.cursor/rules/karpathy-guidelines.mdc`：编码时先澄清假设、保持最小改动、只改任务相关代码、用可验证标准收尾。与本仓库铁律冲突时仍以本仓库为准。

- route-v2：data-roles-v1 数据角色划分、坐标与区域监督审计、v2-loc-1 页内定位指标、对照 A/B/C 评分与局部对比损失，以及 `route-v2-identity`/`route-v2-data`/`route-v2-smoke` 三个任务。smoke 因缺少问题向量缓存未训练。旧文件与旧结果未改动。

- 新增route-v2协议草案与外部建议核查记录；提供显式V2融合、统一类型/OCR输入策略及同页IoU工具和合成测试。新输入必须写全新目录；未切换旧实验、未训练、未读取test_eval样本。

- `docs/paper-draft-notes.md`：小论文章节素材。只记可写内容和已有实验数字，不改评测口径。
- 项目骨架首版：`src/layoutpatch/` 包结构、`tests/`、`configs/`、`docs/`、`experiments/`、`tasks.ps1`、uv 环境三件套（`pyproject.toml` + `.python-version` + 本文件）。
- `docs/02-commands.md` 新增 `phase2r-dude`：DUDE 2-R 训练与一次 `dev_eval` 判定。
- `docs/02-commands.md` 新增 `fusion-arxivqa`：第一次正式融合训练（ArxivQA 单域，一次 `dev_eval` 判定）。
- `docs/02-commands.md` 新增 `region-ann-pilot`：40 题本地区域标注工作簿与格式检查。不训练，不读 `test_eval`。工作簿支持 A/B 导入导出；浏览器不写回仓库。
- A 的 40 题 `region-ann-v1` 标签已按字节归档到独立目录；不覆盖旧 `labels_annotator_A.jsonl`，不写入 manifest，不开训。
- A/B 40 题只读验收、B 按字节归档、裁定前一致率与无训练排序诊断已落盘；不扩标，不开训。记录：`experiments/2026-09-30-region-ann-ab-diagnosis.md`。

- `docs/RULES.md`（开发规范十条铁律）、`docs/00-index.md`（SSOT 导航）、`docs/handoff.md`（进度交接）。
- `docs/MIGRATION_BATCHES.md`（旧仓库 `mmdoc-evidence-rag` → 本项目的分批迁移执行清单，按小论文实验阶段切片）。
- `docs/figures/layoutpatch_network_framework.svg`：依据 `docs/PAPER_SPEC.md` 第 3、5、7–9 节绘制的分格式可编辑网络框架图，覆盖总览数据流、方法组件放大图、在线 MaxSim 检索与贡献/有效性检查。（2026-09-18 关门修正时移除，未入库：框架图非本批实测产物，待收缩方向确定后再按 B1/B2 重画。）
- `docs/figures/case_A_success.jpg` + `case_M_middle.jpg`（2026-09-18 新增，未入库）：EXP-005 两张代表压缩图（成功 A_mmdocir_00001 612x792 + 中间态 M_mmdocir_00522 768x432，长边缩 800px、quality 65，共约 187KB；判读口径：黄粗框=gold，彩色框围住文字即对，不看网格线；顶部小字/页码未框属官方稀疏）。

### Changed

- 修正论文规范的Snappy失败分母/基线称谓、RegionRAG指标、训练标签事实和LN公式，明确旧协议与新草案的数据角色边界；保留历史评分算法及旧权重兼容路径。

- 更新 `docs/handoff.md` 的2026-10-03新会话入口及导航，区分已完成实验、失败证据、标注验收状态与尚未实施的新路线；保留历史记录，避免旧“算涨”和旧下一步误导接续。
- `docs/RULES.md` 新增 0.2「实验讲解粒度（小白模式）」与 4.4「指令透明、agent 可在后台执行」（原因：EXP-001 期间代跑长任务与讲解过简引发时间线质疑；此后实验回复必须白话目标/输入/处理/输出/验证/失败后果/文档出处，操作步骤后附本轮指令原文；版本号升 v1.1）。
- M4 缺口诊断落地（`45af9c0`）：`src/layoutpatch/layout/correspondence.py`（Snappy 公式 + W cover/行归一化）+ `tests/layout/test_correspondence.py`；`src/layoutpatch/evaluation/audit.py` + `audit_overlays.py` + `scripts/run_phase1b_audit.py`（`docs/02-commands.md` 登记为 `phase1b-audit`）；叠图页号差一 bug 修复（`c7a817c`，去掉 `-1` 偏移，文本判别法双文档验证）；机器 Gate 通过（20261 页/170338 区域/越界 1/零覆盖 0）。

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
- M3 检索评测落地：`retrieval/{scoring,colpali,pipeline}.py`（仅 bm25/dense/colpali/hybrid 四页级分支，不含旧方向 region/evidence_set/oracle）、`evaluation/{metrics,pipeline}.py`（页级指标 + `evaluate_run`，不含 sufficiency）、`lp retrieve/evaluate` 命令、`tasks.ps1 mmdocir-smoke/mmdocir-colpali-full`、`configs/experiments/mmdocir_{colpali,bm25_page,colpali_smoke}.yaml`、`tests/test_retrieval_metrics.py` + `tests/test_colpali_integration.py`；smoke 链路（2 文档/9 query）prepare→retrieve→evaluate 已通；embedding cache 20395 个 `.pt` 已复制到 `artifacts/colpali/`（不进 git）；**EXP-001（2026-09-16）全量复验 R@5=0.8390 与旧仓 EXP-002 逐位一致，`ndcg_at_k` 回滚为旧仓逐行一致并补回归测试，`experiments/registry.csv` 首行 + 记录页已登记。**
- EXP-001 加固（选项 A，用户亲批）：停 12:51 编码进程、删净缓存、run `20260916_134144` 本机从零重编码约 52 分钟（七指标与旧仓逐位一致，顶替作废的 `105545`）。
- EXP-002 A/B/C/D 首次诊断（`45af9c0`）：`src/layoutpatch/evaluation/{region_metrics,region_diagnosis}.py`（正式 bbox IoU≥0.5）+ `tests/evaluation/test_region_metrics.py`；A=1345/B=45/C=0/D=268，B 占页命中 3.24%，IoU 敏感性 0.3/0.5/0.7=0.8154/0.8112/0.8100；与 EXP-001 差 1 题为 gold 页口径差异（`mmdocir_01342`）；记录页 `experiments/2026-09-16-exp-002-abcd-diagnosis.md` + registry 第二行已登记。
- EXP-005 关门补证（2026-09-17，未提交）：`scripts/run_phase1b_stratify.py` 重写为统一脚本（一次重算分层+交叉+可寻址+oracle+直方图+30 张叠图；`tasks.ps1` 新增 `phase1b-stratify` 任务并经其重跑验证，`docs/02-commands.md` 对齐为 EXP-005）；`stratification.json`/`cases.json` 写 `meta` 冻结（k=5/iou=0.5/面积与覆盖均用题内均值/三分位点/三档与判读口径定义）；`crosstab.json`（matched 题 1598：A=1343/B=0/D=255；unmapped_only 题 60：A=2/B=45/D=13；B=45/45 unmapped_only）；`addressability.json`（可寻址 B=0，双分母 0/1390=0.0、0/1598=0.0，离 10% 线各低 10pp）；`oracle.json`（页命中内 1345/1390=96.76%、全量 1600/1658=96.50%；Top-K 内 C=0 为定义性结果不许写成发现；B 是 oracle 未中 58 题真子集）；`strat_area_hist.png/json` + `strat_cov_hist.png/json` 落盘（matplotlib 由 scipy/sklearn 间接引入已锁 uv.lock，主依赖未回填，见 EXP-005 第 8.5 节）；`overlays_cases/` 极值 20 保留 + `overlays_cases_mid/` 中间态 10（`M_mmdocir_00522` IoU 0.4036 最近阈值）；S1 记录页恢复留档标 SUPERSEDED（git 无历史，凭上一版重建），registry 保留两行；自匹配 5 题（seed=7）IoU 全 1.0 且 Top-1 node_id 与 gold 映射一致（候选召回上限非排序能力；unmapped_only 有 2 题 both-A 反例 `mmdocir_00036/00491`）；旧行标 SUPERSEDED 并登记 EXP-005；`./tasks.ps1 check`（ruff + 38 pytest）全绿。
- EXP-006 实测 1C（2026-09-17，未提交）：新建 `src/layoutpatch/retrieval/{propagation,region_pooling,region_grouping}.py`（Snappy max/mean/iou + 固定 coverage/iou_mass + 分组 P25/P50/P75；MaxSim 展平修复 + 单测 6 用例；缓存布局断言 [7 prefix, 1024 patches]）+ `scripts/run_phase1c.py`（冒烟 `--limit-docs 2` 10A/0B 约 23 秒 + 全量 1343A/45B 约 225 秒；B 分母严格 45 非 47；`tasks.ps1` 新增 `phase1c-smoke/baselines` 对齐）；`phase1c.json`（1343A Top-1 最高 0.3187 fixed:iou_mass / Snappy-iou 0.2621 / max/mean ~0.10 / group ≤0.1035；45B Snappy/固定五档消解全 0.0，group 碰框 0.6889/0.3556/0.0889 虚高不计）；B 占比 3.24% 且可寻址 0 → 不进 Phase 2 转 11.3 收缩（B1/B2）；记录页 + registry EXP-006 行（query_count 回填 1658，region 格为 Top-1 口径 0.3187，与 0.8112 不可比）已登记；`./tasks.ps1 check`（ruff + 44 pytest）全绿；禁令：未建 `fusion/` 子包、未写 `train_fusion.py`。
- 关门修正（2026-09-18，`bd24fcb`）：`pyproject.toml` 显式声明 `matplotlib`（直方图主依赖，不再靠间接引入）+ `uv.lock` 同步；`docs/figures/` 仅 1 个 SVG（`layoutpatch_network_framework.svg`，19KB，非本批产物，未入库，待确认是否保留）；B1 效率表 `experiments/2026-09-17-eff-b1.md`（9.4 一行表，缺格明写）+ B2 分类学草稿 `experiments/2026-09-17-b2-taxonomy-draft.md`（三数并列，只摆材料不选择）已登记未提交时入库。
