# 导师决策包（11.3，只摆数不选择）

> 出处：小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3/7.4/8/9.4 节；大论文规范 `docs/THESIS_SPEC.md` 第 11.2/11.3 节。
> 状态：决策材料，结论由学生+导师共判，agent 不选择。
> 禁令：不建 `fusion/` 子包、不写 `train_fusion.py`；训练须学生+导师双确认。

## 1. B 占比 3.24% 且可寻址 0

- B=45/1390 页命中=3.24%（<10% 线，低 6.76pp）；可寻址 0/1390=0.0、0/1598=0.0（离线各低 10pp）。
- B=45/45 unmapped_only（matched B=0）；matched 内 1598 题=1343A+0B+255D（含 2 题 both 归 A）；unmapped_only 60 题=45B+13D+2A（2A 实为 both 题 matched 行命中）。
- 源：`artifacts/diagnosis/mmdocir_evaluation/crosstab.json` + `addressability.json`（EXP-005）。

## 2. Snappy 最好消解 0/45

- 45B 固定五档（max/mean/iou/coverage/iou_mass）消解全 0/45=0.0；group 碰框 0.6889/0.3556/0.0889 虚高不计（P25→P75 单调降即证据）。
- 11.2 第二条（≤50%）满足，但第一条（≥10%）不满足 → 按 11.2 不进 Phase 2。
- 源：`artifacts/baselines/mmdocir_1c/phase1c.json`（EXP-006）。

## 3. A Top-1 最高 0.3187（与 0.8112 不可比）

- 1343A 固定候选 Top-1 最高 428/1343=0.3187（fixed:iou_mass）；Snappy-iou 0.2621；max/mean 约 0.10；分组 ≤0.1035。
- 口径：Top-1 排序能力，非候选召回；EXP-002/005 的 0.8112 为候选召回上限，两数不可比。
- Text 双轨（`text_dual.json`，oracle 上界非 Top-1 实测）：1343 命中题 oracle 选框 Text-Recall/F1 均值 0.9101；IoU 未中但 Text≥0.8 组 n=0（无 ≥20 例可抽查；B 类 gold_text 为空故不入均值，非置零）。
- 源：`phase1c.json` + `artifacts/diagnosis/mmdocir_evaluation/text_dual.json`。

## 4. 效率缺格清单（B1 维持草稿，不许引用为对照）

- 缺：全量纯在线延迟、全量峰值显存、文本索引大小、k+1 具体数值、phase1c 分档耗时。
- 有：缓存 5.05GB（0.254MB/页）；探针 20 题 query 编码 mean 52.5ms/p50 35.7ms/峰值 mean 5681MB；七档选框 262.3ms；k+1 路线口径（LFRAG 块向量/ColParse 平均 2~9 向量 α0.6~0.8）。
- 源：`experiments/2026-09-17-eff-b1.md` + `artifacts/baselines/mmdocir_1c/phase1c_probes.json`。

## 5. 待判（三个问题，不选择）

1. B2 分类学是否足以撑"诊断+基准"型小论文，还是需补 Text Top-1 实测（需存逐题 picks 重跑，不编数）？
2. B1 缺格是否补测全量延迟/显存，还是维持草稿现状？
3. B3 跨页表格是否立项（需另立 Gate，本轮无跨页统计，不自动 fallback）？
