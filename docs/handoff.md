#   工作交接记录（变化的进度）

> 用途：新开 Cursor 窗口时手动 `@docs/handoff.md`，让新会话接上当前进度。
> 约定：每次会话结束前更新本文件；本文件只写变化的进度，不写不变的规范（规范在 `.cursor/rules/` 与 `docs/RULES.md`）。
> 配套必读：`docs/MIGRATION_BATCHES.md`（批次清单）→ `docs/00-index.md`（SSOT 导航）→ `docs/PAPER_SPEC.md`（小论文执行规范）。

## 2026-10-03 新会话入口：旧路线暂停，新路线研究重定中

> Status: working。当前状态以本节为入口；下方旧日期节保留为历史，不直接执行其中的“下一步”。本节不是训练指令；route-v2已有working草案，尚未冻结或开训。

### 2026-10-08 SciEGQA全量候选准备ready（最新；未编码/评分）

- 最终审计`@artifacts/route_v2_external/full_prep_v1/20261008_222512/audit.json`为`ready`：1623题、837唯一页、1941题—页单元完整保留，837页通过、失败0、候选9746；候选文件实读9746行/9746唯一`page_id+layout_id`/覆盖837页，SHA256 `19dbd7257d696bca19859fd1a53e69520e3380590d5fe0445fac61d8d2518263`与审计一致。
- 最终运行复用835页、新处理2页。原26页尺寸失败源于小数PDF point边长的`round(×2)`与PyMuPDF真实`Pixmap.irect`像素边界不同，现按真实像素区间验收。两个90度页的MinerU输出为已旋转792×612 point frame，映射到1584×1224渲染且与3300×2550官方原图内容对齐；2/7候选、越界0。真实CropBox差异仍拒绝。
- 旧`20261008_145005`虽有837回执但最终收尾前中断，故`started`不算成功；另修复`splitlines()`误把候选文本内`U+2028`当JSONL换行、进而误报两行损坏的问题，按真实`\n`流式读取时旧候选全部合法。中断/最终异常现在记录stage/type/error并非零退出。
- 复用逐页核验固定归档与唯一成员、原始解析/渲染/原图哈希、内容映射和候选身份/计数/唯一性；缺行可从已记录来源链或哈希已验证原始解析重建，不重跑MinerU。最终定向Ruff和16测试通过。
- 本轮只完成外部候选准备；没有训练、向量编码、评分、Oracle或页面召回计算。下一轮最少输入见本节末：冻结配置、最终`audit.json`和`candidates.jsonl`；效果不得用于调参、删基线或换指标。详细失败链与坐标证据见`@experiments/2026-10-07-external-preparation.md`最新节。

### 2026-10-07 固定八页最终核对（历史；视觉/几何通过，文本接口当时阻塞）

- 助手通过Read目视检查既定8张叠图，8/8未见错页、旋转、整体偏移或异常截断；粗段落框不调整。没有把助手检查冒称用户人工签字。
- 已授权官方Images.tar下载完成、指定SHA256通过，只提取既定8页；原图2550×3300，渲染1224×1584，内容映射8/8通过。图像机器回执：`@artifacts/route_v2_external/preparation_v1/20261007_221908/`。
- 最终逐页视觉/标注坐标一致性/真实接口回执：`@artifacts/route_v2_external/preparation_v1/20261007_231625_final_review/`。0–1000的gold rel_bbox与0–1的解析框分开；内容支持原图→渲染x/y均乘0.48。8页几何/身份与标注坐标转换通过，无效果/Oracle计算。
- **需要外部文本接口补接，撤回本轮早期“无需修改”的表述。** 原D的实际`node_text`对image/table读取`ocr_text`，外部导出为null、真实解析内容在`text`，直接接入会丢图表文本。8页只含text/title，不能覆盖此路径。必须明确原生PDF/OCR来源并保留真实文本，禁止伪称纯OCR或混入生成描述；本轮未改冻结评分规则、候选或权重。
- 实际`page_layout`单页变长结构通过，真实节点mask=true；空文本应零向量并保留节点/缺失标记，不能当padding。未来padding节点mask=false；已核对融合源码softmax前屏蔽。没有运行网络前向或生成向量缓存。
- 最终状态`fixed_eight_geometry_reviewed_external_text_contract_blocked`，仍不具备全量条件。下一步先补外部文本来源适配，之后用已登记的`route-v2-external-final-review`复核（确切语法见`@docs/02-commands.md`）；全量入口目前尚未实现，撤回未实现任务名的执行建议。
- 最终定向Ruff及11项合成测试通过（1.58秒），冻结比较/解析配置、训练依赖锁未变；不修19个旧Ruff问题。完整记录见`@experiments/2026-10-07-external-preparation.md`。
- 全量计划必须核对全部837页身份、PDF/原图成员唯一性与哈希、rotation/crop/media、内容映射及候选接口，失败页保留并停止准入；本单文档8页通过不替代全量验收。尚缺全量任务/授权、向量缓存与容量预算；现有数据/模型可复用。本轮停止，无训练、评分、调参、重解析或全量。

### 2026-10-07 固定八页续接完成（历史；候选已导出，视觉与原图映射待验）

- 两份指定元数据回执的受控脚本访问已恢复，固定八页身份/清单哈希不变。复用中断前独立uv解析环境、PDF、八张渲染图和第一页原始解析，只补其余七页，没有重装或重复下载。
- 实际MinerU4.0.10、onnxruntime1.30.0、docvortex0.5.10；Basic/auto、ONNX CPU实际会话核验通过。模型`opendatalab/MinerU-4_models_onnx`固定revision `358310b4f64b95f9fefc372ad899356e4111f376`，逐文件身份已核验；工具包带附加许可义务，模型沿用组件许可，数据许可未明确。
- 产物：`@artifacts/route_v2_external/preparation_v1/20261007_200400/`。8/8页候选导出、50候选、8叠图；7页新解析/1页复用。逐页资源及失败历史见`@experiments/2026-10-07-external-preparation.md`最新节和产物回执；首复用页资源缺失，不能补造八页总时长。
- 解析器0–1框到当前144 dpi渲染像素的机器检查通过，坏框/越界/重复/空页均0；候选字段及到448模型画布转换通过，仅结构检查，无评分或向量缓存验收。auto文本可能来自原生PDF或OCR，不声称纯OCR或与MMDocIR原版一致。
- **完整验收未完成，仍不能进入全量。** Read读取`@artifacts/route_v2_external/preparation_v1/20261007_200400/overlays/2309.06983_p1.png`返回`permission denied`；Cursor规则仍排除图像，视觉检查0/8，未绕过或修改权限。原SciEGQA图像尺寸及其到PDF渲染的映射也未核验，不能称外部输入就绪。
- 新工具配置`@configs/tools/mineru_external_pages_v1.yaml`与原比较配置隔离；原比较配置保留历史状态，不回写其旧零页/安装禁令字段。训练依赖/锁文件、比较配置及既有权重身份清单前后哈希保护通过。定向Ruff和6项合成测试通过（1.47秒）；不重复元数据审计、不修19个旧Ruff问题。
- 文档与工程登记已更新，命令见`@docs/02-commands.md`。下一步仅需受控开放八张叠图或人工检查，并补齐原始图像映射；本轮停止，未训练、评分、Oracle、视觉编码或837页全量处理。

### 2026-10-07 17:12 固定八页工程验收授权（历史；当时回执访问阻塞）

- 已获本轮独立uv工具环境安装MinerU/必要模型及固定八页处理授权；训练环境依赖/锁文件不改，冻结比较配置与权重不改，禁止全量、训练、调参或外部评分。
- 指定manifest.json和audit.json读取均返回`permission denied`，无法核实既定八页身份；未绕过访问限制或重新选页，安装/下载/渲染/解析均未启动。这是访问阻塞，不判定数据损坏。
- 官方资料确认MinerU4.0系列存在Basic ONNX/CPU路径并声明Windows支持；具体发布包版本/许可/坐标契约尚未核完，未安装未经确认的包。uv查询的3.12解释器指向Anaconda，未使用；uv的pip index子命令不可用，未试装其它版本。
- 八页0/8完成；实际时长、内存、候选数及全量预算未测，仍不具备全量准备条件。需先恢复两份精确回执的受控访问。核查依据与错误记录见`@experiments/2026-10-07-external-preparation.md`。

### 2026-10-07 SciEGQA外部比较冻结与输入准备（历史；硬阻塞停止）

- 本轮仅授权比较计划、元数据适配和条件满足时的固定八页工程验证；禁止训练、调参、效果/Oracle评分及全量解析/视觉编码。没有安装依赖、下载模型或替换候选来源。
- `@configs/experiments/route_v2_external_v1.yaml`已frozen：D-no-text为主候选、D为文本对照，保留A/B/C/C-wide；D-no-text来自EXP-016开发选择，尚无独立验证，不改论文贡献结论。主比较D-no-text−A/B/C-wide及三项Bonferroni校正已预定，原D比较仅次要分析。
- 四训练方法各用既有seed0/1/2的source_val最佳权重；精确registry索引核对12份权重身份，未加载张量。绑定清单`@artifacts/route_v2_external/preparation_v1/20261007_152240/weights.json`。
- 固定SciEGQA revision及全部1623题，清点80文档/837唯一证据页/1941题—页单元，保留所有题身份与失败状态。最终格式核验0失败；归一化框为0–1000。清单和回执：`@artifacts/route_v2_external/preparation_v1/20261007_155402/`；完整哈希及曾误用0–1的核验记录见详情，不修改旧产物。
- 当前直接阻塞是项目`.venv`没有可执行、模型身份已绑定的MinerU候选生成流程。MMDocIR原版面框来自MinerU，但生成版本/模型/参数未知；不能声称同版。原图尺寸及渲染变换尚未验收、保持null，也不允许猜测。
- 八页ID按文档/整数页号固定；渲染0/8、解析0/8，实际处理耗时/显存/候选数量均未测，无法给可靠全量时长。没有用gold生成或调优候选，没有静默删题；数据许可仍未解决。
- 新命令已定点登记，新增适配与冻结配置相关Ruff通过、5项测试通过（1.44秒）；未全仓check，未处理19个旧Ruff问题。命令见`@docs/02-commands.md`。详情、固定清单、待批准工具方案及预算限制见`@experiments/2026-10-07-external-preparation.md`。本轮到此停止；比较冻结不代表测试输入就绪或允许正式外测。

