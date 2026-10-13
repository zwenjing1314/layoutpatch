# 4 实验设置

## 4.1 实验目标与评测范围

实验评估的是给定问题和正确页面后，从既有解析候选区域中排序证据区域的能力。所有训练方法共享冻结的 ColPali 视觉与问题表示、候选集合和区域评测脚本。实验不评估文档库页面召回、任意坐标框生成或答案生成；因此候选区域排序结果不能直接解释为页面召回保持或端到端检索收益。

## 4.2 数据角色与划分

内部数据沿用 `data-roles-v1` 和 `regions-v1` 的文档级角色划分。原始角色计数如下：`source_train` 为169篇文档、826题，`source_val` 为43篇文档、375题，`source_dev` 为91篇文档、412题，`quarantine` 为10篇文档、45题。MMDocIR 官方 evaluation 在本协议中重新划作 `source_train`、`source_val` 和 `source_dev` 来源池；`source_train` 用于构造监督并更新参数，`source_val` 仅用于早停和 checkpoint 选择，`source_dev` 用于冻结权重后的开发比较，不能称为最终独立测试。隔离角色不进入训练、验证或开发评测。

论文同时报告题数与题—页单元数。内部区域审计得到 train 1059、val 450、dev 545、quarantine 53 个单元；D/C 的实际训练只使用 `source_train` 中局部损失可用且未被页级重叠排除的1002个单元。checkpoint 选择使用 `source_val` 的374题、448个评测单元；因此“source_val 原始375题”与“实际用于选择的374题”不能混写。统一开发评测使用 `source_dev` 的412题、545个单元和91篇文档，其中包含无正 patch、无负 patch 或页重叠标记的评测单元；局部损失资格不等于评测资格。

E 从原 D 的1002个训练单元继续筛选，得到843个可训练且与 D 相交的单元，排除159个单元。其中117个没有负候选，42个没有 IoU≥0.5 的正候选；该筛选使用候选级标签，不能将843写成 D 的训练分母，也不能将 E 描述为同训练集复现。E 的 checkpoint 选择仍使用 `source_val` 的374题、448个单元，未使用 `source_dev`。

外部评测固定使用 SciEGQA-Bench 的 test revision `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`，共1623题、837个唯一证据页、1941个题—页单元和9746个共同候选。外部候选由记录的 MinerU 4.0.10 Basic ONNX CPU 解析流程生成；内部训练侧候选的原解析版本与外部流程并未在本轮逐项复现，不能据此声称候选生成配置完全一致。外部 gold 只用于确定评测分母和计算指标，不进入向量生成、布局融合或候选排序。外部评测未静默删除异常题页，所有方法共享相同候选和分母。

## 4.3 候选、监督与过滤

页面 patch 表示固定为1024个图像 patch，提示 token 保留在页面缓存中但不参与局部区域评分。内部布局节点来自页面解析候选；D 的文本输入按节点类型取正文/公式的 `text` 或图像/表格的 `ocr_text`，缺失文本节点保留并以零向量进入文本投影。外部缓存记录837页的节点身份、形状和有限值检查通过，其中150个节点缺失文本但保留，9596个节点使用冻结的外部文本规则。

patch 级训练沿用第3节的正、负、忽略标签：patch 中心位于任一 gold 框内为正；与所有 gold 框零交集为负；其余边界 patch 忽略。无正 patch 或无负 patch 的单元不参与 C/D 局部损失，但仍可进入验证、开发或外部评测。E 使用候选级标签：候选与任一 gold 框的 IoU≥0.5 为正，其余有效候选为负；在排除空 (W_{\mathrm{raw}}) 候选后仍须同时保留正、负候选才可更新参数。两种监督粒度和过滤后的实际训练子集不同。

## 4.4 训练配置与权重选择

