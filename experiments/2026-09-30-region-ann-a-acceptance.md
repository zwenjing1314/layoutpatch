# A 标注验收与归档（region-ann-v1，40 题）

不是训练。不是扩到 400 题。不是开训许可。未读 `dev_eval` / `test_eval` / evaluation gold。未改冻结划分、指标或任何 `ranker.pt`。未自动把 pending 改成 labeled。未改人工判断。

## 结论

- 输入集合通过：恰好 40 题，`sample_id` 与 pilot 完全对应，无重复/缺失/额外题，协议全部 `region-ann-v1`。
- 格式与一致性检查**未通过**。阻塞项是 `ann-0378`、`ann-0380` 的 pending 字段不是 null。
- 人工标签未改。旧 `labels_annotator_A.jsonl` 未覆盖。manifest 未写入。
- B 本轮不验收。仓库没有 B 文件。未读取、未复制 Downloads 中可能存在的 B 文件。未用 A 或模型生成 B。

## 完成状态

| 状态 | 题数 | 题号 |
| --- | ---: | --- |
| labeled | 37 | 其余 37 题 |
| pending | 2 | ann-0378, ann-0380 |
| skipped | 1 | ann-0158 |

- 潜在可训练题（`cover_ok=true` 且已选框非空）：37。这不是训练批准。
- labeled 单框 23 / 多框 14。
- cover 框计数：full 47，partial 8。
- 含 full 的 labeled 题 37；含 partial 的 labeled 题 6。
- `cross_box`：40 题均为 false。
- `no_candidate`：true 1（ann-0158），false 39。
- 格式通过不代表证据语义正确。本文件未裁定语义对错。

## 需人工处理

| 题号 | 字段 | 原因 |
| --- | --- | --- |
| ann-0378 | cover_ok, no_candidate, cross_box | pending 应按协议保持 null，当前为 false。未自动改。 |
| ann-0380 | cover_ok, no_candidate, cross_box | 同上。 |
| ann-0108 | cover_levels | 已选框 13 未填 cover_levels。协议允许留空，需确认是否故意。 |
| ann-0234 | remark, note | 备注以 `remark": "` 开头，疑似导出残留。未改原文。 |
| ann-0365 | remark, note | 备注以引号开头，疑似导出残留。未改原文。 |
| ann-0395 | cross_box, cover_levels, remark | 备注写需图与文字联合，同时框 1 为 full 且 cross_box=false。不自动裁定。 |

无 `full` 且 `cross_box=true` 的硬矛盾。多框独立 full 未强制 `cross_box=true`。

## 归档

- 来源：`C:/Users/WenJing/Downloads/labels_annotator_A_v1.jsonl`（原文件保留）
- SHA-256：`acfb7bf62b41334db7fa92c03f81bdbf7af86d08af76077955cb69d637b888a5`
- 字节归档：`experiments/region_annotation/archive/2026-09-30_annotator_A_v1/labels_annotator_A_v1.jsonl`
- 独立结果：`experiments/region_annotation/labels_annotator_A_v1.jsonl`
- 校验报告：`experiments/region_annotation/archive/2026-09-30_annotator_A_v1/acceptance_report.json`
- 过程缺口：`experiments/region_annotation/archive/2026-09-30_annotator_A_v1/provenance.md`
- 校准题：`experiments/region_annotation/archive/2026-09-30_annotator_A_v1/calibration.md`

## 过程记录缺口

缺失：模型名称或显示名、使用日期、提示词、原始建议、人工审核或修改记录。协议允许 A 参考 DeepSeek，但不能据此倒推本次实际使用的模型或原始回复。

## 校准题

- 确认：ann-0004（协议登记）。
- 确认：ann-0018（题目含 Figure (A) descending part，即“图A下降段”）。
- 待确认：无。找不到其他可确认编号的共同讨论证据，不猜。
- 校准题保留在数据中，不进盲标一致率分母。本轮不算一致率。

## B

未完成验收。仓库无 `labels_annotator_B.jsonl` / `labels_annotator_B_v1.jsonl`。本轮不等待之外的处理：不复制 A，不用模型冒充第二位人工。逐题审查结果不要给 B 看。