### 2026-10-07 EXP-016最小归因完成（历史；已停止）

- 正式run：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_exp3_attribution/20261007_135013/`。九次从头训练共91epoch，九份source_val选择全部确定后一次统一dev；A/B/C/D保存预测完全不变，无外测/调参/重跑。
- 配置`configs/experiments/route_v2_exp3_attribution.yaml` frozen，哈希绑定原EXP-015预算且原配置未改。C-wide隐藏1062、273318有效参数；D-no-text只置零文本；D-no-coord只置零编码器坐标，保留真实W/邻域/cover_mass。
- 主指标三seed均值：C-wide0.4296925566、D-no-text0.5566747573、D-no-coord0.5037486516，原D0.5296521036。D减三变体点估计依次+0.0999595469/−0.0270226537/+0.0259034520；预固定Bonferroni 98.333%文档区间依次[0.0438330675;0.1559586798]/[−0.0551388889;−0.0023474178]/[−0.0025943396;0.0541463415]。
- 三项共同解读：单纯增宽普通适配器不能解释D收益；该预算下去文本反而更好；显式坐标经多重校正证据不足，且不是全部空间信息消融。仅开发归因，不证明新颖性/泛化。D相对两个输入消融的Cov@5与gold召回@5均更低，须同时披露。
- 相关Ruff和20测试通过；正式入口内部读回检查选择、预测、逐题分数、三项统计和输入身份通过，exit0；无NaN/Inf/显存超限。未全仓check、19旧Ruff不改。代码commit起点`1961493b6b7f655459ffb24fe0b75536b0075a66`，本轮未提交。
- 五件套/定点代码快照/九份选择及训练日志齐全；详情及指标来源见`experiments/2026-10-07-exp-016-attribution.md`和run的metrics.json。完成后已停止，不自动调参、替换D、增变体或外测。

### 2026-10-06 23:14 EXP-015正式D开发比较完成（历史；已停止）

- 本轮授权补dev节点并执行一次D三seed正式训练/开发比较。配置`route_v2_exp2_D.yaml`已frozen；train/val原缓存未变，独立dev缓存457页3904节点（3581非空、323缺失、23截断），编码身份/规则一致。
- 完整run：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_exp2_D/20261006_230924/`。seed0/1/2实际6/7/7epoch，最佳1/2/2；仅val选权重，全部选择后一次dev评分；A/B/C原预测值完全不变。
- D均值0.5296521036±0.0250218861，C均值0.4253101402；D−C=0.1043419633、95%文档bootstrap[0.0552878179,0.1521909233]，达到预定推进标准。D−A=0.0127831715但区间跨0，不能宣称可靠胜过面积基线。Top5 Cov/gold召回均提高，不是全面创新或独立泛化证据。
- 五件套/代码身份/输入哈希/三seed权重/逐epoch gate残差梯度齐全。32相关测试通过；保存结果回验4360unit预测、3296逐题分数、20轮日志和配对统计通过。无NaN/Inf/显存超限。未运行全仓check，19旧Ruff问题仍披露。
- 详情与原文：`experiments/2026-10-06-exp-015-route-v2-D.md`及run的metrics.json；registry已登记EXP-015。仅source_dev开发结果，不容量匹配（D273410/C66176）。未读SciEGQA、未重训C、未重复smoke。
- 已结束；不自动调D、加loss、扩数据、消融或外测。后续需新的明确任务。

### 2026-10-06 夜间 EXP-015 D准备与技术验收完成（历史；未正式训练）

- 文本来源按固定官方数据卡落实：正文/标题/公式取text，图/表取ocr_text，禁止vlm_text回退；逐节点OCR引擎版本未提供，来源限制如实记录。
- 仅train/val候选节点缓存：`artifacts/route_v2_data/d_nodes_v1/`，1067页/11972节点，11116非空，train/val覆盖约92.845%/92.856%；本地既有BGE-M3冻结1024维CLS向量，未下载或编码页面。
- D组合原TextLayoutEncoder与SparseLocalFusionV2，TopK4，W_raw cover/W_attn/cover_mass，273410可训练参数；公共训练/评分支持可选layout输入，C旧路径及EXP-014代码快照/结果保留。
- 固定16题/19unit、seed42、200步D smoke通过：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_d_smoke/20261006_220102/`。首步上游零梯度、后续学习信号及参数变化已验证；无NaN/Inf，提示/空patch保留。仅训练侧技术验收，非泛化/创新结果。
- 最终相关Ruff通过、30测试通过，节点缓存全部回验通过；本轮未运行全仓check，19旧Ruff问题未修。
- 唯一配置`configs/experiments/route_v2_exp2_D.yaml` working、正式入口已准备但未执行；同EXP-014预算，主比较D−C，保留D−A/B与Top-5差值。**唯一数据准备阻塞：source_dev节点缓存未在本轮授权范围生成**，正式训练前需同身份/规则补齐并绑定哈希再冻结。
- 详细来源、覆盖、smoke原文与缺项：`experiments/2026-10-06-exp-015-preparation.md`。本轮结束，不启动D正式训练、不重评dev、不运行外部测试。

### 2026-10-06 EXP-014 route-v2-exp1 完成（历史；已停止）

- 用户授权A面积/B冻结传播/C PatchAdapter三seed正式开发比较；配置`configs/experiments/route_v2_exp1.yaml`与协议第9节在开训前冻结。
- 完整run：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/runs/retrieval/route_v2_exp1/20261006_162042/`。训练1002unit，val374题/448unit，dev412题/545unit。seed0/1/2实际14/7/11epoch，选择9/2/6epoch；全部checkpoint确定后才一次开发评分。
- 主指标A=0.5168689320、B=0.3430420712、C三seed均值=0.4253101402；C−B=+0.0822680690、95%文档bootstrap区间[0.0150793651,0.1488425926]，达到本轮推进标准；C−A=−0.0915587918，未超过面积强基线。C的Cov@5/gold召回@5低于B，不能称全面改善。
- 五件套、逐轮日志、独立权重、逐题预测、工作区代码快照与输入哈希齐全；只读复核2725预测行、32epoch日志、checkpoint和配对统计通过。定向45测试通过；全仓仍19既有ruff错误。
- 原文数字、辅助指标与限制见`experiments/2026-10-06-exp-014-route-v2-exp1.md`和上述run的`metrics.json`；registry已登记EXP-014。仅开发结果，没有外部测试、D创新或页面召回保持证据。
- 本轮结束。未训练D、未扩数据、未开启第二轮参数调整；后续行动需要新的明确任务。

### 2026-10-06 问题缓存与固定 smoke 完成（历史；该轮到此停止）

- 本轮明确授权仅编码非隔离来源问题并完成既有 smoke；未启动 route-v2-exp1、Visual-CoT 或模块 D，未读取/评分 SciEGQA 外部测试。
- 缓存 `artifacts/route_v2_data/query_cache_v1/source_queries.pt` 已生成；1613 题与冻结 manifest 精确匹配，train/val/dev=826/375/412。源/manifest/模型/processor/token/向量哈希已绑定，复用校验通过且文件未变。
- smoke：`artifacts/route_v2_smoke/20261006_153418/`，固定 16 题、19 unit、CPU、200 步，loss 下降、梯度有限非零、参数变化及数值稳定性均通过。全部原文数字与官方代码借鉴差异见 `experiments/2026-10-04-route-v2-data.md` 第 9–10 节；仅训练集诊断。
- 定向 ruff 与 38 项测试通过；全仓 check 仍有既有 19 个 ruff 错误，因而未执行全仓 pytest。
- A/B/C 的缓存与 smoke 技术前置具备，但正式实验配置仍需预先冻结：C 的正式训练预算/学习率/预定 seed、source_val 选择规则、source_dev 比较与访问计划、主比较/最小有意义差值/页面非劣界限及正式 task/config/五件套登记。不能把 smoke 的超参自动当作正式实验冻结值。本轮不继续。

### 2026-10-04 route-v2 数据准备完成，smoke 被问题向量缓存拦下（历史）

- 用户授权：MMDocIR evaluation 改作 route-v2 训练/开发池。Codex 已暂停，由 Claude 原地接手。协议见 `docs/ROUTE_V2_PROTOCOL.md`，数字见 `experiments/2026-10-04-route-v2-data.md`。
- 已完成：
  - data-roles-v1 划分（train 169 篇/826 题、val 43/375、dev 91/412、quarantine 10/45）
  - 坐标审计通过
  - 区域单元审计（局部 loss 可用 train 1002 unit/786 题）
  - 监督可视化
  - v2-loc-1 指标（`docs/PAPER_SPEC.md` 第 8.1 节）
  - 对照 A/B/C 的代码
- 重要发现：页向量是图像在前，旧 `[7:]` 切片让所有旧 patch 级区域分数错位 7 格。旧结果保持原样，解读时注明。
- 阻塞：smoke 缺 `artifacts/route_v2_data/query_cache_v1/source_queries.pt`。需要用户批准后，用现有 ColPali 编码 1,613 题的问题向量。
- 已知问题：旧脚本 ruff 19 错；`test_box_ranker.py::test_guards_reject_test_eval_and_coverage_label` 失败；不要用 `-ExecutionPolicy Bypass`。
- 下一步（待批准）：先编码问题向量 → 重跑 `./tasks.ps1 route-v2-smoke` → 冻结 route-v2-exp1（A/B/C，source_dev 只评一次）。

