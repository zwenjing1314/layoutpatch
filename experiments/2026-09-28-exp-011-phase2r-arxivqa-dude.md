# EXP-011 Phase 2-R ArxivQA+DUDE

## 1. 实验目的

- 验证 ArxivQA+DUDE 混训头，在多域 dev_eval 上这一次框排序。
- Gate：方案 A 已冻结。本页只登记已有 run，不重训。

## 2. 环境

- 本机 `.venv`。不下载模型，不编新页。

## 3. 数据和 split

- 训练：11575。
- 早停：1891。
- 判定：dev_eval 415 题。区域分母 401。

## 4. 配置文件

- `scripts/train_phase2r_arxivqa_dude.py`。方案 A：K=4，早停 2 轮，batch 32。

## 5. 运行命令

```powershell
./tasks.ps1 phase2r-arxivqa-dude
```

本页没有重跑这条命令。

## 6. 代码 commit

- 未提交。

## 7. 输出目录

- `runs/retrieval/mmdocir_phase2r_arxivqa_dude/20260928_151348/`。

## 8. 关键指标（`metrics.json` 原样抄）

- `region_n`：401。
- `area1`：0.46944212489134424。`base1`：0.28594452702337386。
- `area5`：0.7674845426972748。`base5`：0.7441786161356058。
- `page_hits`：371。`page_n`：415。`page_r5`：0.8939759036144578。
- `page_baseline_hits`：371。`page_baseline_n`：415。`page_r5_baseline`：0.8939759036144578。
- `page_r5_delta_pp`：0.0。`page_r5_within_0_3pp`：true。
- `train_questions`：11575。`early_stop_questions`：1891。
- `early_stop_round`：5。`best_epoch`：3。
- `verdict`：算涨。`test_eval`：not_read。`new_pages_encoded`：0。

训练 11575，早停 1891，第 5 轮停，最好第 3 轮。同一 401 题 Area@1 0.4694>0.2859，Area@5 0.7675>0.7442，页级 371/415，差值 0。范围只写 ArxivQA+DUDE 混训头，在多域 dev_eval 上这一次。

## 9. 错误信息

- 无。

## 10. 结果解释

- 算涨。范围只写 ArxivQA+DUDE 混训头，在多域 dev_eval 上这一次。
- 与 EXP-009 同表，只写事实：

| 实验 | 头 | Area@1 | Area@5 | 页级 |
| --- | --- | --- | --- | --- |
| EXP-009 | ArxivQA 单域头 | 0.4673 | 0.7706 | 371/415 |
| EXP-011 | ArxivQA+DUDE 混训头 | 0.4694 | 0.7675 | 371/415 |

混训 Area@1 比 ArxivQA 单域头高 0.0022，Area@5 低 0.0031。不是混训全面更好。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否。只是这一次 dev 判定，不是投稿结论。
- 下一步：无。
