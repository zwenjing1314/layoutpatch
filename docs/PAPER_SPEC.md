# 小论文执行规范：布局约束的文档侧 Patch 融合方法（PAPER_SPEC）

> Status: stable | Scope: 小论文方法、实验、评测、实现清单 | SSOT: 是
> 迁移来源：旧仓库 `mmdoc-evidence-rag/docs/SMALL_PAPER_DEV_SPEC.md` 全文迁移；包名 `mmdocrag`→`layoutpatch`、
> 大论文规范引用 `docs/THESIS_RESEARCH_ROUTE_DRAFT.md`→`docs/THESIS_SPEC.md` 已替换。
> 分工：`docs/THESIS_SPEC.md` 回答“为什么做、做到哪算完、什么不许做”；本文档回答“具体怎么做、做到什么程度、用什么证明”。
> 本文不写最终论文结论，所有“创新成立”判断以 Phase 1B/1C 数据和第 11 节 Gate 为准。
>
> 文献基准：8 篇原文核对结论见 `docs/THESIS_SPEC.md` 第 4 节对照表。旧仓库 `docs/literature/小论文创新点调研.md`
> 只作防御草稿，不作查重结论（该笔记按 `docs/MIGRATION_BATCHES.md` 批次 6 才迁入，本仓库暂无）。
> 旧仓库 `docs/literature/12_Bag-of-patches阅读笔记.md` 为空文件，必须补实后才能在 related work 中引用 Beyond。



## 0. 阅读指引与文档关系

```text
docs/THESIS_SPEC.md   大论文规范：目标、主线、文献地图、RQ 操作定义、Gate、评测规范、表述边界
本文档                 小论文执行：创新点 wording、网络结构、模块技术细节、数据、实验步骤、实现清单
docs/literature/      逐篇阅读笔记（十段模板，批次 6 迁入前暂缺）
Documents/论文第三阶段阅读/  8 篇原文 PDF（唯一事实来源，旧仓库留档）
```

凡两处都出现的信息，以本文为准做事、以大论文规范为准定边界，矛盾时先停工对齐。

## 1. 研究背景与问题



### 1.1 一句话问题

> ColPali 的视觉 patch 表示能找到相关页面，但能否在**不裁剪页面、不重复视觉编码、保持 MaxSim 接口**的条件下，利用 OCR/Layout 结构改善**页面内证据区域定位**？



### 1.2 三个正式研究问题（2026-09-18 修订：与 MMDocIR 官方口径对齐）

- **RQ1（缺口是否存在）：** 页面命中是否等于证据命中？输出 A/B/C/D 四类统计 + 官方面积召回三层分解（页面召回 / 候选覆盖上限 Oracle Area Recall / 实际排序 Area Recall）。主口径其中 A/B/C/D（单框 IoU≥0.5）降级为严格辅助诊断，不再作为唯一 Gate；为官方 `recall_layout`（交集面积 / gold 面积，可跨框累加，不要求同框）。
- **RQ2（规则能走多远）：** 固定 OCR/Layout 框聚合 vs patch 显著性动态分组，各解决多少？Snappy 式传播是上限探针。统一用官方 Layout Area Recall@1/5/10 报告，IoU [Hit@0.5](mailto:Hit@0.5) 与 Text 双轨并列为辅助。
- **RQ3（学习是否值得）：** 若规则仍有稳定缺口，可学习的文档侧 patch 融合 / 候选重排能否同时做到：页级不掉、区域涨（官方口径）、成本可控？

三指标必须同报（页级 + 区域官方口径 + 效率），只涨一处不算成。IoU 口径结果必须与官方口径并列声明，不许单报 IoU 否定方法。

### 1.3 硬约束（实现时不许违反）

```text
C1. 不裁剪区域子图，不重复运行视觉编码器（0 次额外视觉编码）。
C2. 保持 late-interaction / MaxSim 检索接口，patch 数量不变（仍为 N=1024）。
C3. 文档侧 query-independent：P_fused 离线算好，所有 query 共用，在线只编码 query。
```



### 1.4 已知的代价（Discussion 必须主动承认）

1. 不能随 query 动态改变文档表示（Argus 的 D(q) 能，我们不能）。
2. 一个 patch 压住多个主题/框时，统一注入可能互相污染，甚至拉低页级。
3. OCR 错误会通过交叉注意力污染视觉表示，必须有门控保底和噪声消融。



### 1.5 与 MMDocIR 官方口径对齐声明（2026-09-18 新增，SSOT）

1. 官方评测（`metric_eval.py: recall_layout`）为主口径：`Area(预测∩gold)/Area(gold)`，可跨框累加，不要求同框、不要求 IoU≥0.5。我们的单框 IoU≥0.5 为严格辅助诊断，两者必须并列报告。
2. 官方原文已解释 gold 与 MinerU candidate 允许不精确匹配（gold 含 MinerU + 人工补框；评测时只给 MinerU 预测框）。本地 115 unmapped = 精确 bbox 查户口失败，属预期现象（Issue #3 复现 0/115），不是数据全坏。
3. 官方检索范围为文档内（`search.py` 按 `page_indices/layout_indices` 切片打分），与本仓 `search_scope=document` 一致；`layout_topk` 在文档内 layout 切片上取，不强制先截 Top-K 页。级联（先页后面区）为论文概念，代码实现为文档内分别打分。
4. MMDocIR 原文未来工作建议文本+视觉联合训练/微调（joint training or fine-tuning）。本方法 C1–C3 是该建议的低成本子集（冻视觉主干、只学文档侧融合）；输入层拼接 OCR（image_hybrid 弱于 pure image）是已知坑，我们用门控残差避开，不在输入层拼接。