### 2026-10-04 外部建议复核后更新

用户要求核查 `C:/Users/WenJing/Desktop/模型回答.txt` 并落实合理修订。已建立 `docs/ROUTE_V2_PROTOCOL.md`（working草案），证据与逐项判断见 `experiments/2026-10-03-route-v2-review.md`。优先验证保留ColPali、真实OCR与区域监督的融合，但数据重定、外部测试、loss和数值Gate尚未冻结/执行。

确认旧adapter类型丢失、归一化W行和coverage退化，以及旧judge的IoU未筛同页。训练和评测的文本输入实际上都为零。旧“失败只因弱监督”的归因应收回；旧Area未达目标的结果不变。LN是设计风险，未证明是根因。代码新增显式V2、输入来源策略和同页IoU工具，旧训练脚本/权重/指标结果保留，新runner尚未接入。70项定向单测通过、src/tests ruff通过；全局check被既有scripts的19个错误阻塞，详见审查记录第6节。

### 1. 用户目标、决定与执行边界

- 目标仍是有真实网络修改/可学习模块的方法型小论文，服务于视觉文档检索与证据定位大论文；用户不希望只写失败分析论文。导师正式验收条件仍需本人确认，不能承诺毕业或投稿结果。
- 原研究问题是在不裁剪页面、不重复视觉编码、保持MaxSim接口的条件下，利用OCR/Layout改善页内证据定位。重定路线时须明确哪些约束继续保留、哪些需要修订；接口兼容不等于页面召回不变，给定正确页的区域定位也不等于端到端检索。
- 用户已要求暂停旧路线：不再盲调2-R或原融合、不默认扩到400题、不边试边改变指标。正在精读Snappy、RegionRAG，重新考虑监督、候选区域、骨干和任务。
- 用户已明确提出：将MMDocIR原evaluation（包括旧test部分）改作新路线的有标注训练/开发来源，不再用它作新路线最终测试。这是新方向，不是已执行的数据迁移；不能用旧文档中的数据分工永久否定用户的新决定。
- 独立route-v2草案已建立，仍需落实并冻结数据角色、按文档划分和外部测试隔离。保留旧冻结文件、权重和运行记录；原test被用于训练后不得继续声称它是新路线独立测试。
- BBox-DocVQA是外部评测候选，ColQwen3-4B是骨干候选，Visual-CoT是现成区域监督候选。均未在本轮确认可用或完成接入；跨数据集文档去重、实际checkpoint和12GB资源可行性仍待核实。
- 最近任务是审核外部模型意见并修改合理内容，已完成文档与独立代码版本修订。前文“最多16题/200步”等模板仍仅为建议，不代表已运行；本轮未训练、下载、编码或处理旧test数据。
- 不能因打不过面积规则就删除它。可在新任务中预先定义合理主/辅指标，但不能事后选指标、选分母或隐藏强基线。

### 2. 已完成的事实（证据优先于registry的note）

| 阶段 | 实际状态 | 必看证据 |
| --- | --- | --- |
| 2-R | 6特征线性框排序头，P不变；EXP-009的397/401个Top-1是最大框，未证明学习增益。EXP-011不能写全面优于EXP-009。已停止。 | `experiments/2026-09-28-phase2r-area-bias-frozen.md`、`experiments/2026-09-28-phase2r-comparison.md`、`experiments/2026-09-28-phase2r-stop-frozen.md` |
| patch融合 | 节点编码、W、TopK局部注意力、残差MLP和gate已实现；形状/显存/反向传播测试及一次正式ArxivQA训练均已完成。Area@1/5=0.296199/0.714743，低于面积0.467264/0.772670。 | `experiments/2026-09-29-fusion-arxivqa.md`、`experiments/2026-09-29-fusion-failure-audit.md` |
| 人工标注pilot | A/B各40条，已有模型辅助标注和归档/诊断，但不是40条均验收通过。Jaccard约0.8357，分母35，完全一致26/35；校准题ann-0004/0018不计独立一致率。存在pending/状态矛盾及语义分歧。 | `experiments/2026-09-30-region-ann-ab-diagnosis.md`、`experiments/region_annotation/annotation_protocol_v1.md` |
| 新路线 | route-v2草案与兼容旧版的代码修订已建立；未生成新数据划分、未训练、未评测效果。 | `docs/ROUTE_V2_PROTOCOL.md`、`experiments/2026-10-03-route-v2-review.md` |

pilot诊断的面积Hit@1：A=0.8919（37题）、B=0.8158（38题），均高于当时无训练语义对照；这是人工正框诊断，不是官方Area。原始标签与过程记录不足见报告。不自动裁定、不取并集/交集充当gold、不把修标签当成恢复旧路线的必经任务。

必须防止的旧结论误读：

1. registry中的“算涨”仅指超过当时fixed，不等于超过面积，不证明可学习模块有效。
2. 原融合训练用页级正负监督，文本全零。失败说明该实现未达目标，不证明所有弱监督或融合方法必然失败。
3. 旧区域评测在正确页上进行：415题页级/401题区域。页级R@1/5/10=264/371/392来自复制冻结页序，P'未参与页级重排，不能据此证明P'保持检索能力。
4. Area@K中的K是候选框数。当前`recall_layout`累加Top-K框与同页gold的交集面积，再除以gold面积总和；不是取最大，也不是去重并集，理论上可超过1。IoU是交并比，须单列Top-K与命中阈值。
5. 旧IoU计数与后来重放不一致：fixed 130/136、geom 214/220。审计尚未解释差因，不得混为统一对照。
6. 人工v1标签是“所有可核实直接证据候选”，不是最小充分集合，也不是精确gold框或Area软标签。full=单框足以回答，partial=有直接证据但单独不足；多个独立充分框时cross_box=false。

### 3. 阅读顺序（不要求打开全部历史数据）

1. 本节；再读`docs/RULES.md`、`docs/00-index.md`，运行命令前读`docs/02-commands.md`。
2. `docs/PAPER_SPEC.md`第2.3b/2.4、5、8节；`docs/THESIS_SPEC.md`第2、4、6、11节；再读`docs/ROUTE_V2_PROTOCOL.md`。两份规范已标明历史条款范围，新方案以working草案区分，未冻结或训练。
3. 上表两份失败证据与pilot诊断；再按`experiments/registry.csv`定位对应run。需要时才读已允许范围的产物，不只看note。
4. 原论文：
   - `C:/Users/WenJing/Desktop/论文第三阶段阅读/Spatially-Grounded Document Retrieval via Patch-to-Region Relevance Propagation.pdf`
   - `C:/Users/WenJing/Desktop/论文第三阶段阅读/RegionRAG Region-level Retrieval-Augmented Generation for Visual Document Understanding.pdf`
5. 实现（解释现状时阅读）：`src/layoutpatch/retrieval/rerank/box_ranker.py`、`src/layoutpatch/layout/nodes.py`、`src/layoutpatch/layout/correspondence.py`、`src/layoutpatch/retrieval/fusion/sparse_fusion.py`、`src/layoutpatch/retrieval/propagation.py`、`src/layoutpatch/retrieval/region_pooling.py`、`src/layoutpatch/evaluation/region_metrics.py`、`scripts/train_fusion_arxivqa.py`。不存在此前口头说的`src/layoutpatch/fusion/local_fusion.py`。

### 4. 文献学习所得与仍待核实的问题

以下为本对话读原文所得，不是已复现结果；新会话应定位原文核对，而非只引用本摘要。

- Snappy（第5–6页方法、第9–10页实验）：问题-patch相似度传播到OCR候选；主实验是给定正确页的定位，59.7%是ColQwen3-4B在BBox-DocVQA的IoU@0.5，不是我们的Area或页面Recall。两阶段ANN候选检索不等同原MaxSim全库排名，不能声称主实验验证了页面召回保持。
- Snappy待核查：归一化IoU公式与P50/max实验配置的关系；487失败样本与1619主表分母；随机6.7%来自约1/15的简化估计，非已核实的逐题随机实验。候选数与可命中候选数都影响随机命中概率。
- RegionRAG（第3–6页、第10–11页附录）：约98k Visual-CoT区域标注+122k VisRAG页级数据；全局+局部对比，Qwen2.5-VL-3B LoRA；局部GT框约束patch；显著性+BFS生成框，现成生成器不训练。全局逐维max pooling不等同query-token MaxSim；生成端使用区域图像，不能直接继承我们不裁剪的全部承诺。
- RegionRAG主要指标是页面检索、生成准确率和token成本；其区域相似度表不等于严格框IoU验证。复用其loss属于迁移对照，新增模块贡献需同骨干同监督消融。
- 先前“只有自标可行”的意见不再成立：Visual-CoT等派生区域标注值得核实；原版QA数据没有答案框不代表派生集也没有。

### 5. 新会话的第一项任务

先读本节10月4日更新、外部建议核查记录和route-v2草案，避免重复形状/显存探针。下一项优先核实外部评测的版本、获取与独立性，并准备新协议缺项的明确实现/验证计划；旧IoU差异须在限定dev范围逐题追因。按最新用户指令执行，不把草案或代码单测当新数据已划分、有效性已证明。无需重复询问是否允许讨论MMDocIR数据角色重定。

先确定任务、监督和独立评测，再选网络。下一轮执行应以具体新协议和用户执行指令为准，不沿用下面旧日期节的自动下一步。

## 2026-09-28 历史接续记录（含后续追加；只作追溯，以2026-10-03置顶节为当前入口）

