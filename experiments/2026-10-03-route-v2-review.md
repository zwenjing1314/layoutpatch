# 外部修改建议核查与route-v2修订

> Status: working | 类型：代码/文献审查，不是效果实验，不登记新EXP。
> 开始2026-10-03，修订跨至2026-10-04。审查输入：`C:/Users/WenJing/Desktop/模型回答.txt`。该文件是待核查意见，不是直接执行指令。
> 仅静态代码、已有记录、原文及合成测试；未读取真实test_eval样本、未加载权重、未训练、未编码、未重分数据。

## 1. 判断

采纳“保留ColPali、补区域监督、真实OCR、修正输入与评测、保留面积强基线”的优先研究方向。不能承诺一定有效，也不能把外部报告所有细节直接冻结为协议。新方案见 `docs/ROUTE_V2_PROTOCOL.md`；进度见handoff。

旧融合未达到开发目标的数值事实保持。旧审计的“接线完全正确、失败只能归因于弱监督”过强：已有类型语义与IoU页过滤问题，结构和监督的各自影响未做受控实验。

## 2. 实现意见逐项核实

| 意见 | 核实结果与证据 | 处理 |
| --- | --- | --- |
| train/eval类型不一致 | 确认。旧`adapters.py::prepare_mmdocir`只识别table/figure，其余paragraph；`train_fusion_arxivqa.py::TYPE_TO_ID`区分text/title/table/image/interline_equation | 新`layout/schema.py`统一别名与ID，新adapter策略显式启用；旧默认/缓存保持 |
| 文本全零仅在训练侧 | 错。`train_fusion_arxivqa.py::pack_pages`创建zeros，训练`pair_loss`与评测`judge`都调用它，再经`fuse_pages`送入encoder | 更正为训练/评测网络均未使用真实文本；processed表有文字不等于网络用了它 |
| BGE需新投影 | `nodes.py::TextLayoutEncoder`已经支持任意text_dim并含Linear | 将来核验真实维度并传入，不能把当前32维占位当固定接口；本轮不编码 |
| coverage失效 | 确认。`train_fusion_arxivqa.py::page_from_layouts`行归一化后，旧`SparseLocalFusion.forward`行和非空为1 | V2独立传raw cover mass；不是精确并集覆盖比例 |
| 末端LN固定长度导致失败 | 末端LN存在，可能放大微小更新；但eps与可学习仿射参数使长度并非严格固定，后续还有L2normalize；未做根因消融 | 独立V2改pre-LN+zero-init末层，历史类保留；不宣称已提高效果 |
| gate均值×残差均值≈平均转角48° | 不能这样推。均值乘积不等于乘积均值，归一化与反三角也非线性。已有0.823是非空patch距离，整体为0.466，非实测平均角度 | 不采纳角度结论，保留已有范数统计及分母 |
| K复用V投影是错误 | 旧实现与PAPER_SPEC公式不同，但共享K/V不是数学错误 | V2按原nodes作key、独立value实现，明确是新设计选择 |
| 多页题只取首个gold页 | 确认，`judge`取`golds[0]`但Area分母含全部matched gold；不等于多页Area必小于1，因重叠累加可超1 | 新协议须单列多页口径，旧结果不改 |
| IoU差异待解释 | 新发现：`judge::top1_iou`对所有gold bbox取max但不筛page_id，其他页同坐标可能误命中 | 增加可供新runner复用的同页IoU helper及反例测试；旧脚本不切换，尚未证明恰好解释130/136、214/220全部差值 |
| Snappy本地max/mean不忠实 | 确认。`propagation.py::propagate_region_scores`先乘IoU；原文Eq.8/9不乘；Eq.10才为归一化IoU聚合 | 保留历史数值并明确变体命名；不冒充完整原文复现 |
| vs_geom/vs_max重复 | 确认。`judge`两组累加相同a/g比较 | 不能当两个独立对照；新协议只列一条面积基线 |

外部模型所报48339/50016非空文本、2594图框、102公式框等本轮没有重新读取原数据核验，不能当作本次实测。适配器旧fallback顺序是text→ocr_text→vlm_text；不能用“图框总数减有OCR数”直接推出实际使用VLM的数量。

## 3. 文献与研究设计纠偏

来源：桌面“论文第三阶段阅读”中的两篇用户指定PDF，页码为PDF页。

