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
| `@configs/tools/sciegqa_images_v1.yaml` | frozen | 固定SciEGQA Images.tar revision/SHA256；只提取manifest八页，机器审计官方原图与PDF渲染内容映射；不评分、不生成候选、不处理其他页面 |
| `@configs/tools/route_v2_external_full_prep_v1.yaml` | frozen | 固定manifest的837页候选准备；复用PDF、Images.tar与MinerU环境；2026-10-08最终ready为1623题/837页/1941单元、9746候选，审计`@artifacts/route_v2_external/full_prep_v1/20261008_222512/audit.json`；不编码、不评分、不训练 |
| `@configs/tools/mineru_external_pages_v1.yaml` | frozen | 固定MinerU4.0.10/ONNX CPU及模型revision；八页候选导出、叠图视觉和官方原图内容映射均完成；完整D图表文本接入仍阻塞，不改训练环境或比较计划 |
| `@configs/experiments/route_v2_external_v1.yaml` | frozen | 2026-10-07外部比较计划冻结；D-no-text为EXP-016开发主候选但无独立验证，A/B/C/C-wide/D保留；十二份source_val权重和固定SciEGQA元数据清单已绑定；比较配置未改，其旧准备状态为历史快照，独立解析授权及八页最后验收结果见`@experiments/2026-10-07-external-preparation.md`；视觉/原图映射8/8通过，无评分 |
| `configs/experiments/route_v2_exp3_attribution.yaml` | frozen | EXP-016；2026-10-07用户授权C-wide/D-no-text/D-no-coord各seed0/1/2；继承并哈希绑定EXP-015预算，九权重确定后统一dev；三项文档bootstrap及Bonferroni区间预固定，不调优不外测 |
| `configs/experiments/route_v2_exp2_D.yaml` | frozen | EXP-015；2026-10-06本轮授权dev节点编码和一次正式D比较，457页dev缓存与基线兼容性门通过，预算沿EXP-014；禁止事后改参 |
| `configs/experiments/route_v2_exp1.yaml` | frozen | EXP-014；2026-10-06 用户授权 A/B/C 正式比较，seed 0/1/2，训练与一次开发比较规则见 route-v2 协议第 9 节；不得事后改参 |
| `configs/datasets/mmdocir.yaml` | working | MMDocIR evaluation 数据集主配置，环境变量已改为 `LAYOUTPATCH_*` |
| `configs/experiments/mmdocir_colpali.yaml` | frozen | EXP-001 Phase 1A ColPali 基线（`colpali_page/document/top_k=20/batch 1-2-4`），R@5=0.8390；改动需新版本 |
| `configs/experiments/mmdocir_bm25_page.yaml` | working | Phase 1A BM25 对照（`bm25_page/document/top_k=20`） |
| `configs/experiments/mmdocir_colpali_smoke.yaml` | working | smoke 限流（2 文档），不进论文 |
| `configs/experiments/mmdocir_bge_m3_page.yaml` | working | EXP-003 Phase 1A dense 对照（`dense_page/document/BAAI/bge-m3/require_model=true/top_k=20`，禁 TF-IDF 降级） |
| `configs/experiments/mmdocir_hybrid_page.yaml` | working | EXP-004 Phase 1A Hybrid 对照（`hybrid_page/document/page_methods=[bm25,dense]/RRF k=60/candidate_top_k=20`） |
| `scripts/train_fusion_arxivqa.py` | working | 第一次正式融合训练（ArxivQA 单域，页级正负监督，一次 `dev_eval` 判定） |