- A/B 40 题 `region-ann-v1` 已只读验收并按字节归档，不是开训许可，不扩到 400。A 哈希未变，复用 `experiments/region_annotation/archive/2026-09-30_annotator_A_v1/`。B 新归档 `experiments/region_annotation/archive/2026-09-30_annotator_B_v1/`。独立副本：`labels_annotator_A_v1.jsonl`、`labels_annotator_B_v1.jsonl`。两边格式都未过：A 的 ann-0378/0380 pending 字段非 null；B 的 ann-0317 pending 带已选框，ann-0373 skipped 却 cross_box=true。独立 Jaccard 均值 0.8357（分母 35，校准 ann-0004/0018 除外），完全一致 26/35。无训练对照里面积 Hit@1 仍高于 iou_mass / region MaxSim。唯一下一步：先修标签/协议。诊断：`experiments/2026-09-30-region-ann-ab-diagnosis.md`。未训练。未读 `dev_eval`/`test_eval`。
- A 的 40 题 `region-ann-v1` 先前已单独验收归档；本轮哈希复核相同，不重当新来源。旧 `labels_annotator_A.jsonl` 仍未覆盖，manifest 未写入。

- EXP-009 算涨。范围只写 ArxivQA 单域头，在多域 dev_eval 上这一次。记录：`experiments/2026-09-28-exp-009-phase2r-arxivqa.md`。
- EXP-010 不算涨。范围只写 DUDE 单域头，在多域 dev_eval 上这一次。记录：`experiments/2026-09-28-exp-010-phase2r-dude.md`。
- EXP-011 算涨。范围只写 ArxivQA+DUDE 混训头，在多域 dev_eval 上这一次。记录：`experiments/2026-09-28-exp-011-phase2r-arxivqa-dude.md`。Run：`runs/retrieval/mmdocir_phase2r_arxivqa_dude/20260928_151348/`。
- 当前头是 `artifacts/phase2r/arxivqa_dude/ranker.pt`。不要改 w、b。不要覆盖 `artifacts/phase2r/arxivqa/ranker.pt` 和 `artifacts/phase2r/dude/ranker.pt`。
- test_eval 未打分。不读 test_eval。不编新页。不建 fusion/。不改四池 id。不改 recall_layout。不改三轮 metrics.json。
- 比较表已落盘：`experiments/2026-09-28-phase2r-comparison.md`。表用法已写明。
- 401 是现行 matched 题单，不是第二套口径。391 是旧表重数。证明：`experiments/s2_splits/phase2r_gap_proof.json`。
- 混训 11575 比 9241+2312 多 22。多的是编码前被“至少一框”筛掉、后来页缓存又齐的题。不是丢页，不删题。
- 逐题重算与三份旧 Area 逐位一致：`experiments/s2_splits/phase2r_per_question_summary.json`。混训对 ArxivQA 有 398/401 题相同，不能写全面优于。
- EXP-012 算涨。无文本对照。Run：`runs/retrieval/mmdocir_phase2r_arxivqa_notext/20260928_192725/`。不替换当前头。
- EXP-013 geom:area Area@1 0.46726432578302896，Area@5 0.7726699451254816，算涨。
- EXP-013 geom:center Area@1 0.29591024029859686，Area@5 0.6243802678852584，不算涨。页级仍是 371/415。
- 文本特征不是 Area@1 涨分来源。当前头仍是 arxivqa_dude。
- EXP-009 与 geom:area：Area@1 分数相同 399，Top-1 下标相同 397，Area@5 分数相同 394，Top-5 下标集合相同 383。文件：`experiments/s2_splits/phase2r_geom_area_match.json`。
- 独立重放一致题数 401。文件：`experiments/s2_splits/phase2r_geom_area_replay.json`。当前头仍是 arxivqa_dude。
- 397/401 的 Top-1 是最大框；平均 Area@1 相同来自 01393 与 01408 抵消。当前头仍是 arxivqa_dude。先不打 test_eval。
- Area@1 结论已冻结。文件：`experiments/2026-09-28-phase2r-area-bias-frozen.md`。
- 最佳候选框是最大框 202/401。最大框与 gold 的最大 IoU≥0.5 是 217/401。文件：`experiments/s2_splits/phase2r_max_box_gold_iou.json`。当前头仍是 arxivqa_dude。先不打 test_eval。
- IoU≥0.5：fixed:iou_mass 130/401，EXP-009 214/401，geom:area 214/401。文件：`experiments/s2_splits/phase2r_iou_hit.json`。当前头仍是 arxivqa_dude。先不打 test_eval。
- IoU 结论已冻结。文件：`experiments/2026-09-28-phase2r-iou-hit-frozen.md`。
- 2-R 已停止。停止文件：`experiments/2026-09-28-phase2r-stop-frozen.md`。不打 test_eval。当前头仍是 arxivqa_dude。
- Snappy 三行：max Area@1 0.08253863585117388、Area@5 0.4175999466104787、IoU 45/401；mean Area@1 0.0899524795180662、Area@5 0.4129556803468502、IoU 47/401；iou Area@1 0.22050796570772077、Area@5 0.6880808278948266、IoU 105/401。
- 论文诊断草稿已落盘：`docs/paper-draft-notes.md`。当前头仍是 arxivqa_dude。2-R 保持停止。
- 失败记录：`experiments/2026-09-29-phase2r-failure-note.md`。融合就绪：`experiments/2026-09-29-fusion-readiness.md`。2-R 保持停止；融合未批准。
- 融合形状 smoke test 已完成。`./tasks.ps1 check` 被既有 ruff 错误阻塞，pytest 未执行。新增文件单独 ruff 通过。正式训练未批准。test_eval 未读取。
- 融合显存探针完成/因真实缓存或硬件条件停止；正式训练仍未批准；test_eval 未读取。
- 融合显存探针已复核；训练数据/监督审计完成；正式训练仍未批准；test_eval 未读取。
- 融合反向传播 smoke test 已完成。4 对 / 8 页，3 步，loss 有限且下降，梯度非零，空 patch 保持原值。权重只写到 `artifacts/probe/fusion_train_smoke/smoke_state.pt`。未覆盖任何 `ranker.pt`。不是正式训练。未读 test_eval。记录：`experiments/2026-09-29-fusion-train-smoke.md`。
- 第一次正式融合训练已完成。ArxivQA 单域。`train_fit` 9241 / `train_dev` 1592。最好第 2 轮。dev_eval Area@1 0.29619925776872813、Area@5 0.7147430258823292，低于 geom:area。页级 R@5 371/415。未通过 dev Gate。未读 test_eval。run：`runs/retrieval/mmdocir_fusion_arxivqa/20260929_155042/`。记录：`experiments/2026-09-29-fusion-arxivqa.md`。
- ArxivQA 融合 dev Gate 未通过；失败审计完成；正式扩展训练未批准；test_eval 未读取。记录：`experiments/2026-09-29-fusion-failure-audit.md`。结论 C：接线正确，页级弱监督未迁移到区域定位。未训练 fusion = fixed:iou_mass。不继续训练。
- 当前 fusion 已确认是弱监督迁移失败；替代网络路线审计完成；未批准新训练；test_eval 未读取。记录：`experiments/2026-09-29-fusion-route-decision.md`。推荐重定方法（无框级标签）；query 条件 MIL 仅备选；监督排序当前不可行。
- 现有页级弱监督已确认不足；方法型论文路线审计完成；新训练未批准；test_eval 未读取。记录：`experiments/2026-09-29-method-route-decision.md`。唯一推荐：先在 train_fit 补少量独立框标注，再做面积去偏排序；不同时开 MIL。本地提交 `f946a1d` 未推远程。
- 独立区域标注方案已落盘，不是开标许可，不是开训许可。协议：`experiments/2026-09-29-region-annotation-plan.md`。待标清单 400 题全是 `pending`：`experiments/region_annotation/arxivqa_train_fit_manifest.jsonl`。空模板：`label_schema.json` / `label_template.jsonl`。未开始人工标注。未训练。未读 test_eval。
- 40 题区域标注 pilot 材料已准备；尚未完成人工标注；未训练；test_eval 未读取。清单：`experiments/region_annotation/arxivqa_pilot_manifest.jsonl`。材料：`experiments/region_annotation/pilot_materials/`。说明：`experiments/region_annotation/annotation_protocol_v0.md`。记录：`experiments/2026-09-29-region-annotation-pilot.md`。
- 40 题本地标注流程已准备并做过格式检查。独立待填文件：`experiments/region_annotation/labels_annotator_A.jsonl`。工作簿：`experiments/region_annotation/pilot_materials/workbook.html`。40 题仍全部 `pending`。未开始人工标注。未训练。test_eval 未读取。
- 40 题 HTML 标注工具已可给 A/B 两位初学者分开使用：复选框、cover_ok、无合适候选、跨框、备注、导入/导出 JSONL。浏览器不写回仓库。协议仍是 `region-ann-v0`。不确定保持 pending。未训练。test_eval 未读取。

## 2026-09-27 新窗口接续（已归档，不再更新）

- 当前目标：一篇可投稿小论文。要有可训练参数、独立训练数据、dev/test、三指标同报、明确对照。见 `docs/PAPER_SPEC.md` 第 2.4/2.6 节。B1/B2 只作大论文诊断附录，不单独投稿。
- 叙事页：`docs/paper-progress.md`。规范仍以 `docs/PAPER_SPEC.md` 为准。数字以 `experiments/registry.csv` 和各证明文件为准。
- 已冻结、不要重做：泄漏剔除（`experiments/s2_exclusion/`）、四池划分（`experiments/2026-09-26-dev-test-split-frozen.md`）、2-R 设计（`experiments/2026-09-26-phase2r-design-frozen.md`）。
- 训练仍禁止。不建 `fusion/`，不写 `train_fusion.py`，不用 evaluation gold 构造 `y(c)`，不用 `T_oracle≥0.5` 过滤 train，不读 `test_eval` 分数，不下载新模型。
- 编码已批、尚未执行：只编 `train_fit` 的 ArxivQA（正负页都至少 1 框，9241 题 / 7112 页 / 外推 7.70 小时），写成 ColPali 页向量 `.pt`。这不是开训。其余域先不编。
- 给下一个对话的执行令见本节末「交给下一个对话」。旧「下一步」代码块已过期，不要按它重跑 1A/1B/1C，也不要因为它禁止一切训练代码而删掉已有的 `rerank/box_ranker.py`。

