# 项目开发规范（Rules）

> Status: stable | Scope: 全仓开发行为 | SSOT: 是
> 用途：任何人（包括未来的你和 AI agent）在本仓库写代码、跑实验、改文档前必读。违反本规范的改动一律不合入 `main`。
> 关系：研究边界看 `docs/THESIS_SPEC.md` 与 `docs/PAPER_SPEC.md`；本文件只管"怎么开发"，不管"研究什么"。

## 0. 十条铁律（速查）

1. 只用 uv 一个环境，禁止 conda / 手动 pip / 临时 venv 跑实验。
2. 只通过 `./tasks.ps1` 或 `docs/02-commands.md` 里的命令启动实验，不裸敲 `uv run ...` 组合。
3. 新命令必须先登记进 `docs/02-commands.md` 再使用。
4. 根目录尽量保持干净：新增顶层文件/目录必须先在本规范 4.2 登记理由，否则放进现有目录。
5. 每次正式实验必留五件套（config/run_info/metrics/predictions/summary），并登记 `experiments/registry.csv`。
6. `runs/`、`data/`、`artifacts/` 永不进 git。
7. 代码改动走短分支 + `./tasks.ps1 check` 三绿才合 `main`。
8. 用户可见变更必须写 `CHANGELOG.md`；SSOT 文档变更必须同步 `docs/00-index.md` 状态行。
9. 禁止新建任何流水账文件（change log / current results / progress 类）。
10. 一切以 SSOT 为准：同一信息只允许一个出处，其他地方只引用。

## 0.1 沟通与准入（与铁律同等强制）

- 面向用户的回复一律中文；用户是开发新手，每个概念先讲"是什么、为什么"再讲"怎么做"，每次回答结尾附编号「操作步骤」清单。细则见 `.cursor/rules/01-communication.mdc`。
- 引入新依赖、新模型、新工具、新工作流前，必须先说明问题/候选方案/连锁影响/回退方式，并等到用户明确同意才动手。细则见 `.cursor/rules/02-tech-approval.mdc`。

## 1. 环境规范（唯一环境）

### 1.1 唯一运行时

- 项目唯一正式环境：uv 管理的 `.venv`，由 `pyproject.toml + uv.lock + .python-version` 三件套锁定（Python `>=3.11,<3.13`，ColPali extra 锁 `torch==2.13.0 cu130`）。
- 禁止用任何 Conda 环境或手工 venv 跑正式实验。
- 环境验证唯一命令：

```powershell
uv run --extra colpali python -c "import torch, colpali_engine; print(torch.__version__, torch.cuda.is_available())"
```

### 1.2 环境变更流程

1. 改依赖一律改 `pyproject.toml`，然后 `uv sync --dev [--extra colpali]`，让 `uv.lock` 落盘；
2. 在 `CHANGELOG.md` `[Unreleased]` 记一条 Changed；
3. 任何被锁版本、CUDA 源、Python 版本变化，必须同步 `docs/01-quickstart.md`；
4. 禁止 `uv pip install`、`pip install` 等绕过 lock 的操作。临时探索用 `uv run --with <pkg> python`，结论若要保留，必须回填 `pyproject.toml`。

### 1.3 硬件与确定性

- 基准硬件：RTX 3080 Ti 12GB。默认 batch 取 `configs/experiments/*.yaml` 中冻结值（image 1 / query 2 / score 4），改 batch 等于开新实验版本。
- 需要确定性的实验在 config 里记录 seed；未记录 seed 的 run 不得声称可复现。
- 环境变量的设置方法只写在 `docs/01-quickstart.md`。

## 2. 架构规范（轻量根目录）

### 2.1 允许存在的根目录条目（白名单）

```text
layoutpatch/
├── src/                  # 唯一正式实现（包名 layoutpatch）
├── tests/                # 单元测试 + smoke
├── scripts/              # 一次性脚本（需可独立运行）
├── configs/              # 数据 / 实验 / split 配置（注册表 configs/README.md）
├── docs/                 # 全部文档（含 SSOT）
├── experiments/          # 实验注册表与记录（registry.csv + 模板 + 记录页）
├── data/                 # 数据（gitignore）
├── artifacts/            # 模型/索引/缓存等可再生文件（gitignore）
├── runs/                 # 每次运行的不可变结果（gitignore）
├── tmp/                  # 临时文件（gitignore，可随时清空）
├── .venv/  .uv-cache/    # 环境（gitignore）
├── .cursor/              # rules + skills（进 git）
├── tasks.ps1             # Windows 唯一命令入口
├── pyproject.toml  uv.lock  .python-version
├── README.md  CONTRIBUTING.md  CHANGELOG.md
└── .env.example  .gitignore  .gitattributes
```

### 2.2 根目录变更纪律

