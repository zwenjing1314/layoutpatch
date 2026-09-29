# 小论文进度（叙事，不是规范）

> 状态：working。2026-09-28 更新。规范以 `docs/PAPER_SPEC.md` 为准，数字以 `experiments/registry.csv` 和各证明文件为准。
> 交接用 `docs/handoff.md`。本页不替代它。
> 2-R 已停止。停止文件：`experiments/2026-09-28-phase2r-stop-frozen.md`。不再训练，不再编码，不读 test_eval。

## 现在在哪

EXP-009 算涨。EXP-010 不算涨。EXP-011 算涨。当前头是 `artifacts/phase2r/arxivqa_dude/ranker.pt`。test_eval 未打分。

EXP-011：训练 11575，早停 1891，第 5 轮停，最好第 3 轮。同一 401 题 Area@1 0.46944212489134424，对照 0.28594452702337386；Area@5 0.7674845426972748，对照 0.7441786161356058。页级 371/415，差值 0。范围只写 ArxivQA+DUDE 混训头，在多域 dev_eval 上这一次。和 EXP-009 同表：混训 Area@1 高 0.0022，Area@5 低 0.0031。不是混训全面更好。

数字出处：`runs/retrieval/mmdocir_phase2r_arxivqa_dude/20260928_151348/metrics.json`。记录页：`experiments/2026-09-28-exp-011-phase2r-arxivqa-dude.md`。

比较表已落盘。分域结果已落盘。test_eval 未打分。表用法已写明。

## 去重是什么，不是什么

去重不是「测试集来自训练集，所以要把重复页删掉」。

泄漏处理已经做过，而且图片内容没有重复：

- 文档名重叠 24 个、问句重叠 38 句，对应训练题已剔除 118 题。证据：`experiments/s2_exclusion/exclusion_proof.json`。
- 页图像素指纹（md5）对撞：评测 20395 页对训练 67845 页，命中 0。证据：`experiments/s2_exclusion/md5_reuse.json`。
- 剔除后，训练文档名和评测 313 个文档名的交集是空的。

现在说的去重，是编码前的省事：同一页会被很多题当成正页或负页。按「文档名 + 页号」只算一次向量，后面所有题共用。文档名只去掉结尾 `.pdf`，不再从最后一个点截断（旧口径会把 `1308.1101` 切成 `1308`，已作废）。

## 已完成的步骤

1. 训练数据清点：65319 题。没有框级标准答案。`experiments/2026-09-24-s2-train-audit.md`。
2. 泄漏剔除：65201 题留下。见上节。
3. 四池划分冻结，seed=42，按文档切。`experiments/2026-09-26-dev-test-split-frozen.md`。`test_eval` 只记了 id，没打分。
4. 2-R 设计冻结：不改 ColPali。只学一个小线性层，用冻结小块分、框几何、本机 bge-m3 文本相似度。损失是「正页的框整体高于负页的框」。`experiments/2026-09-26-phase2r-design-frozen.md`。
5. 代码骨架：`src/layoutpatch/retrieval/rerank/box_ranker.py`、`scripts/train_phase2r.py`。缓存不在就退出，不开训。
6. 20 页测速：每页 3.896 秒，显存 8.10 GiB。全量 63064 页要 68 小时，不批。`experiments/2026-09-26-encode-probe.md`。

## 已停止

2-R 已停止。停止文件：`experiments/2026-09-28-phase2r-stop-frozen.md`。不再训练，不再编码。

## 2026-09-27 补充

执行令已写进 `docs/handoff.md` 置顶节。本页仍是叙事，不替代那一节。划分不按域重切。其余域是否编码，等 ArxivQA 的 `dev_eval` 结果，不预先排全量。
