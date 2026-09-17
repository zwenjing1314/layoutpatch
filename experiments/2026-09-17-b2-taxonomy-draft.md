# B2 失败分类学草稿（决策材料，不做选择）

> 出处：小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3/7.4/8 节；大论文规范 `docs/THESIS_SPEC.md` 第 11.2/11.3 节。
> 状态：草稿，仅供学生与导师共判，不写论文结论。数字全部可在 `experiments/registry.csv` 追到源头。
> 禁令：不建 `fusion/` 子包、不写 `train_fusion.py`；训练须学生+导师双确认。

## 三数并列（同一口径 K=5 / IoU≥0.5）

1. **45B 全 unmapped_only 框缺失**：B=45/45 unmapped_only（matched B=0），见 `artifacts/diagnosis/mmdocir_evaluation/crosstab.json`（EXP-005）。
   含义：页中了但官方布局没给该框，无训练重排消不掉这类题。
2. **oracle 58 缺框**：全量 oracle 未中 1658-1600=58；页命中内 oracle 未中 1390-1345=45；B 是 58 的真子集（45⊆58），见 `artifacts/diagnosis/mmdocir_evaluation/oracle.json`（EXP-005）。
   含义：页给定时天花板 96.76%，框缺口 45/58；另 13 题在 D（页未中），不在本轮 1C 评估集。
3. **1343A Top-1 仅 0.3187 排序缺口**：matched A 候选召回上限 100%（定义），但固定候选 Top-1 最高 428/1343=0.3187（fixed:iou_mass），Snappy-iou 0.2621，max/mean 约 0.10，分组 ≤0.1035，见 `artifacts/baselines/mmdocir_1c/phase1c.json`（EXP-006）。
   含义：框在≠能排第一；这是真实排序能力，与"候选召回上限非排序能力"声明一致。
4. **Text 方法分（n=1388 中 NaN 53/有效 1335；group 三档未跑）**：fixed:iou_mass Recall 0.3455/F1 0.3341；snappy:iou 0.2716/0.2712；coverage 0.2708/0.2704；max/mean 约 0.09~0.10；大框超 50% 置零 341 格（分档 max 58/mean 58/iou 72/coverage 72/iou_mass 81）；IoU 未中但 Text≥0.8 组 n=0（condition-not-met，本口径恒为空），见 `artifacts/diagnosis/mmdocir_evaluation/text_dual.json`。

## 分类学（B2 草稿，三类）

- **B2-a 框缺失型（45/45 B）**：gold 框不在 nodes 表，固定五档消解率全 0.0；group 碰框 0.6889/0.3556/0.0889 为大框碰大框虚高，不计消解（P25→P75 单调降即证据）。
- **B2-b 排序缺口型（1343A 内约 68% Top-1 未中）**：框在但排不到第一；iou_mass（0.3187）> snappy-iou（0.2621）> max/mean（约0.10），说明尺寸归一化比局部峰值重要。
- **B2-c 口径约束型（D=268=255 matched D 页未中 + 13 unmapped_only D 页未中）**：255 题 matched 但页未中故不在 1C 集；13 题 unmapped_only 页未中；A 总 1345=1343（matched A）+2（unmapped_only A 纯 unmapped 命中 `mmdocir_00520/00672`）；both 题 `mmdocir_00036/00491`（既有 matched 行又有 unmapped 行）在 matched 行内归 A。全量 1658=1343+45+2+255+13；47=45B+2A。

## 与 11.2/11.3 的对照（只摆数字，不选择）

- 11.2 进 Phase 2 需 B 占比≥10%：实际 B=45/1390=3.24%，可寻址 0/1390=0.0、0/1598=0.0，离线各低 10pp/6.76pp（后者按 10%-3.24%）。
- Snappy 最好消解 0/45=0%（≤50% 条满足，但第一条不满足）→ 按 11.2 不进 Phase 2。
- 11.3 收缩候选：B1 效率对比（见 `experiments/2026-09-17-eff-b1.md`，P75 根因与 k+1 页码见该表；仍缺即维持草稿）/ B2 本草稿 / B3 跨页表格需另立项（本轮无跨页样本统计，不立项）。

## 待导师判（三个问题）

1. B2 分类学是否足以撑"诊断+基准"型小论文，还是需补 Text Recall/F1 双轨（第 8 节）？
2. B1 效率表缺的在线延迟/峰值显存是否需要补测，还是维持"缺格明写"现状？
3. B3 是否立项：若立项需另立 Gate 与协议，本轮不自动 fallback。
