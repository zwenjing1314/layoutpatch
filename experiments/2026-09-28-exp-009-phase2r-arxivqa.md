# EXP-009 Phase 2-R ArxivQA

## 1. 实验目的

- 验证 ArxivQA 页弱监督能否提高 dev_eval 框排序。
- Gate：编码 8341 对已齐，方案 A 已冻结。

## 2. 环境

- 本机 `.venv`，ColPali 与 bge 只用已有缓存，不下载。

## 3. 数据和 split

- 训练：ArxivQA train_fit 9241 题。
- 早停：ArxivQA train_dev 1592 题。
- 判定：dev_eval 415 题。区域分母按当前 `region_labels.parquet` 重数是 401。

## 4. 配置文件

- `scripts/train_phase2r.py`，方案 A：三组特征、K=4、早停 2 轮、batch 32。

## 5. 运行命令

```powershell
./tasks.ps1 phase2r-arxivqa
```

本次实际由 `.venv` 的 python 直接跑了同一脚本。页级重算没有重训，没有改 w、b。

## 6. 代码 commit

- 未提交。

## 7. 结果

- 早停第 4 轮，最好第 2 轮。
- Area@1 0.4673，对照 0.2859。Area@5 0.7706，对照 0.7442。沿用本轮已写数字。
- 旧键 `page_r5` 仍是 0.0，不覆盖。原因：脚本把 `evidence_page_ids` 当成字符串，和页 id 对不上。
- 新键：冻结 ColPali 371/415 = 0.8940。2-R 不改页序，页级同样 371/415。差值 0，在 ±0.3 个百分点内。对照是这 415 题，不是全集 0.8390。
- 区域分母：`experiments/s2_splits/dev_eval_region_401.txt`，401 题。391 是旧表重数，现行表重数是 401，规则没变。
- 同一 401 题上 Area@1 0.4673>0.2859，Area@5 0.7706>0.7442，页级差值 0。算涨。范围只写 ArxivQA 训出来的头，在多域 dev_eval 上这一次。

## 8. 关键指标

- 旧 `metrics.json` 的 `page_r5`：0.0（保留）。
- 新键 `page_r5_frozen_colpali`：0.8939759036144578（371/415）。
- 新键 `page_r5_phase2r`：0.8939759036144578（371/415）。
- `page_r5_delta_pp`：0.0。`page_r5_within_0_3pp`：true。

## 9. 错误信息

- 无新报错。旧 `page_r5=0.0` 是字符串 gold 页和预测页求交失败，不是这 415 题真的全未命中。

## 10. 结果解释

- 页级过线。同一 401 题上 Area@1、Area@5 都高于 fixed:iou_mass。
- 算涨。范围只写 ArxivQA 训出来的头，在多域 dev_eval 上这一次。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否。只是这一次 dev 判定，不是投稿结论。
- 下一步：无。本页只更正冲突，不开新实验。

## 审查

- 通过。401 题单 401 行、不重复，且是 dev_eval 415 题的子集。
- Area@1 0.4673、Area@5 0.7706、页级 371/415 与 `metrics.json` 一致。旧 `page_r5=0.0` 保留。
- registry、本页、`summary.md` 都写「算涨」。范围只限 ArxivQA 训出的头、多域 dev_eval 这一次。
- `ranker.pt` 能加载，参数只有 `linear.weight`、`linear.bias`。没有 `train_fusion.py`，没有 test_eval 分数文件。未重训。

