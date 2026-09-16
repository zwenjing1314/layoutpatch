# EXP-002 Phase 1B A/B/C/D 缺口诊断（正式）

## 1. 实验目的

- 一句话：测量 ColPali 页级 Top-5 与 gold 区域的匹配缺口，验证小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节的 B 类（页中区不中）缺口是否存在、多大。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 4（Phase 1B），前置批次 3（EXP-001）已过。

## 2. 环境

- uv `.venv`，无 GPU 依赖（纯 CPU 统计）
- 输入三件：EXP-001 run 的 `predictions.parquet`（colpali_page，Top-5）、`nodes.parquet`（页内候选框）、`region_labels.parquet`（2638 行 gold 区域，M2.5 产物）

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split
- 分母：有 gold 区域标注的 query = 1658（region_labels 覆盖全部 1658 题，每题 ≥1 行）
- 判定口径：
  - 页命中：gold 页（region_labels 的 `page_id`）进 Top-5
  - 区域命中：gold 页内每个 nodes 框与 gold bbox 算 IoU（原图像素坐标），≥0.5 记中
  - 四格定义：A 页中区中 / B 页中区不中 / C 页不中区中 / D 都不中

## 4. 配置文件

- 无新 config（静态测量）；代码 `src/layoutpatch/evaluation/region_diagnosis.py` + `region_metrics.py`

## 5. 运行命令

```powershell
uv run python -c "from layoutpatch.evaluation.region_diagnosis import diagnose, write_diagnosis; from layoutpatch.paths import artifacts_dir; r = diagnose(k=5); print(r); write_diagnosis(r, artifacts_dir() / 'diagnosis' / 'mmdocir_evaluation')"
```

## 6. 代码 commit

- `c7a817c`（叠图页号修复）之上的工作区改动；`region_diagnosis.py` / `region_metrics.py` 为新增
- 工作区状态：诊断代码与 EXP-002 记录未提交（本记录页写作时）

## 7. 输出目录

- `artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`
- run 依赖：`runs/retrieval/mmdocir_colpali/20260916_134144`（EXP-001 从零重编码产物）

## 8. 关键指标（abcd_diagnosis.json 原样）

| 指标 | 数值 |
| --- | --- |
| 分母（gold 区域 query） | 1658 |
| A 页中区中 | 1345 |
| B 页中区不中 | **45** |
| C 页不中区中 | 0 |
| D 都不中 | 268 |
| 页命中（A+B）/分母 | 0.8384 |
| 区域命中（A+C）/分母 | 0.8112 |
| **B 占页命中比例** | **0.0324（3.24%）** |
| IoU 敏感性 0.3/0.5/0.7 | 0.8154 / 0.8112 / 0.8100 |

## 9. 错误信息

- 无运行错误。
- 口径差异说明：本诊断页命中率 0.8384（1390/1658）与 EXP-001 R@5 0.8390（1391/1658）差 1 题，原因是两者 gold 页来源不同——EXP-001 用 `evidence_page_ids`，本诊断用 `region_labels` 的 `page_id`。唯一差异题 `mmdocir_01342`：evidence 页 `..._p182` 进了 Top-5，但 region_labels 的 gold 框在 `..._p149`。两套口径并存是官方数据自身差异，不影响 B 类统计（该题两侧都算页中）。

## 10. 结果解释

- **B 类缺口存在但很小：3.24%**（45/1390 页命中题）。IoU 阈值从 0.3 提到 0.7，区域命中率仅从 0.8154 降到 0.8100，说明命中不是压线通过，是实打实的框对框。
- C 类为 0：不存在"页没进 Top-5 但区域命中"的题，页级检索是区域定位的充分前提，方法设计（同一套 P' 两读数）与此一致。
- 对照 `docs/PAPER_SPEC.md` 第 7.3 节 Gate 原文"B 类稳定存在才进 1C；否则停工修数据/协议"：**B 类存在（45 题、3.24%），字面上通过**。
- 但对照大论文规范 `docs/THESIS_SPEC.md` 第 11 节的研究价值判断：B 类仅 3.24%，说明官方页级 Top-5 内的 gold 区域几乎总能被 nodes 框覆盖——**缺口主要不在"框覆盖"，而在排序**（区域是否排到前面）。这正是 1C 三基线要测的：用无训练方法重排区域内 patch，看能否把 3.24% 拉上去、以及 Snappy 式传播能消掉多少。若 1C 三基线都消不掉 B 类，则 Phase 2 训练模块的动机才成立。
- 与上一版对比：无上一版（首次诊断）。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（Phase 1B 的 A/B/C/D 主表；分层统计与 10 成功/10 失败案例图待补，属第 7.3 节剩余输出）。
- 下一步：
  1. EXP-003/004：补跑 BGE-M3 dense 与 Hybrid（`docs/PAPER_SPEC.md` 第 7.2 节四基准补齐，`encoder=BAAI/bge-m3`、`require_model: true` 防 TF-IDF 降级）；
  2. 批次 5（Phase 1C）：Snappy 传播 / 固定 IoU 聚合 / 动态分组三基线，重点看 B 类 45 题被消掉多少；
  3. Phase 2 训练动机待 1C 数据后与导师确认。