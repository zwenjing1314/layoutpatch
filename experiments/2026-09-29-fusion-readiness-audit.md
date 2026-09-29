# 融合显存探针复核 + 训练前数据审计

不训练。不读 test_eval。不加载 ColPali。不编码。不保存权重。不写全量 W/T 缓存。

复核对象：`experiments/2026-09-29-fusion-memory-probe.md`。

## 一、探针是否有效

CUDA 现在仍可用：`torch.cuda.is_available()=True`，设备 `NVIDIA GeForce RTX 3080 Ti`，总显存 `11.999512 GB`。与探针记录一致。

探针记录的设备与读数来源：

- 设备名与总显存写入探针页。
- 峰值显存来自 `torch.cuda.max_memory_allocated()`。
- 前向在 `torch.inference_mode()` 下执行，并用 `torch.cuda.synchronize()` 计时。
- `TextLayoutEncoder` 与 `SparseLocalFusion` 被 `.to(cuda)`；P/W/T 同样放到 CUDA。不是 CPU 冒充。

输入不是随机替代品：

| 项 | 来源 | 证据 |
| --- | --- | --- |
| P | `artifacts/colpali/mmdocir_evaluation/vidore_colpali/<page_id>.pt` | 8 个文件均存在；`embedding` 形状 `[1031,128]`，去掉 7 个 prefix 后用 `[1024,128]` |
| 框 | `data/processed/mmdocir_evaluation/nodes.parquet` | 真实 bbox + `node_type` |
| 页尺寸 | `region_labels.parquet` 的 `page_size` | 只用于坐标缩放，不把 gold 框当训练标签 |
| W | `correspondence.py` 现场计算 | 无 W 缓存 |
| T | `nodes.py` 现场计算 | 坐标和类型真实；文本全零过投影层 |

8 页逐页：

| page_id | P 文件 | M | page_size | 空 patch | 空比例 | 类型 |
| --- | --- | ---: | --- | ---: | ---: | --- |
| `05-03-18-political-release_p10` | 同上目录 `..._p10.pt` | 10 | 612×792 | 464 | 0.453125 | paragraph 10 |
| `..._p11` | `..._p11.pt` | 8 | 612×792 | 555 | 0.5419921875 | paragraph 8 |
| `..._p12` | `..._p12.pt` | 11 | 612×792 | 449 | 0.4384765625 | paragraph 11 |
| `..._p13` | `..._p13.pt` | 6 | 612×792 | 637 | 0.6220703125 | paragraph 6 |
| `..._p16` | `..._p16.pt` | 6 | 612×792 | 704 | 0.6875 | paragraph 5, table_block 1 |
| `..._p2` | `..._p2.pt` | 15 | 612×792 | 408 | 0.3984375 | paragraph 15 |
| `..._p3` | `..._p3.pt` | 8 | 612×792 | 753 | 0.7353515625 | paragraph 8 |
| `..._p4` | `..._p4.pt` | 10 | 612×792 | 461 | 0.4501953125 | paragraph 10 |

8 页合计：M min=6，median=9.0，max=15。空 patch 比例 min=0.3984375，median=0.5419921875，max=0.7353515625。8 页同文档、同页尺寸。

padding：

- batch=1：M=10，无 padding。
- batch=2：真实 M=10,8，pad 到 10。
- batch=4：真实 M=10,8,11,6，pad 到 11。
- mask：`SparseLocalFusion` 里 `valid = chosen_w > 0`，softmax 前对无效位置置 `-inf`；空行跳过 softmax，`P_out=P_in`。探针记录空 patch 恒等通过。

常见框数是否覆盖：只读 `nodes.parquet` 元数据，20261 页有类型框。eval M：min=1，p25=4，median=7，p75=11，max=99。M≤15 占 0.9062237796752382。探针 6–15 盖住中位和 p75，没盖住长尾（M≥50 有 75 页，max=99）。因此：小 M 的 GPU 前向显存读数有效；不能当成训练时最大 M 的显存上界。

探针有效性结论：CUDA 前向真实，显存读数可靠，输入真实。限制是 8 页同文档、M 偏小。不改结构。