- 新增顶层文件/目录前，先回答：能不能放进 `src/`、`configs/`、`docs/`、`experiments/` 之一？能放就不新增。
- 确需新增，必须：CHANGELOG 记一条 + 更新本节白名单 + 更新 `docs/00-index.md`。
- 根目录可见条目不超过 25 个，超过即触发一次整理。
- 过期文档移入 `docs/90-archive/`，原位置不留说明文件。

### 2.3 src/ 内部约定

```text
src/layoutpatch/
├── config/ paths/schemas/io 相关模块
├── datasets/       # 数据准备与 parquet 产物
├── layout/         # 布局节点编码、W 对应矩阵（Phase 1B 前建）
├── retrieval/      # 检索器与融合（fusion/ 子包 Phase 2 建）
└── evaluation/     # 页级/区域指标、坐标审计
```

- 每个新模块先在 `docs/PAPER_SPEC.md` 立项，再建包，包内必须有对应 `tests/`。
- 禁止在 `scripts/` 写会被复用的逻辑；复用逻辑一律下沉到 `src/`。
- CLI 子命令必须注册进 `pyproject.toml` 的 `[project.scripts]`（命令名 `lp`）。

## 3. 文档规范（SSOT 体系）

### 3.1 六类信息，六个家

| 信息类型 | 唯一出处 | 禁止行为 |
| --- | --- | --- |
| 命令怎么跑 | `docs/02-commands.md` | 其他文档复写长命令 |
| 环境怎么配 | `docs/01-quickstart.md` | 其他文档复写环境步骤 |
| 研究边界与 Gate | `docs/THESIS_SPEC.md` + `docs/PAPER_SPEC.md` | 在笔记里另立方向 |
| 评测口径 | `docs/PAPER_SPEC.md` 第 8 节 | 在代码注释里另立口径 |
| 实验结果 | `experiments/registry.csv` + 记录页 | 新建 results/current 类文件 |
| 当前进度 | `docs/handoff.md` | 在多处重复记进度 |

### 3.2 文档状态与生命周期

- 每篇 SSOT 文档头部必须有 `Status: stable|working|frozen|archived`，`docs/00-index.md` 登记全部 SSOT 状态。
- 新建 SSOT：写文档 → `00-index.md` 加状态行 → CHANGELOG 记一条。
- 废弃 SSOT：Status 改 `archived`，移入 `docs/90-archive/`，顶部加"已废弃，见 XXX"。
- 冲突裁决顺序：本规范 > `00-index.md` > 各领域 SSOT > 笔记类文档。

### 3.3 禁止出现的文件名模式

```text
*_change_log.md / CHANGELOG_*.md（根目录 CHANGELOG.md 除外）
current_*results*.md / *progress*.md / *_notes_final*.md
*_v2_final_真的最终版.md
```

发现即删或并入对应 SSOT。

## 4. 命令规范（统一入口）

### 4.1 唯一启动方式

- Windows：`./tasks.ps1 <task>`。所有任务共用同一 uv `.venv`，任务内部自动清掉外层 `VIRTUAL_ENV`。
- 新的实验形态必须新增 task，而不是让使用者拼 `uv run` 长命令。
- 裸 `uv run --extra colpali lp ...` 只允许两类场景：`tasks.ps1` 内部实现、`02-commands.md` 中标注"底层等价（备查）"的说明。
- 临时调试命令不进文档；被重复使用两次以上必须升级为 task。

### 4.2 新增 task 的流程

1. 在 `tasks.ps1` 的 `param ValidateSet` 注册任务名并实现分支；
2. 任务开头打印 EXP 编号 / Config / Dataset / split / Output / GitCommit；
3. 前置数据检查不通过必须 throw，不允许静默降级；
4. 在 `docs/02-commands.md` 按固定四段格式登记：命令 / 输入 / 输出 / 检查；
5. CHANGELOG 记一条；提交信息用 `chore(tasks): add xxx` 或 `exp(mmdocir): add xxx`。

### 4.4 指令透明、agent 可在后台执行（2026-09-16 起强制）

- agent 每次后台执行命令前，必须先在回复里用代码块给出**实际执行的完整 PowerShell 指令**（含工作目录 `layoutpatch/` 前提），逐条说明这条指令读什么、写什么、大概跑多久。
- GPU 长任务（ColPali 编码、full 复验）由 agent 在后台执行，用户不需亲手输入；agent 只在「停进程」「删产物」「改评测口径」三类动作前等用户明确同意。
- agent 不得擅自 `Stop-Process` 停掉正在跑的进程；必须先说明停的是哪个进程、为什么停、半成品产物如何处理，并等用户同意。
- 汇报结果时必须贴：完整 run 目录（含 timestamp）、`metrics.json` 原文、关键产物行数，禁止只给"跑通了"一句话。
- 每次回复的操作步骤之后，另附「本轮指令说明」小节：逐条列出本轮实际跑过的指令原文（一字不改）+ 一句话作用（读/写/耗时）。未跑指令则写"本轮未执行任何命令"。

