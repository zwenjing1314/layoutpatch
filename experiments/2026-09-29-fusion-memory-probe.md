# 融合显存探针

不训练。不读 test_eval。不加载 ColPali。不编码新页面。不保存权重。不写入全量 W/T 缓存。

文本向量为零，仅用于结构/显存探针。这不是文本实验结果。

## 输入来源

| 项 | 来源 | 说明 |
| --- | --- | --- |
| P | 已有缓存 `artifacts/colpali/mmdocir_evaluation/vidore_colpali/*.pt` | 读取后去掉 7 个 prefix，使用 1024×128 图像 patch |
| 框坐标/类型 | 已有 `data/processed/mmdocir_evaluation/nodes.parquet` | 真实 bbox + `node_type` |
| 页尺寸 | 已有 `data/processed/mmdocir_evaluation/region_labels.parquet` 的 `page_size` | 只用于把框归一化并计算 W，不读 gold 框做训练 |
| W | `correspondence.py` 现场内存计算 | 未落盘 |
| T | `nodes.py` 现场内存计算 | 坐标+类型真实；文本全零过投影层 |

设备：NVIDIA GeForce RTX 3080 Ti，总显存 11.99951171875 GB。

实际页数：8。

page_id：

- `05-03-18-political-release_p10`
- `05-03-18-political-release_p11`
- `05-03-18-political-release_p12`
- `05-03-18-political-release_p13`
- `05-03-18-political-release_p16`
- `05-03-18-political-release_p2`
- `05-03-18-political-release_p3`
- `05-03-18-political-release_p4`

8 页真实框数 M：min=6，median=9.0，max=15。

## batch 结果

| batch | 输入形状 | 输出形状 | 该 batch 的 M | 峰值 GPU 显存 | 单次前向耗时 | NaN/Inf | 空 patch P_out=P_in | 超过 12GB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `[1, 1024, 128]` | `[1, 1024, 128]` | 10 | 0.015976905822753906 GB | 0.0015220000004774192 s | 否 | 是 | 否 |
| 2 | `[2, 1024, 128]` | `[2, 1024, 128]` | 10, 8 | 0.023471832275390625 GB | 0.0016178000005311333 s | 否 | 是 | 否 |
| 4 | `[4, 1024, 128]` | `[4, 1024, 128]` | 10, 8, 11, 6 | 0.03849601745605469 GB | 0.0030823000006421353 s | 否 | 是 | 否 |

batch=2 按最大 M=10 padding；batch=4 按最大 M=11 padding。padding 位置在 softmax 前置 -inf（`SparseLocalFusion` 的 `valid = chosen_w > 0`）。

## 结论

融合显存探针完成。未超过 12GB。未训练。test_eval 未读取。正式训练仍未批准。
