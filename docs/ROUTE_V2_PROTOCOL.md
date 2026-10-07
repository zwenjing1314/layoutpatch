# 区域监督布局融合：route-v2 协议

> Status: working | Scope: 新路线的数据角色、监督、对照、评测与验证要求 | SSOT: 是（仅 route-v2）
> 2026-10-03 建立草案；2026-10-04 落地数据角色声明（data-roles-v1）、监督规则、评测口径与 smoke 协议。评测指标定义唯一出处是 `docs/PAPER_SPEC.md` 第 8.1 节，本文只引用。
> 旧实验按原配置、原划分及对应 Git 版本复现；不覆盖旧 frozen 文件、数据、权重或 runs。证据见 `experiments/2026-10-03-route-v2-review.md` 与 `experiments/2026-10-04-route-v2-data.md`，进度只记 `docs/handoff.md`。

## 1. 研究目标与借鉴边界

目标限定为**证据区域定位**：给定问题和正确页，从该页的解析候选框里排出证据框；不做答案生成系统。保留 ColPali（`vidore/colpali`）与已有页向量缓存，冻结视觉/问题编码器；本阶段不切换 ColQwen3、不下载新骨干、不全量重编码。保持不裁剪页面、不额外视觉编码、文档表示与 query 无关、MaxSim 接口不变。

ColPali 的 patch 向量经过全图上下文建模，研究动机不是“patch 不懂文字”，而是其页级训练目标没有直接保证页内候选区域的证据排序。

### 1.1 借鉴 RegionRAG 的部分（迁移，不是创新）

| 借鉴项 | 原文出处（PDF 页） | 本项目用法 |
| --- | --- | --- |
| 正/负/忽略 patch 规则 | p4 第 3.3 节 | patch 中心落在任一 gold 框内（含边界）为正；与所有 gold 框零重叠为负；其余边界 patch 忽略，不当负例 |
| 多正例局部对比损失 Eq.3 | p4 | 同式，温度 τ=0.25（附录 B，p10） |
| 区域标注来源思路 | p10–11 附录 C、表 S1 | 原文用 Visual-CoT 约 98k 文档向框；本项目先用 MMDocIR 自带问题框，Visual-CoT 仅备选（2.6 节） |

不照搬的部分：RegionRAG 的 Qwen2.5-VL LoRA 微调、全局逐维 max pooling 的单向量 query、全局对比损失、无标注伪标签、显著图 + BFS 动态区域与生成器。本项目的 patch 分数保留 ColPali 全部有效 query token：`s_j = max_i <q_i, p_j>`（页级 MaxSim 不变）。这是接口适配，不是新方法。

因此，“换监督 + 借 loss”本身只是迁移基线（5 节对照 C）。可声称的新部分只能是**离线、query 无关的布局条件 patch 表示修正 P→P′**，且必须在同骨干、同监督、同候选、同预算下优于对照 C 才成立。

## 2. 数据角色声明（data-roles-v1）

### 2.1 用户授权

2026-10-03/04 用户明确决定：MMDocIR 原官方 evaluation（313 文档、1658 题，含旧 `test_eval`）改作新路线的**有标注训练/开发来源池**，可读取其标签做训练数据准备，不受旧 test 用途限制；旧 `test_eval` 不再作新路线最终测试。此授权只适用于 route-v2；旧实验记录、划分与结论保持原样。

### 2.2 角色与计数

精确名单与哈希：`experiments/route_v2_splits/data-roles-v1/`（`split_proof.json`）。计数见 `experiments/2026-10-04-route-v2-data.md` 第 2 节，不在此复写。

| 角色 | 来源 | 允许 | 禁止 |
| --- | --- | --- | --- |
| `source_train` | 旧 `test_eval` 文档，按身份单元抽约 80% | 构造训练标签、训练参数 | 报告为泛化结果 |
| `source_val` | 旧 `test_eval` 其余文档 | 早停、超参与 checkpoint 选择 | 称为独立测试 |
| `source_dev` | 旧 `dev_eval` 文档（扣除隔离） | 方法间的预注册开发比较 | 称为独立确认集；反复迭代调参 |
| `quarantine` | 外部重叠未决文档、其内部身份单元及 dev 双胞胎 | 无 | 进入任何角色 |
| `external_test` | SciEGQA-Bench（2.5 节） | 冻结后只评一次 | 选模型、阈值、超参 |

### 2.3 划分规则（结果出来前固定）

