# EXP-018：唯一 E 直接候选排序事后补充对照

## 1. 实验目的

本实验只补一个 E：冻结原始页面 patch 表示 `P` 和 query 向量，直接学习候选排序，回答“在同信息、同监督来源、同候选和接近参数预算下，冻结 `P` 的这一个具体直接排序方案是否已经足够”。结果角色固定为 **post-hoc supplementary**（事后补充），不改写 EXP-017 的原六方法与三项确认性比较。

本实验不增加第二个 E 变体，不重新训练或评分原六方法，不重新编码，不根据外部结果调维度、损失、阈值或融合权重。

## 2. 环境

使用项目唯一的 uv `.venv`。正式训练环境：Python `3.11.16`、torch `2.13.0+cu130`、CUDA `13.0`、`NVIDIA GeForce RTX 3080 Ti`。没有新增依赖或下载模型。

正式训练总 elapsed 为 `137.7851015999986` 秒，峰值 reserved VRAM 为 `75497472` bytes。三次 E 外部模型评分分别为 `11.923593899999105`、`7.203484800000297`、`7.423120700001164` 秒，合计 `26.550199400000566` 秒；外部峰值 reserved VRAM 为 `58720256` bytes，低于 12 GiB 上限。

## 3. 数据和 split

训练以原 D 的 `source_train` 可训练 unit 为起点：原 D 为 1002 unit，E 可训练且与 D 相交为 843 unit，排除 159 unit；其中无负候选 117、无 IoU≥0.5 正候选 42。空 `W_raw` 候选为 0。E 与 D 使用同一标注来源，但候选级 IoU 标签与 D 的 patch 监督不是同粒度，也不是完全相同训练集。外部标签未进入训练。

checkpoint 只按 `source_val` 的 374 题/448 unit 选择；没有评分 `source_dev`。外部 SciEGQA 分母固定为 1623 题、837 页、1941 题—页 unit、9746 共同候选。

## 4. 配置文件

配置为 `configs/experiments/route_v2_E_supplement_v1.yaml`，状态 frozen。E 使用 `v_j=normalize(Σ_i W_raw_ij P_i/Σ_i W_raw_ij)`，`x_j=max_t(q_t⊙v_j)` 是逐维交互特征，不称标准 MaxSim；72 维正弦坐标经 `Linear(72,128)` 后与六类型 128 维 embedding 相加。分数为 `score_B+MLP([x,v,l])`，MLP 为 `Linear(384,680)→GELU→Linear(680,1)`，末层零初始化。实际可训练参数 `272593`，仅表示接近 D-no-text 登记参数量，不表示有效容量完全匹配。

