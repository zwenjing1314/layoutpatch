# 中文小论文写作交接与执行计划

更新：2026-10-12。用途：新对话的最小入口；整理既有记录及已核对代码，不是新的实验审计或正式论文。本轮未训练、调参、下载数据或重新评分，未修改旧协议、结果、权重及收尾记录。

## 1. 已决定的方向与尚待确认事项

用户决定先写中文小论文初稿，再考虑大论文后续研究。师姐建议先写，不等于导师已经认可投稿定位。暂定题目：**布局条件的视觉文档证据定位：表示修正与直接排序的实证比较**。研究问题：在冻结 ColPali、整页只编码一次的条件下，布局条件 patch 适配相对普通适配、几何规则与直接候选排序提供哪些收益与局限？

任务是给定问题及正确页面，从既有解析候选中排序证据区域，不是页面召回、答案生成或任意坐标框生成。P′兼容原 MaxSim 接口不等于页面召回保持。新增了真实可学习模块，但这不自动证明新颖性或优于所有基线。E也不是可直接改名为创新的主方法。

待用户/导师确认：目标期刊或学校认定范围、篇幅和模板、提交时间、署名/单位。未确定前先用中文Markdown分节写作，不阻塞方法与结果初稿；不能承诺接收或毕业。论文无需叙述所有调试历史和旧路线尝试。

## 2. 证据优先级与少读规则

首次读本文件与研究简稿即可；每轮只按当前章节读取下列1—2份必要记录。运行结果是数值依据，实验记录是解释索引，代码是实现依据；聊天与本交接不是替代证据。遇矛盾标记“待核实”并定点查源，不静默选更有利数字。不扫描整个仓库，不读大预测/缓存/日志，不重新评分。

- 研究简稿：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/route-v2-paper-decision-brief.md
- 数据角色与监督：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/ROUTE_V2_PROTOCOL.md
- 数据准备记录：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-04-route-v2-data.md
- A/B/C开发实验：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-06-exp-014-route-v2-exp1.md
- D开发实验：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-06-exp-015-route-v2-D.md
- 容量与消融：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-07-exp-016-attribution.md
- 原冻结外部结果：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-09-exp-017-sciegqa-external.md
- E事后补充结果：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-10-exp-018-E-supplement.md
- 事后分析与E设计：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/route-v2-review-response.md
- 旧收尾：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/route-v2-results-and-closure.md（早于E；“只剩写作/无缺口”不是投稿充分性结论，不能压过后续E证据）。

旧 PAPER_SPEC/THESIS_SPEC 的历史愿望不自动变成本轮实验要求。旧route-v1曾有图像token切片错位，不能把旧401题结果与route-v2直接拼表。先前40题人工标注pilot不是此次正式训练样本来源，不能写成用40题训练。

## 3. 数据与评测事实

MMDocIR官方evaluation被重新指定为有标注训练/开发来源池，不再作为新路线最终测试。按文档划分：train169篇/826题，val43篇/375题，dev91篇/412题，隔离10篇/45题。题数不等于实际参与局部损失的题—页单元数：D训练1002单元；E候选监督可用843，排除117个无负候选及42个无正候选。E实际权重选择用val374题/448单元；写实验设置时引用对应过滤记录，不能混用375与374。

外部SciEGQA固定1623题、80文档、837唯一证据页、1941题—页单元、9746共同候选。837不是MMDocIR验证集页数，也不是整库召回页面。外部候选由MinerU4.0.10 Basic ONNX CPU生成；训练侧官方候选的原解析版本未知，不能声称候选生成配置完全一致。独立来源不等于排除了全部预训练暴露或零泄漏。许可与重叠筛查的精确状态以数据记录为准，投稿前须定点确认。

主指标：Top-1候选与任一gold的IoU≥0.5即命中，先在题内对页平均、再题宏平均。它不是整题全部证据覆盖率。Cov@5为前五候选对gold的去重面积覆盖，Gold Recall@5为IoU阈值下的gold召回；精确定义应在写作时引用冻结评测口径，不能混成旧Area@5。三个seed先逐题平均，再按文档配对bootstrap2000次；区间反映固定模型条件下的文档抽样，不完整涵盖训练随机性。

## 4. 方法、公式与必须保留的解释

图像P为1024×128，Q为T×128。缓存1031行的前1024行是图像patch，后7行是提示token。问题只移除全零批padding，不能随意删有效增广token。定义归一化相似度S_ti=<q_t,p_i>。