1. 文档 ID：去掉结尾 `.pdf`，保留内部点号。所有题按原 annotations 物理行顺序编号 `mmdocir_00000…`，隔离前编号。
2. 外部隔离：外部身份复核中决定为 unresolved/confirmed 的本地文档全部隔离；仅被图像筛查命中、经正文复核判为模板误报的不隔离。
3. 身份单元：内部 `confirmed_doc_groups`（两侧各至少 2 个不同匹配页）传递合并为单元；单元在分配中不可拆。隔离沿单元传播。
4. dev 优先：单元同时含旧 dev 与旧 test 文档时，保留 dev 文档，旧 test 成员隔离。
5. 训练/验证：旧 test 剩余单元按首文档 ID 排序，`random.Random(42).shuffle`，按文档数累计到 `floor(0.8×N)` 前的单元进 `source_train`，其余进 `source_val`。不按结果挑样本、不重切。
6. 页级排除：内部页对证据为 confirmed/unknown 且跨角色的页，涉及该页的 unit 不进局部 loss（标记 `page_overlap_excluded`），dev 侧照常评测但单独计数；不因单页模板重叠隔离整篇文档。

### 2.4 曾参与旧探索的披露

整个 MMDocIR evaluation 都在旧路线中出现过：EXP-001 页检索与 Phase 1B/1C 无训练基线用过全部 1658/1390 题；旧 `dev_eval`（现 `source_dev`）还被反复用于 2-R 与融合的方法选择和停止判定。因此 `source_dev` 上的数字只能叫开发结果，不能作最终独立测试，也不能把旧 401 题数字与新口径混成同一实验。

### 2.5 外部测试：SciEGQA-Bench（原 BBox-DocVQA 的人工评测集）

- 身份：arXiv 2511.15090（v1 名 BBox-DocVQA，v2 改名 SciEGQA，2026-03-30）；HF `Yuwh07/SciEGQA-Bench`，固定 revision `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`，仅 `test` 划分；README 指向论文与 `github.com/yuwenhan07/SciEGQA`。
- 规模与来源：80 篇 arXiv 论文（8 个学科各 10 篇），论文表 2 记 1,941 页、1,623 题（SPSR 46.15%/SPMR 34.26%/MPMR 19.59%）；人工标注语义区域框，双人交叉、IoU<0.9 时第三人复核；PDF 以 300dpi 渲染。本地 PDF.tar 解析出 1,823 页，与论文页数不一致，原因未查。
- 官方评测：答案准确率为主，IoU@θ 评框；任务 1 给定证据页预测框（坐标归一化到页面）。本项目只用其“给定正确页的定位”部分。
- 候选框：数据集不提供解析候选；评测前需在其 PDF 上跑与训练侧同版本的解析器，并报告该候选集的 Oracle 上限。这一步属于新工具/新计算，执行前单独征得同意。
- 许可证：数据集卡未声明（HF API `cardData.license=None`），论文本身为 CC BY 4.0，不等于数据许可。状态：**未解决**，仅本地研究评测，不再分发。
- 与 MMDocIR 的重叠：文档 ID、问题近重复、全页文本、图像 pHash 四层筛查 + 正文复核；190 个图像候选中 189 个判为模板误报，1 个 unresolved（`Country_Reports_2021…`，旧 dev），已隔离。结论：在 identity-v1/verification-v1 阈值下未发现确认重叠，**不声称零泄漏**（改写/翻译/预训练暴露无法排除）。
- 已读取的部分：身份筛查程序读取过其问题文本做近重复比较；未读取答案/gold 做任何打分，未用于选模型或阈值。

### 2.6 备选区域监督：Visual-CoT（不下载、不混入）

RegionRAG 用的 98k 文档向框来自 Visual-CoT（arXiv 2403.16999）的 TextVQA 18k、TextCaps 32k、DocVQA 33k、InfographicsVQA 15k。框的来源：原数据集问答 + PaddleOCR 检测文本区域，取与答案对齐的词句区域作框；TextCaps 的问答由 GPT-4 生成。框是答案片段粒度，比 MMDocIR 版面块小很多。代码与数据卡为 Apache-2.0，图像仍受各源数据集条款约束，作者声明仅限研究。只在 MMDocIR 监督规模被证明不足时再提申请。

## 3. 输入与版本隔离

