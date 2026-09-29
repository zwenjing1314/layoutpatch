# Phase 2-R 停止冻结

397/401 的 EXP-009 Top-1 是最大框。

Area@1 平均相同来自 01393 的 -1 与 01408 的 +1 抵消。

IoU≥0.5 为 fixed:iou_mass 130、EXP-009 214、geom:area 214。

因此 2-R 停止，不打 test_eval。214 不写成训练贡献。

本轮 Snappy 三行，同一 401 题、同一 gold 页：

- snappy:max：Area@1 0.08253863585117388，Area@5 0.4175999466104787，IoU≥0.5 45/401。
- snappy:mean：Area@1 0.0899524795180662，Area@5 0.4129556803468502，IoU≥0.5 47/401。
- snappy:iou：Area@1 0.22050796570772077，Area@5 0.6880808278948266，IoU≥0.5 105/401。

当前头仍是 arxivqa_dude。