## 2. 创新点章节（写作规范，不是定稿）



### 2.1 现在允许写的表述（Gate 通过前）

> 本文设计并实现一种布局约束的稀疏文档侧 patch 融合方法，在不裁剪页面和重复视觉编码的条件下，利用 OCR/Layout 区域信息学习增强的视觉 patch 表示，并在页面检索和证据区域定位任务上进行系统评估。



### 2.2 现在不许写的表述

- “首次”“首个”“完全没有工作做过”“填补空白”“坚不可摧”“高度创新”。
- 把 Gate、残差、zero-init、IoU 映射、坐标编码、统一评测、不重复编码**单独列为创新点**。它们是设计细节或工程约束。
- 把 Phase 1C 的无训练基线（Snappy 式传播、固定聚合、动态分组）说成“复现 Snappy/RegionRAG”。只能叫“受其启发的诊断基线”，除非完整复现其训练。



### 2.3 候选贡献清单（每条都要有证据才能进论文）


| 编号   | 候选贡献                                                                                              | 成立证据                                                                                       | 若证据不足则降级为           |
| ---- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------- |
| C-a  | 问题证据：量化“页面命中但区域未命中”在 MMDocIR 上的规模与结构                                                              | Phase 1B 的官方三层分解（页面召回 / Oracle 覆盖 / 实际排序）+ A/B/C/D 严格辅助 + 按类型/面积/OCR 密度分层 + 10 成功/10 失败可视化 | 引言动机段，不进贡献列表        |
| C-b  | 方法：在 C1–C3 约束下的稀疏局部融合前向结构（W + TopK + 局部交叉注意力 + 门控残差，patch 数不变）                                    | 第 5 节结构实现 + 前向公式 + 离线/在线拆分证明（0 次额外视觉编码）                                                    | 方法描述，不称创新           |
| C-b2 | 轻量候选重排头（2026-09-18 新增备选路径）：冻结 ColPali，只学框级 reranker（patch 分 + 框先验 + 文本相似度），在 Oracle 覆盖高但排序低的子集上验证 | Phase 2-R（重排分支）dev 提升 + 页级不掉                                                               | 若 dev 不涨则删除本条       |
| C-c  | 效果：冻结主干下，页级保持 + 区域提升（官方口径） + 成本可控，三指标同报                                                           | Phase 2/2-R dev 稳定提升 + 最终 test + 与 Snappy/固定聚合/ColMate 对照的对照表                              | 若 dev 不涨则删除本条，转失败分析 |
| C-d  | 机理：消融证明每个组件解决哪个观察到的问题（坐标、类型、soft bias、Gate、蒸馏、K）                                                  | 第 9 节消融矩阵，每行对应一个 1B/1C 观察                                                                  | 只保留涨/跌显著的行，其余放附录    |
| C-e  | 鲁棒性：OCR 噪声下 Gate 自动关小、保底退回原 ColPali 性能                                                            | 噪声扰动曲线（坐标打乱/词替换比例 vs 页级/区域）                                                                | 若 Gate 关不小，如实报负结果   |




### 2.3b 小论文投稿底线（2026-09-24 新增，SSOT）

```text
可投稿 = C-a（动机）+ C-b/C-b2（可学习模块二选一，2-R 先行）+ C-c（三指标同报）
        + C-d（至少一组显著消融）+ C-e（噪声结论正负皆可但必做）+ 第 2.4 节六项全勾。
B1（效率对比表）/ B2（失败分类学）只是大论文内的一节诊断附录与 Discussion 素材，
绝不单独作为小论文投稿；若 2-R 与全融合 dev 皆不涨，小论文判方法失败，
必须重定方法或换路线，不许拿 B1/B2 顶替投稿。
```

### 2.4 创新成立六条检查项（投稿前逐条勾）

```text
[ ] 有可训练参数（不是纯规则）；
[ ] 有独立训练数据（不用 evaluation gold 当训练监督）；
[ ] 非测试集调参（映射规则、K、阈值、loss 权重全部 dev 冻结）；
[ ] 有明确对照（Snappy 式、固定聚合、动态分组、ColMate 位置差异，必要时 ColParse/LFRAG 成本对照）；
[ ] 三指标同报（页级 + 区域 + 效率）；
[ ] 证明不是“加 OCR 就有效”（无 OCR / 无坐标 / 无类型 / 无 Gate 消融至少一组显著）。
```



### 2.5 与 8 篇论文的一句话区分（related work 直接用）

