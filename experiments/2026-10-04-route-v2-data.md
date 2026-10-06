# 2026-10-04 route-v2 数据准备、审计与 smoke 前置检查

> 非注册 EXP；只记录数据准备与审计。基于 commit 620e3b4 + 未提交改动。本轮先由 Codex 开始，用户决定暂停 Codex 后由 Claude 原地接手（同一工作树、同一 route-v2）。

## 1. 产物

- 划分：`experiments/route_v2_splits/data-roles-v1/`（`split_proof.json`、`identity_inputs.json`）
- 坐标审计：`artifacts/route_v2_data/coordinate_audit_v1.json`
- 区域单元：`artifacts/route_v2_data/regions_v1/`（units/candidates/questions parquet、`audit.json`）
- 监督可视化：`artifacts/route_v2_data/regions_v1/supervision_viz/`（8 张 + `index.json`）
- smoke 前置：`artifacts/route_v2_smoke/20261004_021336/preconditions.json`
- 命令：`./tasks.ps1 route-v2-identity`、`route-v2-data`、`route-v2-smoke`（见 `docs/02-commands.md`）

## 2. 划分（data-roles-v1）

| 角色 | 文档 | 题 |
| --- | --- | --- |
| source_train | 169 | 826 |
| source_val | 43 | 375 |
| source_dev | 91 | 412 |
| quarantine | 10 | 45 |

- 外部隔离 1 篇：`Country_Reports_2021_Complete_MASTER.no_maps-011323-Accessible`（旧 dev）；其身份伙伴 `Country_Reports_on_Terrorism_2020` 随单元传播隔离。
- dev 双胞胎隔离 8 篇：21-00620-INLSR-Vol2_Report-FINAL、INCSR-Vol-INCSR-Vol.-2-pdf、INCSR-Vol-INCSR-Vol.-I-1、NASDAQ_QCOM_2021、NETFLIX_2015_10K、NIKE_2021_10K、NYSE_DHR_2020、SAO-StudentSupport_Guidebook-Content。
- 身份单元跨角色：无；四角色两两交集为空。
- 分布偏移（只报告，不重切）：source_val 中 `news_combined` 一篇占 137/375 题，候选密集（每 unit 候选中位 12，p75 68；train 7、dev 8）。

## 3. 坐标审计（通过，约 7.5 s）

- token 布局为图像在前：0–1023 行是 32×32 patch，1024–1030 行是提示词。提示词行跨页余弦 [0.996, 0.998, 0.983, 0.978, 0.998, 0.979, 0.627]；0–6 行仅约 0.29–0.36。
- 行优先墨迹相关随偏移 0..7 递减：0.275、0.237、0.209、0.187、0.161、0.137、0.124、0.110；列优先最大约 0.12。最佳假设 row:0。
- 页框：20,261 页尺寸都在容差内，最大相对差 0.0023，134 页无版面行。
- 墨迹召回 0.8969，垂直翻转对照 0.5938，正常方向在 96.67% 的页上胜出。缓存签名抽 400 页，0 不符。
- 影响：旧代码 `[7:]` 切片（propagation.py、train_fusion_arxivqa.py、train_phase2r*.py）让所有旧 patch 级区域分数错位 7 格，Phase 1C 传播、2-R patch 特征和 ArxivQA 融合都受影响。页级 MaxSim（EXP-001）与面积基线不受影响。旧结果不改写，只在解读时注明。

## 4. 区域单元审计

| 指标 | train | val | dev | quarantine |
| --- | --- | --- | --- | --- |
| unit | 1059 | 450 | 545 | 53 |
| eval_ready | 1053 | 448 | 545 | 53 |
| 坐标冲突 | 5 | 2 | 0 | 0 |
| 无正 patch | 11 | 18 | 10 | 1 |
| 无负 patch | 25 | 0 | 11 | 0 |
| 页级重叠排除 | 16 | 4 | 6 | 0 |
| 局部 loss 可用 unit（扣除页级排除） | 1002 | 426 | 519 | 52 |
| 局部 loss 可用题 | 786 | 357 | 396 | 44 |
| gold 框 | 1355 | 576 | 645 | 59 |
| gold 与候选精确匹配 | 1286 | 562 | 615 | 59 |
| unit 级 Oracle IoU≥0.5 | 989 | 437 | 516 | 53 |

- 重复框去重 train 1、val 1；无效框 1；越界框 1；gold 页不在问题页内 2（train）。
- 每 unit 只有 1 个候选：train 103/1053、val 9/448、dev 27/545。这些 unit 上所有方法必然打平，所以另报 M≥2 子集。
- gold 面积占页中位：train 0.103、val 0.043、dev 0.094。
- MMDocIR 的 gold 多数就是解析块本身，所以在 MMDocIR 上做固定候选排序比在人工语义框的外部集上容易。

## 5. 监督可视化

我查看了 02、03、04 三张：框位置对齐，正 patch 落在 gold 内，忽略 patch 构成边界带，没有翻转或平移。03 是很小的标题级 gold，0 个正 patch；04 是近整页 gold，960 个正 patch、0 个负 patch。这两类按协议都不进局部 loss。

## 6. 外部来源（检索日期 2026-10-04）

- SciEGQA-Bench（原 BBox-DocVQA，arXiv 2511.15090）：HF `Yuwh07/SciEGQA-Bench` 固定 rev `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`，只有 test 划分。许可证未声明，状态未解决。本地 PDF.tar 解析出 1,823 页，论文写 1,941 页。PDF.tar/jsonl 由 Codex 下载，Codex 还为身份筛查读取过问题文本；答案和 gold 没有用于任何打分或选择。
- Visual-CoT（arXiv 2403.16999，HF `deepcs233/Visual-CoT` sha 223d2d8…）：Apache-2.0，图像受源数据集条款约束。未下载。

## 7. smoke 结果：未训练

前置检查 7 项中 6 项通过，`query_cache` 不通过：

- 需要 `artifacts/route_v2_data/query_cache_v1/source_queries.pt`（带 query_id 与 schema），该文件不存在。
- 现有唯一的 MMDocIR 问题向量 `artifacts/phase2r/arxivqa/dev_eval_queries.pt` 只覆盖旧 dev 的 415 题，且没有 ID 和签名，不能用于 source_train。按协议停止，不伪造、不替换。

## 8. 已知问题（本轮未修）

- `./tasks.ps1 check`：旧脚本里有 19 个 ruff 错误。
- `tests/retrieval/test_box_ranker.py::test_guards_reject_test_eval_and_coverage_label` 失败。原因是 commit 1288fbe 删除了 `assert_no_test_eval`。
- 执行环境拒绝 `-ExecutionPolicy Bypass`；改用 `powershell.exe -NoProfile -File tasks.ps1 <task>`。
- 第一次运行 route-v2-data 时报 `TypeError: Object of type SizeDict is not JSON serializable`，留下一个残缺的审计文件。已删除该文件，并把三个脚本改为原子写入，重跑后通过。
