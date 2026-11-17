# LayoutPatch 候选解析方式补充实验：论文整合交接材料

整理日期：2026-11-17。本文件用于交接实验事实、证据及解释边界，**不是论文正文，不授权修改任何论文**。数字来自已封存全量结果和审核说明；文末的论文放置方案属于建议。

## 1. 接手须知

先读本文件，再核对文末链接的协议、结果与审核说明。等用户提供论文版本并明确批准修改范围后再编辑，不自行选用仓库中的旧稿或此前生成的整合稿。本次整理不改变实验结果、原始数据或论文，不启动新实验或数据集筛选。

实验工作区：`C:\Users\WenJing\.codex\worktrees\parser-candidate-study\layoutpatch`。原仓库 `C:\Users\WenJing\Documents\WorkTransfer\layoutpatch` 的数据、缓存及 checkpoint 只读复用。

归档记录中的分支为 `experiment/parser-candidate-study`，HEAD 与 paper-v1.0 为 `02693ee908aec8a12ef53b3492892f84cf588499`。这是归档身份，不表示本交接文件已经提交；后续操作前应重新核查状态。不要切换分支、推送、合并或改标签。

## 2. 实验是什么

原研究使用冻结 ColPali，在正确证据页面已给定的条件下，对解析器给出的固定候选区域排序。它不是完整页面检索，不生成答案，也不由排序网络任意生成新框。

初始假设是 MinerU 顶层候选可能与 gold 证据粒度不匹配，但这只是待检验假设。更细并不必然更好：整段、整表被拆开后，单框 IoU 可能下降。

本实验回答：替换候选生成方式后，几何可达性是否改善；固定编码器和 checkpoint 时，实际排序是否受益；A、B、D-no-text 的影响是否一致。

过程包括 MinerU 原始层级复用探索、DeepSeek-OCR-2 四页技术验证、固定 40 页探索，最终完成既有外部集合的全量实验。**本文所有结果数字均来自最终全量实验，不将先导样本当作独立确认测试，也不与全量相加。** “全量”指既有 SciEGQA 外部评价集合的 837 个证据页，不是所有 PDF 的全部页面。

## 3. 固定设置与执行过程（已核实）

### 3.1 对照条件

旧条件为 `mineru_top_v1`，新条件为 `deepseek_ocr2_grounding_v2`。

| 方法 | 本次实际含义 |
|---|---|
| A | 候选面积降序 |
| B | 既有冻结 patch 相关性传播与 IoU 加权汇聚，不是完整 Snappy 复现 |
| D-no-text | 固定布局适配器，文本输入置零，保留节点类型及空间关系，不运行 BGE-M3 |

保留 D-no-text 的原 seed 0/1/2，按原 source_val 规则选定 checkpoint，epoch 分别为 1/1/5。不重新训练、不改编码器、网络或损失，不选择外部最佳 seed。

复用原页面 P、问题 Q、gold 与题—页映射。两条件重建候选 ID、几何、类型、W_raw、W_attn、cover_mass、patch—候选 IoU 权重、D-no-text 的 P′与分数。新候选没有复用旧候选下的 P′或区域分数。

本轮没有重跑完整 D、E、C/C-wide 等变体，不能把它们的旧结果混入本次新候选对照。

### 3.2 OCR、Docker 与坐标

Windows 为宿主系统，OCR 在固定的 Linux CUDA Docker 容器中运行，容器提供 Linux 依赖和 GPU 运行环境；不需要将 Windows 更换为 Linux。冻结评分使用原 Windows Python/PyTorch，读取缓存向量与小型适配器 checkpoint。

- 模型：`deepseek-ai/DeepSeek-OCR-2`。
- revision：`aaa02f3811945a91062062994c5c4a3f4c0af2b0`。
- Docker 镜像：`sha256:a59f549647c823db086de838a3837056901428f8bea69a1d124f12f78de91b9f`。
- 参数：base_size=1024、image_size=768、crop_mode=True、eval_mode=True、save_results=False、test_compress=False。
- BF16、flash_attention_2、技术 seed=0、temperature=0、max_new_tokens=8192、no_repeat_ngram_size=35、use_cache=True。
- 定位提示词为以下两行：

