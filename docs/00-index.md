# 00-index（全仓导航 SSOT）

> Status: working | Scope: 全仓 | SSOT: 是
> 2026-10-09：EXP-017 SciEGQA冻结外部定位评测完成并停止；正式run `@runs/retrieval/route_v2_external_eval_v1/20261009_163938/`，固定1623题/837页/1941题—页单元/9746候选。D-no-text对B和C-wide的Bonferroni区间全正，对面积A的区间跨零；这是给定正确页定位，不是端到端页面检索。详情见`@experiments/2026-10-09-exp-017-sciegqa-external.md`，最新状态见`@docs/handoff.md`。
> 2026-10-08：SciEGQA全量候选准备已ready；固定1623题/837页/1941题—页单元，837页通过、9746候选，最终审计见`@artifacts/route_v2_external/full_prep_v1/20261008_222512/audit.json`。未编码、评分或计算Oracle；最新状态见`@docs/handoff.md`，完整准备记录见`@experiments/2026-10-07-external-preparation.md`。
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
2. `@docs/02-commands.md`（working, SSOT）：命令唯一入口；含SciEGQA全量候选准备、外部向量编码、EXP-017合成测试/准入/冻结评分/保存结果复核及既有工程核验入口。
3. `docs/RULES.md`（stable, SSOT）：开发规范十条铁律 + 0.2 实验小白讲解 + 4.4 指令透明后台执行

## 现行研究

- `docs/THESIS_SPEC.md`（working）：大论文边界；2026-10-03/04纠正文献分母、数据标签与新旧路线范围
- `docs/PAPER_SPEC.md`（working）：小论文执行；历史Gate保留，新路线见下方独立协议
- `docs/ROUTE_V2_PROTOCOL.md`（working）：区域监督布局融合协议；2026-10-06第9节冻结EXP-014；第10节及10.1节落实D输入并冻结EXP-015正式授权；配置注册见`configs/README.md`
- 固定八页原图映射审计任务已登记：只下载/复用固定revision的`Images.tar`，按manifest提取8页并与既有PDF渲染做内容对齐检查；不生成候选、不评分、不处理其他页面。
- `@docs/handoff.md`（working）：新会话先读2026-10-03入口下的2026-10-09最新节；EXP-017 SciEGQA冻结外部定位评测已完成并停止，结论边界与正式run见该节
- `docs/paper-progress.md`（working）：小论文进度叙事。2026-09-27 起，执行令以 `docs/handoff.md` 置顶节为准。
- `docs/paper-draft-notes.md`（working）：小论文章节素材。数字以 registry 和证明文件为准，不替代 `docs/PAPER_SPEC.md`。
- `docs/MIGRATION_BATCHES.md`（working）：M0-M6 分批迁移清单（批次 = 实验阶段）

## 实验过程

- `@experiments/2026-10-09-exp-017-sciegqa-external.md`：SciEGQA冻结外部给定正确页定位评测；六方法、三seed、三个预定主比较及Bonferroni区间完整登记。D-no-text可靠高于B和C-wide，尚不支持可靠高于面积A；非端到端页面检索，完成后停止。

- `@experiments/2026-10-07-external-preparation.md`：SciEGQA比较冻结与固定八页工程准备；叠图视觉与官方原图内容映射均8/8通过，实际D消费者暴露图表文本丢失风险；最终回执保留接口阻塞，全量需逐页身份/几何/内容检查，无外部效果结果。
- `experiments/2026-10-07-exp-016-attribution.md`：三变体九次训练最小开发归因已完成；仅开发证据，不证明外部泛化。
- `experiments/2026-10-06-exp-015-route-v2-D.md`：EXP-015正式D三seed开发比较，绑定配置和输入，主比较D−C，保留Top-5差值。
- `experiments/2026-10-06-exp-015-preparation.md`：D文本来源与训练/验证缓存、固定smoke、唯一正式配置候选及dev节点缓存缺项；未正式训练。
- `experiments/2026-10-06-exp-014-route-v2-exp1.md`：冻结A/B/C三seed正式开发比较，五件套与输入/代码身份齐全，达到C−B推进标准但未超过面积A，完成后停止。
- `experiments/2026-10-03-route-v2-review.md`：外部修改建议的代码/文献核查及修订依据，不是新效果实验

- `experiments/registry.csv`：唯一实验注册表（含 EXP-001~017、外部准备记录及历史专名实验）。EXP-017 详情见上方入口；2-R 缺口证明：`experiments/s2_splits/phase2r_gap_proof.json`。第一次正式融合：`experiments/2026-09-29-fusion-arxivqa.md`。
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
