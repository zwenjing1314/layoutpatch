# 融合前置只读审计

不实现融合。不训练。不读 test_eval。不编码。

## 代码

- P：`artifacts/colpali/mmdocir_train/vidore_colpali/`。已有。
- 布局节点 T：`src/layoutpatch/layout/` 无 `nodes.py`。缺失。
- 对应权重 W：`src/layoutpatch/layout/correspondence.py`。已有。
- 空 patch 兜底：`src/layoutpatch/layout/correspondence.py` 只标空行。缺失。
- 坐标审计：`src/layoutpatch/evaluation/audit.py`。已有。

融合前置缺失 2 项：T、空 patch 兜底。

## train_fit 缓存

只检查已有 `.pt`。没有编码。

- 覆盖：11575 题，10471 页。
- 缺缓存：45487 题，48096 页。

## 显存

`experiments/2026-09-26-encode-probe.md` 只测了 20 页编码，峰值 8.10 GiB。没有融合前向记录。未知。

## 开训前必须批准

不替用户选择。

- 融合结构。
- 损失。
- 训练数据范围。
