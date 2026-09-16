# 实验记录模板（SSOT）

> 复制本模板到 `experiments/YYYY-MM-DD-exp-NNN-主题.md`，一次正式 run 一篇。
> `experiments/registry.csv` 是唯一注册表，本模板是详情页。不要再写 `current_experiment_results.md` / `experiment_progress_and_commands.md` / `xxx_change_log.md`。

## 1. 实验目的

- 一句话：本次要验证什么（对应 Phase 1A / 1B / 1C / 2 和 H1-H4）
- Gate 归属：本次属于哪一步，为什么现在可以跑

## 2. 环境

- uv / Python / torch / CUDA 是否可用
- conda（如有）：`$env:CONDA_DEFAULT_ENV`
- 模型缓存：`HF_HOME=artifacts/hf_cache` 是否生效

## 3. 数据和 split

- 数据集：
- split / query 数：
- 数据版本依据（MMDocIR 看 `01-quickstart.md` 第 4 节）

## 4. 配置文件

- Config 路径（含 `--split` 覆盖）：
- 关键参数（top_k / search_scope / model / batch）：

## 5. 运行命令

```powershell
./tasks.ps1 <task>
```

底层等价 `uv run lp ...` 见 `tasks.ps1` 打印的 `RUN:` 行，原样抄。

## 6. 代码 commit

- commit：
- 是否干净（`git status --short` 有无未提交）：

## 7. 输出目录

- Run 目录（含时间戳，不写 `latest`，`latest` 只用于命令行寻址）：
- `latest.txt` 指向确认：

## 8. 关键指标（`metrics.json` 原样抄）

- Page R@1/5/10：
- MRR / nDCG@5 / nDCG@10：
- Region Hit@5：
- Sufficiency / mismatch（如有）：

## 9. 错误信息（原样抄，无则写无）

- stderr / 报错 / 缺图 / CPU 拒绝 / 显存：

## 10. 结果解释

- 支持了哪个假设（H1-H4）：
- 属于 A/B/C/D 哪类（如适用）：
- 与上一版对比一句话：

## 11. 是否可用于论文 + 下一步

- 可用于论文：是 / 否（smoke 一律否；full 需满足 protocol 才算）
- 下一步 EXP：