```text
<image>
<|grounding|>Convert the document to markdown.
```

解析进程只接收页面图像、评价渲染图及映射 receipt、模型、代码和不含问答/gold 的页面清单；不读取问题、答案、gold、旧候选、P/Q 或评分 checkpoint。先保存原始输出，再从 ref/det 定位标记导出框，不能把 Markdown 文本当成定位框。

坐标范围为 0–999，以 999 为分母映射回固定评价页面像素；不额外旋转，也不把内部裁剪图当作原 ColPali 整页。figure_title→text，未知类型保留 UNK/type_id=0；只对精确重复框去重并保留别名，不做 IoU 去重，不按 gold 修框、拼框或筛选。

40 页经图像、映射、revision、提示词及生成参数等身份核验后复用原始输出并重新导出，另外 797 页新推理。每页最多尝试一次；非法框或格式失败整页为空候选，无旧框 fallback。失败页、题目及题页单元均保留在分母内。

### 3.3 执行步骤

1. 固定全量协议，核查模型、图像、清单、缓存及 checkpoint 身份。
2. 运行页面 OCR，保存原始输出、耗时、资源和生成终态，再导出候选。
3. 审计坐标、格式、类型、重复与截断，并在不看 gold 的前提下检查叠图。
4. 在同一页面/问题/gold 集合上计算可达性，重建派生量，运行 A/B/三个 D-no-text checkpoint。
5. 汇总逐题指标与配对变化、文档 bootstrap 区间，复算预测和派生文件，核对旧条件历史结果。
6. 保存归档及哈希，审核解释边界。验收通过不以效果上涨为条件。

## 4. 全量规模、失败与验收

| 项目 | 数量 |
|---|---:|
| 文档 | 80 |
| 固定证据页 | 837 |
| 问题 | 1623 |
| 题—页单元 | 1941 |
| gold 实例 | 2497 |
| 旧候选 | 9746 |
| 新候选 | 9222 |
| 成功导出页 | 833 |
| 失败页 | 4（0.478%） |

失败涉及 10 道题、10 个题页单元，均保留。新条件下相应 50 条方法/seed 预测的三项指标均为零。837 页全部生成 EOS，0 页达到 token 上限，最大生成 3583 tokens（上限 8192）；四个失败来自输出格式/坐标，而非截断。

全部页面接受机器结构检查；无 gold 视觉检查覆盖 63 个成功叠图和 4 个失败页原图/原始文本，未发现系统性坐标变换错误，局部漏框、拆分与裁切保留。未知 formula_number 共 110 框、29 页，保留为 UNK。

19410 条预测及 6696 份派生文件完整复算一致（1674 份几何、5022 份 P′）；旧条件 9705 条记录的排名、分数和指标与历史全量结果一致。审核时 24 项来源及 11 项归档哈希一致；逐题重聚合的 30 项宏平均与汇总差异小于 1e-12。

以上属于同一实现/环境内的可重复性证据，不等于独立团队或另一实现复现，不能排除共用函数错误；未重新运行 OCR 检验逐 token 可重复性。

## 5. 指标与统计口径

所有主表百分比先对同题的证据页取平均，再对 1623 题宏平均，不是直接平均 1941 个题页。差值单位为百分点，由未舍入数据计算；不能要求展示值相减完全等于展示差值。

| 指标 | 定义 |
|---|---|
| Oracle@0.5 | 题页内任一候选与任一 gold 的 IoU≥0.5 |
| 逐 gold 独立可达率 | 每个 gold 是否存在 IoU≥0.5 的候选，允许同一候选匹配多个 gold |
| 全部 gold 独立可达率 | 题页内每个 gold 均独立可达，不要求一对一 |
| 全候选一对一贪心召回 | 所有候选与 gold 按原贪心规则匹配后的召回 |
| Top-1 | 第一候选与任一 gold 的 IoU≥0.5 |
| Cov@5 | 前五候选并集与 gold 并集交集的面积 / gold 并集面积；不是命中率 |
| Gold Recall@5 | 前五候选与 gold 按 IoU 降序、索引打破平局的一对一贪心匹配召回；不是最大匹配 |