- **页向量 token 布局（2026-10-04 核实）**：缓存 `[1031,128]` 为图像在前：0–1023 行是按行优先排列的 32×32 patch，1024–1030 行是固定提示词 `<bos><bos>Describe the image.\n`。旧代码按“7 prefix 在前”切 `[7:]`，所有 patch 级区域分数错位 7 格。route-v2 只用 `layoutpatch.retrieval.colpali_layout.split_page_embedding`。证据：`artifacts/route_v2_data/coordinate_audit_v1.json`。
- 问题向量：保留 ColPali 原 token 结构（`<bos>`+问题+10 个 `<pad>` 增广 token，全部 attention=1），只丢弃批内补齐产生的全零行，不做池化。
- 缓存复用前核验：模型名、页图路径/大小/mtime 签名、形状。签名不符视为缺失，不静默使用。
- 类型表沿用 `layout/schema.py`（UNK=0、text=1、title=2、table=3、image=4、equation=5）。文本来源实测（gold 页候选 16,718 行）：text 类 14,508 行中 `ocr_text` 非空 0、`text` 非空 14,012；equation 84 行只有 `text`；image 1,488 行 `ocr_text` 757、`vlm_text` 1,480；table 638 行 `ocr_text` 637。旧“只用 `ocr_text`”规则会让正文块全部无文本，所以 D 冻结前必须重定文本来源规则，并写清各字段的产生方式；未重定前 D 不开训。
- 新产物写新目录；`SparseLocalFusion`、旧 nodes/cache/权重不切换、不复用为已验证起点。

## 4. 监督与候选

- unit =（问题，gold 页）。gold 只来自该问题的 `layout_mapping`；候选只来自该页的解析版面行，**训练 gold 从不放进推理候选**。
- 精确重复的 gold 框去重并计数；越界框计数并在画布内裁剪；零面积框无效。gold 与候选的页面尺寸冲突时该 unit 不评测、不训练。
- 无正 patch（框太小，没有 patch 中心落入）的 unit 不进局部 loss，计数报告，不改用最大重叠 patch 代替；仍参与评测。
- 无负 patch（gold 覆盖近整页）的 unit 同样不进局部 loss（对比损失没有负例），仍参与评测。
- route-v2 不使用 `docs/PAPER_SPEC.md` 第 5.7 节的覆盖率软标签 y(c)；监督只来自上面的正/负/忽略 patch 规则。
- MMDocIR 的 gold 框多数就是解析块本身（精确匹配率见审计），在其上的固定候选排序比外部集容易；外部集 gold 为人工语义框，必须单报候选 Oracle，不能把两者混比。

## 5. 对照与比较条件

同题、同骨干、同缓存、同候选、同评测脚本：

- A 面积降序（无训练，强基线，不删）。
- B 冻结骨干 Snappy 式传播：patch 分 `s_j` + IoU 归一化聚合（原文 Eq.10 形式，无百分位过滤；不称原文复现）。
- C 同监督可学习适配对照：`PatchAdapter`，只看 patch 向量，无文本/类型/坐标/W，零初始化时等于 B。
- D 候选新模块（布局条件 P→P′）：**尚未冻结**。起点结构拟用现有 `SparseLocalFusionV2`（每 patch 取空间权重前 4 个区域节点做注意力，pre-LN 残差，末层零初始化，门控输入含原始覆盖质量）；旧融合权重不加载、不作起点。节点向量的文本编码器与维度、文本来源规则（3 节）在冻结时写定。P′ 只替换 0–1023 行，提示词行保持原值。与 C 同 loss、同数据、同调参预算，参数量差异如实报告。
- E（D 冻结时再准备）：P 不变、在同监督下训练的候选框排序头，用来区分“改表示”与“直接学框排序”。
- 随机期望与候选 Oracle 每次同表报告；另报候选数 M≥2 的子集（M=1 时所有方法必然打平）。

固定候选排序与动态生成区域分开报告；候选生成的改善不归因于表示学习。若 P′ 用于页检索，必须实际重算文档内页排序；复制冻结页序不能证明 P′ 保持检索能力。

## 6. 损失与训练（smoke 已固定，正式实验待冻结）

- 局部 loss：1.1 节规则与 τ=0.25；batch 内对 unit 取平均。
- smoke 只训练对照 C，用于验证管线；正式实验的 D 结构、页面保护项（文档内页面分数蒸馏）、学习率与 epoch 在开训前另行冻结，只在 `source_val` 上选择。
- 冻结骨干；只训练轻量模块；原融合权重不作起点。

