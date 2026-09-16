# ColPali ViDoRe V1 官方复现记录

## 1. 目标与范围

本次实验复现 ColPali 原始预训练 checkpoint 在 ViDoRe Benchmark V1 上的页面检索评测，不进行训练或微调。

本次复现验证的链路为：

```text
vidore/colpali
-> 页面图像编码与查询编码
-> ColBERT MaxSim 晚期交互
-> ViDoRe V1 QA 格式评测
-> nDCG@5 等检索指标
```

官方源码单独保存在 `colpali-official-repro`，未复制到本毕业论文主仓库。主仓库仅保留本报告与后续接入 baseline 所需代码。

## 2. 运行环境

| 项目 | 值 |
| --- | --- |
| 运行机器 | Windows 台式机 |
| GPU | NVIDIA GeForce RTX 3080 Ti，12 GB 显存 |
| Python | 3.11（Conda 环境 `vidore-eval`） |
| PyTorch 安装目标 | `torch==2.5.1`、`torchvision==0.20.1`，CUDA 12.1 wheel |
| CUDA 可用性 | 已通过运行时验证，评测期间 `python.exe` 占用约 8.7 GB GPU 显存 |
| ColPali 模型 | `vidore/colpali`（原始论文 checkpoint） |
| 基础模型 | `vidore/colpaligemma-3b-mix-448-base`（由 checkpoint 自动加载） |
| 评测工具 | `vidore-benchmark==5.0.0` |
| 数据格式 | ViDoRe V1 `qa`，包含 query 去重 |
| 评测时间 | 2026-08-30 |

模型和数据由 Hugging Face 缓存管理，未提交 Git。Windows 未启用符号链接仅会增加缓存磁盘占用，不改变模型或指标。

## 3. 数据与命令

ViDoRe V1 collection：

```text
vidore/vidore-benchmark-667173f98e70a1c0fa4db00d
```

它包含 10 个测试集：ArXivQA、DocVQA、InfoVQA、TabFQuAD、TAT-DQA、ShiftProject 与 4 个 SyntheticDocQA 领域测试集。

正式全量评测命令：

```powershell
conda activate vidore-eval

vidore-benchmark evaluate-retriever --model-class colpali --model-name vidore/colpali --dataset-format qa --collection-name vidore/vidore-benchmark-667173f98e70a1c0fa4db00d --split test --batch-query 1 --batch-passage 1 --batch-score 1 --num-workers 0 --output-dir outputs\colpali_full
```

为适配 12 GB 显存，页面、查询和评分 batch 均使用 1。这会显著延长全量评测时间，但不改变指标定义。完整原始 JSON 保存在官方复现仓库：

```text
colpali-official-repro/outputs/colpali_full/colpali_vidore_colpali_metrics.json
```

## 4. 结果

| 数据集 | nDCG@5 |
| --- | ---: |
| `vidore/arxivqa_test_subsampled` | 78.433% |
| `vidore/docvqa_test_subsampled` | 57.003% |
| `vidore/infovqa_test_subsampled` | 80.563% |
| `vidore/tabfquad_test_subsampled` | 84.023% |
| `vidore/tatdqa_test` | 64.582% |
| `vidore/shiftproject_test` | 68.901% |
| `vidore/syntheticDocQA_artificial_intelligence_test` | 93.393% |
| `vidore/syntheticDocQA_energy_test` | 90.647% |
| `vidore/syntheticDocQA_government_reports_test` | 90.701% |
| `vidore/syntheticDocQA_healthcare_industry_test` | 91.710% |
| **宏平均（10 个数据集）** | **80.00%** |

汇总 JSON 元数据：`vidore_benchmark_version = 5.0.0`，完成时间为 `2026-08-30T23:14:48`。

## 5. 与公开结果的解释

官方仓库当前 README 为 `vidore/colpali` 列出的 ViDoRe 分数为 81.3。此次宏平均 nDCG@5 为 80.00%，相差约 1.30 个百分点。

该差异不能直接视为模型复现失败：本次使用的是 2026-01 更新的 ViDoRe collection、`vidore-benchmark==5.0.0` 和当前可获得的模型/依赖版本，未证明与论文发表时的数据快照、代码 commit 和评测实现完全一致。应将本实验准确表述为：

> 已完成原始 `vidore/colpali` checkpoint 在当前 ViDoRe V1 collection 上的 GPU 端到端推理与全量评测复现，获得 80.00% 宏平均 nDCG@5。

## 6. 下一步

1. 在 Windows 机器导出并保存 `conda env export --from-history -n vidore-eval` 与 `python -m pip freeze`，补充精确依赖快照。
2. 将 ColPali 页面图片编码、查询编码和 MaxSim 排序封装为 `mmdoc-evidence-rag` 的统一 baseline。
3. 在 MMDocIR 的相同 query、gold 标注和评价接口下，比较 BM25、BGE-M3 Dense、Hybrid、ColPali 和后续 StructDocIR。

## 7. MMDocIR Baseline 接入

主仓库已新增 `colpali_page` 检索器和配置文件
`configs/experiments/mmdocir_colpali.yaml`。MMDocIR 的原始页面 parquet 包含 JPEG 二进制列；执行准备命令时，项目会将页面图片写入
`data/interim/mmdocir_evaluation/page_images/`，并在处理后的 `pages.parquet` 中保存 `page_image_path`。这些可再生成图片和 ColPali embedding 缓存均被 Git 忽略。

Windows CUDA 机器上的首次运行步骤：

```powershell
conda activate colpali
cd C:\Users\WenJing\Documents\WorkTransfer\mmdoc-evidence-rag
python -m pip install -e ".[colpali]"
mdr prepare --dataset mmdocir
mdr retrieve --config configs\experiments\mmdocir_colpali.yaml
mdr evaluate --run runs\retrieval\mmdocir_colpali\latest
```

页面 patch embedding 默认缓存到 `artifacts/colpali/mmdocir_evaluation/vidore_colpali/`。首次运行将耗时较长；之后相同模型与未改动页面会直接复用缓存。

第一次接入时，先运行一份文档的 smoke test；它会覆盖处理后的 MMDocIR 表，因此完成后必须重新准备全量数据：

```powershell
mdr prepare --dataset mmdocir --limit-docs 1
mdr retrieve --config configs\experiments\mmdocir_colpali_smoke.yaml
mdr evaluate --run runs\retrieval\mmdocir_colpali_smoke\latest

mdr prepare --dataset mmdocir
mdr retrieve --config configs\experiments\mmdocir_colpali.yaml
mdr evaluate --run runs\retrieval\mmdocir_colpali\latest
```
