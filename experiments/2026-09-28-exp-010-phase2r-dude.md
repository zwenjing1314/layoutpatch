# EXP-010 Phase 2-R DUDE

## 1. 实验目的

- 验证 DUDE 页弱监督训出的框打分头，能否在多域 dev_eval 上提高框排序。
- Gate：DUDE train_fit 3330 页、train_dev 422 页缓存已齐。方案 A 已冻结。

## 2. 环境

- 本机 `.venv`，ColPali 与 bge 只用已有缓存，不下载。

## 3. 数据和 split

- 训练：DUDE train_fit 2312 题，3330 页。
- 早停：DUDE train_dev 292 题，422 页。
- 判定：dev_eval 415 题。区域分母是 `experiments/s2_splits/dev_eval_region_401.txt` 的 401 题。

## 4. 配置文件

- `scripts/train_phase2r_dude.py`，方案 A：三组特征、K=4、早停 2 轮、batch 32。

## 5. 运行命令

```powershell
./tasks.ps1 phase2r-dude
```

## 6. 代码 commit

- 未提交。

## 7. 结果

- Run：`runs/retrieval/mmdocir_phase2r_dude/20260928_142234/`。
- 早停第 3 轮，最好第 1 轮。早停命中率 0.547945、0.537671、0.530822。
- 同一 401 题 Area@1 0.07710372026423774，对照 fixed:iou_mass 0.28594452702337386。
- 同一 401 题 Area@5 0.4068356330705695，对照 0.7441786161356058。
- 页级两侧都是 371/415 = 0.8939759036144578。差值 0，在 ±0.3 个百分点内。对照是这 415 题的冻结 ColPali，不是全集 0.8390。
- Area@1 没涨，Area@5 没涨。不算涨。范围只写 DUDE 训出来的头，在多域 dev_eval 上这一次。

## 8. 关键指标

- `metrics.json` 的 `area1`：0.07710372026423774。`base1`：0.28594452702337386。
- `area5`：0.4068356330705695。`base5`：0.7441786161356058。
- `page_hits` / `page_n`：371 / 415。`page_baseline_hits` / `page_baseline_n`：371 / 415。
- `page_r5_delta_pp`：0.0。`verdict`：不算涨。

## 9. 错误信息

- 无。显存未超过 12GB。batch 仍是 32。

## 10. 结果解释

- 页级过线，因为 2-R 不改页序。
- 区域两侧都低于同一 401 题上的 fixed:iou_mass。页弱监督迁不到框排序。
- 不算涨。范围只写 DUDE 训出来的头，在多域 dev_eval 上这一次。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否。这是一次 dev 负结果，不是投稿结论。
- 下一步：无。本页只记录这一次判定。

## 审查

- 通过。`artifacts/phase2r/dude/ranker.pt` 只有 `w`、`b`，形状是 (1, 6) 和 (1,)。
- `artifacts/phase2r/arxivqa/ranker.pt` 修改时间仍是 2026-09-28T04:18:03.8172638Z，没有被覆盖。
- `metrics.json` 的 401、371/415 与本页一致。独立重算冻结 ColPali 文档内 Top-5 也是 371/415。
- 没有读 `test_eval`。`config.json` 与 `run_info.json` 都写 `test_eval: not_read`。没有 `test_eval` 分数文件。

## 归因

- DUDE 单域头在多域 dev_eval 上低于同一 401 题的 fixed:iou_mass。这次不能区分「页弱监督迁不到框排序」和「域偏移」。两者都只是猜测。
