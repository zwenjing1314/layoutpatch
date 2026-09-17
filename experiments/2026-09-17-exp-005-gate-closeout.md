# EXP-005 Phase 1B 关门补证：交叉表 + 可寻址B + oracle天花板 + 直方图 + 中间态10张（正式）

## 1. 实验目的

- 一句话：给 Phase 1B 关门——B 类 45 题到底多少可寻址、离 10% 线多远、框缺失天花板多少、20 张极值之外中间态长什么样。不跑新大实验，只在冻结输入上重算。
- Gate 归属：迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 4；对应小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节。小论文口径冲突以本文 frozen 定义为准。

## 2. 环境

- uv `.venv`，纯 CPU（统计 + matplotlib 落盘 + PIL 叠图，无 GPU）
- 输入五件：EXP-001 run `20260916_134144` 的 `predictions.parquet`（Top-5）+ `nodes.parquet` + `region_labels.parquet`（2638 行：matched 2523 + unmapped 115）+ `queries.parquet`（问题类型）
- `matched` 定义：题有 ≥1 行 matched gold（1598 题，含 2 题既 matched 又 unmapped）；`unmapped_only` 定义：题只有 unmapped gold 行（60 题）；1598+60=1658。

## 3. 数据和 split

- 数据集：`mmdocir_evaluation` 全量，无 split；K=5，IoU 阈值 0.5。
- 冻结定义（各 JSON 的 `meta` 同字）：
  - `area_ratio`（分 bins 键）= 题内各 gold 行 `bbox_area/page_area` 的**均值**；`area_best_gold_ratio` 仅存 cases 供参考，不参与 bins。
  - `ocr_coverage`（分 bins 键）= 题内各 gold 页 `sum(该页nodes框面积)/page_area` 的**均值**。
  - 三分位点：面积 `0.05581485322805808 / 0.17420044972840382`；覆盖 `0.43053905063708986 / 0.5592540474433977`。
  - `topk_best_iou` = gold 页**在 Top-K 内**候选的最大 IoU（区域信号）；`oracle_best_iou` = **全部 gold 页**候选的最大 IoU（不限 Top-K，天花板）。
  - A/B/C/D 用 Top-K 定义：`region_hit` 要求 `page_hit`，故 C=0 是**定义性结果**，不许写成发现。

## 4. 配置文件

- 无新 config；代码 `scripts/run_phase1b_stratify.py`（统一脚本，一次重算 stratification + crosstab + addressability + oracle + 直方图 + 30 张叠图；复用 `region_metrics.bbox_iou` 与已修页号 `_page_image_for`；gold 黄 6 像素粗框，红=表格/橙=段落/绿=图，蓝=32×32 网格）

## 5. 运行命令

```powershell
uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5
```

底层等价：无（单脚本直跑）；`docs/02-commands.md` 登记为 `phase1b-stratify`，`tasks.ps1` 经 `check` 覆盖（脚本无独立 task，由命令手册对齐）。

## 6. 代码 commit

- 工作区改动：`scripts/run_phase1b_stratify.py` 重写为统一关门脚本 + `audit_overlays.py` gold 黄框（已在 S1 提交基线）+ 本记录页 + registry 更名；`./tasks.ps1 check` 全绿见第 9 节。
- 是否干净：否（含 EXP-003/004 已登记未提交 + 本实验新产物未提交，随后一起提交）

## 7. 输出目录

- `artifacts/diagnosis/mmdocir_evaluation/stratification.json`（`meta` 含 k/iou/面积均值定义/三分位点/run 路径；18 行）
- `artifacts/diagnosis/mmdocir_evaluation/cases.json`（`meta` 含三档定义与判读口径；success 10 / failure 10 / middle 10）
- `artifacts/diagnosis/mmdocir_evaluation/crosstab.json`（matched/unmapped_only × A/B/C/D）
- `artifacts/diagnosis/mmdocir_evaluation/addressability.json`（可寻址 B 双分母 vs 10% 线）
- `artifacts/diagnosis/mmdocir_evaluation/oracle.json`（天花板）
- `artifacts/diagnosis/mmdocir_evaluation/strat_area_hist.png` + `strat_area_hist.json`（面积直方图 bin 计数）
- `artifacts/diagnosis/mmdocir_evaluation/strat_cov_hist.png` + `strat_cov_hist.json`（覆盖直方图 bin 计数）
- `artifacts/diagnosis/mmdocir_evaluation/overlays_cases/*.jpg`（极值 20 张：`A_`/`B_` 前缀，缺图 0）
- `artifacts/diagnosis/mmdocir_evaluation/overlays_cases_mid/*.jpg`（中间态 10 张：`M_` 前缀，缺图 0）

## 8. 关键指标（各 JSON 原样抄）