### 项目是什么

LayoutPatch 要在 ColPali 的页面小块向量上，利用 OCR 框做页内证据定位。评测集页向量已经算好。现在要训的不是改写这 1024 个小块的大融合网，而是一个小打分层：冻结小块分 + 框几何 + 本机 `BAAI/bge-m3` 文本相似度。训练集没有框级标准答案，所以损失只能是「正页的框整体高于负页的框」。

### 已完成（不要重做）


| 步       | 结果                                                                                                          | 证据                                                |
| ------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| 页级四基准   | ColPali R@5=0.8390，Hybrid 0.7883，BGE-M3 0.7750，BM25 0.7521                                                  | EXP-001/003/004/008                               |
| 1B / 1C | 旧 IoU 口径 B=45、规则消解 0。现行主口径是官方 Area：Oracle@1=0.9136，fixed:iou_mass=0.2787，gap=0.63 只观察                       | EXP-007-S1，THR-B                                  |
| 泄漏剔除    | 65319 题删 118，剩 65201。页图 md5 复用 0。剔除后与评测文档名、问句交集都是空                                                          | `experiments/s2_exclusion/exclusion_proof.json`   |
| 四池      | seed=42，按文档切，不按域切。train_fit 57062/25577，train_dev 5400/713，dev_eval 415/93，test_eval 1243/220。跨文档正负页剔除 2739 | `experiments/s2_splits/split_proof.json`          |
| 2-R 设计  | 方案 A：三组特征全开，K=4 只进损失，早停 2 轮，batch 32。Area 只在 gold 页全部候选框上重排                                                 | `experiments/2026-09-26-phase2r-design-frozen.md` |
| 代码骨架    | `src/layoutpatch/retrieval/rerank/box_ranker.py`，`scripts/train_phase2r.py`。缓存不在就退出                         | 未开训                                               |
| 测速      | 20 页 77.91 秒，每页 3.896 秒，显存 8.10 GiB。全量 68.24 小时不批                                                           | `experiments/2026-09-26-encode-probe.md`          |


### 去重不是泄漏

泄漏是训练和评测撞车，已经查完：24 个同名文档、38 句相同问句已剔除；页图像素指纹命中 0。编码去重是另一件事：同一页被很多题共用，按「文档名 + 页号」只算一次向量。文档名只去掉结尾 `.pdf`。旧的 `Path.stem` 会把 `1308.1101` 切成 `1308`，已作废。

### 为什么只编 ArxivQA

有框训练页共 58515，外推 63.33 小时，不批。按域拆开后，ArxivQA 是不超过 12 小时里页最多的整域：7112 页，7.70 小时。SlideVQA 12.92 小时、Wiki-ss 23.67 小时先不动。ArxivQA 编完并训出 `dev_eval` 结果后，涨了再补 DUDE、MP-DocVQA、SciQAG、TAT-DQA。不涨就停，不要把剩下的页也编完。划分不按域重切，已冻结的 id 不要改。

### 交给下一个对话

按顺序做完再停。中间不要改冻结文件，不要问下一步。

```text
1. 先读本置顶节 + docs/paper-progress.md + experiments/2026-09-26-phase2r-design-frozen.md。
2. 只编码 train_fit 的 ArxivQA：正负页都至少 1 框的 9241 题、7112 个去重页。
3. 用现有 ColPaliPageRetriever，模型名 vidore/colpali。权重已在本机缓存。vidore/colpali 是适配器，没有 config.json 是正常的，基座在 vidore/colpaligemma-3b-mix-448-base。不要下载。
4. 写入 artifacts/colpali/mmdocir_train/。断点续跑。已有 .pt 不重写。不要写入评测缓存目录。
5. 同时用本机 BAAI/bge-m3 编这些页的框文本向量，写入 artifacts/bge_m3/mmdocir_train_boxes/。空文本记 0，不删框。
6. 编码完就停。不要启动正式训练，不要读 test_eval，不要建 fusion/。
7. 回复只写：计划页数、实际写成的 .pt 数、耗时、失败页数。
```

停机条件：要下载新模型；要读 `test_eval`；要改四池 id；要改 `recall_layout`；显存规划超过 12GB。

### 禁止

- 不把全集 0.2787 当成 `dev_eval` 子集分数。对照必须在同一 gold 页、同一子集上重算。
- 不把 `bool(layout_mapping)` 当区域分母。`dev_eval` 区域分母按 EXP-005 matched 口径是 391，不是 415。
- 不把页弱监督不涨改成用 evaluation gold 补标签。失败归因写「页弱监督迁不到框排序」。
- 成功线以后才用，本轮编码不评：Area@1 涨、Area@5 涨、页级 R@5 变化在 ±0.3 个百分点以内。

## 2026-09-26 新窗口接续（已归档，不再更新）

- 当前目标不变：完成一篇标准小论文。B1/B2 只作大论文诊断附录，不单独投稿。
- S2 审计已完成（`experiments/2026-09-24-s2-train-audit.md`）。文本泄漏剔除已落盘，不是开训许可。
- 剔除并集：24 个重叠文档的全部 train 题 + 38 句重叠问句（实际 47 条 train 题，有重复）+ 页图 md5 命中。md5 复用数 = 0，未触发停工。剔除前 65319 题 / 30913 文档，剔除 118 题，剔除后 65201 题 / 30889 文档。剔除后文档名交集、问句交集都是空。证据在 `experiments/s2_exclusion/`。
- 划分已冻结，不是开训许可：`experiments/2026-09-26-dev-test-split-frozen.md`。seed=42，按文档切。四池 id 在 `experiments/s2_splits/`。跨文档正负页剔除 2739 题。test_eval 只记 id，未打分。EXP-001 / EXP-007-S1 全集基线不因划分作废。
- 训练仍禁止。不建 `fusion/`，不写 `train_fusion.py`，不用 evaluation gold 构造 `y(c)`，不用 `T_oracle≥0.5` 过滤 train。
- 下一步未批准开训。设计页已确认并冻结：`experiments/2026-09-26-phase2r-design-frozen.md`。确认不是开训许可。不建 `fusion/`，不写 `train_fusion.py`，不读 `test_eval` 分数。
- 编码未开始。下一步已批但尚未执行：只编 `train_fit` 的 ArxivQA（正负页都至少 1 框，9241 题 / 7112 页 / 外推 7.70 小时），写成 ColPali 页向量 `.pt`。这不是开训。进度叙事见 `docs/paper-progress.md`。

## 2026-09-24 新窗口接续（已归档，不再更新）

- 当前目标（重申）：完成一篇标准小论文（有可训练参数 + 独立训练数据 + dev/test + 三指标同报 + 明确对照，见 `docs/PAPER_SPEC.md` 第 2.4/2.6 节）。B1（效率对比）/ B2（失败分类学）只是大论文内的一节诊断附录，绝不单独作为小论文投稿（见 `docs/THESIS_SPEC.md` 第 11.3 节修订）。
- 当前位置：S1 已关（导师 2026-09-24 定阈值提案 B，落盘 `experiments/2026-09-22-threshold-frozen.md`，registry 新增 THR-B 行，现共 11 行）。S2 门口：train 6878 本地无数据，`phase2r-train-leakage-review.md` 5 项全待勾，训练禁令维持（不建 `fusion/`、不写 `train_fusion.py`）。
- 现行主口径（官方面积召回，EXP-007-S1 eval1390）：L2 对齐 Oracle@1=0.9136，L3 最好 fixed:iou_mass=0.2787，gap≈0.63 只观察。旧 IoU 口径数（B=45、0/45、Top-1 0.3187）只作严格辅助诊断，不作准入判据。
- ColMate 借鉴结论（2026-09-24）：三组件中只借 TopKSim 作 2-R 框排序 loss 变体（面积加权 TopK 回归 Area 覆盖分，K 与权重 dev 重冻）；MOLM/MaskedCL 动主干预训练，不用。落点只在 2-R 轻量重排头，不进全融合主线。
- 下一步（按序）：S2 获 train 数据（parquet + jsonl）并过泄漏 5 项 + 标签审计 → S3 2-R 首跑（2 周窗口，dev 门槛：页级 R@5 ±0.3pp + Area@1/5 同向涨）→ 过则议全融合，不过则 B1/B2 只作大论文章节 + 小论文判失败重定方法，不单独投稿。S4 B1 缺格最后补。

## 2026-09-23 新窗口接续（已归档，不再更新）

