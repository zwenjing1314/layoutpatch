# ArxivQA train_fit 40 题区域标注 pilot 材料

不是训练。不是人工标注完成。不读 `test_eval`。不用 evaluation gold。不改四池 id。不改 `recall_layout`。不改任何 `ranker.pt` / `fusion.pt`。不编码新页。不自动填写答案框。

本页把 `experiments/2026-09-29-region-annotation-plan.md` 落到 40 题可标材料。协议说明：`experiments/region_annotation/annotation_protocol_v0.md`。

## 0. 一句话

40 题区域标注 pilot 材料已准备；尚未完成人工标注；未训练；`test_eval` 未读取。

## 1. 为什么做 40 题

`docs/PAPER_SPEC.md` 第 2.3b / 2.4 要求独立训练数据，不许用 evaluation gold。第 5.7 的 `L_region` 需要独立框标注。第 8 节主指标仍是官方 Area；第 11 节无独立训练数据又要用 gold 即停。

400 题全量待标清单已有，但还没有页面图。本轮只准备 40 题，用来试协议、试界面、试 `no_candidate` 比例，不扩到 400，不开训。

## 2. 抽样

- 源：`experiments/region_annotation/arxivqa_train_fit_manifest.jsonl`（400 题，全部 `pending`）。
- seed=42。按已有 `stratum = layout_bin|nbox_bin|area_bin` 比例分配 40 题。
- 只抽 ArxivQA `train_fit`。`line_index` 必须在 `experiments/s2_splits/train_fit_ids.jsonl` 的 ArxivQA 行。
- 不与 ArxivQA `train_dev` 的 `line_index` 重叠。
- 不打开 `experiments/s2_splits/test_eval_ids.jsonl`、`dev_eval_ids.jsonl`。文档泄漏用 `experiments/eval313_doc_ids.txt` 与冻结 `split_proof.json` 检查。
- 正页图像只从 `data/raw/mmdocir_train/hf_hub/parquet/ArxivQA_filter.parquet` 解码。不读 evaluation 页图，不读 `region_labels.parquet`。

结果：40 题，39 个正页文档，40 个正页。`annot_fit` 33 / `annot_val` 7（沿用 400 题文档切分，不重切四池）。

## 3. 分层

| 轴 | 计数 |
| --- | --- |
| layout_bin | text 33，image 7，other 0 |
| nbox_bin | low 15，mid 11，high 14 |
| area_bin | low 14，mid 14，high 12 |

层计数见 `experiments/region_annotation/pilot_sampling_meta.json`。400 题里 `other` 共 4 题，40 题配额下为 0。

## 4. 每题材料

目录：`experiments/region_annotation/pilot_materials/samples/<sample_id>/`

| 文件 | 内容 |
| --- | --- |
| `page.png` | 正页原图 |
| `overlay.png` | 全部候选框 + `box_id` 数字。无 gold 框，无预选框 |
| `card.md` | query、`query_id`、`pos_doc`、`pos_page`、每个框的 `box_id` / 坐标 / 类型 |
| `boxes.json` | 同一套候选；`chosen_box_ids=[]` |

清单：`experiments/region_annotation/arxivqa_pilot_manifest.jsonl`。状态全部 `pending`。标签字段为空：`chosen_box_ids=[]`，`cover_levels={}`，`cover_ok/no_candidate/cross_box/labeled_at=null`，`remark/annotator=""`，`protocol_version=region-ann-v0`。

## 5. 只读检查

| 项 | 结果 |
| --- | --- |
| 题数 | 40 |
| 每题页面图 | 40/40 `page.png` |
| 每题叠图 | 40/40 `overlay.png` |
| 每题候选框 | 40/40，最少 1 框 |
| `box_id` 映射回 parquet `layouts` | 通过，无 mismatch |
| 越界 / 重复 / 空框 | 无 |
| ColPali 页缓存存在 | 40/40（只检查文件在不在，不重新编码） |
| `line_index` ⊂ ArxivQA train_fit | 是 |
| 与 ArxivQA train_dev `line_index` 交集 | 0 |
| 完整文档名 ∩ eval313 | 0 |
| 填写了 `chosen_box_ids` | 0 |
| 机器填写 `no_candidate` | 0（仍为 `null`） |
| 打开 `test_eval_ids.jsonl` | 否 |
| 使用 evaluation gold | 否 |

## 6. 现在不许做

- 不开始正式 400 题标注扩张，除非 40 题协议被人工确认。
- 不训练。
- 不读、不评分 `test_eval`。
- 不把本页当成开训许可。