- Snappy：同用 overlap，但它推理期分分数、不改表征；我们离线改表征。它是 1C 最强基线。
- Beyond：自顶向下 global token + 文本监督；我们自底向上坐标级局部融合 + 页内区域评估。
- ColMate：空间只在预训练 loss 的 Bj pooling；我们是前向显式融合层。
- RegionRAG：在线 query 条件 saliency + BFS 组图像 crop；我们离线 query 无关融合，存一份 P_fused。
- LFRAG/ColParse：ColParse k+1 次视觉编码（k 子图 + 1 整页，§3.2.2/Algorithm 1）、LFRAG n+2 次（n 块 + 全局页 + 屏蔽页 Bn+1，§3.2），换布局/存储；我们 0 次额外编码换定位。（出处页码：LFRAG 表1 p.4/表3 p.7/§4.2 p.8，ColParse 表1 p.7/表8 p.26/图6 p.7/§4.2.3-4 p.7-8，旧仓 `Documents/论文第三阶段阅读/` 两 PDF；引用值须标原文硬件 A100/H200，不许与 3080Ti 实测混比；两原文均未单列索引 GB 与检索延迟，B1 该格维持缺）
- Argus：在线 query 条件 D(q) + MoE；我们离线 P_fused。部署 trade-off，Argus 列未来工作。
- MM-Matryoshka/ColChunk/SAP：压缩正交可组合，P_fused 可作其输入。



## 3. 总体网络架构



### 3.1 数据流总览

```text
                        离线建库（与 query 无关）
┌──────────┐   ┌──────────────┐   ┌─────────────────┐   ┌──────────────────┐   ┌───────────┐
│ 页面图像 │──▶│ ColPali 冻结 │──▶│ P ∈ R^{N×D}     │──▶│ 稀疏布局融合模块 │──▶│ P' 存索引 │
│ d        │   │ 视觉编码器   │   │ N=1024, D=128   │   │ (第5节)          │   │ P_fused   │
└──────────┘   └──────────────┘   └─────────────────┘   └──────────────────┘   └───────────┘
                                              ▲                    ▲
┌──────────┐   ┌──────────────┐                │                    │
│ OCR文本  │──▶│ 布局节点编码 │──▶│ T ∈ R^{M×D}     │──────────────────┘
│ +BBox    │   │ (第5.2节)   │   │ M=页内区域数    │
│ +类型    │   └──────────────┘   └─────────────────┘
└──────────┘          │
                      │  W ∈ R^{N×M}（第5.3节，离线算好）
                      ▼
              ┌──────────────┐
              │ 空间对应矩阵 │──▶ 融合模块的 TopK 掩码 + 注意力偏置
              └──────────────┘

                        在线检索（每 query 一次）
┌──────────┐   ┌──────────────┐   ┌──────────────────────────────┐
│ query文本│──▶│ ColPali 文本 │──▶│ MaxSim(Q, P') 页级打分        │──▶ Top-K 页
│ q        │   │ 编码器 Q     │   │ + 页内区域分（第5.6节）        │──▶ Top-R 框
└──────────┘   └──────────────┘   └──────────────────────────────┘
```

关键性质：patch 数 N 不变，网格不打碎；视觉编码器只跑 1 次/页；在线新增成本只有一次 query 编码 + MaxSim，与原 ColPali 同阶。

接口边界（不许违反）：`P_fused` 只用于检索排序与区域打分，**不作为任何生成模型的输入**。大论文生成阶段的输入永远是原始页面图像 + 框坐标（crop 或视觉提示），与本模块解耦。

### 3.2 张量形状约定（实现时统一）

```text
P      : [N, D]，N=1024（32×32），D=128，L2 归一化，冻结主干输出。
T      : [M, D]，M 为本页区域数（动态，batch 需 padding + mask）。
W      : [N, M]，非负，行可归一化；W=0 的行记为空 patch（第 5.5 节兜底）。
N(i)   : patch i 的邻域，下标集，|N(i)|=K（K dev 冻结，如 4/8 对比）。
delta  : [N, D]，局部增量。
gate   : [N, 1]，sigmoid 输出，zero-init 使初值≈0。
P'     : [N, D]，P' = P + gate * residual(delta)，L2 重归一化后入库。
Q      : [Lq, D]，query token 向量，L2 归一化。
S      : [Lq, N]，S[i,j] = Q_i · P'_j。
```

所有点积前必须 L2 归一化；凡涉及 M 动态长度处必须有 mask，禁止 padding 位置参与 softmax/TopK/归一化分母。

### 3.3 与基线的位置关系图（防“堆模块”质疑）

```text
Snappy      : P 不变；S 不变；只在 S→框分加 IoU 加权。无参数。
固定聚合    : P 不变；框分 = 框内 patch 池化（mean/max/IoU）。无参数。
动态分组    : P 不变；由 S 的显著 patch 在线组框。无参数（阈值除外）。
我们（P2）  : P→P' 可学习；S 用 P' 重算；框分复用同一套聚合，保证“涨分来自表征”。
```

Phase 1C 必须先跑前三行，Phase 2 的涨分才有归因意义。

## 4. 数据说明



### 4.1 主数据集 MMDocIR evaluation（官方双任务主线）

```text
文档 313（平均 65.1 页，10 领域）；query 1658；页级标签 2107；布局标签 2638。
官方任务：page-level retrieval + layout-level retrieval。layout gold 同时含 MinerU 输出与人工补框，candidate 来自 MinerU layouts.parquet；gold 与 candidate 不要求精确 bbox 一致。
主区域指标：官方 Area Recall（metric_eval.py: recall_layout，Top-K candidate 与 gold 的交集面积 / gold 面积，可跨 candidate 累加）；严格 IoU Hit@0.5 仅辅助诊断。
本地审计：115/2638 gold bbox 无精确 candidate（Issue #3 复现，0/115），但不自动视为不可用；详见 `experiments/audit/`。
config：configs/datasets/mmdocir.yaml（role: main_retrieval）。
```



