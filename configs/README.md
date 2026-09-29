# configs/ — 配置注册表（SSOT）

命名约定：`configs/experiments/<dataset>__phase<m>__<method>[_<variant>].yaml`

首批需要的配置（迁移时从旧仓库复制并核名）：

```text
[ ] datasets/mmdocir.yaml
[ ] experiments/mmdocir__phase1a__colpali.yaml        （对应旧 mmdocir_colpali.yaml）
[ ] experiments/mmdocir__phase1a__bm25_page.yaml
[ ] experiments/mmdocir__phase1a__dense_page_bge_m3.yaml
[ ] experiments/mmdocir__phase1a__hybrid_page_bge_m3.yaml
[ ] experiments/mmdocir__phase1b__layout_node_bge_m3.yaml
```

状态标记：working（可改）/ frozen（锁定，改动需新版本）/ deprecated（禁用）。
每个 config 首次使用前必须在本文件登记一行状态；冲突以小论文规范 `docs/PAPER_SPEC.md` 为准。

## 状态表（M2 起登记）

| config | 状态 | 说明 |
| --- | --- | --- |
| `configs/datasets/mmdocir.yaml` | working | MMDocIR evaluation 数据集主配置，环境变量已改为 `LAYOUTPATCH_*` |
| `configs/experiments/mmdocir_colpali.yaml` | frozen | EXP-001 Phase 1A ColPali 基线（`colpali_page/document/top_k=20/batch 1-2-4`），R@5=0.8390；改动需新版本 |
| `configs/experiments/mmdocir_bm25_page.yaml` | working | Phase 1A BM25 对照（`bm25_page/document/top_k=20`） |
| `configs/experiments/mmdocir_colpali_smoke.yaml` | working | smoke 限流（2 文档），不进论文 |
| `configs/experiments/mmdocir_bge_m3_page.yaml` | working | EXP-003 Phase 1A dense 对照（`dense_page/document/BAAI/bge-m3/require_model=true/top_k=20`，禁 TF-IDF 降级） |
| `configs/experiments/mmdocir_hybrid_page.yaml` | working | EXP-004 Phase 1A Hybrid 对照（`hybrid_page/document/page_methods=[bm25,dense]/RRF k=60/candidate_top_k=20`） |
| `scripts/train_fusion_arxivqa.py` | working | 第一次正式融合训练（ArxivQA 单域，页级正负监督，一次 `dev_eval` 判定） |
