# EXP-001 ColPali full Phase 1A baseline（迁移复验，正式）

## 1. 实验目的

- 一句话：把旧仓库 EXP-002 的 Phase 1A ColPali 页级 baseline 在本仓库（layoutpatch）完整重跑一遍，证明迁移代码与数据准备无偏差。
- Gate 归属：批次 3（M3），判据 `R@5` 与旧 `0.8390` 偏差 < 0.005。

## 2. 环境

- uv `.venv`（唯一运行时，`python C:\...\layoutpatch\.venv`）
- PyTorch `2.13.0+cu130`，CUDA 可用（NVIDIA GeForce RTX 3080 Ti），`colpali_engine` 已装（`--extra colpali`）
- HF_HOME 指向 `artifacts/hf_cache`；`vidore/colpali` 权重自 Hugging Face 拉到本地
- embedding 缓存 `artifacts/colpali/mmdocir_evaluation/vidore_colpali/`（20395 个 `.pt`，本机全量重编码）

## 3. 数据和 split

- 数据集：`mmdocir_evaluation`（官方 evaluation）
- split：无 / 全量文档内检索（`search_scope=document`）
- 规模：313 documents、20,395 pages、170,338 nodes、1,658 queries；`region_labels` 2638 行（不参与页级指标）
- 预测 30,112 hits（= 1658 × top_k20，单文档检索有溢出时仍按页数封顶）

## 4. 配置文件

- `configs/experiments/mmdocir_colpali.yaml`
- `colpali_page, search_scope=document, model=vidore/colpali, top_k=20`
- `image_batch_size=1, query_batch_size=2, score_batch_size=4, use_embedding_cache=true`

## 5. 运行命令

```powershell
./tasks.ps1 mmdocir-colpali-full
```

底层等价（备查）：`uv run --extra colpali lp retrieve --config configs/experiments/mmdocir_colpali.yaml`；
评测：`uv run lp evaluate --run runs/retrieval/mmdocir_colpali/latest`。

## 6. 代码 commit

- `bbe13ed`（配置头打印）；评测时 `metrics.py` 已回滚 ndcg 口径为旧仓逐行一致（另提交）
- 工作区：`git status --short` 在运行后仅剩本次文档/登记改动，无代码运行期改动

## 7. 输出目录

- `runs/retrieval/mmdocir_colpali/20260916_105545`（`latest` 指向）
- 历史 run：`20260915_215535`（误启动，页图路径旧导致签名失效重编码，已停，仅作排错参考）

## 8. 关键指标（metrics.json 原样抄）

| 指标 | 本仓库 | 旧仓库 EXP-002 | 偏差 |
| --- | --- | --- | --- |
| page_recall@1 | 0.5724 | 0.5724 | 0 |
| page_recall@5 | 0.8390 | 0.8390 | 0 |
| page_recall@10 | 0.9047 | 0.9047 | 0 |
| mrr | 0.6890 | 0.6890 | 0 |
| ndcg@5 | 0.6932 | 0.6932 | 0 |
| ndcg@10 | 0.7231 | 0.7231 | 0 |
| region_hit@5 | 0.0（NA） | 0.0 | 0 |

结论：全指标与旧仓逐位一致，`R@5` 偏差 0.0000 < 0.005，迁移复验通过。

## 9. 错误信息

- 无；Hugging Face 未认证提示不影响本次（权重已缓存）。
- 说明：复制自旧仓库的 20395 个 `.pt` 因 `source_signature` 含旧绝对路径+mtime 全部判失效，本次为本机全量重编码（约 8 小时），重编码后签名与本机一致，后续复用零成本。

## 10. 结果解释

- 支持假设：确定 ColPali 页级 baseline 分母（0.8390），验证迁移代码/数据链路无偏差。
- A/B/C/D：待 1B 诊断。
- 与上一版对比：与旧 EXP-002 逐位一致（复验即目标）。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（Phase 1A 页面级 baseline；区域指标不适用，`region_hit@5` 为页级方法失配占位）。
- 下一步：Phase 1B 页面命中 vs 证据区域命中缺口诊断（先过坐标审计，再到 A/B/C/D）。
- Gate：1A 已完成；1B 的 A/B/C/D 完成前，不进入 1C 或搭建训练网络。