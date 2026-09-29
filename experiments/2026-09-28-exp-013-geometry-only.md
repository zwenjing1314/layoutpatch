# EXP-013 无训练几何对照

无训练，不是方案 A，不替换当前头。

同一 401 题、同一 gold 页、同一 `recall_layout`。没有保存 `ranker.pt`，没有调用训练循环。

- geom:area：Area@1 0.46726432578302896，Area@5 0.7726699451254816。相对 fixed:iou_mass 算涨。
- geom:center：Area@1 0.29591024029859686，Area@5 0.6243802678852584。相对 fixed:iou_mass 不算涨。
- 页级仍是 371/415。test_eval 未读。当前头仍是 `artifacts/phase2r/arxivqa_dude/ranker.pt`。
