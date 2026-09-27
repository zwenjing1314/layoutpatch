# 小论文进度（叙事，不是规范）

> 状态：working。2026-09-26 写。规范以 `docs/PAPER_SPEC.md` 为准，数字以 `experiments/registry.csv` 和各证明文件为准。本页只帮新窗口看懂做到哪、下一步是什么。
> 交接用 `docs/handoff.md`。本页不替代它。

## 现在在哪

设计已冻结，训练没开始。下一步是把 `train_fit` 里 ArxivQA 的页面用 ColPali 编成视觉向量文件（`.pt`）。编完才能训那个小打分层。

还没做：正式编码、正式训练、`dev_eval` 一次判定、`test_eval` 打分。

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

## 已批、还没执行的下一步

只编 `train_fit` 的 ArxivQA，正页和负页都至少有 1 个框：9241 题，7112 个去重页，外推 7.70 小时。

产物应写入 `artifacts/colpali/mmdocir_train/`，断点续跑，已有 `.pt` 不重写。不要编 Wiki-ss（23.67 小时）和 SlideVQA（12.92 小时）。不要读 `test_eval`。不要下载新模型。

编码完成并另批之后，才训练小层，再在 `dev_eval` 上判一次：Area@1 涨、Area@5 涨、页级 R@5 变化在 ±0.3 个百分点以内。对照是同一子集上重算的 `fixed:iou_mass`，不是全集 0.2787。