C、D 及 D 的开发变体均使用三个 seed（0、1、2），最多训练30个 epoch。已冻结配置使用 AdamW，学习率 (1\times10^{-3})，weight decay 0.01，((\beta_1,\beta_2)=(0.9,0.999))，(epsilon=10^{-8})，每4个 unit 的损失取平均后更新，梯度范数裁剪上限为1.0，无 scheduler。温度 (\tau=0.25)。每个 seed 独立初始化；不加载 smoke、C 或旧融合权重。

每个 epoch 在 `source_val` 的全部448个评测单元上计算 Top-1 IoU≥0.5 主指标，严格提高时保存 checkpoint，平局保留较早 epoch，连续5个 epoch 未严格提高则早停。全部 seed 的 checkpoint 确定后才进行一次 `source_dev` 比较。C、D 及其变体的登记可训练参数分别为 C 66176、C-wide 273318、D 273410、D-no-text 273410、D-no-coord 273410；接近的登记参数量不代表有效容量严格匹配。

E 使用三个 seed，并按其冻结补充配置在 `source_val` 上选择 checkpoint；实际训练/最佳 epoch 分别为 seed0 的6/1、seed1 的7/2、seed2 的7/2。E 的登记可训练参数为272593。指定配置记录 E 使用 AdamW，学习率 `lr=0.001`，`weight_decay=0.01`，`betas=[0.9,0.999]`，`eps=1e-8`，`units_per_update=4`，`clip_max_norm=1.0`，且 `scheduler=null`。E 的候选级训练单元、模型结构和 checkpoint 选择分母仍与 C/D 不同。

## 4.5 指标与统计规则

主指标为 Top-1 IoU Hit@0.5：对同一问题的各证据页先取页内平均，再按问题宏平均。它衡量排序首个候选是否与任一 gold 框达到 IoU 0.5，不是页面召回率，也不是整题全部证据覆盖率。辅助指标包括 Cov@5（前五候选对 gold 并集的面积覆盖率）和 Gold Recall@5（IoU≥0.5 条件下前五候选对多个 gold 框的一对一召回率）。

训练方法的外部主指标先按题计算三个 seed 的逐题分数均值，再按文档聚类 bootstrap 2000次估计配对区间。seed 间标准差为样本标准差（ddof=1），单位为百分点；文档 bootstrap 区间描述固定模型下的文档抽样不确定性，未完整覆盖训练随机性。原冻结外部实验预先规定 D-no-text 与 A、B、C-wide 的三项主比较，并同时报告普通95%区间和 Bonferroni 校正后的98.333%区间。E 为事后补充，只报告 D-no-text−E 的唯一95%文档配对比较，不并入原三项比较族。所有差值沿用结果文件的精确值，不由舍入后的均值重新反算。

## 写作核对备注（不并入正文）

1. 使用的记录：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/ROUTE_V2_PROTOCOL.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-04-route-v2-data.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-06-exp-014-route-v2-exp1.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-06-exp-015-route-v2-D.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-07-exp-016-attribution.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-09-exp-017-sciegqa-external.md、@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-10-exp-018-E-supplement.md，以及两份指定 `metrics.json`。
2. EXP-015 明确记录 D 训练了 `SparseLocalFusionV2(top_k=4)`；因此其源码头注“v2 class has no trained checkpoint”按本轮核对属于过时文档注释，不据此推断实验失败，也未进行权重审计或重训练。
3. 外部数据卡显示 SciEGQA 许可证未声明，且与内部数据的重叠筛查不能排除改写、翻译或预训练暴露；这些数据治理与泄漏边界不影响本轮分母转录，但投稿前仍需披露和核实。
4. E 配置字段定点来源为 @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/configs/experiments/route_v2_E_supplement_v1.yaml；已核对 `optimizer`、`units_per_update=4`、`clip_max_norm=1.0` 和 `scheduler=null`。内部候选解析器的完整版本对齐、E 训练调用的全部掩码细节仍待核实。
5. 缓存评分耗时与显存只在第5节作为运行口径说明，不解释为包含解析、编码和模型训练的完整系统成本。
