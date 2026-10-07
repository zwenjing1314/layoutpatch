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

## 9. 2026-10-06 本地官方代码借鉴边界（仅核对，不改算法）

本轮起点 `layoutpatch` commit：`1bd6c787ba1dc7d2aba4955ca1a3146ffc183d29`，工作区干净。官方本地仓库均无未提交改动：RegionRAG `1ff0f29220e05d288ebe48f7c9070f396a358552`；Snappy `acde4a1fdfd75f31d4ff13a04c03b1f06706b6f1`。仅只读参考，不安装、不部署服务。

- 局部损失：RegionRAG `colpali_engine/loss/late_interaction_losses.py::RegionContraLoss.infonce_loss` 对每个正 patch 的负 log-softmax 求平均；route-v2 `local_contrastive_loss` 是正集合 logsumexp 与正负集合 logsumexp 的差，即对正集合总概率取负对数。两者多正例时不等价。官方类默认 local_tau=0.5，但 `scripts/configs/training.yaml` 设置 0.25；route-v2 保持 0.25。官方另加全局损失和无框伪标签；本轮无这些项。协议中“同式”不能解释为与该官方 commit 逐行等价，本轮只追加此事实说明，不改既有协议、监督或损失。
- 问题聚合：该官方 loss 对 query token 相似度求和后除以非零 token 数，是 token 平均；route-v2 保留全部有效 token 并对每个 patch 取最大相似度。这也不同于论文全局逐维 max pooling 的描述，不能把论文表述当该代码行为。
- 框到 patch：官方 `collators/visual_retriever_collator.py` 将单框归一化，以 `floor(x1*w)` 到 `floor(x2*w+1)` 的矩形网格设正（Qwen 网格再除 2），没有当前的边界忽略集合；route-v2 用固定 32×32 网格，多 gold 框中任一包含 patch 中心为正、零重叠为负、其余忽略，保留现有 regions-v1。
- Snappy `backend/benchmarks/README.md` 提供多种 token 聚合、分位数过滤和区域聚合选项；route-v2 保持协议指定的 token max 与无分位数过滤的 IoU 加权传播，仅称 Snappy 式传播，不称完整复现。

## 10. 2026-10-06 问题缓存与 smoke（非正式 EXP，完成后停止）

### 缓存与运行记录

- 成功运行目录：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/query_cache_v1/runs/20261006_153320_261096/`，详情为 `run_info.json`。
- 缓存：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/query_cache_v1/source_queries.pt`；SHA256=`fc0a48afc1908805842c5f807288cf1c7521db2fd93eeb304142500b7b446681`。
- 实际 1613 题，角色计数 train=826/val=375/dev=412；隔离题未编码。原始物理行/question_index、全局 query_id、doc_id、冻结源哈希和全部 manifest 哈希一致。向量 `[T,128]`、bfloat16，T=16..92，无 NaN/Inf 或全零有效行；保留默认问题处理和 10 个增广 token。
- 模型 `vidore/colpali` revision `7754422bfa37f8e3cd771e13d4d7f07de3103c95`，基础模型 `vidore/colpaligemma-3b-mix-448-base` revision `6ff0d944ea09c3ead97d2bc57427e3d4f01d192f`。本地文件 SHA256、processor/tokenizer 类与实现哈希、依赖版本、每题文本/token/向量哈希均存缓存；未下载或安装。
- 首 batch=1，后续 batch=2；模型加载 5.083741199996439 秒，编码 25.5566739999922 秒，程序 34.91568620000908 秒；峰值 allocated=6048958464 bytes，reserved=6706692096 bytes（PyTorch 口径，不含桌面程序）。
- 复用记录：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/query_cache_v1/runs/20261006_153457_316982/`，`status=reused`，哈希不变，无重新编码。
- 首次尝试失败记录保留：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/query_cache_v1/runs/20261006_153121_307954/`。原始错误：`IncompleteSnapshotError: The cached snapshot for 'vidore/colpaligemma-3b-mix-448-base' (revision 'main', commit 6ff0d944ea09c3ead97d2bc57427e3d4f01d192f) is incomplete: 6 file(s) are missing (.gitattributes, README.md, preprocessor_config.json, ... (3 more)). Outgoing traffic is disabled ('local_files_only=True'). Re-run the download with network access to complete the snapshot.` 修正为只检查模型必要文件并验证权重索引所有分片，processor 从 ColPali 快照加载；没有补下载。

### smoke 与指标原文

完整目录：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_smoke/20261006_153418/`。含 `preconditions.json`（7 项通过）、`adapter.pt`、`smoke_result.json`（20 条训练日志及 19 个 unit ID）、`metrics.json`。固定 seed=42，16 题全部可用 19 unit；CPU、PatchAdapter、AdamW lr=1e-3、200 步。训练前实时重新核验所用页缓存签名与有限性，不重编码页面。保持现有 smoke 的 unit 均值诊断，不替代正式问题宏平均评测。未运行 val/dev/外部测试评分。

`metrics.json` 原文：

```json
{
  "steps_completed": 200,
  "gradient_norm_min": 0.009345004335045815,
  "gradient_norm_max": 1.0503872632980347,
  "gradient_nonzero_steps": 200,
  "gradients_all_finite": true,
  "parameters_changed": true,
  "parameter_delta_l2": 6.939946174621582,
  "initial": {
    "step": 0.0,
    "loss": 1.715434193611145,
    "grad_norm": 1.011820912361145,
    "mean_gap": 0.010067342143309744,
    "max_gap": -0.029316268469157972,
    "top_patch_positive": 0.3157894736842105
  },
  "final": {
    "step": 200.0,
    "loss": 0.07738713175058365,
    "mean_gap": 0.47885976339641373,
    "max_gap": 0.9030132136846843,
    "top_patch_positive": 1.0
  },
  "nonfinite_steps": 0,
  "trainable_parameters": 66176,
  "training_seconds": 12.762948300005519,
  "train_questions": 16,
  "train_units": 19,
  "train_hit1@0.5_before": 0.5263157894736842,
  "train_hit1@0.5_after": 1.0,
  "localization_aggregation": "unit_mean (existing smoke diagnostic)",
  "note": "training-set diagnostics only; not a generalization or paper result",
  "elapsed_seconds": 13.448630899991258,
  "checks": {
    "loss_decreased": true,
    "gradients_finite_nonzero": true,
    "parameters_changed": true,
    "no_nonfinite": true
  },
  "passed": true
}
```

### 验证与剩余前提

- 最终 `route-v2-cache-tests`：ruff `All checks passed!`；pytest `38 passed in 3.30s`。覆盖物理行/题下标映射、隔离排除、源哈希变化、ID 错配、token 补齐、缓存损坏拒绝，以及非有限输入/梯度出现时参数不更新。
- 离线且禁止同步依赖的 `check`：`Found 19 errors.`，均为旧脚本中的既有 ruff 问题；停在 lint，全仓 pytest 未执行。不修改本轮范围外旧脚本。
- 已具备问题缓存和 smoke 技术前置，但正式 A/B/C 配置尚未冻结：C 的正式训练预算、学习率与预定 seed；source_val 选择/早停；source_dev 比较计划；主比较、最小有意义差值、页面非劣界限（若声称页级保持需真实页排序）；正式 task/config/五件套与登记。D 的布局/文本配置不属于本轮，不作为 A/B/C 的新增实现。
- 本轮结束，不启动 route-v2-exp1。上述训练样本诊断不证明泛化或创新，旧权重、旧缓存、旧结论及另一模型产物保持原样。