## 7. smoke 协议（route-v2-smoke-v1）

前置条件全部满足才运行：本协议含本声明；`split_proof.json` 身份就绪且四角色两两无交集、身份单元不跨角色；坐标审计通过；16 题均有页缓存（签名一致）与问题向量缓存。

运行：`source_train` 中局部 loss 可用的题按 seed 42 洗牌取前 16 题，用其全部可用 unit；对照 C，AdamW lr=1e-3，最多 200 步全批，CPU（显存远低于 12GB 预算）；权重写 `artifacts/route_v2_smoke/<timestamp>/`。只检查 loss 下降、梯度有限非零、正负 patch 分差与数值稳定性。不运行 dev/外部测试，不扩大训练，不挑 seed。任一前置不满足即停止并写 `preconditions.json`，不伪造或替换输入。

## 8. 统计与推进

- 主比较、最小有意义差值与页级非劣界限在正式实验开训前冻结；文档聚类 bootstrap 为主，McNemar 为辅；报告全部预定 seed。
- 开发信号出现前不做多 seed 消融；失败如实记录，不删基线、不换主指标。
- 不要求每个 seed 单独 p<0.05；不显著不等于等价，等价性只能用预先冻结的非劣界限判断。
- 旧结果中 IoU 计数口径的不一致（130/136、214/220）只影响旧结论的解读，不改动 route-v2 的口径。

## 9. route-v2-exp1-v1（EXP-014，2026-10-06 训练前冻结）

用户明确授权执行 A/B/C，目标是检验普通区域监督适配器在未参与参数更新的问题上的定位开发效果；不验证 D 创新。唯一数值配置为 `configs/experiments/route_v2_exp1.yaml`（frozen）。已通过只读输入核验，回执路径由该配置绑定。保持 data-roles-v1、regions-v1、现有候选/排序、image-first patch 切片、query token、局部损失和 τ，不重新编码或重新划分。

- 只用 source_train 中 local_loss_ready 且非 page_overlap_excluded 的 unit 更新 C。每 seed 独立初始化 PatchAdapter(hidden=256)，不读取 smoke 权重。seed=0/1/2，各最多30 epoch；AdamW lr=1e-3、weight_decay=0.01、betas=(0.9,0.999)、eps=1e-8，无 scheduler。按排序后的 unit_id 起点，以每 seed 独立且跨 epoch 连续的 Python RNG 洗牌。逐 unit 前后向，每组4 unit按实际数量平均，尾组同样平均；clip max_norm=1.0。
- GPU float32，禁用 TF32，不启用混合精度，确定性算法；12 GiB 显存上限。首次训练前仅在 train/val 检查 C 零残差与 B 分数一致（绝对容差1e-6）。本轮不添加页面保护项或额外损失。
- 每 epoch 在 source_val 全部 eval_ready unit 上计算第8.1节主指标（题内平均再按问题宏平均），包括无正/负patch及页重叠标记的评测样本。初始 best=-∞，仅训练后的 epoch 可入选；严格提高保存独立 checkpoint，平局保留更早者，连续5轮未严格提高早停。每个 seed 均报告，不选择最佳 seed。
- 三个 seed 的 checkpoint 全部确定并写选择回执后，才进行一次统一 source_dev A/B/C 比较。A/B 各计算一次；三seed逐题 C 主指标先平均，再与同题 B 按文档聚类 bootstrap（2000次，seed0），95%区间。seed标准差使用样本标准差（ddof=1）。McNemar 仅对各 seed 的二元 unit 命中与 B 配对，注明忽略同文档相关性，不将跨seed均值当二元数据。
- 推进标准：C−B点估计≥0.01且95%区间下界>0；始终报告 C−A，未超过 A 不能称超过面积强基线。未达标则暂停扩大，不推论所有区域监督/布局融合无效。
- 指标完全沿用 PAPER_SPEC 第8.1节；M≥2按符合条件的 unit 过滤后再做题内/题间平均，单列分母，不替代全集。框大小分位数报告 unit 分布。source_val 的 news_combined 集中分布只披露，不重切。source_dev只称开发结果。
- 本轮只做给定正确页定位，不做页级非劣实验、不声称页面召回保持，故第8节中页级非劣界限要求不适用于此实验。禁止读取/评分外部测试、训练D或自动开第二轮。
- 输入身份/缓存不符、角色泄漏、NaN/Inf、显存超限或实现偏离冻结协议时硬停止，保留失败目录，不自动降级重跑。既有无关ruff问题单独记录。