### 4.2 训练候选 MMDocIR train（Phase 2 前必须先审）

```text
文档 6878（平均 32.6 页）；query 73k+；仅部分子集有布局级标签。
使用前必须书面回答：标签构造规则是什么？硬负例怎么采的？与 evaluation 有无泄漏？
```



### 4.3 页级泛化补充 ViDoRe V2（可选）

只做页级 nDCG@5/MAP@5，不做区域评测。ViDoRe V3 不做区域评测（Argus 报的 V3 仍是页级）。

### 4.4 数据划分铁律

```text
1. evaluation gold 只用于最终评测，不许同时当训练监督和测试。
2. overlap 定义、K、阈值、loss 权重全部独立 dev 冻结，test 只跑一次冻结配置。
3. 跨页证据单独标注，不混入单页区域分母。
4. 公平比较：同 query 集、同页面集、同划分、同评测脚本、同 Top-K。
```

dev/test 具体划分文件与 query id 列表在执行手册第 7 节登记，本文只定规则。

## 5. 方法模块与技术细节



### 5.1 输入准备

- `P`：ColPali 视觉编码器输出，冻结。`vidore/colpali`，448×448 输入。
- OCR 文本：区域级字符串，空文本区域保留但标记（表、图可能无文本，靠类型+坐标参与）。
- BBox：原图绝对像素 `(x1,y1,x2,y2)`，必须先做第 6 节坐标审计再用。
- 类型：文本/标题/表格/图像/公式等，若 MinerU 不提供则先用“文本/非文本”二分类占位，不许编造细粒度类型。



### 5.2 布局节点编码器 TextLayoutEncoder

```text
t_j = Proj( [ TextEmb(ocr_j) ; CoordEmb(bbox_j) ; TypeEmb(type_j) ] )
```

- TextEmb：第一版用轻量文本投影（frozen 小 embedding + mean pool + Linear），不引入 LayoutLM/UDOP 大模型，控制显存与变量。OCR 特征必须过投影层，禁止因维度相同直接相加。
- CoordEmb：归一化坐标 `[x1/W, y1/H, x2/W, y2/H, w/W, h/H]` + 正弦 2D 位置编码（LayoutLMv3 式）。消融必须含“无坐标”一组。
- TypeEmb：可学习 embedding；类型缺失时用 UNK，不许删除该区域（删区域会改变 W 分母）。
- 输出统一投影到 D=128，与 P 同空间，L2 归一化后再参与注意力。



### 5.3 Patch–Region 空间对应矩阵 W（数学定义）

设 patch i 的像素区域为 Pi，布局区域 j 的像素区域为 Rj（两者已通过第 6 节审计映射到同一坐标系）。候选三种，dev 定一种，test 不许换：

```text
a) W_ij^(cover) = Area(Pi ∩ Rj) / Area(Pi)        # patch 被框占多少（定位敏感）
b) W_ij^(fill)  = Area(Pi ∩ Rj) / Area(Rj)        # 框被 patch 覆盖多少（大框友好）
c) W_ij^(iou)   = Area(Pi ∩ Rj) / Area(Pi ∪ Rj)   # 对称版本（小框数值过小，需注意阈值）
```

实现要求（全部为硬性规定，禁止临场发挥）：

```text
1. 先做第 6 节坐标审计（resize/padding/网格对齐），再算 W。
2. W 离线算好存 artifacts，禁止在线重复算。
3. 行归一化只在非空行做：W_ij = W_ij / Σ_k W_ik；分母为 0 的行记为空 patch（全 0），走第 5.5 节兜底。
4. 多框覆盖同一 patch 时按行归一化分摊权重，不得重复送分。
5. 注意力偏置用 spatial_bias(W_ij) = log(W_ij + eps)；eps 与截断阈值 dev 记录。
6. tie-break：TopK 比较时按下标稳定排序；跨界框、越界框按第 6 节审计规则裁剪后计面积。
```



### 5.4 稀疏局部融合（核心前向，数学定义）

```text
N(i) = TopK_j W_ij ∪ 半径内邻域（K dev 冻结，如 4/8 对比；邻域半径与 TopK 二选一或组合，dev 定）
e_ij = (p_i · t_j)/sqrt(D) + spatial_bias(W_ij)      # spatial_bias = log(W_ij+eps)
a_ij = softmax_{j∈N(i)} (e_ij)                        # softmax 前将非 N(i) 与 padding 位置置 -inf
delta_i = Σ_{j∈N(i)} a_ij * (t_j W_V)
p_i' = p_i + gate_i * MLP(LN(delta_i))                # residual + 零初始化
P' = L2norm(P')
```

- 稀疏原因：防 O(N²) 与过平滑，强制局部吸收，边界 patch 允许 soft 跨区（不用硬 mask）。
- `MLP` 结构固定为 `Linear(D→2D) → GELU → Linear(2D→D) → LayerNorm`，末层 `Linear(2D→D)` 权重与 bias 全零初始化，保证训练起点 `P'≈P`。
- softmax 的 mask 语义：非 N(i) 邻居与 padding 区域在 softmax 前置 -inf，禁止事后置零（事后置零会破坏分母）。
- TopK 实现必须可复现：tie 时按下标稳定排序；K 大于有效邻居数时按实际数，不补无效位。



### 5.5 门控、零初始化与空区域兜底

