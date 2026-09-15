# Research Scope（已对齐 2026-06 新主线）

## Thesis Question

大论文核心问题：如何在保持视觉文档检索效率的同时，让检索结果不仅命中正确页面，还能可靠定位页面内支持答案的证据区域，并为后续可信生成提供结构化证据。

当前小论文聚焦窄问题：ColPali 的视觉 patch 表示能找到相关页面，但能否在不裁剪页面、不重复视觉编码、保持 MaxSim 接口的条件下，利用 OCR/Layout 结构改善页面内证据区域定位？

## Contribution Ladder（新）

1. **缺口证据**：量化 MMDocIR 上"页面命中但区域未命中"的规模与结构（Phase 1B 的 A/B/C/D + 分层 + 案例）。
2. **方法**：布局约束的文档侧 patch 融合——OCR 文本 + BBox + 区域类型构建布局节点 T，经稀疏局部对应 W 与门控残差学习 `P_fused = P + gate·MLP(LN(delta))`，patch 数不变。
3. **效果与机理**：三指标同报（页级 + 区域 + 效率）；消融证明每个组件解决哪个观察；OCR 噪声下 Gate 保底。

方法细节与公式唯一出处：`docs/SMALL_PAPER_DEV_SPEC.md` 第 5 节。文献对照唯一出处：`docs/THESIS_RESEARCH_ROUTE_DRAFT.md` 第 4 节。

## Key Terms

- **patch 表示 P**：ColPali 冻结视觉编码器输出的 [N=1024, D=128] 向量。
- **布局节点 T**：由 OCR 文本 + 坐标 + 类型编码的 [M, D] 区域向量。
- **W**：patch 与布局区域的稀疏空间对应矩阵，三种定义 dev 三选一。
- **P_fused**：融合后的文档侧表示，离线计算入库，query-independent。
- **页面命中 / 区域命中**：gold 页在 Top-K 内 / 预测框与 gold 框 IoU≥0.5（主指标），辅以 Text Recall/F1。
- **A/B/C/D**：页面命中×区域命中的四象限分解（1B 的核心产物）。
- **Oracle page -> region**：上界分析，永远不与可部署方法并列排名。

## Current Known Boundary

截至 2026-06：Phase 1A ColPali full baseline 已完成并登记（EXP-002，Page R@5=0.8390）；布局节点编码、W 计算、稀疏融合、区域指标、坐标审计均未实现；Phase 1B/1C/2 未开始。config 或 schema 字段的存在不等于功能已实现。

## Out Of Scope Unless Explicitly Justified

- 训练新的多模态基础模型；把 OCR/表格识别作为主要贡献；
- 把通用 PDF 问答当研究系统；无图像基线却声称视觉/多模态收益；
- **复活旧方向**：`cn_annual_reports + evidence set + sufficiency/verify/citation/拒答` 是开题后被否的方向，代码与文档已归档（`docs/90-archive/`），只可引用不可续写；
- 小论文阶段做跨页证据或复杂表格解析（那是大论文扩展方向或 Plan B3，需另立 Gate）。