- A：候选面积降序，不训练、不用问题。
- B：s_i=max_t S_ti；r_j=Σ_i a_ji s_i/Σ_i a_ji，其中a_ji=IoU(patch_i,候选j)。是归一化加权平均，不是未归一化累计。页级MaxSim为Σ_t max_i S_ti，与patch热力图的max方向不同。
- C：x=normalize(P)；P′=normalize(x+MLP(x))。MLP为LayerNorm→Linear128→256→GELU→Linear256→128，末层零初始化，共66176参数。每个patch共用一个网络；不直接接收问题、W、节点文本、坐标和类型。C是与D平行的无布局对照，不接收D的P′。C-wide仅将隐藏宽度扩大到1062，273318参数。
- D：文本1024→128、六维坐标经72维正弦编码→128、类型embedding128，拼接384→128形成节点。patch根据W选择最多4个有效邻居，以patch—节点相似度加log空间权重计算注意力，汇总局部节点信息δ；P′=normalize(P+sigmoid(gate([P,δ,cover_mass]))×residualMLP(δ))。节点编码器与融合器可训练，登记273410参数，骨干冻结，P′不依赖当前问题。D-no-text把文本输入置零，并非删除文本投影支路，不能声称有效容量严格匹配。
- E：保留P，按W_raw池化为候选视觉v；问题交互x=max_t(q_t⊙v)是逐维交互，非标准MaxSim。坐标与类型编码为l；r_E=r_B+MLP([x,v,l])，MLP384→680→1，末层零初始化，272593参数。E直接输出候选分数，不生成新的P′。

共同损失形式：L=−log[Σ_正例 exp(score/τ)/Σ_正负例 exp(score/τ)]，τ=0.25。C/D的score为patch分数，patch中心在gold内为正，与所有gold零交集为负，其余忽略；E的score为候选分数，与任一gold IoU≥0.5为正，其余有效候选为负。二者同标注来源但不同监督粒度/实际训练单元，不能称严格单因素机制实验。该损失优化正例集合概率，不保证每个正例均获高分。C/D的固定候选汇总不直接进入当前patch训练损失。

已于2026-10-12核对本地Snappy commit acde4a1：其本地评测路径同样归一化Q/P后点积、按问题token取max、按IoU加权平均区域。B核心公式一致，但骨干、解析器、token及协议未完整复现。官方提供none/percentile等不同筛选；不能声称所有入口强制P50。对同一排序按分位数筛选通常不改变Top-1，因此不能把差距归因于少了筛选。

代码仅写方法时按需读取：
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_scoring.py
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/layout/nodes.py
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/fusion/sparse_fusion.py
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_candidate.py
- @C:/Users/WenJing/Documents/WorkTransfer/Snappy/backend/benchmarks/local_client.py
- @C:/Users/WenJing/Documents/WorkTransfer/Snappy/backend/benchmarks/dataset_runner.py

## 5. 外部核心结果与论断边界

百分比，训练方法为三个seed均值；完整标准差写表时从对应实验记录提取，不猜测。

| 方法 | Top-1 | Cov@5 | Gold Recall@5 |
|---|---:|---:|---:|
| A | 33.7954 | 64.1249 | 57.0240 |
| B | 23.9063 | 60.1992 | 54.9908 |
| C | 21.3802 | 51.4124 | 46.9398 |
| C-wide | 23.3518 | 50.5222 | 46.4161 |
| D | 21.9450 | 54.6627 | 51.2939 |
| D-no-text | 30.7969 | 58.5998 | 54.3233 |
| E（事后补充） | 35.3563 | 61.5927 | 56.4387 |

原三项D-no-text−A/B/C-wide差值与Bonferroni98.333%区间（百分点）：−2.9986 [−7.8964,1.8096]；+6.8905 [3.1573,10.6887]；+7.4451 [3.8736,11.1144]。E唯一补充主比较D-no-text−E=−4.5595，95%区间[−6.7715,−2.4905]。E三个seed为33.0561/32.3783/40.6346%，标准差4.5837个百分点；不得挑最好seed。E−A均值+1.5609个百分点，没有预定显著性证据。

可主张：实现真实布局条件适配；D-no-text在本外部测试Top-1优于B/C-wide；特定E优于D-no-text。不可主张：D/E可靠超过面积、P′优于直接排序、完整Snappy复现、页面召回保持、SOTA或已证明具体空间机制。D-no-text的Top-5低于A/B，E的Top-5低于A，不能隐藏。登记参数量接近不等于有效容量严格相同。

