# experiments/ — 实验注册表与记录（SSOT）

结构（Phase M2 起填充）：

```text
experiments/
├── registry.csv                     # 注册表：EXP 编号 / 日期 / config / run 目录 / 一句话结论
├── templates/experiment-record.md   # 11 段记录模板（从旧仓库原样复制）
└── YYYY-MM-DD-exp-NNN-*.md          # 每次正式实验一个详情页
```

迁移时从旧仓库复制：`registry.csv`（保留 EXP-001/002 行）、`templates/`、两份 EXP 记录。
