# 融合反向传播 smoke test

不是正式训练。不是效果实验。不计算 Area。不读 `dev_eval` / `test_eval`。不加载 ColPali。不编码新页面。不构造框级 `y(c)`。

文本向量为零，仅用于结构/反传探针。这不是文本实验结果。

## 输入

| 项 | 来源 | 说明 |
| --- | --- | --- |
| 子集 | ArxivQA `train_fit`，seed=0，4 个正负页对，8 页 | 与 `artifacts/phase2r/arxivqa/fit_queries.pt` 的 9241 条有框题对齐 |
| P | `artifacts/colpali/mmdocir_train/vidore_colpali/*.pt` | 去掉 7 个 prefix，使用 `[1024,128]` |
| W | `data/raw/mmdocir_train/hf_hub/parquet/ArxivQA_filter.parquet` 真实框坐标 | `correspondence.py` 现场计算，未落盘 |
| T | 真实坐标 + 类型 + 零文本 | `nodes.py` 现场计算，未落盘 |
| 监督 | 同题正页/负页 | 页级 MaxSim 对比：`- (s_pos - logsumexp([s_pos, s_neg]))` |
| query | `artifacts/phase2r/arxivqa/fit_queries.pt` | 已有缓存，不加载 ColPali |

抽到的 `line_index`：7373、8021、766、5018。

页：`1303.3891` p5/p4，`1310.1941` p7/p4，`1205.1004` p10/p8，`1005.5718` p7/p2。

每页框数 M：6、13、14、15、2、8、11、17。padding 后最大 M=17。

## 形状

| 张量 | 形状 |
| --- | --- |
| P | `[8, 1024, 128]` |
| W | `[8, 1024, 17]` |
| T | `[8, 17, 128]` |
| P' | `[8, 1024, 128]` |

## 反传

optimizer：Adam，`lr=1e-3`。步数：3。

| 步 | loss | 耗时 |
| ---: | ---: | ---: |
| 0 | 0.953373908996582 | 0.45760100000006787 s |
| 1 | 0.6409244537353516 | 0.01126269999986107 s |
| 2 | 0.6030998229980469 | 0.00928109999949811 s |

- loss 有限：是。
- loss 下降：是。
- 梯度非零：是。最后一步梯度绝对值之和 216.85693035740405。
- 参数更新量（L1）：全部 213.28560887277126；其中 `SparseLocalFusion` 137.20405858755112。
- NaN/Inf：否。
- 空 patch 保持原值：是。
- 峰值显存：0.15952396392822266 GB。未超过 12GB。

## 权重

临时保存：`artifacts/probe/fusion_train_smoke/smoke_state.pt`。

未覆盖：

- `artifacts/phase2r/arxivqa/ranker.pt`
- `artifacts/phase2r/arxivqa_dude/ranker.pt`
- `artifacts/phase2r/arxivqa_notext/ranker.pt`
- `artifacts/phase2r/dude/ranker.pt`

是否训练正式模型：否。

test_eval 是否读取：否。

正式训练仍未批准。
