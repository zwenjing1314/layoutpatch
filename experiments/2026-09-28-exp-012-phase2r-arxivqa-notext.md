# EXP-012 Phase 2-R ArxivQA no-text

## 1. 实验目的

- 验证 ArxivQA 无文本对照头。它不是方案 A，不替换当前头。

## 2. 环境

- 本机 `.venv`。不下载模型，不编新页。

## 3. 数据和 split

- 训练：9241。
- 早停：1592。
- 判定：dev_eval 415 题。区域分母 401。

## 4. 配置文件

- `scripts/train_phase2r_arxivqa_notext.py`。K=4，batch 32，早停 2 轮。文本向量为 None。

## 5. 运行命令

```powershell
./tasks.ps1 phase2r-arxivqa-notext
```

## 6. 代码 commit

- 未提交。

## 7. 输出目录

- `runs/retrieval/mmdocir_phase2r_arxivqa_notext/20260928_192725/`

## 8. 关键指标

- Area@1：0.46736379336701905。对照 0.28594452702337386。
- Area@5：0.7766031311029473。对照 0.7441786161356058。
- 页级：371/415。差值 0。

## 9. 错误信息

- 无。

## 10. 结果解释

- 相对 fixed:iou_mass 算涨。范围只写这一次无文本对照。

## 11. 是否可用于论文 + 下一步

- 可用于论文：否。只是 dev 对照，不是投稿结论。
- 当前头仍是 `artifacts/phase2r/arxivqa_dude/ranker.pt`。