### 4.3 命令产出目录约定

```text
runs/retrieval/<config_name>/<timestamp>/
    config.json           # 本次生效配置快照
    run_info.json         # commit、数据规模、耗时、环境摘要
    predictions.parquet   # 逐 query 预测
    metrics.json          # 指标（evaluate 产物）
    summary.md            # 人读摘要
    errors.csv            # 仅出错时
    latest.txt            # 指向最新 timestamp，仅用于命令行寻址
```

- 记录、汇报、论文引用一律写完整 timestamp 目录，不写 `latest`。
- run 目录不可变：跑完不许改写；重跑生成新 timestamp。

## 5. 实验记录规范

### 5.1 三层记录，缺一不可

1. **命令层**：`docs/02-commands.md`——干什么、输入、输出、地址、判定标准；
2. **注册层**：`experiments/registry.csv`——EXP 编号、日期、config、run 目录、一句话结论；
3. **详情层**：`experiments/YYYY-MM-DD-exp-NNN-主题.md`——按 11 段模板完整记录。

任何一层缺失，该实验不算完成（DoD 见 `CONTRIBUTING.md`）。

### 5.2 详情记录强制字段

commit、输出目录、指标原文、错误原文四段必须原样粘贴，禁止概括转述。目的与解释写清支持/不支持哪个假设、属于 A/B/C/D 哪类。

### 5.3 结果引用规则

- 引用一个数字必须能沿"数字 → metrics.json → run 目录 → registry 行 → 记录页 → 命令 → config"追到源头；
- 追不到源的数字一律不得使用（包括口头汇报）；
- smoke 结果永不进论文。

## 6. 代码修改记录规范

### 6.1 Git 层（为什么改）

- 提交信息：`<type>(<scope>): <subject>`，type 限定 `feat|fix|docs|exp|chore|refactor|test`；
- 一次 commit 只做一件事；禁止 `misc`、`update`、`修复一些问题`；
- 影响实验结论的改动必须在 commit body 写一句对旧结果的影响。

### 6.2 CHANGELOG 层（用户可见变更）

- 只记面向使用者的变更；不记每日流水；`[Unreleased]` 常驻。

### 6.3 设计决策层（为什么这么做而不那么做）

- 方法论取舍写进对应 SSOT，不写进代码注释；
- 代码注释只解释非显然的约束与陷阱（坐标系、padding、归一化、tie-break），禁止叙述性注释。

## 7. 质量门与合入规范

### 7.1 合入 main 的最低条件

```powershell
./tasks.ps1 check   # ruff + pytest 全绿
```

另须同时满足：config 登记状态、正式 run 五件套齐全 + registry 登记、`00-index.md` 状态行更新。

### 7.2 分支与提交节奏

- `main` 只合可跑版本；短分支 `paper/phase-1b-diag` 风格命名；
- 长分支超过一周未合必须 rebase 并重跑 check；
- 实验型提交用 `exp(...)`，与代码 `feat/fix` 分开。

### 7.3 破坏性操作

- 删除/改名 SSOT 文档、tasks 任务、config，必须 CHANGELOG 单独记一条并给出替代路径；
- 重跑会覆盖产物的操作必须先确认 run 目录 timestamp 唯一；`prepare` 禁止用 `--limit-docs` 写入 full 目录。

## 8. AI agent 协作规范（本仓库特别条款）

- agent 改代码前必须先读：本规范 → `docs/00-index.md` → `docs/handoff.md` → 相关领域 SSOT。
- agent 跑实验只允许 `./tasks.ps1`；需要新 task 时按 4.2 流程添加。
- agent 不得新建白名单外的顶层文件、不得跳过 `experiments/registry.csv` 登记、不得在 SSOT 里写未验证的实验结论。
- agent 汇报结果必须给出 run 目录完整路径与 metrics.json 原文，禁止只给"提升了 X%"。
- 会话结束前 agent 必须更新 `docs/handoff.md`，并保证工作区不留"改了一半"的未说明改动。

## 9. 违规处理

- 违规产物（流水账文件、错误环境的 run、未登记的实验）：发现即移入 `docs/90-archive/` 或删除，不修补；
- 环境不明、seed 缺失的不确定结果一律标记"不可用于论文"；
- 本规范自身修改：`docs:` 提交 + CHANGELOG + 第 10 节版本号递增。

## 10. 版本

- v1.0（2026-06-16）：LayoutPatch 新项目首版（继承自 mmdoc-evidence-rag v1.0，包名/CLI 名/SSOT 名更新）。
- v1.1（2026-09-16）：新增 4.4「指令先行、用户亲手验证」。原因：EXP-001 期间 agent 代跑长任务、未充分展示命令与结果，引发时间线质疑；此后 GPU 长任务一律由用户亲手输入，agent 只做事后核对。
