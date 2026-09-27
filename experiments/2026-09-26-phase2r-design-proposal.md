# Phase 2-R 设计（proposal，已被确认，不是开训许可）

> 状态：已被用户确认。确认不是开训许可。不建 `fusion/`，不写 `train_fusion.py`。冻结副本：`experiments/2026-09-26-phase2r-design-frozen.md`。
> 划分已冻结：`experiments/2026-09-26-dev-test-split-frozen.md`。本页不改那套 id。
> 超参写死方案 A：特征三组全开、K=4、早停 2 轮、batch 32。`dev_eval` 只判一次，不搜参。

## 1. 目标与非目标

目标只在 `dev_eval` 上判定，三条同时满足：

- 相对同一 `dev_eval` 子集重算的 `fixed:iou_mass`，Area@1 上涨。
- 同一子集上 Area@5 也上涨。两条必须同向。
- 页级 R@5 相对同一子集上的冻结 ColPali，变化在 ±0.3 个百分点以内。

非目标：

- 不做全融合 `P→P'`。不改 1024 个视觉小块。
- 不改 ColPali 主干，不训练它的权重。
- 不看 `test_eval` 分数。`test_eval` 本轮只有 id。

## 2. 输入特征

只允许三组。

1. 冻结 ColPali 的 patch 分。对一个问题和一页，已有缓存是每个小块一个分数。框分用框与小块的面积重叠，把小块分汇成框分。这是 `fixed:iou_mass` 已经在用的汇法，2-R 只是在它旁边再学一个分数，不替换这组输入。
2. 候选框几何：框面积、框面积除以页面积、框中心相对页宽高的两个数。只用候选框自己的坐标，不用 gold 框坐标。
3. 框文本与问题的相似度。用已在本机的 `BAAI/bge-m3`（文本向量模型，EXP-003 已用于页级检索）。问题向量和框内 OCR 文本向量做点积。不新下模型。框文本为空时，这一项记 0，不删框。

不多加特征。evaluation gold 的框坐标、覆盖分 `Area(c∩G)/Area(G)`，都不进训练标签，也不进特征。

## 3. 训练信号

没有框级 gold。学的不是「这个框盖住标准答案多少」，而是「正页上的框，整体应高于负页上的框」。

一题自带 1 个正页、1 个负页，两页都在同一文档里。页上每个候选框先算出三组特征，拼成向量 `x`。一个小线性层打分：

\[
s(c) = w \cdot x_c + b
\]

正页框集合记为 \(C^+\)，负页框集合记为 \(C^-\)。主损失只比较两侧各自面积最大的前 K 个框，K=4。面积只用来选哪 4 个框进损失，不把面积当成 gold 覆盖分。

\[
L = -\log \frac{\sum_{c \in \mathrm{TopKArea}(C^+)} \exp(s(c))}{\sum_{c \in \mathrm{TopKArea}(C^+)} \exp(s(c)) + \sum_{c \in \mathrm{TopKArea}(C^-)} \exp(s(c))}
\]

K=4 只作用在训练损失这一侧。推理排序不用这 4 个，推理给该页全部候选框打分。空框页（一侧不足 4 个）用现有框，不补假框。两侧都没有框的题跳过，不造 gold。

这不是 \(y(c)=\mathrm{Area}(c\cap G)/\mathrm{Area}(G)\)。训练集没有 G，不能构造这个标签。

主损失是页级弱监督：只知道哪一页是正页，不知道页上哪个框盖住答案。若 `dev_eval` 区域不涨，记为「页弱监督迁不到框排序」。不许改用 evaluation gold 补标签。

## 4. 推理与对照

页排序保持冻结 ColPali。2-R 不改页序，也不改页级 R@5 的算法。

Area@1 / Area@5 与官方 `recall_layout` 同一口径：只在该题 gold 页的全部候选框上排序，再取 Top-1 / Top-5。2-R 用 \(s(c)\) 重排这页全部候选框。不是只给 ColPali Top-1 页的框打分。后一种和全集 0.2787 不是同一口径，不许这么写。

这是评测时用 gold 页当候选范围。gold 框坐标和覆盖分不进训练标签。训练侧仍然禁止 \(y(c)\)。

对照 `fixed:iou_mass` 必须用同一 gold 页、同一 `dev_eval` 子集重算：筛出这 415 题，在每题 gold 页的全部候选框上用 `fixed:iou_mass` 取 Top-1 / Top-5，再跑官方 `recall_layout`。全集 0.2787 不拿来当子集分数。页级对照只在这 415 题上重算冻结 ColPali 的 R@5。

成功线三条缺一不可：Area@1 涨、Area@5 涨、页级 R@5 变化在 ±0.3 个百分点以内。

## 5. 数据池

| 池子 | 干什么 |
| --- | --- |
| train_fit（57062 题 / 25577 文档） | 只更新 \(w, b\)。标签只有正页/负页。 |
| train_dev（5400 题 / 713 文档） | 只看页级早停。不选特征，不搜 K，不看区域 gold。 |
| dev_eval（415 题 / 93 文档） | 只按第 4 节判一次涨跌。不搜参。 |
| test_eval（1243 题 / 220 文档） | 本轮不打分。 |

超参写死方案 A，不走方案 B，不在 `dev_eval` 上消融：

- 特征三组全开。
- K=4。
- 早停 2 轮：每轮看 `train_dev` 上正页最高框分是否高于负页最高框分的比例，连续 2 轮不升就停。
- batch 32。若超 12GB，停下来另批申请，不在本页改成 8，也不靠这 713 个文档改 batch。

`dev_eval` 只判一次，不搜参。不在这 713 个文档上选特征、不选 K、不看区域 gold。

`with_layout_gold` 不能用 `bool(layout_mapping)`。那个判断会把只有 unmapped 框的题也算进区域分母。对齐 EXP-005：题至少有一条 matched gold 才进区域分母。按这个口径重数，`dev_eval` 415 题里 matched 391（含 1 题同时有 matched 和 unmapped），unmapped_only 24，无布局行 0。区域 Area 分母是 391，不是 415。24 题只报页级，不进区域分母。

## 6. 工程边界

确认前不创建这些路径。确认后才允许建：

- 打分模块设想：`src/layoutpatch/retrieval/rerank/box_ranker.py`
- 训练脚本设想：`scripts/train_phase2r.py`
- 不建 `src/layoutpatch/retrieval/fusion/`，不写 `train_fusion.py`。

显存上界 RTX 3080Ti 12GB。2-R 训练只更新一个小线性层，batch 写死 32 题。ColPali 与 bge-m3 不在训练步里反传。若 32 超 12GB，停下来另批申请，不在本页把 batch 改成 8。

已有、优先用：

- ColPali 页向量缓存（EXP-001，评测集）。
- `BAAI/bge-m3` 本地权重（EXP-003 已用，不新下）。
- 评测候选框与 gold：`region_labels.parquet`、`phase1c_picks.json`。

缺，本轮不下载：

- 训练集 57062 题的 ColPali query/页 patch 分缓存。训练前必须另批申请，不能在本页确认后直接下或编码。
- 训练集框文本的 bge-m3 向量缓存。同样另批申请。

## 7. 三句禁止

- 不用 evaluation gold 构造 \(y(c)\)。
- 不用 \(T_{oracle}\ge 0.5\) 过滤 train。
- 本页不是开训许可。