事后分析：同页不同gold的问题对中D约45%—48%改变Top-1，仅支持查询依赖，不证明语义理解。有效邻居最多4，TopK=4未截断。大框中的局部证据可能被平均稀释、固定评分可能未充分读出P′、训练与评测目标可能不一致：这些是解释假设，不能写成已验证原因。IoU汇总不直接删除布局信息。未来P′接E式排序、显式面积先验等方案未运行，不可放入本论文已完成方法/结果。

效率90.57秒与约60MiB仅为原外部缓存评分口径，不能当作含解析、编码的系统成本。E训练/评分也为缓存小模型口径。旧GBK输出报错发生在结果保存后，已无重评分恢复；无需把调试细节铺进正文。

精确数值如有必要只定点读：
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_external_eval_v1/20261009_163938/metrics.json
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_E_external_supplement_v1/20261010_132706/metrics.json

## 6. 从零到完整稿的分轮计划

建议正文目录：1引言；2相关工作；3任务定义与方法；4实验设置；5结果与分析（开发/消融、冻结外部、E事后补充分开）；6讨论与局限；7结论。摘要最后写。没有目标期刊前不锁定页数，先中文完整论证，避免同时做Word/LaTeX排版。

| 轮次 | 交付 | 限定读取与验收 |
|---|---|---|
| 1 | 逐节提纲＋主张/证据/局限表＋待核实项 | 本交接＋简稿；不写全文、不扩大实验 |
| 2 | 任务定义与方法初稿、符号表、流程图草案 | 方法相关代码；公式与代码一致，C/D/E关系清楚 |
| 3 | 实验设置与结果初稿 | 对应实验记录逐份读取；主/补充结果分开，分母和单位明确 |
| 4 | 最小文献证据表及相关工作 | 核实ColPali、Snappy、RegionRAG、MMDocIR、SciEGQA及少量直接相关工作；逐条记录题名、作者、年份、发表状态、URL/DOI及支撑论点。未核实标待查，不编引用；不启动系统综述 |
| 5 | 讨论、引言、结论、摘要，合并初稿 | 依据前几轮；贡献不超过证据，假设不伪装成实验结论 |
| 6 | 一次集中审阅、导师反馈、定向修订 | 核对公式、表格、引用、方法比较边界；不反复邀请模型给接收概率 |

图表优先：一张方法流程图；一张数据角色表；一张方法差异表；开发/消融表；冻结外部主表；E补充表。案例图待选用已保存预测，预先定成功/失败/面积与E对照的选择原则，不只挑有利例子，不重新运行模型。写作不要求先做新的实验。

建议新建写作产物（以下目前均为计划路径，不代表已存在）：
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/outline-and-claims.md
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/manuscript.md
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/references-evidence.md
- @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/writing-status.md

每轮结束用不超过15行更新writing-status：已完成章节、精确产物、采用的证据、未决项、唯一下一步。下一窗口先读本交接与状态，再读当次章节；不复制整个聊天。正文采用中文学术表达，解释性小白讲解留在聊天；保留英文术语、公式、文献题名。原实验文件只读，修改仅限写作产物。不自动提交、推送、投稿或发消息。

## 7. 模型分流建议（工作建议，不是质量保证）

日常结构化写作与按记录写章节：GPT-6.1 Sol / medium；方法公式或统计解释较难时high。已有文本的格式整理可用GPT-6 Luna / low或medium，数值不交给它凭记忆修订。完整初稿后的单次论证审阅：GPT-6 Astra / high。无需每轮都用Astra或xhigh/max；没有这些型号时按实际可选列表调整，不虚构Cursor价格或权限。

2026-10-12已读取官方模型与推理说明：https://developers.openai.com/api/docs/models ，https://developers.openai.com/api/docs/guides/reasoning 。官方将Sol定位为较低成本的复杂任务选择；推理强度升高通常增加思考预算，不能代替数据和文献核验。客户端账单取决于所用平台，API标价不能直接当作Cursor实际费用。

## 8. 新窗口第一轮提示词

请使用research-writing-skill，协助撰写中文小论文。本轮只完成逐节提纲、主张—证据—局限表和待核实清单，不写完整正文，不训练、调参、下载数据或重新评分。

先只读取：
@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/route-v2-writing-handoff.md
@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/route-v2-paper-decision-brief.md

按交接中的当前任务边界与结果写作：原冻结实验与E事后补充分开，保留面积与不利结果，不宣称P′优于E、可靠超过面积或保持页面召回。目标期刊与模板尚未确定，先通用中文Markdown。材料缺项标“待核实”，不扫描仓库、不读取全部历史记录。

输出：
@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/outline-and-claims.md
@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/writing-status.md

只创建或更新写作文件，保留实验原件。最终简述本轮产物、最多三个关键缺项和下一轮唯一任务。
