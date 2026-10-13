# 第6轮合并检查记录

## 已完成的检查与修正

1. 已将@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/01-introduction.md至@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/07-conclusion.md按章节顺序合并为完整初稿；正文移除了各源文件的“写作核对备注”、本地路径、待办清单和运行历史。
2. 已新增约500字中文摘要和5个关键词；摘要包含任务条件、A/B/C/C-wide/D/D-no-text/E比较、内部与外部数据、核心结果及有限结论，并将E标为事后补充。
3. 已统一方法名称为A、B、C、C-wide、D、D-no-text和E；页级MaxSim、patch相关分数、候选区域分数分别保留其定义。
4. 已核对(P)、(P')、(Q)、(W_{\mathrm{raw}})、(W_{\mathrm{attn}})与候选评分权重(A)的用途；修正合并时可能将公式中的(S_{ti}(P))误替换为文本标记的问题。
5. 已修正普通括号形式的学习率、betas、epsilon和温度表达；式（1）—（21）标签唯一，表3-1及表5-1至表5-4编号连续，方法流程图草案保留在第3节。
6. 已将结果表格数字统一为最多四位小数；差值与区间由结果文件精确值舍入展示，未从舍入均值反算，也未改变原三项Bonferroni比较族或E唯一补充比较。
7. 第4节已明确MMDocIR官方evaluation在本协议中重新划作训练、验证和开发来源，source_dev不称最终独立测试；E的AdamW、学习率、weight decay、betas、epsilon、units_per_update、clip_max_norm和scheduler均已逐项写明。
8. 已根据@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-09-exp-017-sciegqa-external.md修正Oracle表述：固定候选集合的Oracle仅作为上限分析，未被写成候选生成器或完整任务链评估。
9. 六个临时引用键（ColPali、Snappy、RegionRAG、MMDocIR、SciEGQA、LayoutLMv3）均在正文出现并各有一个文末条目；未新增文献或编造DOI、卷期、页码和录用状态。

## 仍需核实的缺项

- Snappy的正式出版状态与完整复现条件；RegionRAG正式出版页面；SciEGQA正式出版状态及数据许可。
- 内部与外部候选解析配置的逐项对齐，以及E训练调用中的全部掩码细节。
- 目标期刊及最终参考文献格式尚未确定，但不阻塞当前通用中文Markdown初稿。

本轮未新增实验、重评分、调参、检索文献或修改实验代码、协议和旧结果。