## 10. EXP-015 D输入与实现准备（2026-10-06；正式运行未启动）

本轮以用户授权完成D训练侧技术验收，不改EXP-014。唯一候选配置`configs/experiments/route_v2_exp2_D.yaml`，状态working；数值与接口已落定，正式冻结前补同规则dev节点缓存及身份回执。本轮仅处理source_train可训练页与source_val可评测页的全部候选，不编码dev节点、不评分dev或外部测试。

- 文本来源：MMDocIR官方数据卡revision `bdcb36ecb3eee73667180ee3fb24fe433f6dd2a4` 的 Miscellaneous Document Files / Layout-related files明确text为正文/公式OCR原文、ocr_text为图/表OCR原文，vlm_text为VLM描述；官方encode.py对非图表取text。正文/标题/公式取text，图/表取ocr_text；strip首尾空白，空/null保留节点并记录缺失，缓存零文本向量但仍过投影层；绝不回退vlm_text。未知类型来源未明则停止（类型表仍保留UNK）。标题沿官方非图表分支，本轮实际候选未出现独立title/UNK。未获得逐节点OCR工具/版本，不声称可复现其原始解析流水线。详细证据与覆盖率见EXP-015准备记录。
- 既有本地BAAI/bge-m3 revision `5617a9f61b028005a4858fdac845db406aefb181`，SentenceTransformer原CLS池化、1024维、L2归一化、float32、max_seq_length=512、batch2，模型冻结。属于既有编码器接口适配，不沿旧5.2节计划另换mean池化。只离线编码候选框文本，不运行视觉编码器。截断和缺失计数报告。
- D由原TextLayoutEncoder(text_dim=1024,num_types=6,coord_width=72)与原SparseLocalFusionV2(top_k=4)组合；文本1024维投影，坐标6维，经72维正弦编码，类型ID沿layout-types-v1；输出节点128维。节点按layout_id升序；mask为boolean[M]。坐标/W按既有裁剪与448映射，W_raw采用cover，W_attn只对非空行归一化，cover_mass为原始行和；均离线缓存。此实现选择不经dev调参。
- D只接收页面patch和页面节点，不接收query/gold；gold仅构造既有损失mask。只训练节点编码器（文本/坐标投影、类型嵌入与融合投影）和融合V2；冻结BGE-M3与ColPali。提示行1024–1030逐值保留；空patch原值保留；padding在softmax前屏蔽。正式训练每seed独立零残差初始化，禁止载入C、旧融合或smoke权重。
- D技术smoke固定沿用20261006_153418的16题/19unit，seed42，GPU float32、AdamW lr1e-3/weight_decay0.01，200步全批平均；不作为正式预算调优或效果结论。记录后续上游梯度、gate、归一化patch变化及训练定位。
- EXP-015正式预算/早停与EXP-014相同。主比较三seed逐题D均值减三seed逐题C均值，文档聚类bootstrap2000次/seed0，点估计≥0.01且95%下界>0；同报D−A、D−B。A/B/C只复用EXP-014已存预测。保留全部8.1节指标、随机/Oracle、M≥2、参数与成本；Top-5差值必须显式报告，不被Top-1改善覆盖。
- source_dev仅在全部D checkpoint确定后统一评一次，是新的开发比较而非独立测试。D优于C本身不等于论文新颖性成立。本轮无正式D训练许可，不自动扩展。

### 10.1 2026-10-06 22:41正式执行授权与冻结增补

本节覆盖第10节准备轮次的“未授权正式运行”状态，不修改其输入/方法/预算。用户明确授权补source_dev节点缓存并执行一次EXP-015。独立dev缓存`d_nodes_dev_v1`，与train/val同编码器/字段规则/几何/截断；原train/val不覆盖。配置`route_v2_exp2_D.yaml`经输入/预算/基线预测兼容性门后改为frozen，绑定缓存manifest与preflight。

正式参数273410（D）对66176（C），不声称容量匹配。只训练source_train，val选择；三个seed全部权重确定后一次dev评分，A/B/C只复用EXP-014预测。逐epoch增加训练侧gate及未经归一化MLP残差范数、归一化patch变化诊断，不影响梯度、损失或checkpoint选择。主比较与Top-5披露沿第10节。无论推进判定结果如何，完成后停止，不消融、不调参、不外测。
