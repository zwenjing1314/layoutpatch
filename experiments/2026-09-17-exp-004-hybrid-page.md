# EXP-004 Hybrid（BM25+BGE-M3 RRF）页级 baseline（正式）

## 1. 实验目的

- 一句话：补齐小论文执行规范 `docs/PAPER_SPEC.md` 第 7.2 节 Phase 1A 四基准中的 Hybrid 一项，验证稀疏+稠密融合相对单路的效果。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 3（Phase 1A）；与 EXP-003 同源 BGE-M3、同一 query 集、同一脚本、同 Top-K，满足公平比较。

## 2. 环境

- uv `.venv`（唯一运行时），CPU 检索；BGE-M3 同 EXP-003 的全局缓存复用
- 编码耗时：约 13.5 分钟（812.9s，含 BM25 + BGE 双路候选各 Top-20 再 RRF）

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split
- 规模：313 documents、20395 pages、170338 nodes、1658 queries
- 预测 30112 hits（RRF 融合后每 query 取 Top-20）

## 4. 配置文件

- `configs/experiments/mmdocir_hybrid_page.yaml`
- `hybrid_page, search_scope=document, page_methods=[bm25, dense], encoder=BAAI/bge-m3, require_model=true, top_k=20, candidate_top_k=20, RRF k=60`

## 5. 运行命令

```powershell
./tasks.ps1 mmdocir-hybrid-full
```

底层等价（备查）：`uv run lp retrieve --config configs/experiments/mmdocir_hybrid_page.yaml`；
评测：`uv run lp evaluate --run runs/retrieval/mmdocir_hybrid_page/20260917_115238`。

## 6. 代码 commit

- 同 EXP-003（`74aa05a` 之上工作区；`pipeline.py` 接通 `hybrid_page` 分支是本实验前提）
- 工作区状态同 EXP-003 记录页

## 7. 输出目录

- `runs/retrieval/mmdocir_hybrid_page/20260917_115238`（`latest.txt` 指向它）
- 五件套齐全（+ `errors.csv` 自动生成）

## 8. 关键指标（metrics.json 原样抄）

| 指标 | 本实验 |
| --- | --- |
| page_recall@1 | 0.5386007237635706 |
| page_recall@5 | 0.7882991556091676 |
| page_recall@10 | 0.8769601930036188 |
| mrr | 0.6537654693997015 |
| ndcg@5 | 0.644523349617594 |
| ndcg@10 | 0.6820056848241621 |
| region_hit@5 | 0.0（页级方法占位） |

- `run_info.json` 的 `retriever_type=hybrid_page`，`actual_retrievers=["hybrid_page"]`；dense 分支同样 `require_model=true`，无降级。

## 9. 错误信息

- 无运行错误；同 EXP-003 的 HF 未认证警告一条。

## 10. 结果解释

- 支持假设：Hybrid（R@5 0.7883）高于 BM25（R@5 0.7521）与 BGE-M3（R@5 0.7750），但仍低于 ColPali（R@5 0.8390），说明文本双路融合有效但天花板仍在视觉侧。
- A/B/C/D：不适用（页级对照）。
- 与上一版对比：首次 Hybrid 真模型全量；BM15_215504 的 BM25（R@5 0.7521）为同口径对照（`configs/experiments/mmdocir_bm25_page.yaml`）。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（Phase 1A Hybrid 基线）。
- 下一步：补第 7.3 节分层表（问题类型/面积/OCR 密度）+ 10 成功/10 失败案例图；再进批次 5 三无训练基线（`propagation/region_pooling/region_grouping`），看 B 类 45 题消解率。