按 80 篇文档进行配对 cluster bootstrap，2000 次，随机 seed=0。D-no-text 先在题内平均三个 seed，再做新旧比较。区间以这三个固定 checkpoint 为条件，不重采样训练 seed；seed 间样本标准差不是置信区间。

三项 Top-1 新旧比较构成主比较族，同时报告普通 95% 和 Bonferroni 98.3333% 区间。次指标、分层及此前先导探索不在这一校正内。有限 bootstrap 尾部分位数有蒙特卡洛误差，未另做区间稳定性研究，不补造 p 值。

## 6. 全量结果

### 6.1 候选可达性

| 指标（%） | MinerU | DeepSeek-OCR-2 | 新−旧（百分点） | 95% 配对区间 |
|---|---:|---:|---:|---|
| Oracle@0.5 | 69.59 | 69.93 | 0.34 | [-0.77, 1.51] |
| 逐 gold 独立可达率 | 63.86 | 64.29 | 0.43 | [-0.67, 1.60] |
| 全部 gold 独立可达率 | 58.13 | 58.66 | 0.52 | [-0.70, 1.78] |
| 全候选一对一贪心召回 | 63.86 | 64.29 | 0.43 | [-0.67, 1.60] |

独立可达率与贪心召回本次数值相同，不代表定义相同。页候选数中位数 11→10；候选面积占页面比例中位数 2.17%→2.39%。不能概括为候选统一变细，也不能反向断言每页变粗。

### 6.2 冻结排序

单位为 %；D-no-text 汇总为三个 seed 的均值 ± 样本标准差。

| 方法 | 旧 Top-1 | 新 Top-1 | 旧 Cov@5 | 新 Cov@5 | 旧 Gold Recall@5 | 新 Gold Recall@5 |
|---|---:|---:|---:|---:|---:|---:|
| A | 33.80 | 34.29 | 64.12 | 66.12 | 57.02 | 57.33 |
| B | 23.91 | 26.56 | 60.20 | 64.09 | 54.99 | 55.24 |
| D-no-text seed 0 | 31.85 | 36.08 | 60.49 | 65.33 | 55.85 | 57.21 |
| D-no-text seed 1 | 30.01 | 32.69 | 57.76 | 62.56 | 53.57 | 55.14 |
| D-no-text seed 2 | 30.53 | 31.89 | 57.56 | 62.65 | 53.54 | 55.36 |
| D-no-text 汇总 | 30.80 ± 0.95 | 33.55 ± 2.22 | 58.60 ± 1.64 | 63.51 ± 1.57 | 54.32 ± 1.33 | 55.90 ± 1.13 |

### 6.3 配对变化

| 方法 | Top-1 新−旧 | 95% 区间 | Bonferroni 98.3333% 区间 | 改善/变差/不变题数 |
|---|---:|---|---|---|
| A | 0.49 | [-0.54, 1.52] | [-0.74, 1.79] | 39/33/1551 |
| B | 2.65 | [0.37, 5.04] | [-0.22, 5.50] | 131/89/1403 |
| D-no-text | 2.75 | [0.78, 5.09] | [0.42, 5.72] | 160/96/1367 |

| 方法 | Cov@5 新−旧（95% 区间） | Gold Recall@5 新−旧（95% 区间） |
|---|---|---|
| A | 2.00 [0.86, 3.13] | 0.31 [-0.90, 1.53] |
| B | 3.89 [2.77, 5.01] | 0.25 [-0.93, 1.37] |
| D-no-text | 4.91 [3.63, 6.21] | 1.58 [0.21, 2.93] |

### 6.4 页面分层（描述性）

| 原页面分层 | D-no-text 三 seed 平均 Top-1 新−旧（百分点） |
|---|---:|
| both:other_layout | -0.53 |
| both:two_column_proxy | -2.96 |
| image:other_layout | +1.11 |
| image:two_column_proxy | -3.15 |
| table:other_layout | -8.99 |
| table:two_column_proxy | -3.45 |
| text_other:other_layout | +10.24 |
| text_other:two_column_proxy | +3.22 |

