# 外部区域监督预训练数据审计

不是训练。不是下载。不读 `test_eval` 内容。不改权重。不改四池。不用 evaluation gold。不启动人工标注。不启动 A 路线 MIL。

本页只回答：仓库外有没有「问题 + 页图 + 答案文本 + 答案区域」能立刻拿来做 `L_region` 预训练。结论先写：

**没有一份外部数据能在不下载、不重新编码、不改候选框定义的条件下，直接提供与 MMDocIR 评测同构的问题到 MinerU 候选框监督。** 最接近的是 DUDE 抽取题的 evidence 框和 TAT-DQA 单元格/块映射，但本仓库 parquet 已经把它们降成页级，再用原版等于新数据工程。

## 0. 需要什么样的监督

小论文执行规范 `docs/PAPER_SPEC.md` 第 5.7 节的区域损失需要：对一个问题，知道正页上哪些候选框盖住证据。评测主口径是官方 `recall_layout`（预测框与 gold 的交集面积 / gold 面积）。训练候选必须是版式解析框，不能用手画评测 gold。

因此外部数据要同时满足：

1. 有自然语言问题；
2. 有页面图像；
3. 有答案文本（或等价证据）；
4. 有答案区域坐标，或至少能稳定映射到词框/单元格，再 IoU 对齐到候选框或 32×32 patch。

只有 1–3、没有 4，就还是页级/文本 QA，不能解当前失败。只有 4、没有 1，就只是布局分割，不能当问题到证据监督。

本仓库现状（已审计，不重复下载）：`train_fit` / `train_dev` 的 `with_layout_gold=0`。七域 jsonl 只有正负页。parquet `layouts` 只有 `bbox`+`type`。MMDocIR 原文也写：多数训练域缺 layout 级标签，本地转换后只保住页级。

## 1. 对照总表

| 数据集 | 公开 | 问答 | 答案区域坐标 | OCR 文本 | 坐标系 | 能否映射到候选框/patch | 对 MMDocIR evaluation 泄漏 | 许可证 / 下载 | 改造工作量 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DocVQA (SP) | 是，RRC 注册 | 是 | **否**（官方 JSON 无答案框） | 另发词/行框 | 页图像素词框 | 弱：答案字符串对 OCR 子序列，再并成框 | 评测 313 不来自 DocVQA；与 train 的 MP-DocVQA 同源风险高 | RRC 研究用；图+OCR 数十 GB | 高：匹配噪声 + 全量编码 |
| MP-DocVQA | 是，RRC | 是 | **否**（题仍是单页 DocVQA，无 layout gold） | 同 SP | 同 SP | 弱，同 SP；多页只增加干扰页 | 已在 MMDocIR **train** 里；评测 313 已剔除重叠文档 | 同 RRC | 高且无新区域信号 |
| InfographicVQA | 是，RRC | 是 | **否**（只有 evidence 类型标签） | Textract 词框 | 页图像素 | 弱：约 70% 可抽 span 才对得上词框 | 来源是网络信息图，与 313 长 PDF 低重叠 | RRC；约 5.5k 图 | 高：域偏移 infographic≠长文档 |
| FUNSD | 是 | **否**（字段名不是用户问题） | 实体框，不是答案证据 | 词框 | 页图像素 | 只能当布局/键值，不能当检索监督 | 表单扫描件，与 313 低重叠 | 研究许可，体量很小 | 低，但任务不对 |
| DocLayNet | 是 | 否 | 11 类版式框 | 部分文本 | COCO 页图 | 只能当布局先验 | 办公 PDF，与 313 低到中 | CDLA-Permissive | 中：编码量大，无 QA |
| PubLayNet | 是 | 否 | 5 类版式框 | 无 QA | COCO | 只能当布局先验 | PMC 论文 vs 评测学术 PDF，残留同文风险需另审 | CDLA-Permissive；体量很大 | 高：下载/编码，无 QA |
| DUDE 原版 | 是 | 是 | **抽取题有 evidence 框**（约四成题） | 竞赛 OCR | 页图像素 evidence 框 | 中：IoU 到 MinerU 候选或 patch | 已在 MMDocIR **train**；评测已剔除 | 文档偏公有领域；标注另约 2 万美元成本已发生在原项目 | 中高：要拿原 JSON，不在本仓 parquet |
| TAT-DQA 原版 | 是 | 是 | **单元格/块级证据**（单页财务） | 文本块 | 页内块/单元格 | 中：表单元格对齐候选 | 已在 MMDocIR **train**；评测有财务域，文档名需再对一次 | CC BY 4.0 | 中：原 JSON 不在本仓 |
| BBox-DocVQA (2025) | 论文级 | 是 | 宣称有证据框 | 未核本仓 | 未核 | 可能最齐，但未进本仓 | 若从 DocVQA 派生，同源风险同 SP | 未批准下载 | 禁止本轮；需新技术准入 |