- 当前位置：`master` 最新 `c835627`（B1 补格），`./tasks.ps1 check` 全绿（ruff + 44 pytest），工作区干净。registry 共 10 行：EXP-001~008 + EXP-002-S1 + EXP-007-S1。
- 自 `447460f` 之后发生的事（旧“一句话总览”不再更新，以本节为准）：
  1. EXP-007 官方口径重算：`metric_eval.py` 三函数逐行移植（`scripts/run_phase1c_official_recompute.py`），L1 R@5=0.8384，L2 全集 Oracle@1=0.9093（@5/@10 超 1 即官方重叠累加缺陷证据），L3 最好 fixed:iou_mass 0.2787（eval1390）。只出数不改 Gate。
  2. 口径对齐修正：L2 加对齐行（@1=0.9136，与 L3 同 1390 分母），gap≈0.63；`matched/unmapped` 只作诊断分层，不作官方口径二分；A/B 标签不参与官方计算。
  3. 2 题回填（00520/00672，同冻结方法，GPU 约 1 分钟）：picks 集 1388→1390 = 页命中全集；记录页 `2026-09-22-backfill-2picks.md`。
  4. EXP-008 BM25 补登记：9/15 M3 迁移期历史产物（R@5=0.7521，全集 1658），四基准齐（0.7521<0.7750<0.7883<0.8390）。
  5. B1 补格关闭：k+1 出处页码已补（ColParse 表1 p.7/表8 p.26/图6 p.7；LFRAG 表1 p.4/表3 p.7）；纠错两处（ColParse 5.90 是每文档非每页；LFRAG 是 n+2 非 k+1）；P75 191.7ms 根因代码级确认（组数爆炸 + `patch_boxes` 循环内重建，已 hoist 修，输出一致）；B1 表新增 BM25 行。B1 剩余缺格：全量延迟/显存/文本索引称重/索引 GB，维持缺。
  6. 阈值冻结完成（S1 关）：导师 2026-09-24 定提案 B，落盘 `experiments/2026-09-22-threshold-frozen.md`（T_oracle≥0.5，gap=0.63 只观察），registry 新增 THR-B 行（共 11 行）。S2 未完成前训练仍禁止。
  7. 泄漏审查（eval 侧完成）：`experiments/eval313_doc_ids.txt` 已导出；**train 6878 本地无数据**（`data/raw` 只有 evaluation；官方仓库已搬迁为 `MMDocIR_research/`，其 `dataset/` 下也只有 eval 三件）。`phase2r-train-leakage-review.md` 5 项 checklist 全待勾，训练保持禁止。
- 官方仓库搬迁注意：旧文档中 `C:/.../MMDocIR/metric_eval.py` 路径已失效，现为 `C:/Users/WenJing/Documents/WorkTransfer/MMDocIR_research/metric_eval.py`（dataset/、data/、test/ 均在该目录下）。引用时用新路径。
- 实验处理约定（新窗口照做）：一次正式 run 一篇记录页（11 段模板 `experiments/templates/experiment-record.md`）+ registry 一行 + commit；`artifacts/`、`runs/`、`data/` 不进 git（JSON 产物只记路径）；`./tasks.ps1 check` 全绿才入库；S2 未完成前不建 `fusion/`、不写 `train_fusion.py`（S1 已关，旧“新阈值未冻前”禁令已转为 S2 禁令）；训练须用户+导师双确认；旧仓 `mmdoc-evidence-rag` 只读。
- 下一步（按序，以 2026-09-24 置顶节为准，旧 S1→S4 作废）：S2 获 train 数据并过泄漏 5 项 + 标签审计 → S3 2-R 首跑（2 周窗口，dev 门槛：页级 R@5 ±0.3pp + Area@1/5 同向涨；ColMate-TopKSim 只作 2-R loss 变体）→ 过则议全融合，不过则 B1/B2 只作大论文章节、小论文判失败 → S4 B1 缺格最后补。S2 未完成，禁令维持。

## 一句话总览（给新窗口的第一段）

- 项目：LayoutPatch（布局约束的文档侧 patch 融合），旧仓库 `mmdoc-evidence-rag` 迁移而来，保持只读，永不修改。
- 目标：ColPali 页级已达 R@5=0.8390，在此之上长出页内区域定位能力，约束见 `docs/PAPER_SPEC.md` 第 5 节（单次编码/不裁剪/MaxSim 接口不动）。
- 关键结论速记：EXP-001 复验通过（R@5=0.8390 逐位一致）→ 叠图曾因"页号差一"全错，已修（`c7a817c`）→ 机器审计 Gate 通过（越界 1/170338）→ EXP-002 A/B/C/D 首次诊断：B 类仅 3.24%（45/1390），Top-K 内 C=0 为定义性结果（区域命中要求页命中，不许写成发现） → EXP-003 BGE-M3（R@5=0.7750）/ EXP-004 Hybrid（R@5=0.7883）补齐第 7.2 节四基准 → EXP-005 关门：matched 1598=1343A+255D含2 both归A（`mmdocir_00036/00491`）；unmapped_only 60=45B+13D+2A纯unmapped命中（`mmdocir_00520/00672`）；47=45B+2A；可寻址 B 双分母均为 0.0（离 10% 线低 10pp）；oracle 页命中内 96.76%/全量 96.50%；自匹配 5 题 IoU 全 1.0（行级抽样已避开 both 编号；候选召回上限非排序能力；B 是 oracle 未中 58 题真子集） → EXP-006 实测 1C：1343A Top-1 最高 0.3187，45B 固定五档消解全 0.0，不进 Phase 2 转收缩 → 关门加固（`bd24fcb/c29b2ff/5356ba9/6b17287/88334aa/ded49bf/4bbc40c/447460f`）：registry EXP-006 回填 query_count=1658（region 格为 Top-1 口径 0.3187，与 0.8112 不可比）；`pyproject.toml` 显式声明 `matplotlib`；`docs/figures/` 白名单两张代表压缩图（`case_A_success.jpg` 114920B + `case_M_middle.jpg` 71830B，SVG 已删）；Text 双轨同一 picks 方法分 + 探针清洗 + 决策包三问摆数已定稿。
- 当前位置：`docs/MIGRATION_BATCHES.md` 批次 5 已跑完并关门加固完（Phase 1C + Text 双轨 + B1/B2/决策包，registry 为 EXP-006）；`./tasks.ps1 check` 44 绿，干净树 `447460f`；下一步是与导师按 11.2/11.3 共判收缩（B1/B2），agent 只摆数不选择。

## 当前 Phase 与 Gate 状态

- 当前所处阶段：**M5（Phase 1C 三无训练基线，迁移批次清单批次 5）已跑完**；见 `docs/MIGRATION_BATCHES.md` 批次清单与小论文执行规范 `docs/PAPER_SPEC.md` 第 7.4 节。**第 7.2 节四基准已齐**：ColPali R@5=0.8390（EXP-001）/ BM25 R@5=0.7521（20260915_215504）/ BGE-M3 R@5=0.7750（EXP-003）/ Hybrid R@5=0.7883（EXP-004）。**EXP-005（2026-09-17，关门）**：交叉表 matched 1598=1343A+255D含2 both归A（`mmdocir_00036/00491`）+ unmapped_only 60=45B+13D+2A纯unmapped命中（`mmdocir_00520/00672`）；可寻址 B=0，双分母 0/1390=0.0、0/1598=0.0，离 10% 线各低 10pp；oracle 页命中内 1345/1390=96.76%、全量 1600/1658=96.50%，框缺口 45/58；自匹配 5 题 IoU 全 1.0（候选召回上限非排序能力；B 是 oracle 未中 58 题真子集）；分层 18 行 + 极值 20 + 中间态 10；面积/覆盖直方图已落盘。**EXP-006（2026-09-17，1C 实测）**：1343A Top-1 最高 0.3187（fixed:iou_mass）/ Snappy-iou 0.2621 / max/mean ~0.10 / group ≤0.1035；45B Snappy/固定五档消解全 0.0（group 碰框 0.6889/0.3556/0.0889 虚高不计）；B 占比 3.24% 且可寻址 0 → 不进 Phase 2，转 11.3 收缩。
- 已完成的 Phase 与 2026-09-16 当天关键事件：
  - M0/M1/M2/M2.5 全部完成（环境、四表 313/20395/170338/1658、`region_labels.parquet` 2638 行）。
  - M3 完成并加固：旧缓存 20395 个 `.pt` 拷入后按**选项 A（用户亲批）**全删、从零重编码 run `20260916_134144`（约 52 分钟，最早 13:42:28、最晚 14:34:58），七指标与旧仓逐位一致（R@5=0.838962605548854），顶替作废的 `20260916_105545`。
  - M4 前半完成：`correspondence.py`（Snappy 公式 + W cover/行归一化/`row_normalize`）+ 单元测试 `tests/layout/test_correspondence.py`；`audit.py`（原图坐标越界判定）+ `audit_overlays.py`（32×32 网格 + 布局框叠图）+ `scripts/run_phase1b_audit.py`（已登记 `docs/02-commands.md` 的 `phase1b-audit`）。
  - M4 关键 bug 与修复：叠图曾错页（`_page_image_for` 写了 `-1` 偏移，把框画到前一页），文本判别法双文档验证（IBM 直配 779 对差一 3；arXiv 直配 135 对差一 0）证 layouts 页号与页图序号同义，已修（`c7a817c`），`audit.json` 重算：20261 页/170338 区域/越界 1/零覆盖 0/Gate 全过。
  - EXP-002 完成（`45af9c0`）：正式 `region_metrics.bbox_iou` + `region_diagnosis.py` + `tests/evaluation/test_region_metrics.py`，`artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`：A=1345、B=45、C=0、D=268；B 占页命中 3.24%；IoU 敏感性 0.3/0.5/0.7 = 0.8154/0.8112/0.8100；与 EXP-001 的 1 题差因 gold 页口径不同（`mmdocir_01342`：evidence 页 p182 进 Top-5，region_labels 框在 p149）。
- 下一个 Gate：

