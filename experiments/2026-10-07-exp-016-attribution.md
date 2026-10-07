# EXP-016：容量、文本与显式坐标的最小开发归因

## 1. 实验目的

2026-10-07用户明确授权三个变体各三seed；不调优D、不外测、不增变体。三项预定比较：D−C-wide、D−D-no-text、D−D-no-coord。九次训练及一次统一开发评测已完成，现已停止。

## 2. 环境

既有uv `.venv`、RTX3080Ti、float32/确定性/TF32关闭，12GiB硬上限；不新增依赖或模型。正式脚本内部耗时1027.6秒（终端显示精度），完整计时和环境保存在run_info.json，各seed训练与显存记录在metrics.json。无NaN/Inf或显存超限。

## 3. 数据和split

沿EXP-015原划分、缓存、候选、监督、损失、指标与分母。训练1002unit，val374题448unit，dev412题545unit91文档。A/B/C/D复用EXP-015已存预测；兼容性只按保存排名重算指标，不调用模型。输入哈希在正式运行前后核验，保存结果回验确认A/B/C/D预测完全不变。

## 4. 配置文件

`configs/experiments/route_v2_exp3_attribution.yaml`在任何评分前frozen，哈希绑定原EXP-015配置并继承完整预算；原配置不改。每变体seed0/1/2最多30epoch、最多九次；各自从头初始化，val严格提高/平局更早/patience5；九份checkpoint全部确定后统一dev评分。

C-wide只变隐藏宽度：257×1062+384=273318，对D273410误差约0.034%，无占位参数。D-no-text在文本投影前置零文本向量，仍保留投影及偏置。D-no-coord在正弦编码前置零六维坐标，零坐标仍产生固定sin/cos常量；真实W、空间偏置、邻域和cover_mass保留。两个消融结构参数均273410，但被置零/常量化输入会减少数据相关的有效自由度，不能称有效容量完全相同。

三seed先按题平均；文档bootstrap2000次/seed0，原95%区间不变；同时补充Bonferroni 98.333333%区间，三项构成同一比较族。百分位bootstrap覆盖为近似，非精确有限样本保证；不从三项中挑显著结果宣布贡献。不显著不等于等价。

## 5. 运行命令

`route-v2-exp3-tests`、`route-v2-exp3`，完整命令/输入/输出/检查见`docs/02-commands.md`。正式task只执行一次，exit_code=0。没有重训原C/D、重复真实smoke或追加开发模型评分。

## 6. 代码commit

`1961493b6b7f655459ffb24fe0b75536b0075a66`加本轮未提交改动；无commit或合并。正式run保存定点执行代码快照、code_identity.json及workspace.patch；前后核验执行代码/配置身份不变。原训练、评分、损失、指标实现均未改动。

## 7. 输出目录

`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_exp3_attribution/20261007_135013/`

正式五件套：config.json、run_info.json、metrics.json、predictions.parquet、summary.md。另有question_scores.parquet、input_verification.json、code_identity.json、code/、workspace.patch、checkpoint_selection.json、source_dev_started.json、result_verification.json。三个变体子目录分别保留每seed初始化一致性检查、逐epoch日志/训练曲线、改进权重、选择回执和stdout日志。

17个单方法预测组（A/B及C/D/三变体各三seed），共同分母545unit/412题；保存预测与逐题分数均已在脚本内部读回核验。原run不可变，本轮未覆盖。

## 8. 关键指标

数值来源为上述完整run的metrics.json；下表采用正式入口从该指标对象输出的10位小数，不另立指标口径。主指标为Top-1 IoU≥0.5，页内单元先按题平均再题宏平均；均值/标准差使用三个seed，样本标准差ddof=1。

|方法|主指标均值|样本标准差|Cov@5|gold召回@5|实际epoch（seed0/1/2）|最佳epoch（seed0/1/2）|
|---|---:|---:|---:|---:|---|---|
|C（复用）|0.4253101402|0.0057364019|0.8217654376|0.8099659038|—|—|
|D（复用）|0.5296521036|0.0250218861|0.8890783320|0.8871311065|—|—|
|C-wide|0.4296925566|0.0008090615|0.8171157091|0.8057192942|12/11/10|7/6/5|
|D-no-text|0.5566747573|0.0052099728|0.8983029565|0.8943481276|6/6/10|1/1/5|
|D-no-coord|0.5037486516|0.0473701241|0.8933577442|0.8897817460|6/12/18|1/7/13|

终端的三项配对摘要原文（由metrics同一对象打印）：

```text
D-C-wide: delta=0.0999595469; CI95=[0.0512590862,0.1466137566]; Bonferroni=[0.0438330675,0.1559586798]
D-D-no-text: delta=-0.0270226537; CI95=[-0.0487472767,-0.0073956868]; Bonferroni=[-0.0551388889,-0.0023474178]
D-D-no-coord: delta=0.0259034520; CI95=[0.0037735849,0.0497742664]; Bonferroni=[-0.0025943396,0.0541463415]
```

原A/B、随机期望、候选Oracle、全部阈值与覆盖/面积辅助指标、M≥2子集及分母、面积分位数、逐seed结果、逐seed二元McNemar、三项Top5差值、参数和训练/评分成本均保留在metrics.json。McNemar忽略文档相关性，只作辅助，不用于宣告贡献。

Top5方向不能被Top1掩盖：D相对C-wide的Cov@5与gold召回@5均提高；相对D-no-text两项均下降；相对D-no-coord两项也略低。因此显式坐标不能称全面改善。完整精度以metrics.json为准。

## 9. 错误信息及验证

新增文件初次Ruff发现一项`I001 Import block is un-sorted or un-formatted`，已修正导入格式；随后相关Ruff通过、20项测试通过（10.35秒）。覆盖有效容量与梯度、指定输入置零/真实几何不变/缓存不变、九权重选择门、三项同时区间与原统计一致、预算继承，以及原D/早停/预测兼容性回归。

正式运行无失败，九次训练合计91epoch，无配置重试。终端完成回执：`saved result verification passed; ABCD unchanged; all three comparisons retained`；`status=completed`，exit_code=0。脚本内部复核全部选择/保存权重、预测的候选与指标、逐题分数、配对统计和输入身份，回执保存为result_verification.json。复核不调用模型。

`git diff --check`无空白错误，仅Git的LF→CRLF提示。未运行全仓check；19个旧Ruff问题不在本轮，不声称全仓通过。编辑器直接读取runs受.cursorignore保护，本记录采用正式task完成摘要及其内部保存结果复核；未绕过保护或修改忽略规则。

## 10. 结果解释

1. 容量：D−C-wide约+9.996个百分点，Bonferroni区间仍全正。这支持“仅把普通PatchAdapter扩至近似参数量不足以解释D收益”，不能据此独立确定是哪种布局信息或结构机制有效。
2. 文本：D−D-no-text约−2.702个百分点，校正区间全负；本预算下文本输入未贡献正向收益，去掉文本的开发结果更好。不据此泛化为所有OCR文本都无用，也不自动替换D配置。
3. 显式坐标：D−D-no-coord约+2.590个百分点，原95%区间为正，但三项校正后跨0；证据不足以宣称显式坐标独立增益。真实W/邻域/cover_mass仍保留，该项不能推论移除全部空间信息的效果；不显著不等于等价。

## 11. 是否可用于论文及下一步

三项必须一同报告，仅限开发归因证据；不能证明外部泛化、新颖性或页级保持。已完成并停止，不自动调优D、采用消融赢家、扩数据、外测或新增变体。