「弱映射」= 用答案字符串去对 OCR 词，不是人标证据框。官方 Area 要的是证据区域，不是「答案字符串碰巧出现的位置」。

## 2. 必比四组

### 2.1 DocVQA（单页，SP-DocVQA）

官方 JSON 字段是 `questionId, question, image, docId, answers`，没有答案框。另提供商业 OCR：词和行的文本 + 包围盒。答案被要求从页上原文抽出，所以多数题可以把答案匹配成 OCR 子序列，再取这些词框的并集当伪 G。

这不是独立区域 gold：

- 匹配到第一次出现，可能不是真正证据；
- 短数字答案会命中很多框；
- 并集往往碎，和 MinerU 块级候选不对齐；
- 评测 IoU / Area 用的是块，不是词。

坐标系：OCR 词框，原图像素。映射路径：词并集 → 与 parquet 候选算 IoU，或覆盖 32×32 patch。噪声大。

泄漏：MMDocIR evaluation 来自 MMLongBench-Doc 和 DocBench，不是 DocVQA。但 MP-DocVQA 复用同一批 UCSF Industry Documents 图和题。本仓库 train 已含 MP-DocVQA 域。用原版 DocVQA 预训练，主要撞的是 **train 域**，不是已剔除的 313。仍须文档指纹对撞，不能假设零重叠。

许可证：RRC 竞赛下载，研究使用；底层文档来自 UCSF IDL。下载成本：注册 + 图像和 OCR 打包，大约数十 GB。改造：新适配器、泄漏脚本、ColPali 编码（3080 Ti 上是小时到十小时级）、伪 G 质量抽查。**不能直接写进当前 `train_fusion` / 2-R。**

### 2.2 MP-DocVQA

题和答案复用 SP-DocVQA，只是把前后页拼成最多 20 页。额外页是干扰页，**没有新的框级答案**。MMDocIR 训练集约了 875 长文档 / 15266 QA，本地 jsonl 仍只有正负页。

因此：再下 MP-DocVQA **不会得到本仓缺少的区域监督**。泄漏风险高于 DocVQA，因为该域已经在 `train_fit`。改造工作量高、收益相对当前失败为 0。

### 2.3 InfographicVQA

约 3 万题 / 5485 张网络信息图。有问答、答案文本、QA 类型（答案来源 / 证据类型 / 运算）。证据类型是 Text / Figure / Table / Map / Visual，**不是像素框**。OCR 用 Amazon Textract，词框在页图像素。约 70% 题是 Image-span，才适合字符串对齐词框；计数/算术题对不上区域。

域偏移大：单张海报式信息图，不是 MMDocIR 那种平均 65 页 PDF。即使伪 G 能训起来，也很难证明能打过 `dev_eval` 上的 `geom:area`。泄漏：与 313 长文档低重叠，但仍要做图哈希。下载：RRC Infographics VQA 包。改造高，且和 C1–C3 的长文档检索主线不一致。

### 2.4 FUNSD / DocLayNet / PubLayNet：只是布局，不是问题到答案区域

这三份 **不能** 提供「这个问题的证据在哪」。

| | FUNSD | DocLayNet | PubLayNet |
| --- | --- | --- | --- |
| 有什么 | 表单实体：header / question / answer / other + 链接 | 11 类版式分割 | 文本/标题/列表/表/图 |
| 所谓 question | 表单上的字段名，如 “Name:” | 无 | 无 |
| 所谓 answer | 该字段的填写值 | 无 | 无 |
| 能否当 `L_region` | 否。没有检索 query，也没有页内证据定位任务 | 否 | 否 |

它们最多能预训练「框类型 / 坐标编码」，那是布局编码器的旁路，证明不了区域排序超过面积规则。FUNSD 很小（约 199 页），下载便宜但任务错。DocLayNet / PubLayNet 许可相对友好（CDLA-Permissive 一类），体量大、要编码，收益仍不是区域监督。