```text
批次 4 已关（PAPER_SPEC 第 7.3 节）：主表 EXP-002 + 关门 EXP-005（交叉表/双分母 0.0/oracle/直方图/30 张案例/自匹配 5 题）均已登记 registry；叠图判读口径：看彩色框围没围住真实文字/表格（红=表格/橙=段落/绿=图，黄粗框=gold），不看框边压没压网格线；顶部小字/底部文字/页码未框属官方稀疏（p69 已确认通过）；EXP-002-S1 记录页恢复留档标 SUPERSEDED，registry 保留两行；matplotlib 由 scipy/sklearn 间接引入已锁 uv.lock，主依赖未回填（见 EXP-005 第 8.5 节声明）。
第 7.2 节已关（2026-09-17）：EXP-003（run 20260917_113452，CPU 约 13.4 分钟）+ EXP-004（run 20260917_115238，CPU 约 13.5 分钟）已登记 registry 第三四行。
批次 5 已跑完（Phase 1C，PAPER_SPEC 第 5.6/7.4 节，EXP-006）：新建 propagation.py / region_pooling.py / region_grouping.py + scripts/run_phase1c.py + tests/retrieval/test_phase1c.py（含 Snappy max/mean/iou 三聚合 + P25/P50/P75 敏感性；`./tasks.ps1 phase1c-smoke/baselines` 对齐）；1343A Top-1 最高 0.3187，45B 固定五档消解全 0.0；决策材料交导师按 11.2/11.3 判收缩（B1/B2）。
批次 6（Phase 2）禁令重申：未过 1C Gate 不得新建 fusion/ 子包与训练代码、不写 train_fusion.py；训练前须用户+导师双确认。
阻塞问题：无（旧仓库保持只读，不做修改；GPU 当前空闲）
```

## 最近 runs（本地产物，不进 git）


| EXP     | run 目录                                                                                                                                                                        | 关键指标一句                                                                                                                                                                            | 是否可用                     |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| EXP-001 | `runs/retrieval/mmdocir_colpali/20260916_134144`（作废：`20260916_105545`、`20260916_125129`、`20260915_215535` 均已删半成品或被顶替）                                                         | Phase 1A ColPali full（本机从零重编码约 52 分钟）：R@5=0.8390 与旧仓逐位一致；predictions 30112 行/1658 query                                                                                           | 是（当前唯一有效 1B 分母）          |
| EXP-002 | `artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`（静态诊断，无 run 目录）                                                                                                   | Phase 1B A/B/C/D：A=1345 B=45 C=0 D=268；B 占页命中 3.24%；Top-K 内 C=0 为定义性结果（区域命中要求页命中）                                                                                                 | 是（1B 主表；口径修正见 EXP-005）   |
| EXP-003 | `runs/retrieval/mmdocir_bge_m3_page/20260917_113452`                                                                                                                          | Phase 1A BGE-M3 dense（CPU 约 13.4 分钟）：R@5=0.7750/R@1=0.4783/MRR=0.6118；actual_retrievers=dense:BAAI/bge-m3 无降级                                                                     | 是（文本 dense 基线）           |
| EXP-004 | `runs/retrieval/mmdocir_hybrid_page/20260917_115238`                                                                                                                          | Phase 1A Hybrid RRF k=60（CPU 约 13.5 分钟）：R@5=0.7883 高于 BM25/BGE 单路，低于 ColPali                                                                                                      | 是（融合对照基线）                |
| EXP-005 | `artifacts/diagnosis/mmdocir_evaluation/crosstab.json` + `addressability.json` + `oracle.json` + `strat_*_hist.png/json` + `overlays_cases/`（20）+ `overlays_cases_mid/`（10）   | Phase 1B 关门：matched 1598=1343A+255D含2 both归A；unmapped_only 60=45B+13D+2A纯unmapped命中；47=45B+2A；可寻址 B 双分母 0.0（离 10% 线低 10pp）；oracle 页命中内 96.76%/全量 96.50%；自匹配 5 题全 1.0（行级抽样避开 both） | 是（第 7.3 节关门证据；30 张待抽查）   |
| EXP-006 | `artifacts/baselines/mmdocir_1c/phase1c.json`（全量 1343A/45B，约 225 秒）+ `phase1c_smoke.json`（冒烟 10A/0B）+ `phase1c_picks.json`（1388 题逐题五档 picks）+ `phase1c_probes.json`（20 题清洗探针） | Phase 1C 实测：A Top-1 最高 0.3187（fixed:iou_mass）；B 固定五档消解全 0.0（group 碰框虚高不计）；不进 Phase 2 转收缩                                                                                          | 是（第 7.4 节决策材料；B 分母严格 45） |


## 关门加固产出（2026-09-18 全部入库，新窗口直接引用）


| 产物           | 位置                                                                                   | 一句话                                                                                                                                                                                                                                                                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Text 双轨方法分   | `artifacts/diagnosis/mmdocir_evaluation/text_dual.json` + `scripts/run_text_dual.py` | 同一 stored picks 方法分：fixed:iou_mass Recall 0.3455/F1 0.3341，snappy:iou 0.2716/0.2712，coverage 0.2708/0.2704，max/mean 约 0.09~0.10，oracle 上界 0.9101；分母 n=1388 中 NaN 53/有效 1335；大框超 50% 置零 341 格（分档 max58/mean58/iou72/coverage72/iou_mass81）；IoU 未中但 Text≥0.8 组双口径 n=0（本口径恒为空非经验为零）；group 三档未跑（自组框无文本，明写未跑）                                                               |
| B1 效率表       | `experiments/2026-09-17-eff-b1.md`                                                   | 9.4 一行表 8 行（ColPali/Hybrid/BGE/Snappy/固定/分组 + LFRAG/ColParse 引用值行）；探针清洗（n=19 去 warmup，权重基座 5653.3MB）query 编码 mean 38.1ms/p50 35.1ms/max 62.8ms 增量 mean 28.1MB；七档选框合计 243.0ms 分档（P75 191.7ms 最贵：高阈值→hot 少→连通域碎裂→组数多→逐组包围盒开销大，与 P25 1.0ms 成反比）；k+1 引用值已补原文页码表号（LFRAG 表2/表3/图1/§4.1，块均 2.79/页；ColParse 表1/表8/图6/§4.2.3-4，均约 5.9/页）；缺格明写（全量延迟/显存/文本索引大小/索引 GB），维持草稿不许引用为对照 |
| B2 失败分类学     | `experiments/2026-09-17-b2-taxonomy-draft.md`                                        | 四数并列：45B 全 unmapped_only + oracle 58 缺框（45⊆58）+ 1343A Top-1 0.3187 排序缺口 + Text 方法分；三类 B2-a 框缺失/B2-b 排序缺口/B2-c 口径约束（D=268=255+13）；只摆数不做选择                                                                                                                                                                                                                               |
| 导师决策包        | `experiments/2026-09-18-advisor-decision-pack.md`                                    | §1 B 占比 3.24% 且可寻址 0；§2 Snappy 最好消解 0/45；§3 A Top-1 0.3187 与 0.8112 不可比 + Text 方法分；§4 效率缺格清单；§5 三问（B2 够否/B1 补测否/B3 立项否）只摆数不选择                                                                                                                                                                                                                                          |
| 术语终结         | registry EXP-005 行 + EXP-005§8.1 + B2-c + 决策包§1 四处                                   | 统一写法：matched 1598=1343A+255D含2 both归A（`mmdocir_00036/00491`）；unmapped_only 60=45B+13D+2A纯unmapped命中（`mmdocir_00520/00672`）；47=45B+2A；不许第四种写法                                                                                                                                                                                                                           |
| page_size 冻结 | EXP-006§3 三用途行号 + `region_labels.py` 字段声明                                            | Snappy 缩 448（`propagation.py:68`，定义 `correspondence.py:28`）；面积归一分箱（`run_phase1b_stratify.py:148`，覆盖 `:161`）；防刷分母（`run_text_dual.py:110,135`）；`region_labels.parquet` 冻结只读不写                                                                                                                                                                                            |
| figures      | `docs/figures/case_A_success.jpg`（114920B）+ `case_M_middle.jpg`（71830B）              | 两张代表压缩图已入库（长边 800px quality65）；SVG 框架图已删（待收缩方向确定后按 B1/B2 重画）；白名单见 `.gitignore`                                                                                                                                                                                                                                                                                         |


## 配置与分支状态

- 当前分支：`master`，最新 `447460f docs(decision):决策包三问摆数更新禁令重申`；工作区干净（`git status --short` 空），`docs/figures/` 两张代表图已入库（SVG 已删，白名单见 `.gitignore` 末尾两行 `!docs/figures/case_A_success.jpg` / `!docs/figures/case_M_middle.jpg`）。
- 未提交改动：无；`data/`（约 12GB）/`artifacts/`/`runs/` 产物不进 git。
- 工作中 config：`configs/experiments/mmdocir_colpali.yaml`（EXP-001 冻结基线）、`configs/experiments/mmdocir_bm25_page.yaml`（BM25 对照 run `20260915_215504`，R@5=0.7521）、`configs/experiments/mmdocir_bge_m3_page.yaml`（EXP-003）+ `configs/experiments/mmdocir_hybrid_page.yaml`（EXP-004）。
- 最近 commits（关门链）：`447460f`（决策包三问摆数）← `4bbc40c`（page_size 字段冻结指引）← `ded49bf`（超大框降级猜测/page_size 三用途/行级抽样注记）← `88334aa`（Text 分母拆档+恒空声明+B1 探针解释）← `6b17287`（术语终结+Text 方法分+清洗探针）← `5356ba9`（figures 入库+术语修正+B1B2 决策包）← `c29b2ff`（两张代表图记账）← `bd24fcb`（EXP-006 回填 1658+Top-1 口径+B1B2 草稿）← `dbde18f`（handoff 同步）← `7312bb8`（EXP-003~006 登记）。
- 质量门：`./tasks.ps1 check` 44 绿（ruff + 44 pytest，2026-09-18 最新一轮）。

## 实验讲解规则（新窗口必读，docs/RULES.md 第 0.2 节）

- 只要回复涉及实验，必须按小白模式展开：白话目标 → 输入是什么 → 处理逻辑 → 输出落在哪 → 怎么验证对错 → 失败会怎样 → 对应哪个文档哪一节。
- 首次出现缩写必须写全称出处（如"迁移批次清单 `docs/MIGRATION_BATCHES.md` 批次 4，对应小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节 Phase 1B"），之后才可用"批次 4/Phase 1B"。
- 每次回复的操作步骤后另附「本轮指令说明」：逐条贴本轮实际命令原文 + 一句话作用；未跑命令写"本轮未执行任何命令"。
- 实验五问模板（Phase 1A 四基准 / 坐标审计 / A/B/C/D / 1C 三基线 / Phase 2 训练动机）见 `docs/02-commands.md` 各节"判据"行。