分层来自旧候选页面类型与双栏代理，不是 gold 证据类型或人工认证版式。问题可跨层出现，各层只平均该层内的题页，不能简单加权还原总体题宏平均。未做分层显著性检验；用于说明总体提升不等于各类型提升。

## 7. 能支持与不能支持的结论

**总体判断：有限、混合的正向结果，适合作为候选生成方式敏感性补充实验。**

| 证据 | 可支持 | 不可延伸为 |
|---|---|---|
| D-no-text Top-1 +2.75，校正区间为正 | 固定 checkpoint 组合在该集合的新候选条件下平均改善 | D-no-text 普遍优越、任意新 seed 或新领域必然受益 |
| 新 D-no-text 33.55%，新 A 34.29% | D-no-text 数值仍低于面积基线 | 任一方向的显著优劣；本轮没有做 D 对 A 的检验 |
| A 区间跨零；B 校正区间跨零 | A 未显示清晰 Top-1 收益，B 的证据在校正后不足 | 所有方法都稳定显著提升 |
| Oracle +0.34，区间跨零 | 可达性净变化小，未显示明确提高 | MinerU 粒度是主要瓶颈已获证明，或两方案完全等效 |
| 三 seed 点估计均提高，SD 增大 | 改善幅度存在 seed 差异 | 每个 seed 分别显著，或跨 seed 稳定性增强 |
| 候选属性同时改变 | 替换候选组合影响冻结排序 | 变化由“更细粒度”单独造成 |

不能用 Top-1 增量减 Oracle 增量来估计“纯排序贡献”：Oracle 不描述已可达页面内框质量、干扰候选或布局融合变化，本实验没有分离这些机制。

A/B/D-no-text 均不使用新 OCR 文本语义向量，不能归因于文本识别更准确。不能只报告 seed 0 的 36.08% 替代三 seed 汇总，也不能丢弃失败页或只展示获益页面。

SciEGQA 已用于旧分析与 40 页探索，全量协议虽在全量运行前固定，但晚于先导探索；必须保持“探索性补充评价”定位，不能称未见确认测试。新数据集表现、粒度机制及跨领域普遍性仍待验证，本交接不授权追加这些实验。

## 8. 资源与工程成本

- OCR 监控墙钟 5.880 小时；797 页处理时间之和 5.824 小时。复用 40 页不计为新推理。
- OCR 采样峰值 RSS 7.00 GiB；PyTorch allocated 7.60 GiB、reserved 8.34 GiB；系统 GPU 总占用采样峰值 11831 MiB，包含其他进程。
- 冻结评分 621.2 秒，含派生写盘与分析，不含前置核查及复算；RSS 2.24 GiB、CUDA allocated 0.04 GiB。评分读取已缓存向量，不重新运行编码器。
- 没有 MinerU 同条件成本对照，不宣称 DeepSeek-OCR-2 更快。

## 9. 论文放置建议（未执行）

建议正文简述、附录完整记录，最终位置由实际稿件与篇幅决定。

| 位置 | 建议内容 |
|---|---|
| 正文实验部分 | 候选生成方式敏感性分析：研究问题、冻结设置、全量范围、Oracle 和 A/B/D-no-text 汇总主结果 |
| 正文讨论或局限 | D-no-text 有限改善但数值仍低于面积基线；不能识别粒度机制或推广至新领域 |
| 附录 | 全 seed、全指标及区间、统计定义、OCR 参数、坐标转换、失败分母、分层、资源和复算证据 |

不将本实验包装为主创新或突破性证明，也不建议在正文完全隐去它对结论的限制。暂不生成正式论文段落、章节号、表号或引文。模型、数据集、方法的正式引用需在整合时核实一手来源。

## 10. 证据与关键文件

以下路径相对本工作区；完整工作区路径见第 1 节。封存文件保持只读。

