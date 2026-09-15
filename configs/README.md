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