## 5. 运行命令

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-e-tests
powershell.exe -NoProfile -File tasks.ps1 route-v2-e-check
powershell.exe -NoProfile -File tasks.ps1 route-v2-e-train
powershell.exe -NoProfile -File tasks.ps1 route-v2-e-external
powershell.exe -NoProfile -File tasks.ps1 route-v2-e-verify
```

定向测试最终 `17 passed`。小训练侧检查通过。正式外评只执行三个 E seed 各一次；原六方法评分 0 次，视觉重编码 0 次。

## 6. 代码 commit

正式训练记录的 commit 为 `5e2ede0a3a68c6597726daf5e28b44d84dcfade4`。正式目录同时保存定点代码快照、`code_identity.json` 和 `workspace.patch`；运行时工作区包含未提交的 EXP-018 实现与文档改动。

## 7. 输出目录

训练 run：`runs/retrieval/route_v2_E_supplement_v1/20261010_131705/`。

完成的外部补充 run：`runs/retrieval/route_v2_E_external_supplement_v1/20261010_132706/`。

首次外评保存目录 `runs/retrieval/route_v2_E_external_supplement_v1/20261010_132007/` 已完成全部模型评分、指标保存和结果复核，仅在终端打印时失败。严格恢复先从保存预测重算统计，再创建新完成目录；恢复没有加载 checkpoint 或重复模型评分。

训练预测 1344 行。外部完成目录有 32997 行预测、27591 行逐题分数、17 个方法标签；其中 EXP-017 原预测 27174 行逐行精确复用，E 新增 5823 行。保存结果复核通过。

## 8. 关键指标（`metrics.json` 精确值；完整原文见 run）

训练相关字段按原始数值整理：

```json
{
  "training_filter": {
    "source_train_units": 1059,
    "original_D_training_units": 1002,
    "E_trainable_units": 843,
    "D_E_intersection_units": 843,
    "excluded_units": 159,
    "exclusion_reasons_exclusive": {
      "no_negative_candidate": 117,
      "no_positive_candidate_iou_ge_0.5": 42
    }
  },
  "trainable_parameters": 272593,
  "source_val_hit1_by_seed": {
    "E_seed_0": 0.4701426024955437,
    "E_seed_1": 0.46702317290552586,
    "E_seed_2": 0.4590017825311943
  },
  "source_val_hit1_mean": 0.4653891859774213,
  "source_val_hit1_std": 0.005747338717217218
}
```

三个 seed 的实际 epoch/最佳 epoch 为 `6/1`、`7/2`、`7/2`。训练秒数为 `27.12016699999731`、`34.45026620000135`、`31.782078800002637`；`source_val` 秒数为 `4.336856900004932`、`5.40844649999417`、`5.02196119999644`。

外部主要字段：

```json
{
  "E_hit1@0.5_by_seed": {
    "E_seed_0": 0.3305606900800986,
    "E_seed_1": 0.32378311768330253,
    "E_seed_2": 0.4063462723351818
  },
  "E_hit1@0.5_mean": 0.353563360032861,
  "E_hit1@0.5_std": 0.04583678375752732,
  "E_cov@5": 0.6159265258614915,
  "E_gold_recall@5@0.5": 0.5643869377695625,
  "E_area_sum@5": 0.6171936945475585,
  "D-no-text-E": {
    "mean_diff": -0.045594577942082666,
    "ci95_low": -0.0677148846960167,
    "ci95_high": -0.024905359633393215,
    "documents": 80.0,
    "queries": 1623.0
  },
  "top5_D_no_text_minus_E": {
    "cov@5": -0.029928956496668935,
    "gold_recall@5@0.5": -0.021154241117272488,
    "area_sum@5": -0.029886982890365288
  }
}
```

数值位置只作展示：E−A `0.015608954610803083`、E−B `0.11449989730950916`、E−C-wide `0.12004518381597867`，不增加事后主比较。完整原文见两个 run 的 `metrics.json`。

## 9. 错误信息（原样）

首次外评保存与复核完成后，Windows GBK 终端打印 Unicode 减号失败：

```text
UnicodeEncodeError: 'gbk' codec can't encode character '\u2212' in position 246: illegal multibyte sequence
```

恢复逻辑只接受该错误，且要求旧 `result_verification.json` 的 `passed=true`；随后重新验证保存预测并创建完成目录。恢复耗时 `5.3984116000028735` 秒，`checkpoint_loaded=false`，`model_scoring_reexecuted=false`。没有数值、身份、泄漏、显存或模型评分错误。

## 10. 结果解释

D-no-text−E 的 Top-1 点差为 `-0.045594577942082666`，95% 区间 `[-0.0677148846960167,-0.024905359633393215]` 全负，因此 D-no-text 没有胜过这个 E；相反，这个具体直接候选排序 E 的 Top-1 更高。三项 Top-5 差值也均为负，表示 D-no-text 的 Cov@5、Gold Recall@5 和 Area Sum@5 均低于 E。

结果支持“这一个具体直接候选排序方案足以构成强对照”，不支持 `P→P′` 相对该 E 具有额外 Top-1 或 Top-5 价值。它不证明所有直接排序方案都优于融合，也不证明 E 可靠优于面积 A；E 相对 A 只有事后数值位置，没有预定配对区间。更不证明页面召回、端到端检索、生成收益、新颖性或完整效率优势。

## 11. 是否可用于论文 + 下一步

可作为论文的 **post-hoc supplementary** 补充结果，但必须与 EXP-017 的冻结主结果分开标注，并完整报告三个 seed、区间、Top-5、强面积基线和限制。区间跨零时不能写“等效”；本次主区间未跨零，但结论仍只能限定为 D-no-text 与这一个具体 E 的比较。

EXP-018 已完成并停止。无下一 E 变体、无扩训、无外部重评、无面积混合、无追加消融。