| 文件或目录 | 用途 |
|---|---|
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/PROTOCOL.md | 全量冻结协议 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/config.json | 模型/revision、输入哈希、checkpoint、复用页及参数身份 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/full_pages.jsonl | 全量页面清单 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/full_units.jsonl | 固定题页分母 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/EXPERIMENT_GUIDE.md | 操作流程解释 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/RESULT_REVIEW_20261117.md | 最新解释边界审核 |
| experiments/parser_candidate_study/deepseek_ocr2_full_v1/results/full_20261117_01/ | RESULTS.md、archive_manifest.json、候选/评分指标、验收、资源和验证记录 |
| artifacts/parser_candidate_comparison/deepseek_ocr2_full_v1/raw/full_20261117_01/ | 原始 OCR 输出 |
| runs/parser_candidate_comparison/deepseek_ocr2_full_v1/full_20261117_01/ | 候选、失败及可达性审计 |
| runs/parser_candidate_comparison/v1/full_frozen_scoring/full_score_20261117_01/ | predictions.jsonl、question_scores.jsonl、paired_question_changes.jsonl、paired_unit_changes.jsonl、verification.json 等 |
| artifacts/parser_candidate_comparison/v1/full_derived/full_score_20261117_01/ | 重建的几何和 P′ |
| scripts/complete_deepseek_ocr2_full.ps1 | 全量 OCR 执行入口 |
| scripts/audit_deepseek_ocr2_full.ps1 | 候选审计入口 |
| scripts/run_deepseek_ocr2_full_scoring.ps1 与 .py | 全量冻结评分及复算入口 |
| tools/deepseek_ocr2_full_v1/ | 预检、worker、supervisor、审计实现 |
| tools/deepseek_ocr2_candidates_v1/interfaces.py | 页面输入、定位导出和截断监测接口 |
| scripts/run_parser_candidate_study.py | 复用评分与统计汇总 |
| src/layoutpatch/evaluation/localization.py | 定位指标实现 |

## 11. 新窗口第一条消息（可直接复制）

> 请接手 LayoutPatch 论文中“候选解析方式敏感性补充实验”的整合准备，先阅读：
>
> C:\Users\WenJing\.codex\worktrees\parser-candidate-study\layoutpatch\experiments\parser_candidate_study\deepseek_ocr2_full_v1\PAPER_INTEGRATION_HANDOFF.md
>
> 这是已完成的 DeepSeek-OCR-2 全量实验：837 页、1623 题，对比旧/新候选下 A、B、D-no-text，保留原三个 seed。请核对文档列出的封存结果与审核说明，不要与早期 40 页先导结果混淆。
>
> 先简短确认核心发现、解释边界以及正文/附录的放置建议。我随后提供要修改的论文版本；在我提供稿件并明确批准修改范围前，不改写或编辑论文，不自行选用旧稿，不运行实验或搜索新数据集。获准写作后必须保留负面结果、三 seed 汇总、固定分母及探索性定位，不能写成 D-no-text 优于面积基线、MinerU 粒度瓶颈已被证明或未见确认测试。当前分支不切换、不推送、不改标签，原数据与封存结果只读。

## 12. 后续唯一任务与待决定事项

新窗口先理解交接材料，等待用户提供论文并确认整合位置和修改范围，再开展获准的写作。用户尚需决定底稿和允许修改的章节；表格拆分、正式引文和投稿格式依据稿件另定。无需为完成本次交接追加实验。

## 13. 主要证据快捷链接

- [PROTOCOL.md](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/PROTOCOL.md>)
- [config.json](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/config.json>)
- [RESULT_REVIEW_20261117.md](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/RESULT_REVIEW_20261117.md>)
- [RESULTS.md](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/results/full_20261117_01/RESULTS.md>)
- [archive_manifest.json](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/results/full_20261117_01/archive_manifest.json>)
- [scoring_metrics.json](<C:/Users/WenJing/.codex/worktrees/parser-candidate-study/layoutpatch/experiments/parser_candidate_study/deepseek_ocr2_full_v1/results/full_20261117_01/scoring_metrics.json>)
