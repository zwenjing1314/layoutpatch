# LayoutPatch

基于布局条件适配的视觉文档证据区域排序方法研究。

LayoutPatch 在冻结 ColPali 页面与问题编码器的条件下，利用区域文本、坐标、类型及 patch—区域空间关系适配页面表示，并对解析器提供的候选证据区域进行排序。训练仅更新新增模块，页面和问题表示从离线缓存读取。

**任务范围：给定正确页面，在固定候选集合内排序。** 主实验不包含页面召回、任意框生成或答案生成。候选集合不存在可达证据时，重排序无法生成新的区域。

本文说明论文主实验 `route-v2`（EXP-014～EXP-018）的实现与复现流程。仓库保留的早期页面检索和区域定位探索入口，不属于下述主实验。

## 1. 复现范围

代码、配置与大体积实验材料分开管理。`data/`、`artifacts/` 和 `runs/` 不随 Git 仓库分发；仅克隆代码不能直接得到论文结果。

| 层级 | 所需材料 | 可验证内容 |
|---|---|---|
| 实现检查 | 源码、依赖和测试 | 形状、评分、损失、指标与统计实现 |
| 保存结果复核 | 预测、指标、配置、标注及核验脚本引用的材料 | 从保存结果重新检查指标、权重选择及统计，不执行模型评分 |
| 固定缓存上的训练与评测 | 固定候选、划分、页面/问题/节点缓存、身份回执、历史依赖结果与权重 | 在既定输入下重跑适配模块训练或外部评分 |
| 原始文档重新处理 | 原始数据、页图、解析工具、编码器与全部准备阶段依赖 | 建立新的数据准备运行，不保证与历史候选逐字节一致 |

当前入口围绕冻结实验编写，部分配置绑定历史时间戳、文件哈希和既有结果，并非可接受任意路径的通用训练 CLI。下文明确说明这些依赖，不能将命令列表理解为无需数据包的一键复现流程。

内部原解析器版本及逐节点生成过程未完整追溯，历史结果以固定候选文件及身份记录为依据。重新解析 PDF 后的候选若不同，应作为新输入配置单独记录，不能视为对历史候选的严格复现。

## 2. 环境安装

### 2.1 平台和依赖

统一入口为 PowerShell 脚本 `tasks.ps1`。以下命令均在仓库根目录执行，使用 uv 管理的 `.venv`。

| 项目 | 当前配置或历史记录 |
|---|---|
| Python | `.python-version` 为 3.11；项目允许 `>=3.11,<3.13` |
| 依赖定义 | `pyproject.toml`、`uv.lock` |
| ColPali extra | `torch==2.13.0`、`torchvision==0.28.0`、`colpali-engine>=0.3.0`；解析版本见锁文件 |
| Windows CUDA 源 | PyTorch `cu130`，见 `pyproject.toml` |
| 历史外部评测环境 | Python 3.11.16、PyTorch 2.13.0+cu130、CUDA 13.0、RTX 3080 Ti |
| 正式训练设备 | 默认 `cuda:0`，配置显存预算 12 GiB |

历史环境来自 EXP-017 的 `run_info.json`。12 GiB 是配置上限，不是所有阶段的实测显存需求。缓存训练与加载完整编码器的成本不同；依赖锁定也不保证不同 GPU、驱动和平台上的浮点结果逐位一致。

### 2.2 安装步骤

