# 环境与数据准备（SSOT）

> Status: working | Scope: 环境配置唯一出处 | SSOT: 是
> 其他文档只允许引用本篇，不许复写环境步骤。

## 环境搭建（唯一环境：uv .venv）

前置：Windows + NVIDIA GPU（基准 RTX 3080 Ti 12GB）+ [uv](https://docs.astral.sh/uv/) 已安装（`uv --version` 能出版本号）。

```powershell
# 1. 同步基础依赖（ruff/pytest 等开发工具一起装好）
uv sync --dev

# 2. 验证基础环境
uv run lp version

# 3. ColPali 相关任务前，同步 CUDA extra（首次约数 GB 下载）
uv sync --dev --extra colpali

# 4. 验证 CUDA 可用（在 3080 Ti 上应输出 cuda ok）
uv run --extra colpali python -c "import torch; assert torch.cuda.is_available(); print('cuda ok')"
```

说明（新手向）：
- uv（Python 环境与依赖管理器）按 `pyproject.toml` + `uv.lock` 两份文件精确还原环境，`uv.lock` 锁定每个包的版本，保证你和未来任何一台机器装出的环境完全一致。
- `--extra colpali` 表示额外安装可选依赖组 `colpali`（torch 2.13.0 + colpali-engine）。Windows 上 torch 会自动从 `pytorch-cu130` 源装 CUDA 13.0 版，这个映射写在 `pyproject.toml` 的 `[tool.uv.sources]`，不用手动配。
- 禁止 conda / 手动 pip / 临时 venv 跑实验（铁律 1）。临时试包用 `uv run --with <pkg> python`，结论要保留就回填 `pyproject.toml`。

## 数据准备（Phase M1 执行）

MMDocIR 数据根目录布局（放到 `.env` 的 `LAYOUTPATCH_DATA_ROOT` 指向的位置，默认 `./data`）：

```text
data/
└── raw/mmdocir_evaluation/     # 官方发布原始文件
└── processed/mmdocir_evaluation/
    ├── documents.parquet       # 313
    ├── pages.parquet           # 20395
    ├── nodes.parquet           # 170338
    ├── queries.parquet         # 1658
    └── page_images/            # 页图（ColPali 编码必需）
```

prepare 命令登记后（`docs/02-commands.md`），对数检查由 `./tasks.ps1 mmdocir-colpali-full` 的内置断言自动执行。

embedding cache：旧仓库 `artifacts/colpali/` 可整体复制到本项目同路径，省去约 8 小时全量编码；不复制则首次 full 检索自动重算。
