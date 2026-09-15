# Experiment Workflow

## Repository Sequence

只允许通过 `./tasks.ps1` 或 `docs/02-commands.md` 登记过的命令运行实验；环境只允许 uv `.venv`（`pyproject.toml + uv.lock + .python-version` 锁定，禁用 conda / 手动 pip）。

```text
prepare -> retrieve -> evaluate -> （1B 起新增 diagnosis / region-eval）
```

标准数据表：`documents.parquet`、`pages.parquet`、`nodes.parquet`、`queries.parquet`。每次 run 至少保留：config.json、run_info.json、predictions.parquet、metrics.json、summary.md（1B/1C 另加 audit.json；Phase 2 另加 hyperparams_frozen.json）。

## Phase Gates（硬门槛，不许跳步）

```text
1A 页级 baseline（EXP-002 已完成：Page R@1/5/10 = 0.5724/0.8390/0.9047）
  → 1B A/B/C/D 缺口诊断（纯测量，含分层与 10成功/10失败可视化）
  → 1C 三类无训练基线（原始 ColPali / Snappy 式传播 / 固定聚合 / 动态分组）
  → 2 训练融合模块（仅当 B 类占比≥10% 且 Snappy 只消掉≤50% B 类，dev/test 趋势一致）
```

1C 判定的完整口径与 Plan B（B1 效率 / B2 失败分类学 / B3 另立项）见大论文规范第 11.2/11.3 节。agent 只准备决策材料，选择由学生与导师确认。

## Baselines And Controls

- `BM25-page` / `Dense-page(BGE-M3)` / `Hybrid-page`：页级文本对照；
- `ColPali-page`：页级视觉基线（已冻结，EXP-002）；
- `Snappy-style 传播`：无训练区域上限探针，坐标映射必须先过审计；
- `固定 IoU/coverage 聚合`：无训练区域基线；
- `动态显著分组`：无训练区域基线（不许称 RegionRAG 复现）；
- `Oracle-Page -> Region`：上界，单独标注。

## Evaluation

页级：Recall@1/5/10、MRR、nDCG@5/10。区域级：Region Recall@1/5、Region MRR、IoU Hit@0.5（主）、Text Recall/F1（辅，防 IoU 误杀；预测框超页面 50% 面积置零防刷分）。1B 另报 A/B/C/D 分解与按类型/面积/OCR 密度分层。效率表必须与 LFRAG/ColParse 的 k+1 次编码行同表。

## Data Leakage Guard

候选框只能来自 OCR/Layout 解析结果；gold 页/node/框/答案只用于评测与 oracle 分析。MMDocIR evaluation gold（1658 query，其中有布局 gold 的约 1598）永远不作为训练监督；训练候选是 MMDocIR train（用前必须先审标签构造规则与泄漏）。无布局 gold 的 query 不进区域分母；跨页证据单独标注。

## Claim Standard

每个结果声明必须能沿此链追溯：

```text
dataset/version + query 数 + 检索范围 + config 路径 + 模型/后端 + metric@K + run 完整目录 + 运行日期
```

smoke 结果永不进论文；full 结果需满足 `docs/10-small-paper/protocol.md` 才算正式。实验登记于 `experiments/registry.csv`，详情按 11 段模板写 `experiments/YYYY-MM-DD-exp-NNN-*.md`。
