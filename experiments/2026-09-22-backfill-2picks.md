# 2 题 picks 回填运行记录（EXP-006 建集缺陷补漏）

## 1. 实验目的

- 一句话：用与 EXP-006 完全相同的冻结方法，给漏选的 `mmdocir_00520/00672` 补算 5 规则 Top-1 picks，使 picks 集 1388→1390 = 页命中全集。
- Gate 归属：不判 Gate；EXP-007-S1 的前置输入。

## 2. 环境

- 本机 GPU（RTX 3080Ti）；`--extra colpali`；冻结 ColPali query 编码 + 缓存页向量，0 额外视觉编码、无训练。

## 3. 数据和 split

- 数据集：`mmdocir_evaluation`；仅 2 题（`00520` 题级 6 行全 unmapped；`00672` 题级 3 行全 unmapped；两题页命中已用 EXP-001 Top-5 验证，脚本内 `assert`，非页命中拒绝回填）。

## 4. 配置文件

- 无新 config；脚本 `scripts/backfill_2picks.py`（逐题逻辑与 `scripts/run_phase1c.py` 一致：同 gold 页选择规则——Top-K 内 rank 最小 gold 页；同 5 规则；group 三档记 None）。

## 5. 运行命令

```powershell
uv run --extra colpali python scripts/backfill_2picks.py
```

- 约 1 分钟（模型加载为主）；输出 `artifacts/baselines/mmdocir_1c/phase1c_picks_backfill_2.json`（本地产物不进 git）。

## 6. 代码 commit

- 随本记录页入库；原 `phase1c_picks.json` 冻结不动（回填文件独立存放，EXP-007 脚本运行时合并）。

## 7. 输出目录

- `artifacts/baselines/mmdocir_1c/phase1c_picks_backfill_2.json`

## 8. 关键指标（JSON 原样抄）

- `mmdocir_00520`（页 `..._95_p16`）：max/mean→l101；iou/coverage→l97；iou_mass→l96
- `mmdocir_00672`（页 `..._95_p16`）：max/mean/iou/coverage→l160；iou_mass→l159
- 两题 5 规则 picks 全部命中真实候选（无 None），group 三档记 None（自组框，无 node_id）。

## 9. 错误信息

- 无。`assert pages & gold_pages` 通过；`assert regions` 通过（同页候选非空）。

## 10. 结果解释

- EXP-006 漏选确认为建集规则缺陷（要求题级 matched），非数据缺陷；同方法下两题可正常选框。
- 与上一版对比：picks 集 1388→1390；EXP-007-S1 重算后 L3 最好 0.2791→0.2787（2 题贡献≈0，符合其 unmapped_only 弱候选预期）。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否（过程记录；论文引用 EXP-007-S1 即可）。
- 下一步：阈值冻结（提案见 `experiments/2026-09-22-threshold-proposal.md`）。