```text
gate_i = sigmoid( Linear([p_i ; delta_i ; coverage_i]) + b0 )
# coverage_i = Σ_j W_ij（patch 被布局覆盖程度），让留白 patch 自动关小门。
# b0 初始化为负数（如 -3），使初值 gate≈0.05，起点退化为原 ColPali。
```

- 空 patch（W 全 0 行）：跳过注意力，`p_i'=p_i`，不参与任何 softmax 分母；或路由到可学习背景 token（二选一，dev 定，全文统一）。
- NaN 防护：注意力分母加 eps；W 全 0 行禁止进 softmax；梯度裁剪阈值记录。
- Gate 是稳定性设计，不单列创新；但“OCR 噪声下 Gate 关小、保底退回原性能”是可以写的实验结论（第 9.3 节）。



### 5.6 评分：页级与区域级（2026-09-18 修订：官方口径为主）

```text
S[i,j] = Q_i · P'_j
页级分  s_page(q,d) = Σ_i max_j S[i,j]                     # 标准 MaxSim
patch 分 s_patch(j)  = max_i S[i,j]                        # 空间热图（内部探针用）
```

区域主指标采用 MMDocIR 官方定义（`MMDocIR/metric_eval.py: recall_layout`），对
Top-K candidate layout 逐个与 gold 求交集面积并累加：

```text
AreaRecall@K(q) = Σ_{c∈TopK} Σ_{g∈Gold} Area(c∩g) / Σ_g Area(g)   # 同页才计，跨页不计
```

约束：candidate 只能来自官方 `layouts.parquet`；不要求 candidate 与 gold
精确相等；不要求单框 IoU≥0.5；必须保留 page_id 过滤。官方实现允许重叠
candidate 对同一 gold 重复累加，主复现严格跟随官方代码，另报
union-clipped Area Recall 作重叠敏感性分析，两者不许混称。
Snappy 式 `rel=ΣIoU·s/ΣIoU`（max/mean/IoU 三聚合）降级为内部排序探针，不再是
区域主指标。BBox 缩放仍用 Snappy 公式 `B'(r)=(x1*I/W, y1*I/H, x2*I/W, y2*I/H)`，
I=448（仅探针内部用；官方 Area Recall 在原图坐标系直接算交集）。

### 5.7 损失函数（Phase 2）

```text
L = λ_page * L_page + λ_region * L_region + λ_distill * L_distill
```

- `L_page`：页级 InfoNCE（in-batch 负例），保持正确页排序。λ_page 优先保证页级不掉。
- `L_region`：区域排序回归/对比。candidate 软标签 `y(c)=Area(c∩G)/Area(G)`（与官方 Area Recall 对齐；大 gold 被多小框覆盖时各自按覆盖分给分，不判无正样本）。正样本来自独立训练数据的框标注，禁止用 evaluation gold。另设轻量分支 Phase 2-R：冻结 P，只学框级 reranker 头，loss 为 listwise/pointwise 回归 Area 覆盖分。
- `L_distill`：约束 P' 不破坏原排序，如对原 ColPali 分数分布的 KL，或正负 margin 保持。权重 dev 定。
- 三个 λ 全部 dev 网格记录，test 冻结。先只练布局编码器+注意力+投影+门控（主干冻结）；LoRA 动主干是最后手段，需先过显存评估（3080Ti 12GB，batch 1/2/4）。



### 5.8 效率承诺（实现时就得记）

```text
离线/页：视觉编码 1 次 + W 计算 + 一次融合前向 → 存 P'（1024×128）。
在线/query：query 编码 1 次 + MaxSim（与原 ColPali 同阶）。
对比位：LFRAG/ColParse 需 k+1 次视觉编码；Argus 在线路由融合。效率表（第 9.4 节）必须同表列出向量数/索引/离线/在线/显存。
```



## 6. 坐标审计（Phase 1 前置硬 Gate，不过不许往下走）

PaliGemma 默认 448×448、32×32 网格、s=14；OCR 框是原图绝对像素。对不上则 W 全错且静默失败。

审计分两步：机器门限（agent 自动算）→ 人工抽查（只看叠图做判断）。

```text
机器门限（自动，全部写入 audit.json）：
1. 确认渲染分辨率 (W,H)、resize/padding 策略、patch 光栅顺序（左→右、上→下）。
2. 用 Snappy 公式实现 patch_bbox(k) 与 B'(r)，单元测试覆盖：整页框、四角 patch、跨界框、越界框裁剪。
3. 全量计算并记录：越界框比例、缩放后面积误差分布、W 全零 patch 比例、页级 OCR 框覆盖率。
   门限：越界率 < 1%、覆盖率均值在合理区间且无页级为 0 的异常页（阈值在首次全量扫描后冻结写入本节）。
人工抽查（人做，材料由 agent 准备）：
4. agent 自动生成 ≥20 页叠图（patch 网格 + OCR 框，优先抽表格页、双栏页、大图页各 ≥5 张），
   人只回答"表格线/栏边界是否对齐"一个问题。
5. 任何一页不通过 → 停工修数据链，不许"先训起来再说"。
输出：audit.json（W,H,I,G,s、padding 规则、越界处理、机器门限数值）+ 叠图目录 + 通过/不通过结论 + 确认人。
```



## 7. 实验部分



### 7.1 Phase 0：环境与协议冻结

