# ArxivQA train_fit 40 题区域标注 pilot 材料

不是人工标注完成。不是开训。没有 evaluation gold。没有预选框。

抽样：从 400 题 `arxivqa_train_fit_manifest.jsonl` 按 seed=42 分层抽 40 题。只含 ArxivQA `train_fit`。`line_index` 不在 `train_dev`。完整文档名与 evaluation 313 交集为 0。未打开 `test_eval_ids.jsonl`。

## 怎么标

先读 `experiments/region_annotation/annotation_protocol_v0.md`。

每题目录：

```text
samples/<sample_id>/
  page.png      正页原图
  overlay.png   全部候选框叠图，框上数字 = box_id
  card.md       题目、页面 ID、每个框的 box_id / 坐标 / 类型
  boxes.json    同一套候选，chosen_box_ids 为空
```

索引：`INDEX.md`。工作簿：`workbook.html`（本地打开，可勾选候选框并导出 A/B JSONL）。待填清单：`../arxivqa_pilot_manifest.jsonl`。独立标注文件：`../labels_annotator_A.jsonl`、`../labels_annotator_B.jsonl`。计数：`../pilot_sampling_meta.json`。

浏览器不会写回这些 jsonl。导出后请手动保存。不要改 template 或 manifest。检查命令：`./tasks.ps1 region-ann-pilot`。

## 分层（40 题）

版式 `layout_bin`：text 33，image 7，other 0。

候选数 `nbox_bin`：low 15，mid 11，high 14。

最大框相对面积 `area_bin`：low 14，mid 14，high 12。

层 `stratum = layout|nbox|area`：

| stratum | n |
| --- | ---: |
| text\|high\|low | 9 |
| text\|mid\|mid | 5 |
| text\|high\|mid | 4 |
| text\|low\|high | 4 |
| image\|low\|high | 4 |
| text\|mid\|high | 3 |
| text\|low\|mid | 3 |
| text\|mid\|low | 3 |
| image\|low\|mid | 2 |
| image\|low\|low | 1 |
| text\|low\|low | 1 |
| text\|high\|high | 1 |

400 题里 `other` 只有 4 题，按比例未进入这 40 题。这不是漏抽，是稀有层在 40 题配额下为 0。

## 检查

- 40 题都有 `page.png` 和至少 1 个候选框。
- 每题 `box_id` 与 train parquet `layouts` 下标一致。
- 未发现越界、重复框、空框。
- 未填写 `chosen_box_ids`。`no_candidate` 仍是 `null`（人还没标，不是机器判定无候选）。
- 未开始人工标注。未训练。`test_eval` 未读取。