## 二、训练前数据审计

泄漏：已完成。`experiments/s2_exclusion/exclusion_proof.json`：剔除后文档名交集空、问句交集空。`training_authorized=false`。

划分：`experiments/s2_splits/split_proof.json`。train_fit 57062 题 / 25577 文档，`with_layout_gold=0`。train_dev 5400 题 / 713 文档，同样 0。test_eval 未打分。

正页/负页：有。`annotations_top1_negative/*.jsonl` 每题 1 正页 + 1 负页。官方 `train_dataset.py` 只返回这一问题两页，无框级 gold。

真实布局框：训练 parquet 有 `layouts`（bbox+type）。ArxivQA/DUDE 各抽 2000 页元数据：中位 M=7，p75=11；类型含 text/title/image/table/interline_equation；`layouts` 无 OCR 字符串（`lays_with_text=0`）。这是候选框，不是框级答案。

页面向量 P：`artifacts/colpali/mmdocir_train/vidore_colpali/` 有 12126 个 `.pt`。只覆盖已编码的 ArxivQA+DUDE 子集，不是 train_fit 全量 57062 题。缺缓存页本轮不编码。

文本向量：`artifacts/bge_m3/mmdocir_train_boxes/` 有 12126 个 `.pt`。编码脚本写明训练 parquet 无 OCR，框文本向量为 0。这不是可用 OCR 文本特征。融合节点 T 没有现成缓存。

W/T 缓存：无。`artifacts/correspondence/`、`artifacts/layout/`、`artifacts/nodes/` 都不存在。W/T 只能现场算，不许本轮写全量缓存。

独立框级训练标签：无。train_fit/train_dev 的 `with_layout_gold=0`。不能构造 `y(c)=Area(c∩G)/Area(G)`。evaluation gold 不进训练。

当前可执行监督：只有页级正负页。不能直接做框级 gold 回归。

融合接口：

- `TextLayoutEncoder(text, coords, type_ids, valid_mask) → T [B,M,128]`
- `SparseLocalFusion(patches, weights, nodes) → P' [B,N,128]`
- 模块本身不接收正页/负页标记；标记只能放在训练循环外。
- 页级评分：现有 `ColPaliPageRetriever.score` / `score_multi_vector`。P' 若保持 N=1024、D=128，可替换图像 patch。缓存页向量是 `[1031,128]`（7 prefix + 1024 patch）。融合只改 1024 patch，prefix 如何接回 MaxSim 尚未实现，不是本轮修改范围。

## 三、最小训练方案草案（不执行）

训练输入：已有 train P 缓存页 + parquet 真实框算 W + 真实坐标/类型算 T；文本全零过投影，并写明不是文本实验。监督：jsonl 正页/负页。不用 evaluation gold 构造 `y(c)`。

loss：页级 MaxSim 对比，正页高于同题负页；可加蒸馏，约束 P' 不要远离原 P。不做框级覆盖回归。

batch 上限：探针 batch=4、M≤15 时峰值 0.03849601745605469 GB。草案上限 batch=4。M 明显大于探针范围时先停，不在本草案里改结构或缩小 N。

dev 早停：只看 `train_dev` 页级正负页排序是否变好。区域数只在 `dev_eval` 判一次。

与最大框、`geom:area` 的比较：在同一 `dev_eval` 401 matched 题、同一 gold 页、同一 `recall_layout` 上，融合方法必须同时超过 `geom:area` 的 Area@1 和 Area@5，且页级 R@5 相对冻结 ColPali 变化在 ±0.3 个百分点以内。只超过 `fixed:iou_mass` 不够。

何时允许跑 `test_eval`：模型、超参、对照表和叙事全部冻结，且 `dev_eval` 达到上一行标准之后，只跑一次。现在不允许。

本草案不是开训许可。

## 四、结论

探针在 CUDA 上真实运行，显存读数可靠，但只代表 M=6–15。训练集有页级正负和部分 P 缓存，无独立框级 gold，无现成 W/T。正式训练仍未批准。test_eval 未读取。