- 单 uv 环境 + 单 `.venv`；Python/PyTorch/CUDA/ColPali 版本锁定并记录。
- 数据根路径：本仓库统一用 `LAYOUTPATCH_DATA_ROOT`（见 `docs/01-quickstart.md`；旧仓库名 `MMDOCIR_EVALUATION_ROOT` / `MMDOC_RAG_DATA_ROOT` 已映射到本变量）。
- 现有可用 config：`mmdocir__phase1a__bm25-page.yaml`（可用）；`mmdocir__phase1a__colpali-page-full.yaml` 头部自述为新命名草稿、tasks.ps1 暂未使用，可用的是旧名 `mmdocir_colpali.yaml`（image/query/score batch=1/2/4，embedding cache 开）。切换命名前必须等价运行验证。
- ViDoRe V1 官方复现（旧仓库 `docs/reproduction/colpali_vidore_v1_reproduction_20260830.md`，按批次 3 迁入）只证明 `vidore/colpali` 可用，不等于本仓库 Phase 1A 完成。



### 7.2 Phase 1A：页级 baseline

方法：BM25、文本 dense（BGE-M3）、Hybrid、ColPali。目标：可信页级分，后续区域实验的分母。

```text
输入：MMDocIR evaluation 全量（query 1658 对数）。
输出：runs/retrieval/<exp>/（config.json、run_info.json、metrics.json、summary.md、predictions.parquet）。
指标：Recall@1/5/10、MRR、nDCG@5/10。
登记条件：query 数=1658、commit、耗时、输出目录、指标文件五项齐全，否则不算完成。
```



### 7.3 Phase 1B：页面–区域缺口诊断（2026-09-18 修订：三层分解为主）

```text
输入：冻结 ColPali 页级 Top-K + OCR/Layout 框 + gold 页/框。
输出（三层分解，主口径官方 Area Recall）：
  L1 页面召回：Page Recall@1/5/10（文档内范围，与官方 search.py 一致）。
  L2 候选覆盖上限：Oracle Area Recall（正确页上全部 candidate 对 gold 的最大面积覆盖；另报 oracle 单框 IoU≥0.5 作为严格对照）。
  L3 实际排序效果：Official Layout Area Recall@1/5/10（模型 Top-K 下的面积召回）。
辅助：A/B/C/D（单框 IoU≥0.5）+ 按类型/面积/OCR 密度分层 + 10 成功/10 失败可视化 + 失败归因（候选覆盖不足 vs 排序不足 vs 页未中）。
判定：L2 高但 L3 低 → 排序问题，值得做融合/重排；L2 本身低 → 候选生成问题，先做候选合并/补框或换口径说明，不直接进 Phase 2。
历史注记：EXP-002/005 的 B=45（页中但无单框 IoU≥0.5）与 0/45 消解率是严格 IoU 口径结论，已降级为辅助诊断，不作为 Phase 2 唯一 Gate。
```



### 7.4 Phase 1C：无训练基线（2026-09-18 修订：官方口径重算）

1. 原始 ColPali 页检索（文档内范围）；
2. 候选 layout 打分基线：文本相似度 / 面积先验 / Snappy 式传播（含第 6 节审计，max/mean/IoU 三聚合对比，P25/P50/P75 阈值敏感性记录；此时 Snappy 为排序探针，非主指标）；
3. 固定 IoU/coverage 区域聚合；
4. patch 显著性动态分组（阈值 η、邻域半径 dev 记录；不许叫 RegionRAG 复现）。

```text
报告（与 docs/THESIS_SPEC.md 第 11.2 节一致）：
  主表：各基线的 Official Layout Area Recall@1/5/10 + Page Recall@1/5。
  辅助：单框 IoU Hit@0.5、Text 双轨。
判定：
  进 Phase 2/2-R：Oracle Area Recall 高、规则排序 Area Recall 仍有稳定缺口（dev/test 趋势一致），且缺口可归因到排序而非候选全缺；
  转收缩：Oracle 本身低（候选生成瓶颈）或规则已接近 Oracle → 按 docs/THESIS_SPEC.md 第 11.3 节有序收缩（B1 效率 / B2 失败分类学 / B3 需另立项）。
  历史注记：EXP-006 的 0.3187 Top-1 与 0/45 是 IoU 口径数，不可与官方 Area Recall 直接比较；须重算官方口径后再判。
  agent 只准备决策材料（L1/L2/L3 三层表、Oracle–实际 gap、分布直方图），选择由学生与导师共同确认。
```



### 7.5 Phase 2：训练融合模块 + Phase 2-R：轻量重排分支（2026-09-18 修订）

```text
Phase 2（全融合 P→P'）：
顺序：冻主干练小模块 → dev 确认稳定 →（必要时）LoRA → 冻结全部（模型+超参+映射规则+K+阈值+λ）→ test 跑一次。
数据：独立训练集（MMDocIR train 需先审标签规则与泄漏）；evaluation gold 永不进训练。
区域监督：candidate 软标签 y(c)=Area(c∩G)/Area(G)，与官方 Area Recall 对齐。
记录：loss 曲线、梯度范数、Gate 均值（应从≈0 渐变）、页级/区域 dev 曲线、显存峰值、seed。

Phase 2-R（低风险先行分支，推荐先跑）：
冻结 P 不动，只学框级 reranker 头（输入 patch 分 + 框面积/覆盖先验 + 文本相似度），loss 回归 Area 覆盖分或 listwise 排序。
适用：Oracle Area Recall 高但规则排序低的子集；2 周可出数；显存远低于全融合。
若 2-R dev 稳定提升且页级不掉，再决定是否做全融合 Phase 2；若 2-R 亦不涨，转 B2 诊断型论文。
```



