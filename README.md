# LayoutPatch 项目

> 状态：M0–M5 已完成，EXP-001~007 已入库（2026-09-19，`master f86c73e`，`./tasks.ps1 check` 44 绿）。
> 项目目标：研究布局约束的文档侧 patch 融合，用于 ColPali 页内证据区域定位。

## 现在已经有什么

- `src/layoutpatch/`：数据适配、四表读写、页级检索管线（BM25/dense/hybrid/ColPali）、1C 三基线（Snappy 传播/固定聚合/动态分组）、区域指标与坐标审计；
- `data/processed/mmdocir_evaluation/`：四表 313 文档 / 20395 页 / 170338 节点 / 1658 查询 + `region_labels.parquet` 2638 行（2523 matched + 115 unmapped，冻结只读）；
- 实验结论速记：页级 ColPali R@5=0.8390（EXP-001）；区域 IoU 口径 1343A Top-1 最高 0.3187、45B 消解 0/45（EXP-006，严格辅助）；官方口径 Oracle@1=0.9093 vs 最好冻结规则 0.2791（EXP-007，主口径）；
- `experiments/registry.csv`：EXP-001~007 注册表；详情页见 `experiments/2026-09-*.md`；
- `tasks.ps1`：Windows 统一任务入口（`check`、`phase1c-smoke`、`phase1c-baselines` 等）；
- `data/`、`artifacts/`、`runs/` 本地产物不进 git；旧仓库 `mmdoc-evidence-rag` 保持只读。

## 第一次使用

请按顺序阅读：

1. `docs/00-index.md`：全仓导航；
2. `docs/RULES.md`：项目开发规则；
3. `docs/handoff.md`：当前进度；
4. `docs/PAPER_SPEC.md` + `docs/THESIS_SPEC.md`：小论文执行与大论文边界（顶部 `working` 为提案，未转正）；
5. `docs/01-quickstart.md`：环境搭建；
6. `docs/02-commands.md`：命令唯一来源。

环境配置完成后，从项目根目录执行：

```powershell
uv sync --dev
uv run lp version
./tasks.ps1 check
```

## 当前不做的事

- 新阈值未冻前不建 `fusion/` 子包、不写 `train_fusion.py`；
- 不用 evaluation gold 当训练监督；
- 不单报 IoU 口径否定方法（官方 Area Recall 为主口径，IoU/Text 为辅助，双轨并列）；
- 训练须学生 + 导师双确认。

详细顺序见 `docs/MIGRATION_BATCHES.md`，当前进度见 `docs/handoff.md`。