PubLayNet 来自 PMC OA，评测集有学术论文域，存在「同一 PDF 不同切页」的残留风险，真要用必须另做文档指纹，本轮不做。

## 3. 更接近、但仍不是「立刻能用」的两份

### 3.1 DUDE 原版

有问答。抽取题在标注第一阶段要求 **evidence bounding box**。抽取题大约 42%。这是公开 DocVQA 里最接近「问题 → 答案区域」的来源。

本仓库已经有 DUDE 页图和页级正负，**没有** 把 evidence 框写进 parquet。要用，必须再取原竞赛 JSON，按页对齐到现有缓存，再 IoU 到 MinerU 候选。

泄漏：DUDE 在 MMDocIR train；与 evaluation 313 的文档交集已在 `s2_exclusion` 剔除。风险主要是「用 train 域的原框」而不是「污染 test」。许可证偏公有领域文档。工作量中高：对齐脚本 + 只保留抽取题 + 面积去偏。域仍是杂文档，不是 ArxivQA 主评测风格。

### 3.2 TAT-DQA 原版

财务单页，问答，表+文，带单元格/文本块证据（从 TAT-QA 扩展）。许可 CC BY 4.0。MMDocIR 原文写：该域有单页 layout 标签，转换时还要找回页号。本地训练文件同样没有暴露这些框。

泄漏：train 已含 TAT-DQA；evaluation 有财务年报域，文档名必须再对一次（本轮只记风险，未打开 `test_eval`）。工作量中。域窄（财务表），对 ArxivQA 图题迁移弱。

## 4. 和当前三条路线怎么比

| 路线 | 监督是否对齐 5.7 | 是否改 C3 | 下载/编码 | 打过 `geom:area` 的条件 | 工作量 |
| --- | --- | --- | --- | --- | --- |
| 1 外部区域预训练 | 多数只有伪 G；DUDE/TAT 原框才像 | 若只当离线框头，可不改 | 要下数据、要编新页 | 先过域偏移和候选对齐，仍可能学到大框 | 周级。新技术准入：新数据源 |
| 2 MMDocIR 40 题人工点选 | 对齐：同一套 MinerU 候选 | 不改 | 否 | 协议可测；40 题不够训，只够验标注是否可做 | 人时：约半天到一天点选 + 复标 |
| 3 query-conditioned MIL | 仍是页级包标签 | **改 C3**，接近 Argus | 否 | 低：2-R 和 fusion 已用同一监督失败 | 代码 1–2 天，失败风险高 |

`geom:area` 冻结线不变：Area@1 `0.46726432578302896`，Area@5 `0.7726699451254816`，页级 R@5 `0.8939759036144578`。外部预训练即使在源域涨，也必须在同一 `dev_eval` 401 题上过这条线，不能换分母。

## 5. 唯一推荐

**2. 先做 MMDocIR 40 题人工标注。**

理由：

1. 外部主候选（DocVQA / MP-DocVQA / InfographicVQA）**没有金标准答案区域**，只有 OCR 词框和答案字符串。用它们预训练，等于再做一次「页弱监督 + 文本捷径」，解释不了相对最大框的增益。
2. FUNSD / DocLayNet / PubLayNet **没有问题到证据**，不能当区域预训练主数据。
3. DUDE / TAT-DQA 原框有价值，但本仓没有这些 JSON，再用就等于新下载和新编码，触发新技术准入，且域已在 train 里。它们是 40 题协议跑通之后的备选补强，不是现在的第一步。
4. MIL 仍是同一套页级正负，已经让线性头和 fusion 都没超过 `geom:area`，还要改 C3。
5. 40 题是已写协议（`experiments/2026-09-29-region-annotation-plan.md`）的最小可停版本：同一 MinerU 候选、同一泄漏边界、不下载、不编码。目的不是一次训到投稿，而是先量 Jaccard、`no_candidate` 比例、人能不能避开最大框。不过关就停，不必 400，更不必外部预训练。

工作量（路线 2）：从现有 400 行 pending 清单再抽 40 题（建议先抽 `double_annotate=true` 的子集或按层各取），两人各标一遍，第三人只裁定冲突。不写训练标签文件以外的 gold，不改 `dev_eval`。若 40 题 Jaccard≥0.8 且 `no_candidate`≤25%，再议是否扩到 400。若不过，外部预训练和 MIL 都不自动启动。

本轮未做：未下载任何外部数据；未训练；未读 `test_eval`；未开始 40 题标注。