### 7.6 最终 test 与记录格式

test 只在冻结后跑一次；任何 test 数不得反向选模型。每次运行目录至少：

```text
config.json / run_info.json / metrics.json / summary.md / predictions.parquet（如适用）
+ audit.json（1B/1C）/ hyperparams_frozen.json（Phase 2）/ eval_config.json（含 IoU 阈值、Top-K、分母定义）
```



## 8. 评测指标定义（2026-09-18 修订：官方口径为主，全实验统一）

```text
页级：Recall@1/5/10、MRR、nDCG@5/10。检索范围为文档内（与官方 search.py 一致）；页面命中 = gold 页在 Top-K（K 预先声明）内。
区域（主）：Official Layout Area Recall@1/5/10（metric_eval.py: recall_layout；交集面积/gold 面积，可跨框累加；同页才计）。
区域（辅）：单框 IoU Hit@0.5（阈值预先声明，dev/test 一致；须与官方口径并列，不许单报否定方法）。
      Text Recall / Text F1（辅指标，防 IoU 误杀；定义与防刷分规则见 docs/THESIS_SPEC.md 第 8.3 节，
      tokenization：中文按字、英文按词、统一小写去空格；IoU 未命中但 Text-Recall≥0.8 的
      样本单独成组人工抽查 ≥20 例）。
分解：L1/L2/L3 三层 + A/B/C/D 严格辅助；无框 query 不进区域分母；跨页证据单独列。
公平：同 query 集、同页面集（含文档内范围声明）、同划分、同脚本、同 Top-K 同表对比。
```



## 9. 消融、鲁棒性与效率



### 9.1 消融矩阵（每行对应一个观察，不堆表）

```text
必做：无 OCR / 无坐标 / 无类型 / 无布局偏置（spatial_bias=0）/ hard mask vs soft bias /
      三种 overlap 定义 / 无 Gate（gate=1）/ 无蒸馏 / K={4,8} / 背景 token 有无。
记录：每行页级Δ + 区域Δ + 一句话解释（如“去坐标后小表掉分，说明 W 位置信息有效”）。
```



### 9.2 背景 token 与稳定性

空 patch 两种方案二选一、全文统一；NaN 防护与梯度裁剪阈值记录；随机 seed 至少 2 个报均值/方差（资源不够则 dev 单 seed + test 单 seed 并声明）。

### 9.3 OCR 噪声鲁棒性（必做）

```text
扰动：坐标抖动（±5%/±10%）、词随机替换（10%/20%）、框删除（10%）。
看：页级/区域曲线 + Gate 均值是否自动关小 + 是否保底退回原 ColPali（±1 分内）。
结论两种都可写：Gate 有效是贡献；Gate 无效是诚实的负结果 + 未来工作。
```



### 9.4 效率表（与 LFRAG/ColParse 同表，否则“可控”无意义）

```text
列：方法 / 离线编码次数/页 / 存向量数/页 / 索引大小 / 离线融合时间 / 在线延迟 / 峰值显存 / 页级 / 区域。
行：ColPali / Snappy / 固定聚合 / 动态分组 / 我们 / （引用值）LFRAG k+1 / ColParse k+1 / Argus 在线融合。
硬件注：RTX 3080Ti 12GB，batch 如实写（ColPali 1/2/4），不许拿 H200 的数直接比。
```



## 10. 代码实现清单（按本文档开发缺什么补什么）



### 10.1 现状与缺口（旧仓库视角，新仓库按批次 2–6 重建）

```text
旧仓库已有：src/layoutpatch/{datasets,evaluation,exporting,retrieval}、configs/datasets/mmdocir.yaml、
      Phase 1A 部分 experiment yaml、docs/reproduction 复现记录、ColPali embedding cache（artifacts/）。
本仓库缺（按 MIGRATION_BATCHES 补）：布局节点编码器、W 计算、稀疏融合模块、区域评分、IoU/Text 评测、
      坐标审计脚本、Phase 1B/1C/2 的正式脚本与冻结 config、超参冻结表、可视化工具。
```



### 10.2 新建模块（建议路径，建一个实现一个；包名已改为 layoutpatch）

```text
src/layoutpatch/layout/
  nodes.py          # TextLayoutEncoder：文本投影 + 坐标正弦编码 + 类型嵌入 → T [M,D]
  correspondence.py # W 计算（三种 overlap）+ 行归一化 + 空行标记 + 存 artifacts
src/layoutpatch/retrieval/fusion/
  sparse_fusion.py  # TopK 邻域 + LocalCrossAttention + spatial_bias + 背景 token
  gate.py           # 门控 + zero-init（b0=-3）+ coverage 输入
  fused_index.py    # P' = P + gate*MLP(LN(delta)) + L2norm + 离线入库
  region_scoring.py # s_patch + IoU 加权/max/mean 三聚合 + 页-区归一化融合
src/layoutpatch/evaluation/
  region_metrics.py # Region Recall/MRR/IoU Hit@0.5 + Text Recall/F1 + A/B/C/D + 分层
  audit.py          # 第 6 节坐标审计（机器门限 + 叠图生成）
scripts/
  audit_coords.py   # 跑第 6 节，输出 audit.json + 叠图
  run_phase1b.py    # A/B/C/D + 分层 + 案例导出
  run_phase1c.py    # 三基线 + 阈值敏感性 + Phase 2 决策材料（B 类占比/Snappy 消解率）
  train_fusion.py   # Phase 2（冻主干 → LoRA 可选），输出 hyperparams_frozen.json
tests/
  test_correspondence.py  # patch_bbox/B' 公式、越界、多框归一化、空行
  test_fusion_shapes.py   # [N,D]/[M,D]/mask/padding 不参与 softmax
  test_region_metrics.py  # IoU + Text 指标、无框 query 分母、跨页排除、超大框防刷分
```