安装 [uv](https://docs.astral.sh/uv/)，准备与所用 PyTorch CUDA 构建兼容的 NVIDIA 驱动：

```powershell
git clone https://github.com/zwenjing1314/layoutpatch.git
cd layoutpatch

uv sync --locked --dev --extra colpali
uv run --no-sync lp version
uv run --no-sync python -c "import torch, colpali_engine; print('torch:', torch.__version__); print('cuda:', torch.version.cuda); print('available:', torch.cuda.is_available())"
```

正式训练需要 `available: True`。首次安装需要网络和依赖下载空间。`--locked` 拒绝隐式修改锁文件；失败时先核对代码版本、uv 及平台兼容性。

任务脚本主要使用 `uv run --offline --no-sync`，运行时不会自动安装依赖或补齐模型，环境和模型需提前准备。安装 CUDA extra 后，不要用缺少该 extra 的同步命令意外移除运行依赖。

Linux 等平台可参考 `tasks.ps1` 的底层 Python 调用，但本文不提供跨平台部署验收结论；路径、CUDA 安装及 PowerShell 可用性需要另行核对。

## 3. 代码结构与方法

```text
layoutpatch/
├── configs/experiments/       # 实验配置
├── configs/tools/             # 解析和编码配置
├── src/layoutpatch/
│   ├── datasets/              # 数据角色、候选与监督构造
│   ├── layout/                # 节点编码、类型和空间对应
│   ├── retrieval/             # 适配器、候选评分与训练
│   └── evaluation/            # 区域指标与统计
├── scripts/                  # 准备、训练、评测与复核入口
├── tests/                    # 单元与合成数据测试
├── experiments/              # 实验记录和固定划分
├── data/                     # 原始数据和处理表，不随 Git 分发
├── artifacts/                # 缓存和身份回执，不随 Git 分发
├── runs/                     # 权重、预测和运行记录，不随 Git 分发
├── tasks.ps1
├── pyproject.toml
└── uv.lock
```

### 3.1 对照方法

| 方法 | 说明 | 实现 |
|---|---|---|
| A | 候选面积降序 | [route_v2_scoring.py](src/layoutpatch/retrieval/route_v2_scoring.py) |
| B | 冻结 patch 分数的空间传播 | [route_v2_scoring.py](src/layoutpatch/retrieval/route_v2_scoring.py) |
| C / C-wide | 无布局输入的残差适配器及扩大隐藏层的容量参照 | [route_v2_scoring.py](src/layoutpatch/retrieval/route_v2_scoring.py) |
| D | 节点编码与局部布局融合 | [route_v2_layout.py](src/layoutpatch/retrieval/route_v2_layout.py) |
| D-no-text / D-no-coord | 分别将文本输入、显式坐标输入置零 | [route_v2_attribution.py](src/layoutpatch/retrieval/route_v2_attribution.py) |
| E | 在冻结原始 patch 上直接学习候选分数修正 | [route_v2_candidate.py](src/layoutpatch/retrieval/route_v2_candidate.py) |

D-no-coord 仍保留真实空间邻接和覆盖权重，不等同于移除所有空间信息。它属于内部 EXP-016，未纳入 EXP-017 的六方法外部评价。

### 3.2 D 的输入与前向

1. 页面视觉 patch 为 `P: [1024,128]`。完整缓存为 `[1031,128]` 时，前 1024 行是图像 patch，后 7 行是提示 token；区域评分不将提示 token 当作图像网格。
2. M 个区域节点包含文本 `[M,1024]`、坐标 `[M,6]`、类型 `[M]` 和有效节点掩码 `[M]`。文本向量由冻结 BGE-M3 编码；框、类型和原始文本来自布局数据，不由 BGE-M3 生成。
3. [TextLayoutEncoder](src/layoutpatch/layout/nodes.py) 将文本、坐标和类型编码成 `[M,128]` 的节点表示。
4. [SparseLocalFusionV2](src/layoutpatch/retrieval/fusion/sparse_fusion.py) 使用 `W_attn: [1024,M]` 和 `cover_mass: [1024,1]`，为每个 patch 选择至多 4 个局部节点融合，输出 `P′: [1024,128]`。
5. 问题 token 表示 `Q: [T,128]` 与 P′ 匹配，再聚合为 M 个候选分数。按分数降序排序，同分按 `layout_id` 升序处理。

D 的适配前向不接收问题或 gold。同一页面及节点输入产生的 P′ 不随问题变化；后续评分接收 Q，因此排序可以随问题变化。融合阶段空间权重和评分阶段 IoU 权重作用不同，不能混用。坐标映射见 [correspondence.py](src/layoutpatch/layout/correspondence.py)。

### 3.3 评分与损失

有效问题 token 与 patch 分别 L2 归一化，对每个 patch 取全部有效问题 token 相似度的最大值：

$$s_j=\max_t\langle\hat q_t,\hat p'_j\rangle.$$

它沿问题 token 维取最大值，不是页面检索的“每个 query token 取最佳 patch 后求和”。区域 c 的分数为：

$$r(c)=\frac{\sum_j\operatorname{IoU}(b_j,c)s_j}{\sum_j\operatorname{IoU}(b_j,c)}.$$

分母为零的候选使用负无穷排序哨兵。B 使用原始 P，C/D 使用适配后的 P′；B 未采用 Snappy 百分位过滤，不是完整 Snappy 论文配置。

patch 标签由 [route_v2_regions.py](src/layoutpatch/datasets/route_v2_regions.py) 构造：

- 正例：patch 中心落在任一 gold 框内，包含边界。
- 负例：patch 与所有 gold 框均无面积交集。
- 忽略：与 gold 相交，但中心不在任一 gold 框内。

局部多正例对比损失为：

$$\mathcal L=\log\sum_{j\in\mathcal P^+\cup\mathcal P^-}\exp(s_j/\tau)-\log\sum_{j\in\mathcal P^+}\exp(s_j/\tau),\quad\tau=0.25.$$

忽略 patch 不进入损失。没有有效正负样本的单元不能按该损失更新参数，但可能仍满足评价资格。E 使用候选级监督，实际训练子集不必与 D 相同。训练更新和早停见 [route_v2_exp1.py](src/layoutpatch/retrieval/route_v2_exp1.py)。

## 4. 数据、缓存与权重

### 4.1 数据来源及角色

- 内部来源：[MMDocIR Evaluation Dataset](https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset)。本研究重新划分为 `source_train`、`source_val`、`source_dev` 和隔离角色；重划分后的内部结果不作为官方测试成绩。
- 外部来源：[SciEGQA-Bench](https://huggingface.co/datasets/Yuwh07/SciEGQA-Bench)，固定 revision 为 `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`。
- 固定划分：`experiments/route_v2_splits/data-roles-v1/`，包含 `source_*_ids.jsonl`、文档/问题 ID、隔离清单、`identity_inputs.json` 与 `split_proof.json`。

角色划分依据文档身份及重叠审计，不能重新随机打散题—页样本。构造逻辑见 [build_route_v2_split.py](scripts/build_route_v2_split.py)，复现优先使用固定清单。

EXP-017 固定评价范围为 1,623 个问题、837 个唯一证据页、1,941 个题—页单元、9,746 个共同候选。837 页不是完整页面检索库。

### 4.2 内部运行所需文件

| 材料 | 默认位置 |
|---|---|
| 问题与证据关联 | `data/raw/mmdocir_evaluation/MMDocIR_annotations.jsonl` |
| 原始布局及文本 | `data/raw/mmdocir_evaluation/MMDocIR_layouts.parquet` |
| 页面表和真实页图 | `data/processed/mmdocir_evaluation/pages.parquet` 及其引用的图像 |
| 固定角色 | `experiments/route_v2_splits/data-roles-v1/` |
| 候选及监督 | `artifacts/route_v2_data/regions_v1/`：`units.parquet`、`candidates.parquet`、`audit.json` |
| 页面缓存 | `artifacts/colpali/mmdocir_evaluation/vidore_colpali/` |
| 问题缓存 | `artifacts/route_v2_data/query_cache_v1/source_queries.pt` |
| D 训练/验证节点 | `artifacts/route_v2_data/d_nodes_v1/` |
| D 开发节点 | `artifacts/route_v2_data/d_nodes_dev_v1/` |
| 身份审计和准入回执 | 实验配置引用的 `artifacts/route_v2_data/` 下对应文件 |

不能只复制 `.pt` 后省略页面源文件：内部读取代码会复核源图签名。页面表与 manifest 可能包含本机路径，迁移前需检查是否可访问。如果必须更改路径或重新建立签名，应保留原材料，并记录新的配置与回执，不能关闭校验。

### 4.3 外部评价所需文件

绑定规则见 [route_v2_external_eval_v1.yaml](configs/experiments/route_v2_external_eval_v1.yaml)：

```text
data/raw/sciegqa_bench/9bdca77be633cc3259d7e3739d35b38ab00bf5d9/
└── SciEGQA_Bench.jsonl

artifacts/route_v2_external/
├── preparation_v1/20261007_152240/weights.json
├── full_prep_v1/20261008_222512/candidates.jsonl
└── encoding_v1/runs/20261009_141912/
    ├── manifest.json
    ├── queries.pt
    ├── pages/
    └── nodes/
```

还需要 `weights.json` 引用的 C、C-wide、D、D-no-text 各三个 seed 的 checkpoint，共 12 份，以及 manifest 引用的依赖材料。上图只是入口清单，不是完整分发包清单。E 的外部补充评价另需 E 权重及 EXP-017 原预测和统计文件。

目前 README 不提供独立缓存或权重包下载地址。没有这些材料时，可以安装环境、阅读实现并运行合成测试，但这些检查不构成论文数值复现。

### 4.4 重新编码需要的模型

- ColPali：`vidore/colpali` 及其 adapter 配置引用的基础模型。处理器与模型身份需一并保存；内部历史 revision 的绑定存在审计限制，外部以编码 manifest 为准。
- BGE-M3：`BAAI/bge-m3`，revision `5617a9f61b028005a4858fdac845db406aefb181`，CLS 池化、1024 维、归一化、最大长度 512。

模型需提前准备到本地，不能用最新版本代替。内部节点脚本使用用户目录下 `.cache/huggingface/hub/` 的固定 BGE-M3 snapshot 路径；仅设置其他缓存目录不一定会被读取。

正式训练和外部评分直接消费缓存，不重新运行视觉编码；缓存缺失时，不应期待训练脚本自动重建。

## 5. 实现检查

安装依赖后，先执行定向检查：

```powershell
./tasks.ps1 route-v2-exp1-tests
./tasks.ps1 route-v2-d-tests
./tasks.ps1 route-v2-exp3-tests
./tasks.ps1 route-v2-external-eval-tests
./tasks.ps1 route-v2-e-tests
```

这些任务包含相关静态检查和单元测试，检查评分、梯度更新、早停、融合形状、变体行为和评价统计。不启动正式训练，也不证明数据包完整或模型达到论文成绩。

## 6. 已保存结果复核

归档完整时，可先复核结果，无需重新训练：

```powershell
# EXP-014：A/B/C 开发结果及权重选择
./tasks.ps1 route-v2-exp1-result-check

# EXP-015：D 开发结果及权重选择
./tasks.ps1 route-v2-exp2-result-check

# EXP-017：外部保存预测、指标与统计
./tasks.ps1 route-v2-external-eval-verify

# EXP-018：E 补充结果
./tasks.ps1 route-v2-e-verify
```

核验脚本有以下路径与归档限制：

- EXP-014 绑定 `runs/retrieval/route_v2_exp1/20261006_162042/`。
- EXP-015 绑定 `runs/retrieval/route_v2_exp2_D/20261006_230924/`。
- EXP-017 查找匹配冻结配置的完成运行；同一配置出现多个完成结果时会报错，不会自动取最新值。
- E 查找匹配的训练与外部补充结果；当前报告逻辑还读取历史恢复记录 `recovery.json`，因此属于原归档复核入口，不能假定可直接验证所有新 E 运行。
- 内部复核包含 checkpoint 文件时间戳与开发评分开始时间的检查，复制归档改变时间戳可能影响这项检查。

成功要求退出码为 0，报告给出通过结论。复核会重新检查统计，但不重新计算模型分数。耗时取决于磁盘、硬件和材料规模；失败后检查首个异常，不通过改指标文件绕过验证。

## 7. 在固定缓存上重新训练

### 7.1 先核对运行依赖

| 实验 | 配置 | 主要依赖 |
|---|---|---|
| EXP-014：A/B/C | [route_v2_exp1.yaml](configs/experiments/route_v2_exp1.yaml) | 固定候选、页面/问题缓存、`verification` 回执 |
| EXP-015：D | [route_v2_exp2_D.yaml](configs/experiments/route_v2_exp2_D.yaml) | `baseline_run`、`preflight`、节点缓存 |
| EXP-016：变体 | [route_v2_exp3_attribution.yaml](configs/experiments/route_v2_exp3_attribution.yaml) | D 的 `base_config` 及 SHA256、`reference_run` |
| EXP-018：E | [route_v2_E_supplement_v1.yaml](configs/experiments/route_v2_E_supplement_v1.yaml) | D 基础配置及 SHA256；外部阶段另需 EXP-017 归档 |

**依次执行命令不会自动将新 A/B/C、D 的结果传给下一实验。** 下游配置仍引用历史运行。单独复现某个阶段可以恢复其历史依赖；若要所有实验沿新运行串联，需要另建配置版本，更新明确的路径与身份记录，并适配入口选择。当前脚本没有统一 `--config` 参数，不要添加不存在的参数。

新生成的检查回执也不会自动替换配置中的历史回执路径。不要将新文件覆盖到历史时间戳目录，不要关闭哈希检查。改动配置后，引用该配置 SHA256 的下游绑定也必须重新核实并记录。

### 7.2 A/B/C 与 D

第 4 节材料及上述绑定关系满足后执行：

```powershell
# 检查 A/B/C 输入，保存新的检查回执
./tasks.ps1 route-v2-exp1-verify

# 训练 C 的三个 seed，随后评价开发集
./tasks.ps1 route-v2-exp1

# 检查 D 输入，保存新的检查回执
./tasks.ps1 route-v2-exp2-verify

# 训练 D 的三个 seed，复用配置指定的 A/B/C 预测
./tasks.ps1 route-v2-exp2
```

回执写入 `artifacts/route_v2_data/exp1_verification/` 和 `exp015_preflight/`。训练结果分别写入 `runs/retrieval/route_v2_exp1/<timestamp>/` 与 `runs/retrieval/route_v2_exp2_D/<timestamp>/`。D 缺少开发节点缓存时会在训练前停止，不可用训练节点或全零节点替代。

### 7.3 容量和输入变体

```powershell
./tasks.ps1 route-v2-exp3
```

依次训练 C-wide、D-no-text、D-no-coord，每种三个 seed，共九次训练；全部选定 checkpoint 后统一评价 `source_dev`。输出位于 `runs/retrieval/route_v2_exp3_attribution/<timestamp>/`，原 A/B/C/D 结果从指定参考运行复用。

### 7.4 超参数和权重选择

| 参数 | 设置 |
|---|---|
| 随机种子 | 0、1、2 |
| 优化器 | AdamW |
| 学习率 / 权重衰减 | 0.001 / 0.01 |
| 最大 epoch | 30 |
| 每次更新 | 累积 4 个题—页单元；尾组按实际数量平均 |
| 温度 / 梯度裁剪 | 0.25 / 1.0 |
| 选权重指标 | `source_val` 的问题宏平均 `hit1@0.5` |
| 早停 | patience=5，严格改善才保存，同分保留较早 epoch |
| 数值设置 | float32、关闭混合精度和 TF32、启用确定性算法 |

最终模型不是按最低训练损失选择。开发集和外部数据不参与早停。训练时间取决于实际 epoch 和设备，从 `training_curves.jsonl` 查看每轮耗时与指标。

中断后保留 checkpoint、日志及失败记录。主训练入口没有统一断点续训开关，再次执行可能从头训练到新目录，应先检查运行状态。

## 8. 外部评测与 E 补充对照

### 8.1 EXP-017

```powershell
# 核对候选、缓存、权重、分母和身份
./tasks.ps1 route-v2-external-eval-preflight

# 冻结权重评分，不训练、不重新编码页面
./tasks.ps1 route-v2-external-eval

# 从保存结果复核
./tasks.ps1 route-v2-external-eval-verify
```

输出为 `runs/retrieval/route_v2_external_eval_v1/<timestamp>/`，论文对应归档为 `20261009_163938`。

准入成功应给出 `status: ready`，分母为 1,623 问题、837 页、1,941 单元、9,746 候选，并通过 12 个 checkpoint 检查。正式结果包含 A/B 各一个标签，以及四种训练方法各三个 seed，共 14 个标签、27,174 行逐单元预测。

**完成结果复用：** 同一冻结配置已有一个通过核验的完成运行时，入口返回 `status: reused`，不重新执行前向。再次执行不能称为独立重评分。需要独立运行时，应在单独副本中准备所需输入和权重，明确输出绑定并保存新记录，保留原归档。

### 8.2 EXP-018

```powershell
./tasks.ps1 route-v2-e-check
./tasks.ps1 route-v2-e-train
./tasks.ps1 route-v2-e-external
./tasks.ps1 route-v2-e-verify
```

| 命令 | 行为 | 输出 |
|---|---|---|
| `route-v2-e-check` | 检查结构、参数量、零初始化与合成样本行为 | `artifacts/route_v2_E_supplement_check/` |
| `route-v2-e-train` | 三 seed 训练，内部验证选权重 | `runs/retrieval/route_v2_E_supplement_v1/` |
| `route-v2-e-external` | 只新增 E 评分，复用 EXP-017 原预测 | `runs/retrieval/route_v2_E_external_supplement_v1/` |
| `route-v2-e-verify` | 复核历史补充结果，限制见第 6 节 | 标准输出 |

E 训练及外部入口也存在完成结果复用逻辑，需要区分 `reused` 与新计算。E 为事后补充，不能归入原预定主比较，其与 D 的差异也不能作严格单因素归因。

## 9. 从原始材料准备的入口

以下用于重新建立材料，**不是完整归档上全部重跑的必经步骤**。脚本需要原始表、页图、身份审计及本地模型，部分绑定历史准备目录。

| 阶段 | 任务 | 作用与限制 |
|---|---|---|
| 身份检查 | `route-v2-identity` | 外部元数据获取及身份审计，可能访问网络 |
| 角色与候选 | `route-v2-data` | 依赖既有审计、页面和缓存构造划分及监督，拒绝覆盖既有划分 |
| 内部问题编码 | `route-v2-queries` | 本地 ColPali 编码冻结角色的问题 |
| 训练/验证节点编码 | `route-v2-d-nodes` | 使用指定 BGE-M3 snapshot |
| 开发节点编码 | `route-v2-d-dev-nodes` | 单独编码开发节点，不评分 |
| D 输入回验 | `route-v2-d-verify` | 检查准备材料 |
| D 小规模训练 | `route-v2-d-smoke` | 固定样本更新诊断，会训练，不是只读检查 |
| 外部准备审计 | `route-v2-external-audit` | 检查外部准备身份与材料 |
| 外部全量解析 | `route-v2-external-full-prep` | 固定 837 页候选准备，依赖配置中的归档、工具和模型 |
| 外部编码 | `route-v2-external-encoding` | 页面、问题与节点缓存，不做模型比较 |

运行形式为 `./tasks.ps1 <任务名>`，底层调用见 [tasks.ps1](tasks.ps1)。

外部准备配置见 [route_v2_external_full_prep_v1.yaml](configs/tools/route_v2_external_full_prep_v1.yaml)，引用 [mineru_external_pages_v1.yaml](configs/tools/mineru_external_pages_v1.yaml)。后者记录 MinerU 4.0.10、ONNX CPU 后端及固定模型 revision，并保留八页准备阶段限制；全量阶段由独立配置控制。历史候选并非由 DeepSeek-OCR 生成。

编码配置见 [route_v2_external_encoding_v1.yaml](configs/tools/route_v2_external_encoding_v1.yaml)。从头准备还需核对 PDF/图像归档、页面映射、模型快照和阶段依赖，不能仅下载标注后跳到全量解析。新 manifest 的时间戳及哈希不会自动写入下游冻结配置。

## 10. 结果与指标

先检查 `run_info.json` 状态，再读取指标；存在一个指标文件不代表整体运行成功。

| 文件 | 内容 |
|---|---|
| `config.json` | 实际配置 |
| `run_info.json` | 状态、环境、耗时和错误 |
| `metrics.json` | 聚合指标与统计 |
| `predictions.parquet` | 逐题—页排序与指标 |
| `question_scores.parquet` | 逐问题分数，依运行提供 |
| `summary.md` | 结果摘要 |
| `training_curves.jsonl` | 逐 epoch 训练/验证记录 |
| `checkpoint_selection.json`、`seed_*_selection.json` | 权重选择和身份，形式依运行而定 |
| `preflight.json`、`input_verification.json` 等 | 输入核验回执 |
| `code/`、`workspace.patch`、代码身份清单 | 运行源码及未提交差异，依运行保存 |
| `result_verification.json` | 结果复核记录，依运行提供 |

还原历史代码需结合源码快照、patch 和身份记录，不能只使用当前 HEAD。字节 SHA256 与数值一致性是不同检查；自动换行转换、重新排版 JSON 都会改变哈希。

指标定义：

- **Top-1 / `hit1@0.5`**：首位候选与任一 gold 框的 IoU≥0.5。
- **Cov@5 / `cov@5`**：前五候选联合区域覆盖 gold 联合面积的比例，重叠面积不重复计算。
- **Gold Recall@5 / `gold_recall@5@0.5`**：前五候选与 gold 框按 IoU 降序做一对一贪心匹配，要求 IoU≥0.5，已匹配 gold 数除以 gold 总数；每个候选和 gold 最多参与一次匹配。
- **候选 Oracle@0.5**：全部固定候选中是否存在可命中任一 gold 的框，是该候选池的首位命中上限，不是模型性能。

先对同一问题的题—页单元平均，再按问题宏平均。训练方法报告三 seed 均值及 `ddof=1` 标准差，不能直接平均全部预测行替代此口径。

EXP-017 先平均三 seed 逐题分数，再按文档聚类 bootstrap 2,000 次，seed=0；三项主比较采用 Bonferroni 调整的百分位区间。E 的单项事后补充比较单独解释。

### 外部结果参照

以下为固定 SciEGQA 上的历史记录，单位为百分比，不是本次环境的重新运行结果。

| 方法 | Top-1 IoU≥0.5 | Cov@5 | Gold Recall@5 |
|---|---:|---:|---:|
| A | 33.7954 | 64.1249 | 57.0240 |
| B | 23.9063 | 60.1992 | 54.9908 |
| C | 21.3802 | 51.4124 | 46.9398 |
| C-wide | 23.3518 | 50.5222 | 46.4161 |
| D | 21.9450 | 54.6627 | 51.2939 |
| D-no-text | 30.7969 | 58.5998 | 54.3233 |
| E（事后补充） | 35.3563 | 61.5927 | 56.4387 |

D-no-text 相对 B、C-wide 的 Top-1 收益为 6.8905 和 7.4451 个百分点，原记录中的校正区间均高于零；未可靠超过面积规则，Top-5 指标也不占优。E 的补充成绩较高，但监督粒度和实际训练子集不同。结果不支持布局适配在全部对照、全部指标上均有优势的结论。

## 11. 常见问题

| 现象 | 检查事项 |
|---|---|
| 克隆后缺缓存或权重 | Git 不包含这些材料，核对第 4 节 |
| `CUDA device unavailable` | ColPali extra、驱动及本项目 `.venv` |
| 离线模型找不到 | 精确 snapshot、基础模型及脚本读取的实际路径 |
| 哈希或 manifest 不匹配 | 文件版本、换行、路径、归档完整性；不要删除校验 |
| 页图签名不匹配 | 页图与页面表是否对应，不能替换渲染版本 |
| patch 数量或特征维度错误 | 编码器、处理器及提示 token 拆分；不能直接换成 ColQwen 缓存 |
| 新训练权重未被下游使用 | 下游仍绑定历史运行，检查第 7.1 节 |
| `status: reused` | 复用了已完成结果，没有新训练或评分 |
| 改 batch、阈值或数据后回执失败 | 已构成新实验配置，应保存新身份与结果 |
| 换机器后数值不同 | 核对环境、精度、确定性设置及逐题结果，不能默认所有差异都是浮点误差 |

## 12. 相关实现与数据来源

- [ColPali](https://github.com/illuin-tech/colpali)：页面和问题多向量表示。
- [BGE-M3](https://huggingface.co/BAAI/bge-m3)：区域文本编码。
- [Snappy](https://github.com/athrael-soju/Snappy)：patch 相关性向区域传播的参考工作；本仓库 B 不包含其完整配置。
- [MMDocIR](https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset)：内部来源数据与布局标注。
- [SciEGQA-Bench](https://huggingface.co/datasets/Yuwh07/SciEGQA-Bench)：外部证据区域评价数据。

数据、模型和第三方组件分别遵守各自许可。复现实验应保留代码版本、输入身份、配置、权重选择和实际结果；已保存结果的复核与新模型运行应分别记录。