## 数据链地图（新窗口查数用）

```text
data/raw/mmdocir_evaluation/                  官方三文件（约 4GB，不进 git）
data/interim/mmdocir_evaluation/page_images/  20395 张 jpg（约 8GB，不进 git）
data/processed/mmdocir_evaluation/            documents 313 / pages 20395 / nodes 170338 / queries 1658 + region_labels 2638（matched 2523/unmapped 115；题级 matched 1598/unmapped_only 60）
全局 HF 缓存 C:/Users/WenJing/.cache/huggingface/hub/   BGE-M3（models--BAAI--bge-m3，旧仓 robocopy，全局复用；ColPali 同在此）
artifacts/colpali/mmdocir_evaluation/vidore_colpali/  20395 个 .pt（本机 52 分钟重编码，min 265634/max 267497/零字节 0）
artifacts/audit/mmdocir_evaluation/           audit.json（20261 页/170338 区域/越界 1）+ overlays/ 20 张叠图（已修页号）
artifacts/diagnosis/mmdocir_evaluation/       abcd_diagnosis.json（EXP-002）+ EXP-005 十件（stratification/cases/crosstab/addressability/oracle/strat_*_hist.png+json/overlays_cases+mid 30 张）
artifacts/baselines/mmdocir_1c/                 phase1c.json（EXP-006 全量 1343A/45B）+ phase1c_smoke.json（冒烟 10A/0B）
runs/retrieval/mmdocir_colpali/20260916_134144/  EXP-001 五件套（唯一有效；latest 指向它）
runs/retrieval/mmdocir_bm25_page/20260915_215504/  BM25 五件套（R@5=0.7521，同口径对照）
runs/retrieval/mmdocir_bge_m3_page/20260917_113452/  EXP-003 五件套（R@5=0.7750）
runs/retrieval/mmdocir_hybrid_page/20260917_115238/  EXP-004 五件套（R@5=0.7883）
```

## 未解决问题

1. ~~Phase 1A 四基准缺 BGE-M3 dense 与 Hybrid~~已关（2026-09-17，EXP-003/EXP-004）：四基准同表为 ColPali R@5=0.8390 / Hybrid R@5=0.7883 / BGE-M3 R@5=0.7750 / BM25 R@5=0.7521（同 query 集 1658、同文档内范围、同 Top-20、同脚本）。
2. ColPali 库选型：当前 `colpali-engine>=0.3.0`（已废弃但仍可用于原始复现；`colpali-official-repro/README.md` 推荐新路用 Sentence Transformers v6 + `-hf` 模型）。结论：Phase 1A 基线不动库，Sentence Transformers 仅作未来可选新实验，不替换 `vidore/colpali` 的 0.8390。
3. 坐标审计判读口径：已固定为"框围内容、不看网格"，用户已按此口径确认 p69 通过；其余 19 张待抽查（建议表格页优先看 `NYSE_IBM_2020_p126`、`ACTIVISIONBLIZZARD_2019_10K_p113`）。EXP-005 的 30 张案例图（`overlays_cases/` 20 + `overlays_cases_mid/` 10，黄粗框=gold）待用户按同口径抽查，重点看 `M_mmdocir_00522`（IoU 0.4036、仅 2 候选）黄框内是否有文字但框偏小/偏大。
4. 134 页无官方布局节点（占 0.66%）：属官方标注稀疏，页图与缓存正常，检索可用；区域审计分母天然排除，不影响结论。
5. 1C 已跑完（EXP-006 实测）：1343A Top-1 最高 0.3187（fixed:iou_mass），Snappy-iou 0.2621；45B Snappy/固定五档消解全 0.0（group 碰框虚高不计）；B 占比 3.24% 且可寻址 0 → 不进 Phase 2，转 11.3 收缩（B1 效率/B2 失败学）。禁令：未过 1C Gate 不建 `fusion/` 子包、不写 `train_fusion.py`。

## 下一步（给新会话的指令，按序执行）

```text
1. 读完本文件 + docs/00-index.md + docs/MIGRATION_BATCHES.md + docs/PAPER_SPEC.md 第 6/7.2/7.3/7.4 节，再动手。
2. ~~补 Phase 1A（第 7.2 节）~~已关：EXP-003/EXP-004 已跑完登记；无需重跑（除非改 config 即开新版本）。
3. ~~补 Phase 1B 后半（第 7.3 节）~~已关（EXP-005，2026-09-17）：`./tasks.ps1 phase1b-stratify`（= `uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5`）已产分层 18 行 + 交叉表 + 双分母 0.0 + oracle + 直方图 + 极值 20/中间态 10 张 + 自匹配 5 题；registry 为 EXP-005（EXP-002-S1 恢复留档标 SUPERSEDED，registry 保留两行）。
4. ~~批次 5（Phase 1C）~~已跑完（EXP-006，2026-09-17）：`./tasks.ps1 phase1c-smoke`（冒烟 10A/0B 约 23 秒）+ `./tasks.ps1 phase1c-baselines`（全量 1343A/45B 约 225 秒）；新建 propagation.py / region_pooling.py / region_grouping.py + run_phase1c.py + test_phase1c.py；决策材料交导师按 11.2/11.3 判收缩（B1/B2）。
5. 批次 6（Phase 2）禁令重申：未过 1C Gate 不得新建 fusion/ 子包与训练代码、不写 train_fusion.py；训练前须用户+导师双确认。
```

## 更新记录


| 日期         | 更新内容                                                                                                                                                                                                                                           |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-16 | M0 骨架完成：根目录 12 个条目、src 包结构、tests（参考官方 repro：conftest + markers + smoke）、docs 七篇、configs/experiments 占位、MIGRATION 重写为 M0-M6 批次清单                                                                                                                |
| 2026-09-15 | 第一优先级修复完成：删重复旧 skill、修正 rules 旧引用与 30 号 glob、修正 handoff/index 的 MIGRATION 引用、PAPER_SPEC 覆盖为小论文全文、GPU 测试改为函数内 importorskip；依赖保持完整未拆分                                                                                                            |
| 2026-09-15 | M1 完成：`uv sync --dev` 落盘 `uv.lock`、`uv run lp version` 通过、`./tasks.ps1 check` 全绿、git 首个 commit、覆盖 `THESIS_SPEC.md`；`cli.py` 补 callback 修复 typer 单命令折叠                                                                                          |
| 2026-09-15 | M2 完成：adapters（demo/mmdocir）+ `lp prepare` + `tasks.ps1 mmdocir-prepare` + `configs/datasets/mmdocir.yaml` 落地；ruff + 12 pytest 全绿；全量对数 313/20395/170338/1658 验证通过（raw 经临时变量指向旧仓库，产物在本仓库 `data/`）                                               |
| 2026-09-15 | M2.5 完成：官方 evaluation 原始三文件复制到本仓库 `data/raw/`；`region_labels.parquet` 2638 行（2523 matched + 115 unmapped，覆盖 1658 query）；ruff + 15 pytest 全绿；四表对数未动                                                                                             |
| 2026-09-16 | M3 完成：检索评测管线（bm25/dense/colpali/hybrid 页级）+ `lp retrieve/evaluate` + smoke 全绿；EXP-001 全量复验 R@5=0.8390 与旧仓逐位一致（ndcg 口径回滚为旧逐行一致 + 补回归测试）；registry 首行 + 记录页 + 复现凭证已登记；ruff + 25 pytest 全绿                                                         |
| 2026-09-16 | 选项 A 执行：按用户批准停 12:51 编码进程、删净缓存、从零重编码 52 分钟（run 20260916_134144 顶替 105545）；`docs/RULES.md` 新增 4.4（后台执行+指令透明）与 0.2（实验小白讲解）；`configs/datasets/mmdocir.yaml` 的 raw_dir 写死仓内                                                                        |
| 2026-09-16 | M4 前半完成：`correspondence.py` + `audit.py` + 叠图链路 + 机器 Gate（越界<1%、零覆盖 0）；叠图页号差一 bug 经文本判别法定位已修（`c7a817c`）；用户确认 p69"框贴合无偏移、顶部小字/底部文字/页码未框属官方稀疏"通过                                                                                                 |
| 2026-09-16 | EXP-002 完成：A/B/C/D 首次诊断（A=1345/B=45/C=0/D=268；B 占页命中 3.24%；IoU 敏感性 0.3/0.5/0.7=0.8154/0.8112/0.8100；与 EXP-001 差 1 题为 gold 页口径差异）；`region_metrics.py` + 回归测试 + `experiments/2026-09-16-exp-002-abcd-diagnosis.md` 已登记（`45af9c0`）；`pytest` 36 通过 |
| 2026-09-17 | 重绘分格式论文网络框架图：`docs/figures/layoutpatch_network_framework.svg`，参考用户提供的三分格论文图风格，依据 `docs/PAPER_SPEC.md` 第 3、5、7–9 节展示总览数据流、方法组件放大图与贡献/有效性检查；SVG XML 校验通过。                                                                                        |



## 2026-09-30 标注口径更新

当前人工标注使用 `experiments/region_annotation/annotation_protocol_v1.md`，替代旧v0和历史标注方案的选择/辅助流程：选全可核实的直接证据候选，不采用最小充分集合。A/B分别模型辅助、人工独立审核；ann-0004为校准题。旧标签不自动迁移；v1工具导出独立文件，检查需用 `--labels` 指定。多框不强制cross_box=true。二值标签不是官方Area软标签。未修改冻结划分/评测/权重，未训练、未读test_eval。