### 10.3 Config 与 runs 命名（冻结才有效）

```text
configs/experiments/
  mmdocir__phase1a__bm25-page.yaml            # 已有可用
  mmdocir__phase1a__colpali-page-full.yaml    # 草稿名，tasks.ps1 未接；先用 mmdocir_colpali.yaml 跑
  mmdocir__phase1b__gap-diagnosis.yaml        # 新建：Top-K、IoU 阈值、分层键、案例数
  mmdocir__phase1c__snappy-aggregation.yaml   # 新建：聚合方式、阈值网格、审计文件引用
  mmdocir__phase2__sparse-fusion.yaml         # 新建：K、overlap 定义、λ、LoRA 开关、seed
runs/
  retrieval/mmdocir__phase1a__.../  diagnosis/mmdocir__phase1b__.../
  baseline/mmdocir__phase1c__.../   fusion/mmdocir__phase2__.../
```



### 10.4 硬件与确定性

RTX 3080Ti 12GB：ColPali image/query/score batch 从 1/2/4 起；融合模块 batch 按显存测峰值后冻结记录。
确定性：seed、torch deterministic/cudnn benchmark 开关、tokenizer/渲染版本全部进 run_info.json。

## 11. Gate 与停止条件（2026-09-18 修订：官方口径为准，执行时对照）

```text
1A 数据规模对上（1658）                    → 才做 1B
1B 有 L1/L2/L3 三层 + A/B/C/D 辅助 + 分层 + 案例 → 才做 1C
1C 官方口径基线完成（含三聚合探针 + Oracle gap） → 才训练 Phase 2/2-R
Phase 2/2-R dev 稳定提升（页级不掉 + 官方 Area 涨）→ 才冻结跑 test
```

出现任一条即停：审计不通过（机器门限或人工抽查任一不过）；BBox 系统性错位；无独立训练数据又要用 gold 训练；dev 不涨只涨 test；页级掉且区域不涨；复杂融合不如固定聚合；显存超限；1C 判定不满足进 Phase 2/2-R 条件（按 docs/THESIS_SPEC.md 第 11.2/11.3 节定量判定与有序收缩执行）。
历史注记：旧 IoU 唯一 Gate（B≥10%/Snappy 消解≤50%）已废止，EXP-005/006 的 IoU 数保留为辅助诊断，不再作为 Phase 2 准入判据。

## 12. 实验记录模板与超参冻结表（每次运行必填）

```text
## 实验记录（存 runs/<exp>/summary.md）
- 目的/对应 RQ： / 前置 Gate 是否通过：
- config 文件 + commit + 数据版本 + 划分文件：
- 关键超参（K/overlap/阈值/λ/seed/batch）：
- 输入输出路径：
- 页级 / 区域 / 效率三数：
- 与基线差值（一句话归因）：
- 失败案例 id（≥3）与猜因：
- 下一步（只写一步）：

## 超参冻结表（存 hyperparams_frozen.json，test 前锁定）
{ overlap_def, K, neighbor_rule, empty_patch_policy, background_token,
  aggregation, page_region_norm, thresholds, lambdas, lora_on_off,
  seeds, batches, dev_scores, gate_numeric_thresholds,
  frozen_date, frozen_by }
# gate_numeric_thresholds：11.2 节 10%/50% 的最终数值 + 修正依据（B 类分布直方图路径）
```



## 附录：投稿前核对清单（2026-09-18 修订）

```text
[ ] Beyond 空笔记已补，五问可答；
[ ] 第 2.5 节每句区分能在原文找到公式/页码；
[ ] 坐标审计 audit.json + 叠图通过（机器门限 + 人工确认人签名）；
[ ] 1A=1658 对数；1B 有 L1/L2/L3 三层 + 分层 + 10/10 案例；1C 有官方 Area Recall 主表 + 三聚合探针 + 阈值敏感性；
[ ] 1C 决策材料齐全（Oracle–实际 gap、B 类占比辅助、Snappy 消解率辅助、直方图）且 11.2 定量判定已执行；
[ ] Phase 2/2-R 有独立训练数据证明 + dev 曲线 + Gate 均值记录；
[ ] 六条创新检查项逐条有证据；Gate/残差/zero-init 未单列创新；
[ ] 区域指标含官方 Area Recall 主 + IoU/Text 双轨辅助与防刷分记录；
[ ] 效率表含 k+1 对照行 + 硬件 batch 如实标注；
[ ] OCR 噪声 + 背景 token 有记录；test 只跑一次冻结配置；
[ ] arXiv 重扫日期已记（Snappy/Beyond 若出可学习变体即更新第 2.5 节）。
```