### 8.1 matched/unmapped_only × A/B/C/D（crosstab.json 原样）

| source | queries | A | B | C | D |
| --- | --- | --- | --- | --- | --- |
| matched | 1598 | 1343 | 0 | 0 | 255 |
| unmapped_only | 60 | 2 | 45 | 0 | 13 |

- B 类 45 题中 unmapped_only = **45（占比 100.0%）**；matched B = **0**。即 B 类全部落在"题只有 unmapped gold 行"的 60 题子集内（该子集另有 A=2、D=13）。

### 8.2 扣掉 unmapped 后的可寻址 B（addressability.json 原样）

| 口径 | 分子 | 分母 | 比值 | 离 10% 线 |
| --- | --- | --- | --- | --- |
| 页命中分母 | 0（matched B） | 1390（页命中） | 0.0 | **低 10.00 个百分点** |
| 有布局 gold 分母 | 0（matched B） | 1598（matched 题） | 0.0 | **低 10.00 个百分点** |

- 参考：matched 页命中=1343（分母用它则是 0/1343=0.0，同结论）。

### 8.3 oracle 天花板 vs Top-K 定义性 C=0（oracle.json 原样）

- 全 1658 题：oracle 命中 1600，命中率 0.9650。
- 页命中 1390 题内：oracle 命中 1345（=A），未中 45（=B，框缺口），命中率 0.9676。
- `c_topk_definitional=0`：当前 Top-K 内 C=0 是定义使然（区域命中要求页命中），**不许写成"页级是区域前提"的发现**；真正的可表述天花板是"若页给定（oracle 页约束解除），1658 题中 1600 题的 gold 页上存在 IoU≥0.5 的候选框，58 题不存在（含页未中 D 中的 13 题 unmapped_only + 45 题 matched D 中的一部分）"。

### 8.4 分层表（stratification.json，18 行原样）

| 分层 | n | A | B | 页命中率 | 区域命中率 | B占页命中 |
| --- | --- | --- | --- | --- | --- | --- |
| area=large | 551 | 424 | 36 | 0.8348 | 0.7695 | 0.0783 |
| area=medium | 554 | 487 | 6 | 0.8899 | 0.8791 | 0.0122 |
| area=small | 553 | 434 | 3 | 0.7902 | 0.7848 | 0.0069 |
| density=dense | 552 | 439 | 6 | 0.8062 | 0.7953 | 0.0135 |
| density=medium | 553 | 463 | 7 | 0.8499 | 0.8373 | 0.0149 |
| density=sparse | 553 | 443 | 32 | 0.8590 | 0.8011 | 0.0674 |
| qtype=Chart | 101 | 93 | 0 | 0.9208 | 0.9208 | 0.0 |
| qtype=Figure | 170 | 126 | 13 | 0.8176 | 0.7412 | 0.0935 |
| qtype=Generalized-text (Layout) | 30 | 16 | 4 | 0.6667 | 0.5333 | 0.2 |
| qtype=Pure-text (Plain-text) | 119 | 87 | 13 | 0.8403 | 0.7311 | 0.13 |
| qtype=Table | 140 | 112 | 1 | 0.8071 | 0.8 | 0.0088 |
| qtype=meta-data | 153 | 101 | 0 | 0.6601 | 0.6601 | 0.0 |
| qtype=mixed | 217 | 177 | 13 | 0.8756 | 0.8157 | 0.0684 |
| qtype=multimodal-f | 87 | 76 | 0 | 0.8736 | 0.8736 | 0.0 |
| qtype=multimodal-t | 240 | 208 | 0 | 0.8667 | 0.8667 | 0.0 |
| qtype=text-only | 383 | 332 | 0 | 0.8668 | 0.8668 | 0.0 |
| qtype=una-web | 1 | 1 | 0 | 1.0 | 1.0 | 0.0 |
| qtype=unknown | 17 | 16 | 1 | 1.0 | 0.9412 | 0.0588 |

### 8.5 案例名单（cases.json 原样）

- 成功 10（A 按 topk_best_iou 最高）：`mmdocir_00000/00001/00002/00003/00004/00005/00006/00007/00009/00010`（IoU 全 1.0）。
- 失败 10（B 按 topk_best_iou 最低）：`mmdocir_00102/00147/00675/00700/00116/00664/00665/00625/00082/00241`（IoU 0.0~0.0301）。
- 中间态 10（B 内 IoU∈[0.3,0.5) 优先或大框多候选选错类，按 qtype/面积/密度多样贪心）：`mmdocir_00081/00351/00345/00352/00482/00671/00472/00674/00522/00427`（topk IoU 0.0326~0.4036；其中 `mmdocir_00522` IoU=0.4036 最接近阈值，`n_cands_best_page=2`；其余多大框稀疏/中等覆盖，候选数 11~45；全部 10 题 matched=False，即题只有 unmapped 行）。
- 直方图依赖：`matplotlib` 由 `scipy/scikit-learn` 间接引入，已锁定于 `uv.lock`（`name = "matplotlib"`），主依赖未回填 `pyproject.toml`；直方图脚本首行 `matplotlib.use("Agg")` 纯离线落盘。若精简环境需重跑直方图，先 `uv sync --dev` 保证间接依赖存在。

