# 区域标注说明（region-ann-v0）

本页只给人工标注用。不是开训许可。不是把 40 题当成已完成标签。

`protocol_version` 必须写 `region-ann-v0`。

## 你要做什么

看正页原图、候选框叠图和题目，在**现有候选框**里选出所有承载答案证据的框。

只标正页。负页不要点。不要打开 `dev_eval` / `test_eval`。不要看 evaluation gold。

## 选择规则

1. 选择所有承载答案的候选框，写入 `chosen_box_ids`。
2. 答案跨多个框时：全部选择，并把 `cross_box` 设为 `true`。不要只点最大框。不要把无关大框一起点上凑覆盖。
3. 没有任何候选框能承载答案时：`no_candidate=true`，`chosen_box_ids=[]`，`cover_ok=false`，`label_status=skipped`。
4. 不新画框。候选只能来自本页 MinerU / parquet `layouts` 的 `box_id`。
5. 不确定时写 `remark`，保持 `pending`。不要猜框，也不要把不确定改成 `no_candidate`。

覆盖等级 `cover_levels` 只给已选框填：

- `full`：这个框单独已经盖住答题所需证据。
- `partial`：这个框只盖住一部分，需要和其他已选框一起看。

未选框不要写。已选框合在一起够不够答题，用 `cover_ok`。

## 不确定 vs 候选无法覆盖证据

这不是同一件事，工具也不会自动转换。

| 情况 | 怎么填 | 不要做什么 |
| --- | --- | --- |
| 不确定：看不准该选哪些框 | `label_status=pending`，`chosen_box_ids=[]`，`no_candidate=null`，`cover_ok=null`，在 `remark` 写原因 | 不要猜一个框；不要勾无合适候选 |
| 候选无法覆盖证据：看完全部框后，现有候选都盖不住答案 | `no_candidate=true`，`chosen_box_ids=[]`，`cover_ok=false`，`label_status=skipped` | 不要同时选框；不要保持 pending |

本页是 `region-ann-v0` 的操作说明，不改协议版本号。

## 字段


| 字段                           | 谁填   | 空值              | 含义                                   |
| ---------------------------- | ---- | --------------- | ------------------------------------ |
| `chosen_box_ids`             | 人    | `[]`            | 正页上盖住答案证据的候选下标，可多选                   |
| `cover_levels`               | 人，可选 | `{}`            | 已选框的 `full` / `partial`              |
| `cover_ok`                   | 人    | `null`          | 已选框合在一起是否盖住答题所需证据                    |
| `no_candidate`               | 人    | `null`          | 现有候选都盖不住证据                           |
| `cross_box`                  | 人    | `null`          | 证据跨多个已选框                             |
| `remark` / `note`            | 人    | `""`            | 短备注，不进训练。`remark` 与 `note` 同义，先填一个即可 |
| `annotator` / `annotator_id` | 人    | `""`            | 标注者代号，不是账号密钥                         |
| `labeled_at`                 | 人/系统 | `null`          | UTC 时间，例如 `2026-09-29T10:03:11Z`     |
| `protocol_version`           | 系统   | `region-ann-v0` | 不许改                                  |
| `label_status`               | 系统   | `pending`       | 完成后改为 `labeled`；无候选改为 `skipped`      |


Pilot 清单：`experiments/region_annotation/arxivqa_pilot_manifest.jsonl`。材料：`experiments/region_annotation/pilot_materials/`。

## 本地记录流程

两位初学者必须分开做，互不打开对方文件。

1. 用浏览器打开 `experiments/region_annotation/pilot_materials/workbook.html`。
2. 先选标注者 A 或 B。
3. 如需续标，点「导入已有 JSONL」，只导入自己的文件。
4. 每题勾候选框，填 `full`/`partial`、`cover_ok`、跨框、备注。
5. 不确定：保持 pending，写备注。无合适候选：勾该选项，状态变为 skipped。
6. 点「本页校验」，再点「导出 JSONL」。浏览器不会写回仓库，必须把下载文件保存为 `labels_annotator_A.jsonl` 或 `labels_annotator_B.jsonl`。
7. 检查：`./tasks.ps1 region-ann-pilot` 只重建工作簿并检查 A 文件；检查 B 用 `uv run python scripts/region_ann_pilot.py check --annotator B`。




## 禁止

- 不新画框。
- 不自动推断或填写答案框。
- 不打开、不评分 `test_eval`。
- 不使用 `dev_eval` / `test_eval` gold。
- 不把 evaluation 313 文档拿来对照。
- 本轮不训练。

