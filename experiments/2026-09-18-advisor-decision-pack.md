# 导师决策包（11.3，只摆数不选择）

> 出处：小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3/7.4/8/9.4 节；大论文规范 `docs/THESIS_SPEC.md` 第 11.2/11.3 节。
> 状态：决策材料，结论由学生+导师共判，agent 不选择。
> 禁令：不建 `fusion/` 子包、不写 `train_fusion.py`；训练须学生+导师双确认。
> 口径注记（2026-09-22，EXP-007 后）：本包 §1/§2 的“不进 Phase 2”是 **IoU 口径旧 Gate 下的结论**（B≥10%）；官方口径三层表见 `experiments/2026-09-19-exp-007-official-recompute.md`（L2 对齐 0.9140 vs L3 最好 0.2791，gap≈0.63）。旧结论保留为辅助，不删除；新阈值未冻前不做任何进训练/收缩的新判定。

## 1. B 占比 3.24% 且可寻址 0

- B=45/1390 页命中=3.24%（<10% 线，低 6.76pp）；可寻址 0/1390=0.0、0/1598=0.0（离线各低 10pp）。
- B=45/45 unmapped_only（matched B=0）；matched 1598=1343A+255D含2 both归A（`mmdocir_00036/00491`）；unmapped_only 60=45B+13D+2A纯unmapped命中（`mmdocir_00520/00672`）；47=45B+2A。
- 源：`artifacts/diagnosis/mmdocir_evaluation/crosstab.json` + `addressability.json`（EXP-005）。
- 术语终结（2026-09-18）：四处（registry / EXP-005§8.1 / B2-c / 决策包§1）统一为"matched 1598=1343A+255D含2 both归A、unmapped_only 60=45B+13D+2A纯unmapped命中、47=45B+2A"，不许第四种写法。

## 2. Snappy 最好消解 0/45

- 45B 固定五档（max/mean/iou/coverage/iou_mass）消解全 0/45=0.0；group 碰框 0.6889/0.3556/0.0889 虚高不计（P25→P75 单调降即证据）。
- 11.2 第二条（≤50%）满足，但第一条（≥10%）不满足 → 按 11.2 不进 Phase 2。
- 源：`artifacts/baselines/mmdocir_1c/phase1c.json`（EXP-006）。

## 3. A Top-1 最高 0.3187（与 0.8112 不可比）

- 1343A 固定候选 Top-1 最高 428/1343=0.3187（fixed:iou_mass）；Snappy-iou 0.2621；max/mean 约 0.10；分组 ≤0.1035。
- 口径：Top-1 排序能力，非候选召回；EXP-002/005 的 0.8112 为候选召回上限，两数不可比。
- Text 双轨（`text_dual.json`，同一 stored Top-1 picks 方法分，n=1388 中 NaN 53/有效 1335；group 三档未跑）：fixed:iou_mass Recall 0.3455/F1 0.3341；snappy:iou 0.2716/0.2712；coverage 0.2708/0.2704；max/mean 约 0.09~0.10；大框超 50% 置零 341 格（分档 max 58/mean 58/iou 72/coverage 72/iou_mass 81）；IoU 未中但 Text≥0.8 组 n=0（condition-not-met，本口径恒为空，双轨防御缺位，不编）。
- 源：`phase1c.json` + `phase1c_picks.json` + `artifacts/diagnosis/mmdocir_evaluation/text_dual.json`。

## 4. 效率缺格清单（B1 维持草稿，不许引用为对照）

- 缺：全量纯在线延迟、全量峰值显存、文本索引大小、k+1 索引 GB 与检索延迟/显存原文值、phase1c 全量分档耗时。
- 有：缓存 5.05GB（0.254MB/页）；探针清洗后（n=19 去 warmup，权重基座 5653.3MB）query 编码 mean 38.1ms/p50 35.1ms/max 62.8ms、增量 mean 28.1MB；七档选框合计 243.0ms（分档 max 10.8/mean 9.8/iou 10.4/coverage 6.5/iou_mass 5.4/P25 1.0/P50 7.4/P75 191.7ms，P75 碎裂组数多故最贵）、增量 8.1MB；k+1 原文向量数/延迟/页级数（LFRAG 块均 2.79/页、生成 token 减 67.9~77.7%；ColParse 均约 5.9/页、α0.6~0.8、GME-7B 0.81s/文档；页码表号见 B1 表）。
- 源：`experiments/2026-09-17-eff-b1.md` + `artifacts/baselines/mmdocir_1c/phase1c_probes.json`。

## 5. 待判（三个问题，只摆数不选择）

1. B2 分类学是否足以撑"诊断+基准"型小论文？本轮数：EXP-005 三笔账：matched 1598=1343A+255D 含 2 both 归 A（`mmdocir_00036/00491`）、unmapped_only 60=45B+13D+2A 纯 unmapped 命中（`mmdocir_00520/00672`）、47=45B+2A；可寻址 B 0/1390=0.0、0/1598=0.0；oracle 1600/1658=96.50%、1345/1390=96.76%，未中 58=45+13，B 为 58 真子集。EXP-006 Top-1 最高 428/1343=0.3187（fixed:iou_mass），与 0.8112 候选召回不可比。Text 方法分（n=1388 中 NaN 53/有效 1335；group 三档未跑）：fixed:iou_mass Recall 0.3455/F1 0.3341，snappy:iou 0.2716/0.2712，coverage 0.2708/0.2704，max/mean 约 0.09~0.10，oracle 上界 0.9101/0.9101；大框超 50% 置零 341 格（分档 max 58/mean 58/iou 72/coverage 72/iou_mass 81）；IoU 未中但 Text≥0.8 组双口径 n=0（condition-not-met，本口径恒为空）。是否再跑显著性检验由导师定，agent 不选择。
2. B1 缺格是否补测全量延迟/显存，还是维持草稿现状？本轮数：清洗探针（cuda:0，n=19 去 warmup，权重基座 5653.3MB）query 编码 mean 38.1ms/p50 35.1ms/max 62.8ms、增量 mean 28.1MB/max 46.1MB；七档选框合计 243.0ms（分档 max 10.8/mean 9.8/iou 10.4/coverage 6.5/iou_mass 5.4/P25 1.0/P50 7.4/P75 191.7ms，P75 碎裂组数多故最贵）、增量 8.1MB；文本索引缺（BM25 倒排 + BGE 页向量从未落盘）；k+1 引用值 LFRAG 块均 2.79/页、ColParse 均约 5.9/页（页码表号见 B1 表），索引 GB 与检索延迟/显存原文未单列维持缺。探针为单页单点，不可推广全量。补测与否由导师定，agent 不选择。
3. B3 跨页表格是否立项？本轮数：无跨页样本统计，不自动 fallback，需另立 Gate 与协议。立项与否由导师定，agent 不选择。
