# 00-index（全仓导航 SSOT）

> Status: working | Scope: 全仓 | SSOT: 是
> 2026-10-07：EXP-016归因及外部比较冻结已完成；固定八页叠图视觉检查与官方原图映射均8/8通过，原D图表文本接入仍阻塞；837页全量仍未启动，最新状态见`@docs/handoff.md`，准备记录见`@experiments/2026-10-07-external-preparation.md`。
> 新增/修改任何 SSOT 文档，必须同步更新本表状态行。迁移完成前 Status 保持 working。

## 六类信息去哪找

| 信息类型 | 位置 | SSOT |
| --- | --- | --- |
| 代码 | `src/layoutpatch/` `tests/` `scripts/` | - |
| 配置 | `configs/`（注册表 `configs/README.md`） | `configs/README.md` |
| 数据与运行产物 | `data/` `artifacts/` `runs/`（不进 git） | - |
| 稳定规范 | `docs/` 下各 SSOT | 见下行 |
| 一次性记录 | `experiments/` | `experiments/registry.csv`（M2 起填充） |
| 当前进度 | `docs/handoff.md` | `docs/handoff.md` |

## 入门（按顺序读）

1. `docs/01-quickstart.md`（working, SSOT）：环境 + 数据准备
2. `@docs/02-commands.md`（working, SSOT）：命令唯一入口；含外部元数据核验、回执/工具身份检查、固定八页续接、官方原图映射审计及定向测试入口，不含获准外部评分或全量解析任务。
3. `docs/RULES.md`（stable, SSOT）：开发规范十条铁律 + 0.2 实验小白讲解 + 4.4 指令透明后台执行

## 现行研究

- `docs/THESIS_SPEC.md`（working）：大论文边界；2026-10-03/04纠正文献分母、数据标签与新旧路线范围
- `docs/PAPER_SPEC.md`（working）：小论文执行；历史Gate保留，新路线见下方独立协议
- `docs/ROUTE_V2_PROTOCOL.md`（working）：区域监督布局融合协议；2026-10-06第9节冻结EXP-014；第10节及10.1节落实D输入并冻结EXP-015正式授权；配置注册见`configs/README.md`
- 固定八页原图映射审计任务已登记：只下载/复用固定revision的`Images.tar`，按manifest提取8页并与既有PDF渲染做内容对齐检查；不生成候选、不评分、不处理其他页面。
- `@docs/handoff.md`（working）：新会话先读2026-10-03入口下的2026-10-07最新节；固定八页视觉与官方原图映射通过，837页全量尚未授权或执行，无效果评分，历史节不作当前执行令
- `docs/paper-progress.md`（working）：小论文进度叙事。2026-09-27 起，执行令以 `docs/handoff.md` 置顶节为准。
- `docs/paper-draft-notes.md`（working）：小论文章节素材。数字以 registry 和证明文件为准，不替代 `docs/PAPER_SPEC.md`。
- `docs/MIGRATION_BATCHES.md`（working）：M0-M6 分批迁移清单（批次 = 实验阶段）

## 实验过程

- `@experiments/2026-10-07-external-preparation.md`：SciEGQA比较冻结与固定八页工程准备；叠图视觉与官方原图内容映射均8/8通过，实际D消费者暴露图表文本丢失风险；最终回执保留接口阻塞，全量需逐页身份/几何/内容检查，无外部效果结果。
- `experiments/2026-10-07-exp-016-attribution.md`：三变体九次训练最小开发归因已完成；仅开发证据，不证明外部泛化。
- `experiments/2026-10-06-exp-015-route-v2-D.md`：EXP-015正式D三seed开发比较，绑定配置和输入，主比较D−C，保留Top-5差值。
- `experiments/2026-10-06-exp-015-preparation.md`：D文本来源与训练/验证缓存、固定smoke、唯一正式配置候选及dev节点缓存缺项；未正式训练。
- `experiments/2026-10-06-exp-014-route-v2-exp1.md`：冻结A/B/C三seed正式开发比较，五件套与输入/代码身份齐全，达到C−B推进标准但未超过面积A，完成后停止。
- `experiments/2026-10-03-route-v2-review.md`：外部修改建议的代码/文献核查及修订依据，不是新效果实验

- `experiments/registry.csv`：注册表（EXP-001~013 + FUSION-ARXIVQA + EXP-002-S1 + EXP-007-S1 + THR-B + S2-AUDIT + SPLIT-FROZEN）。2-R 缺口证明：`experiments/s2_splits/phase2r_gap_proof.json`。第一次正式融合：`experiments/2026-09-29-fusion-arxivqa.md`。
- S2 剔除清单（2026-09-26，已落盘，未开训）：`experiments/s2_exclusion/` + `experiments/phase2r-train-leakage-review.md`。划分已冻结：`experiments/2026-09-26-dev-test-split-frozen.md` + `experiments/s2_splits/`。冻结不是开训许可。
- `experiments/templates/experiment-record.md`：11 段模板（M2 迁入）
- 关门加固（2026-09-18，全部入库）：`experiments/2026-09-17-eff-b1.md`（B1 效率表 8 行 + 探针清洗 + k+1 页码表号）+ `experiments/2026-09-17-b2-taxonomy-draft.md`（B2 四数并列三类）+ `experiments/2026-09-18-advisor-decision-pack.md`（决策包三问只摆数）+ `scripts/run_text_dual.py`（Text 双轨）+ `scripts/run_phase1c_probes.py`（清洗探针）+ `scripts/run_phase1c.py`（存逐题 picks）

## 文献

- `docs/literature/`：逐篇阅读笔记（M6 迁入）
- `docs/30-literature/README.md`：一句话五问表（M6 迁入）

## 状态图例

`stable` 长期有效少改；`working` 正在写；`placeholder` 占位待覆盖；`frozen` 冻结只增版本；`archived` 只读。

## 迁移状态

- 本项目由 `mmdoc-evidence-rag` 迁移而来，执行清单 `docs/MIGRATION_BATCHES.md`。
- 此处仅记迁移历史，不再保存易过期的当前分支头或下一步。最新状态以 `docs/handoff.md` 置顶节和Git实际状态为准；历史检查通过不代表当前质量门通过。
- M3 全量复验（EXP-001，R@5=0.8390）已通过。本文件 Status 仍保持 working，因为迁移清单批次 6 未关。