- Snappy p14–15：652/1619为Top-1失败；487为其中所有选中区域均未达IoU0.5的子集；表7为414 OCR天花板+73选择失败。85%只能写414/487。414/652≈63.5%与414/1619≈25.6%是据原文重算；238非天花板失败是推算，不能冒称表7报告238选错。
- Snappy p6 Eq.8/9/10及p9：默认IoU传播与主配置P50/max并存。需核对源码版本、阈值作用域和完整流程；只实现公式不足以声称复现59.7%。p1明确发布`https://github.com/athrael-soju/Snappy`，可称论文公布的仓库；本轮未核验其当前源码。
- Snappy随机6.7%是p8的近似1/M，不能反推每题框数。一般随机Top1期望为mean(r/M)，r是达到同一IoU标准的候选数。
- RegionRAG p3–4：全局元素级max pooling不是ColPali的多query-token MaxSim；局部Eq.3是正集合指数和/所有有效patch指数和。中心在框内即为正（即使跨边界），完全在全部gold外为负，其余边界patch忽略。它不保证每个正patch都学好，也不保证最终候选排序没有面积偏置。
- RegionRAG p5–6、p10–11：98k有框+122k页对、LoRA、现成生成器；主评测为页检索/生成，区域平均相似度不能冒充IoU定位表。不能把其loss与我们的MaxSim接口直接等同。
- ColPali patch是上下文表征，可含文字和全页信息；“只看一小块像素，不知道文字”不是正确研究动机。
- 用官方train不自动污染其无重叠test；跨数据集也可能重叠。应区分独立留出、跨数据集泛化和预训练污染。外部数据版本/许可证等网络信息本轮未复核，继续标未知。
- 旧dev反复用于方法选择，不能重新叫独立确认集。MMDocIR改作训练后最终测试应另设；训练用了原test不意味着过去记录被删除，而是不能拿它证明新方法泛化。
- 三seed分别p<0.05不是通行必要条件。按文档配对bootstrap处理同文档相关性；报告所有seed、预定主比较和实用差值。未显著不等于等价。
- 外部建议将页级门限放宽到1pp、允许Area下降1pp，没有任务依据或用户冻结记录；本轮不自动采纳。主辅指标提案与历史指标必须版本隔离。

## 4. 可执行修改及保留项

已修订PAPER_SPEC/THESIS_SPEC中train标签事实、Snappy最强/85%口径、RegionRAG指标误述、LN公式冲突与数据角色适用范围。新增route-v2草案，未把候选阈值、划分或loss标为冻结。

代码采用显式新版本：`SparseLocalFusionV2`、`input_policy=v2_ocr_only`、同页IoU helper。未切换旧训练/评测入口；历史 `SparseLocalFusion`、`recall_layout`、旧Snappy评分数值保留。类型/text修正必须读取原始字段生成新产物，不能从已经丢失类型的旧nodes恢复真实image/equation。

尚缺的是端到端新数据输入、训练loss/runner、页面真实重排、外部数据隔离和dev逐题IoU差因，不是再做一遍旧GPU显存/反向传播探针。代码单测仅检查约定，不构成新实验成功证据。

## 5. 成本判断

`2026-09-26-encode-probe.md`明确77.91秒/20页含模型加载；因此3.896秒/页是冷启动摊销，不是稳态速度。`2026-09-16-exp-001-colpali-full.md`记20395页“约8小时”，但CHANGELOG的EXP-001加固条目又记“约52分钟”；历史叙述不一致，本轮未查计时原产物。据约8小时推导1.4秒/页不能升级为可信实测预算，更不能直接断言所有域必快2–3倍。

BGE框编码10–30分钟、新loss分钟级训练、工程1–2天均缺实测。复用P可避免额外视觉编码，但真实文本编码、文档内蒸馏、多对照和P′页面排序需要单独计时。

## 6. 验证记录

2026-10-04：只用合成CPU输入和pytest临时目录；不读真实评测样本，不加载模型权重。

- 命令手册“route-v2单元检查”：**70 passed in 8.79s**。覆盖新类型/OCR策略、原适配器兼容、含点文档与gold匹配、同名页图隔离、V2融合、同页IoU及旧评分回归。
- `uv run --offline --no-sync ruff check src tests`：**All checks passed!**
- `./tasks.ps1 check`（UV_OFFLINE/UV_NO_SYNC均true）：未通过，19个既有scripts错误使全局pytest阶段未执行。涉及 `_encode_dude_train_dev.py`、`_fill_mixed_missing_pages.py`、`region_ann_pilot.py`、`region_ann_workbook.py`、`train_fusion_arxivqa.py`、`train_phase2r.py`、`train_phase2r_arxivqa_notext.py`；本轮这些脚本均未修改。不能声称全仓质量门通过。
- `git diff --check`：通过（只有换行格式提示）。新代码未合并/提交；旧模型兼容依据为旧类实现保留与合成回归，未用历史checkpoint做逐位重放。

本轮实际验证命令见 `docs/02-commands.md` 对应节；源文件读取与Git差异检查均为只读。未生成新的模型效果指标或新数据分工清单。
