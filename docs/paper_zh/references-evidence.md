# 最小文献证据表

查阅日期：2026-10-12。用途：为第2节“相关工作”提供临时引用键和可核查论据。本文只纳入五篇必需文献和一篇直接相关补充工作，不构成系统综述。除特别说明外，作者、题名、年份、版本和出版状态以 arXiv 元数据为准；论点依据 arXiv 正文 HTML、官方项目页或指定本地 README 核对。

## 1. 必需文献

| 临时引用键 | 准确题名 | 作者 | 年份与发表状态 | 稳定 URL/DOI | 核实来源与查阅日期 | 可支持的具体论点 | 与本研究的差异与限制 |
|---|---|---|---|---|---|---|---|
| [ColPali2025] | *ColPali: Efficient Document Retrieval with Vision Language Models* | Manuel Faysse, Hugues Sibille, Tony Wu, Bilel Omrani, Gautier Viaud, Céline Hudelot, Pierre Colombo | 2024 首次 arXiv；arXiv v6 2025；arXiv 元数据标注发表于 ICLR 2025 | [arXiv:2407.01449](https://arxiv.org/abs/2407.01449) | arXiv 元数据与 HTML 正文（Method、Late interaction、Benchmark），2026-10-12 | 将文档页面图像编码为多向量表示，并以 late interaction 进行视觉文档检索；ViDoRe 作为视觉文档检索基准。可用于说明页面级检索接口和 patch/token 相关性来源。 | 原工作主要评估页面级文档检索；本文给定正确页面，在固定解析候选内排序区域，并研究从冻结 (P) 到 (P') 的适配，任务、输出粒度和评测协议不同。本文的页级 MaxSim 与区域用的 patch 分数取最大方向也需单独定义，不能把二者写成同一分数。 |
| [Snappy2025] | *Spatially-Grounded Document Retrieval via Patch-to-Region Relevance Propagation* | Athos Georgiou | 2025 arXiv 首次提交；v3 更新于2026；当前核实信息为 arXiv 预印本，未另核正式出版状态 | [arXiv:2512.02660](https://arxiv.org/abs/2512.02660)；官方实现 [athrael-soju/Snappy](https://github.com/athrael-soju/Snappy) | arXiv 元数据/HTML 摘要与方法页；@C:/Users/WenJing/Documents/WorkTransfer/Snappy/README.md；2026-10-12 | 将 ColPali 的 patch 相似度通过页面坐标映射传播到 OCR 区域，以 IoU/空间对应关系进行区域相关性评分；README 明确其为推理时方法，不需额外训练，并支持区域级检索。 | 本文 B 的核心候选汇总与该思路一致，但只作为冻结传播参照；骨干、解析器、token 处理、筛选和协议未完整复现，不能称完整 Snappy 复现。本文也不把缺少分位数筛选作为 Top-1 差距的已证实原因；固定候选区域排序与 Snappy 的完整文档检索/两阶段系统不可直接横比。 |
| [RegionRAG2025] | *RegionRAG: Region-level Retrieval-Augmented Generation for Visual Document Understanding* | Yinglu Li, Zhiying Lu, Zhihang Liu, Yiwei Sun, Chuanbin Liu, Hongtao Xie | 2025 arXiv；项目 README 标注 AAAI 2026；正式出版页面本轮未单独核实 | [arXiv:2510.27261](https://arxiv.org/abs/2510.27261)；官方实现 [Aeryn666/RegionRAG](https://github.com/Aeryn666/RegionRAG) | arXiv 元数据/HTML 正文与 @C:/Users/WenJing/Documents/WorkTransfer/RegionRAG/README.md；2026-10-12 | 将 RAG 的检索单位从整页推进到视觉区域；使用区域级多模态对比监督，并在推理时对显著 patch 进行邻域分组形成语义区域；涉及生成端的区域 RAG。 | 本文只做给定正确页面的固定候选排序，不做动态区域生成、页面检索或答案生成；本文 C/D 的 patch 监督和 ($\tau=0.25$) 采用了任务适配的相似形式，但监督/损失借鉴不等于本文创新。本文冻结 ColPali 并学习轻量 (P\rightarrow P')，不使用 Qwen2.5-VL 的端到端 retriever-generator 框架。 |
| [MMDocIR2025] | *MMDocIR: Benchmarking Multimodal Retrieval for Long Documents* | Kuicai Dong, Yujing Chang, Xin Deik Goh, Dexun Li, Ruiming Tang, Yong Liu | 2025；arXiv 元数据标注 accepted to EMNLP 2025 (Main) | [arXiv:2501.08828](https://arxiv.org/abs/2501.08828)；数据项目 [mmdocrag.github.io/MMDocIR](https://mmdocrag.github.io/MMDocIR/) | arXiv 元数据/HTML 正文与官方数据项目；@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/ROUTE_V2_PROTOCOL.md；2026-10-12 | 提供长文档多模态检索基准，区分 page-level retrieval 与更细粒度的 layout-level retrieval，布局元素包括段落、公式、图和表；可作为本文内部来源池和任务背景的基准依据。 | 本文没有把 MMDocIR evaluation 当作最终独立测试，而将其按协议划为训练/验证/开发来源池；source_dev 只能是开发结果。本文评测的是正确页面内固定候选排序，不直接报告 MMDocIR 的页面检索或完整 layout-level benchmark 数字。 |
| [SciEGQA2026] | *SciEGQA: A Dataset for Scientific Evidence-Grounded Question Answering and Reasoning* | Wenhan Yu, Zhaoxi Zhang, Wang Chen, Guanqiang Qi, Weikang Li, Lei Sha, Deguo Xia, Jizhou Huang | 2025 首次 arXiv；v2 2026-03-30；当前核实信息为 arXiv 预印本，正式出版状态待核实 | [arXiv:2511.15090](https://arxiv.org/abs/2511.15090)；官方项目 [yuwenhan07.github.io/SciEGQA-project](https://yuwenhan07.github.io/SciEGQA-project/)；数据卡 [Yuwh07/SciEGQA-Bench](https://huggingface.co/datasets/Yuwh07/SciEGQA-Bench) | arXiv 元数据/HTML、官方项目页与数据卡入口；@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-09-exp-017-sciegqa-external.md；2026-10-12 | 提供带语义证据区域框的科学文档 QA 基准；人工标注 benchmark 包含1623题，支持证据定位与问答联合评估。可作为本文外部给定正确页面区域定位的来源背景。 | 本文只使用其给定正确页面后的候选区域排序部分，不评估答案生成；解析候选由本研究外部流程生成，不能把 SciEGQA 的人工 gold 框直接等同于候选框。数据卡许可证状态未声明，不能宣称零泄漏或无许可风险。 |

## 2. 补充直接相关工作

| 临时引用键 | 准确题名 | 作者 | 年份与发表状态 | 稳定 URL/DOI | 核实来源与查阅日期 | 可支持的具体论点 | 与本研究的差异与限制 |
|---|---|---|---|---|---|---|---|
| [LayoutLMv32022] | *LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking* | Yupan Huang, Tengchao Lv, Lei Cui, Yutong Lu, Furu Wei | 2022；arXiv 元数据标注 ACM Multimedia 2022 | [arXiv:2204.08387](https://arxiv.org/abs/2204.08387) | arXiv 元数据/摘要与正文；2026-10-12 | 通过统一文本/图像 masking 及 word-patch alignment 学习文本、图像和布局的联合表示，说明布局条件表示是文档理解中的一条成熟建模路径。 | LayoutLMv3 面向通用 Document AI 的预训练与下游任务，不是冻结 ColPali 下的候选区域排序器；其预训练目标、输入模态和评测任务均不同，不能作为本文方法的直接性能基线。 |

## 3. 引用使用边界

- 本轮未找到必要的 DOI；稳定 arXiv URL 或官方项目/数据页面已足以作为临时引用入口，目标期刊未定，最终格式留待后续统一。
- 不把 arXiv 预印本写成已录用或正式出版；RegionRAG 的 AAAI 2026 信息仅来自项目 README，正式出版状态仍待核实。
- 不将文献摘要中的 SOTA、准确率或效率数字直接与本文固定候选 Top-1、Cov@5 或 Gold Recall@5 横比；若后续需要数字比较，须按任务、候选、骨干、指标和数据版本逐项对齐。
- 本轮仅建立最小证据表，未扩展为系统性综述，也未核查目标期刊格式。