## 9. 错误信息

- 无运行错误；极值 20 张缺图 0，中间态 10 张缺图 0。
- `./tasks.ps1 check` 原样：

```text
RUN: uv run ruff check .
All checks passed!
RUN: uv run pytest
38 passed in 1.65s
check: all green
```

## 10. 结果解释

- 自匹配验证（2026-09-18，随机 seed=7 抽 matched 行 5 题；脚本一次性，用完即删）：`mmdocir_00686/00308/00892/00108/00158` 的 gold 映射节点 bbox 与自身 nodes 行 bbox 的 IoU 全为 1.0，且在同页候选内按 IoU 排 Top-1 的 node_id 与 gold 映射 node_id 一致（候选数 10/1/8/15/11）。说明 matched 链路是自洽的：A 类的 IoU=1.0 不是巧合，是同一框的自匹配。
- 口径声明：**本诊断测的是候选召回上限、非排序选框能力**——topk/oracle best-IoU 只问"同页候选里有没有≥0.5 的框"，不问"能不能把它排第一"。批次 5 才测排序选框（1343 个 matched A 的 Top-1 选框准确率）。
- 关门数：B 类 45 题 100% 为 unmapped_only（matched B=0），扣掉 unmapped 后可寻址 B=0，双分母口径下均为 0.0，离 10% 线各低 10.00 个百分点。**Phase 2 的"页中区不中可学习缺口"在本口径下为 0**，训练动机不成立；1C 若做，只能验证"消解率≈0"的负结果。
- 天花板表述（修正后）：Top-K 内 C=0 不表述为发现；可表述的是 oracle 数——页给定时 1390 页命中题中 1345 题有框（96.76%），45 题无框；全量 1658 题中 1600 题有框（96.50%）。**B 是 oracle 未中 58 题的真子集**（58=页命中内 45 + 页未中 D 内 13；B 的 45 题 ⊆ 58，前者是后者在页命中约束下的部分）。另注反例：unmapped_only 60 题中有 2 题为 A（`mmdocir_00036`、`mmdocir_00491`，均为 both 题：既有 matched 行又有 unmapped 行，命中来自 matched 行），C=0 仍是定义性结果。
- 中间态判读指引（口径不变：彩色框围没围住真实文字，不看网格线；顶部小字/底部页码未框属官方稀疏）：重点看 10 张 `M_` 图的黄框处是否确实无布局框；`mmdocir_00522`（IoU 0.4036、仅 2 候选）是最值得人工看的一张——若黄框内确有文字但框偏小/偏大，说明阈值附近存在"选错"成分；其余大框多候选（11~45 候选）若黄框横跨整页而布局框全是小段落，则属"框缺失"（gold 框粒度与官方布局粒度不一致）。
- 中间态判读指引（口径不变：彩色框围没围住真实文字，不看网格线；顶部小字/底部页码未框属官方稀疏）：重点看 10 张 `M_` 图的黄框处是否确实无布局框；`mmdocir_00522`（IoU 0.4036、仅 2 候选）是最值得人工看的一张——若黄框内确有文字但框偏小/偏大，说明阈值附近存在"选错"成分；其余大框多候选（11~45 候选）若黄框横跨整页而布局框全是小段落，则属"框缺失"（gold 框粒度与官方布局粒度不一致）。
- 与上一版对比：S1 只给了失败 10 题全 unmapped 的抽样结论；本 EXP-005 给了全量交叉（B=45/45 unmapped_only）+ 双分母 0.0 + oracle 并列 + 直方图落盘 + 中间态 10 张。

## 11. 是否可用于论文 + 下一步

- 可用于论文：是（第 7.3 节关门证据；直方图 `strat_area_hist.png` / `strat_cov_hist.png` 与 bin 计数 `*_hist.json` 已落盘可引用；30 张叠图待用户按同口径抽查）。
- 下一步：与导师共判批次 5 是否值得做——当前数建议"不做 1C 重排、直接按收缩讨论"（大论文规范第 11.2/11.3 节；B 类占比 3.24% 且可寻址 0.0，双不满足进 Phase 2 线）。**禁令重申：未过 1C Gate 不新建 `fusion/` 子包、不写 `train_fusion.py`，训练前须用户明确同意。**
