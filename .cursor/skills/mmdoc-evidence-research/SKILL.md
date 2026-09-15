---
name: mmdoc-evidence-research
description: Layout-constrained visual document retrieval research (small paper: layout-constrained document-side patch fusion on ColPali; thesis: visual document retrieval with evidence localization). Use when analyzing the thesis plan, changing src/ retrieval or fusion code, designing or running experiments (Phase 1A/1B/1C/2), writing paper content, or deciding the next research task. Prevents scope drift into generic PDF chat, old cn_annual_reports evidence-set direction, foundation-model training, or unsupported claims.
---

# MMDoc Evidence Research

本 skill 是本项目的研究罗盘。它不替代工程判断，也不虚构实验结果；它保证每次解释、改代码、跑实验、写论文都绑定在当前研究主线上。

## When To Use

涉及以下请求时使用本 skill：

- 大论文/小论文、研究问题、创新点、实验计划、Phase Gate 判断；
- `src/`、`configs/experiments/`、`tests/`、`docs/` 的改动；
- 视觉文档检索、ColPali、patch 表示、OCR/Layout、BBox、区域定位、evidence set；
- 判断一个提议的功能是否属于当前研究范围。

与本项目无关的请求不要强行套用本 skill。

## Operating Rules

1. 先读文件再下结论：优先读当前代码和带日期的实验记录，其次才是历史计划。
2. 显式区分三种状态：源码已实现 / 已有可复现实验记录 / 仅仅是计划。
3. 主线以两份 SSOT 为准：
   - 大论文规范：`docs/THESIS_RESEARCH_ROUTE_DRAFT.md`（目标、文献地图、Gate、表述边界）
   - 小论文执行：`docs/SMALL_PAPER_DEV_SPEC.md`（方法、公式、实验步骤、实现清单）
   冲突时先停工对齐，不许各改各的。
4. 接任务先读 `docs/handoff.md`（当前 Phase、最近 runs、阻塞问题）；会话结束前更新它。
5. 三条硬约束（违反即方案错误）：C1 不裁剪区域子图、不重复视觉编码；C2 保持 MaxSim 接口、patch 数 N=1024 不变；C3 文档侧 query-independent，`P_fused` 离线算好。
6. 接口边界：`P_fused` 只用于检索排序与区域打分，永远不作为生成模型的输入；生成输入是原始页面图像 + 框坐标。
7. 严禁泄漏：gold 答案、gold 页/框只用于评测；oracle 必须标 `oracle/upper-bound`，不与可部署方法并列。
8. 任何提升声明必须能追到：数据集版本 + config + 指标 + run 目录 + 对照基线；追不到源头的数字不许用。
9. Phase Gate 不许跳步：1A 完成 → 1B A/B/C/D → 1C 三基线 → 2 训练。1C 的定量判定（B 类占比、Snappy 消解率）见大论文规范第 11.2 节。
10. 旧方向警戒：`cn_annual_reports + evidence set + sufficiency/citation/拒答` 是开题后被否的方向，已归档，不得复活为主线。

## Workflow

1. 判断请求属于哪个 Phase（1A 页级基线 / 1B 缺口诊断 / 1C 无训练基线 / 2 训练融合 / 写作）。
2. 读 `docs/handoff.md` + 对应 SSOT 的相关章节 + 最相近的代码、config、测试。
3. 陈述当前基线与最小可验证改动；需要用户决策的点，用 AskQuestion 提出。
4. 按现有 schema、CLI、config、输出约定实现；测试与风险成比例。
5. 只通过 `./tasks.ps1` 或 `docs/02-commands.md` 登记过的命令运行；环境只允许 uv `.venv`。
6. 汇总：改了什么、现在证明了什么、还有什么没实现、支持哪篇论文的哪一节。

## Response Discipline

术语保持一致：`patch 表示`、`布局节点`、`P_fused`、`页面命中`、`区域命中`、`A/B/C/D`、`IoU Hit@0.5`、`Text Recall/F1`、`Phase Gate`。向用户解释时区分 skill 与模型：skill 是指导 agent 的指令包，本身不会提升检索质量、训练模型或执行实验。

## References

- [research-scope.md](references/research-scope.md)：研究范围、贡献阶梯、术语与边界（已对齐新主线）。
- [experiment-workflow.md](references/experiment-workflow.md)：仓库工作流、基线与对照、评测与声明标准。
