# 命令手册（SSOT）

> Status: working | Scope: 全仓命令 | SSOT: 是
> 本篇是命令唯一真理源。其他文档只允许引用，不许重复写长命令。
> 约定：所有命令在项目根目录执行；Windows 用 `./tasks.ps1 <task>`；所有任务共用 uv `.venv`。
> 每条格式固定为：命令 / 输入 / 输出 / 检查。新任务先在这里登记，再在 `tasks.ps1` 实现。

## check（质量门，已实现）

```powershell
./tasks.ps1 check
```

- 输入：`src/` + `tests/`
- 输出：终端结果；无产物
- 检查：ruff 与 pytest 全绿（合入 `main` 的最低条件，见 `docs/RULES.md` 7.1 节）

## route-v2-identity（外部源固定 + 身份审计四步，task）

```powershell
./tasks.ps1 route-v2-identity
```

- 输入/输出：依次执行下列四步（底层等价，备查）；某步产物已存在则跳过，不覆盖。全程不打分、不训练。
- 检查：`artifacts/route_v2_data/verification_v1/verification_report.json` 的 `decision_counts`；`internal_identity_v1.json` 的 `confirmed_doc_groups`。约 3–5 分钟（首次含约 133MB 下载）。

### 底层等价（备查）1/4：acquire（固定外部测试源，仅作身份审计）

```powershell
uv run --offline --no-sync python scripts/acquire_route_v2_external.py
```

- 输入：官方HF `Yuwh07/SciEGQA-Bench` revision `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`；脚本联网获取README、JSONL和PDF.tar（共约133MB），uv不安装依赖。
- 输出：`data/raw/sciegqa_bench/<revision>/` 与SHA256回执；不读取输出题目/答案/gold、不打分、不下载1.1GB Images.tar或模型。
- 检查：固定文件大小和校验和一致；已存在源仅复核不覆盖。网络失败保留.part供诊断。身份核查不等于数据许可证已经确认。

### 底层等价（备查）2/4：identity（固定阈值的身份/近重复检查）

```powershell
uv run --offline --no-sync python scripts/audit_route_v2_identity.py
```

- 输入：MMDocIR原annotations/pages（包括已批准重定用途的旧test身份）、固定SciEGQA标注/PDF；仅程序处理题目、OCR、图像用于去重，不输出答案/gold或计算模型分数。
- 输出：`artifacts/route_v2_data/identity_v1/`，阈值策略、页指纹、overlap_report；报告输入SHA256、每层匹配、隔离文档和限制。
- 检查：80篇外部/313篇本地页面覆盖完整；文档ID、问题近重复、全页文本5-gram Jaccard、64bit pHash+缩略图RMSE交叉核查。匹配文档仅从MMDocIR训练/开发侧隔离，外部题集不删。首次约数分钟；无训练、无额外模型编码；旧文件只读。

### 底层等价（备查）3/4：verify（内容复核，不评模型）

```powershell
uv run --offline --no-sync python scripts/verify_route_v2_candidates.py
```

- 输入：第一阶段候选及原始页/PDF；用正文、160像素前景图、标题复核低分辨率图像候选。
- 输出：`artifacts/route_v2_data/verification_v1/`；约1分钟，未知候选保守隔离。
- 检查：候选不等于重复；确认/模板误报/未知分别列出，输入绑定SHA256。结果仍须结合本地去重和最终split验证。

## route-v2-data（数据角色、坐标门、区域单元与监督可视化，task）

```powershell
./tasks.ps1 route-v2-data
```

- 输入：MMDocIR evaluation 原始 annotations/layouts、processed pages、页向量缓存、旧 s2_splits 清单（只读）与 route-v2-identity 产物。不写题目/答案原文。
- 输出（已存在则跳过，不覆盖）：
  1. `experiments/route_v2_splits/data-roles-v1/`：四角色 ID、`split_proof.json`、`identity_inputs.json`（进 git，只含 ID）；
  2. `artifacts/route_v2_data/coordinate_audit_v1.json`：token 布局、页框比例、框-墨迹召回、缓存签名；
  3. `artifacts/route_v2_data/regions_v1/`：`units.parquet`、`candidates.parquet`、`questions.parquet`、`audit.json`；
  4. `artifacts/route_v2_data/regions_v1/supervision_viz/`：8 张固定样本叠图 + `index.json`。
- 检查：`split_proof.json` 的 `pairwise_document_intersections` 全空、`identity_units_crossing_roles` 为空；`coordinate_audit_v1.json` 的 `passed`；`audit.json` 各角色 `units_local_loss_ready`。约 3–6 分钟，CPU。
- 底层等价（备查）：`uv run --offline --no-sync python scripts/{build_route_v2_split,audit_route_v2_coordinates,build_route_v2_regions,render_route_v2_supervision}.py`，按此顺序。

## route-v2-external-tests（仅新增MinerU候选适配测试）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-tests`

**输入**：MinerU/DocVortex候选适配及原图内容映射的合成测试，`@tests/datasets/test_mineru.py`、`@tests/datasets/test_external_image_review.py`；不读取真实外部题目或运行解析模型。

**输出**：定向Ruff/pytest摘要，无模型或数据产物。

**检查**：0–1框到渲染像素、原页号/旋转/页面尺寸保护、空框/越界停止、重复与空页保留、既有候选字段结构；不重跑已通过元数据审计，不涉及19个旧Ruff问题。

## route-v2-external-audit（外部比较权重、源字段与本地解析工具核验）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-audit`

**输入**：`configs/experiments/route_v2_external_v1.yaml`、冻结训练配置、registry精确运行索引、source_val选择回执与权重文件、固定SciEGQA JSONL/PDF.tar；仅查询当前`.venv`的MinerU/magic-pdf/PyMuPDF版本及明确工具配置路径。

**输出**：`artifacts/route_v2_external/preparation_v1/<timestamp>/`的weights.json、字段结构摘要、全题/唯一证据页manifest.json和audit.json；终端只输出计数/哈希/工具状态，无题目、答案、gold、权重张量或完整运行JSON。manifest保留每题身份与失败状态，原图尺寸/渲染变换未核实时明确置null，不猜坐标。预计数秒至一分钟。

**检查**：1623题与固定源哈希、四个训练方法共十二份既有三seed权重、source_val选择及源配置一致；无模型评分/训练/下载/渲染/解析，不算Oracle。解析器缺失时记录硬阻塞，不更换工具或安装资源。

## route-v2-external-status（续接前精确回执检查）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-status`

**输入**：冻结配置精确指向的两份元数据回执；只使用固定页身份和必要源路径，不处理题目、答案或gold。

**输出**：不超过20行的清单哈希、原审计状态、源PDF包路径及固定八页身份；不写产物，不重新选页，不渲染或解析。

**检查**：manifest哈希及八页身份一致；访问失败保留原始错误并停止。该入口不枚举后续运行，不代表最新八页验收状态，最新状态见`@experiments/2026-10-07-external-preparation.md`。预计数秒。

## route-v2-external-tool-status（独立工具包身份只读检查）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-tool-status`

**输入**：独立MinerU环境的包元数据；通过明确的工具Python路径查询，不自动发现解释器。

**输出**：MinerU/ONNX Runtime/DocVortex版本、Python base prefix、包许可及已核实坐标契约摘要；不读取/打印完整日志或解析文本。

**检查**：核实已安装版本与解释器来源，避免重装；该轻量入口不重新核验模型文件、实际CPU会话或处理回执，不启动解析。完整已执行核验见`@experiments/2026-10-07-external-preparation.md`。预计数秒。

## route-v2-external-contract（已核实输出契约摘要）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-contract`

**输入**：与tool-status相同的独立环境包元数据。

**输出**：当前包版本与已由官方实现核实的`docvortex.middle`2.0、0–1块框、PDF point页面尺寸摘要；不打印文本、题目、答案或gold，不写旧产物。

**检查**：最终实现为轻量身份/契约摘要，与tool-status共用只读分支，不重新读取源码或验证原始JSON。首次续接时已做过官方源码和首份原始输出核验；后续pages入口按固定契约逐页做机器检查。该命令不重新解析、下载或评分。

## route-v2-external-pages（固定八页 MinerU Basic ONNX 工程验收）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-pages`

**输入**：`@configs/tools/mineru_external_pages_v1.yaml`固定解析版本/设置；既有manifest的8页、`@artifacts/route_v2_external/preparation_v1/20261007_184934/`的PDF、八页渲染与第一页原始输出；独立工具环境`@artifacts/route_v2_external/preparation_v1/mineru_tool_v1/`。只读取页身份，不读问答/gold。

**输出**：`@artifacts/route_v2_external/preparation_v1/<timestamp>/`的新7页原始输出、8页候选文件`@artifacts/route_v2_external/preparation_v1/<timestamp>/candidates.jsonl`及候选叠图、逐页回执、渲染/坐标/资源/工具身份/总体审计回执；原PDF/渲染/第一页以精确路径及哈希引用不覆盖。

**检查**：固定8页不重选、第一页不重跑；MinerU4.0.10/ONNX1.30.0/DocVortex0.5.10和模型revision逐文件哈希绑定；当前`docvortex.middle`2.0框为0–1归一化，页面为point。严格检查源页/画布，禁止把旧`pdf_info/page_size`像素假设套上新输出。每页新解析通过同进程CLI包装记录工具导入、ONNX会话加载、CPU实际provider、Windows进程峰值工作集；旧第一页计时/内存未保存则置null。导出仅检查字段和坐标，不调用模型评分/Oracle；原始标注图像映射仍未验证时，不宣称外测输入就绪。约1–3分钟，异常立即停。

**底层等价（备查）**：`uv run --offline --no-sync python scripts/prepare_route_v2_external_pages.py`；脚本内部调用独立环境`@artifacts/route_v2_external/preparation_v1/mineru_tool_v1/.venv/Scripts/python.exe`执行`@scripts/route_v2_mineru_worker.py`，在同一解析进程加载已安装的`mineru-kit`入口并记录资源，不调用自动发现的Anaconda。

## route-v2-external-images（固定八页官方原图下载、提取与PDF映射审计）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-images`

**输入**：`@configs/tools/sciegqa_images_v1.yaml`固定SciEGQA revision、`Images.tar` URL/SHA256、已有manifest八页身份和既有PDF渲染回执。若本地已有完整压缩包只校验复用；若没有则下载约1.13GB到固定源目录。只提取manifest指定的8个archive member，不读取题目/答案/gold来生成候选。

**输出**：固定源目录的`Images.tar`及8张`fixed_images_v1/`原图；新增`@artifacts/route_v2_external/preparation_v1/<timestamp>/image_mapping_audit.json`和`page_receipts.json`，记录下载/哈希、页身份、原图尺寸、PDF页旋转/裁剪、内容前景对齐和坐标契约。

**检查**：清单SHA256和8页身份必须一致；压缩包SHA256必须为`aa8f7e6f5c27fb914a2b36f6accc63fdd48f549f97c2212e03f2b6a85e67b368`；机器内容对齐不能只按宽高判断，失败即停且保留错误/部分证据。明确区分gold `rel_bbox` 0–1000、MinerU框0–1和当前渲染像素框；不评分、不算Oracle、不训练、不处理其他页面。原图已提取后再次调用会停止以避免覆盖；当前已有8页映射回执，无需重跑下载/映射，后续使用final-review核对。

**底层等价（备查）**：`uv run --offline --no-sync python scripts/acquire_route_v2_external_images.py`；仅表示使用项目已锁定环境运行脚本，脚本本身按固定URL联网下载。



## route-v2-external-full-prep（固定837页候选准备）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-full-prep`

**输入**：`@configs/tools/route_v2_external_full_prep_v1.yaml`、固定manifest（1623题/837唯一页/1941题—页单元）、已有`PDF.tar`、`Images.tar`和独立MinerU环境。只读取页身份与解析输出，不用gold选框，不加载ColPali/BGE权重。

**输出**：`@artifacts/route_v2_external/full_prep_v1/<timestamp>/`，逐页PDF/原图/渲染引用、MinerU原始输出、候选`candidates.jsonl`、逐页回执和`audit.json`。单页异常保留回执并排除就绪输入，题—页身份不删除；已有独立运行目录不覆盖。续跑只复用manifest身份、固定归档成员、原始解析/渲染/原图哈希、内容映射及候选身份/计数/唯一性全部通过的页面；旧合并文件缺行时可从已记录来源链或哈希已验证原始解析重建候选行，不重新运行MinerU。

**检查**：固定manifest、PDF/Image归档哈希、PDF页号/rotation/crop/media、原图与PDF内容映射、候选框/类型/文本来源和外部消费者接口。渲染尺寸以PyMuPDF `Pixmap.irect/width/height`真实像素范围为准，不用`round(point×scale)`猜测；解析器frame若与未旋转MediaBox一致则应用PyMuPDF旋转矩阵，若与已旋转`page.rect`一致则直接映射，CropBox真实不同仍停止。JSONL按真实换行流式读取，不能用会拆Unicode行分隔符的`splitlines()`。通过页数837且异常为0才标记`ready`；异常/中断必须记录stage/type/error并非零退出。不编码、不评分、不训练。首次全量约1小时；有效续跑以需重处理页数决定，实际以`audit.json`为准。

## route-v2-external-final-review（固定八页最终坐标与真实文本消费者核对）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-external-final-review`

**输入**：固定manifest八页、已保存原图映射回执、候选/原始解析/PDF渲染回执；仅这8页的标注bbox/rel_bbox元数据。实际冻结D的`node_text`与`page_layout`函数，零占位向量仅验证形状，不编码或执行模型。

**输出**：`@artifacts/route_v2_external/preparation_v1/<timestamp>_final_review/`逐页JSON及最终回执，记录已经完成的叠图视觉检查、原图到渲染仿射、0–1000坐标转换一致性、真实类型/文本消费者/布尔节点mask及明确阻塞。只打印逐页摘要。

**检查**：源/渲染/候选哈希与页身份一致；固定页原标注像素与0–1000坐标量化一致，不计算候选与gold重叠。不把字段存在等同于完整评分接口通过：图表`ocr_text=null`在冻结消费者中会丢失真实`text`，必须保留阻塞；无训练、评分、Oracle、下载或重复解析，预计数秒。exit0仅表示检查完成，准入以回执状态为准。

## route-v2-exp3-tests（EXP-016最小归因相关检查）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-exp3-tests`

**输入**：新增归因模块、正式入口和合成测试；沿用D接口/早停/基线兼容性测试。

**输出**：定向Ruff及pytest汇总，不训练真实数据、不评分dev。

**检查**：有效参数容量、只置零指定输入且缓存不变、九权重选择门、文档bootstrap三项Bonferroni区间、预算继承；不包含19个旧Ruff问题。

## route-v2-exp3（EXP-016三变体九次训练和一次统一开发评测）

**命令**：`powershell.exe -NoProfile -File tasks.ps1 route-v2-exp3`

**输入**：冻结`configs/experiments/route_v2_exp3_attribution.yaml`及哈希绑定的EXP-015配置、既有缓存/划分/候选；原A/B/C/D已存预测。2026-10-07用户授权。

**输出**：`runs/retrieval/route_v2_exp3_attribution/<timestamp>/`五件套、定点代码快照、输入身份、九份选择记录/权重、逐轮日志、逐题预测及保存结果复核回执；终端仅汇总。预计约15–40分钟，早停决定实际时长；中断保留失败及已完成产物，不自动续跑。

**检查**：C-wide隐藏1062、273318参数；D-no-text只置零文本；D-no-coord只置零显式坐标且真实W/邻域/cover_mass保留。每变体seed0/1/2、最多30epoch，只val选权重；全部九个确定后一次统一dev评分，A/B/C/D不重评分。三项D减变体预固定，95%文档区间加98.333% Bonferroni区间，保留全部指标/分母/辅助McNemar。输入不符/非有限值/显存超过12GiB即停，不重试；完成后停止。

## route-v2-exp2-result-check（EXP-015保存结果只读回验）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp2-result-check
```

- 输入：`runs/retrieval/route_v2_exp2_D/20261006_230924/`及EXP-014原预测；只读已存结果。
- 输出：终端回执，无训练或模型前向。
- 检查：A/B/C复制值不变、D候选/分母一致、32项相关测试之外的实际checkpoint选择/早停及配对bootstrap重算一致；预计数秒，不重评dev。

## route-v2-exp2-verify（正式D输入及基线兼容性门）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp2-verify
```

- 输入：EXP-014配置/代码快照/已存预测及选择回执、当前数据角色、候选、问题/节点缓存、EXP-015配置。
- 输出：新`artifacts/route_v2_data/exp015_preflight/<timestamp>/preflight.json`；核验逐条已存预测的候选/排序/指标，不调用模型定位评分。
- 检查：训练预算一致、原评分损失实现不变、角色和缓存哈希一致，412题545unit相同分母、逐题宏平均及预测兼容；不一致即停止，预计数十秒。

## route-v2-d-dev-nodes（2026-10-06授权补dev节点，仅编码）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-d-dev-nodes
```

- 输入：source_dev eval_ready所需页的全部既有候选；严格复用train/val的本地BGE-M3身份、字段规则、1024维、512token、batch2及缺失处理。节点构造不含问题或gold。
- 输出：独立`artifacts/route_v2_data/d_nodes_dev_v1/`与`d_nodes_runs/<timestamp>/`回执；train/val原缓存逐文件哈希在编码前后校验，禁止覆盖。
- 检查：身份/来源/节点对应、有限性、显存≤12GiB；只编码不定位评分、不改变输入规则、不下载；预计约1分钟，以实测为准。

## route-v2-d-verify（D准备产物只读回验）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-d-verify
```

- 输入：训练/验证d_nodes_v1、D smoke回执与EXP-014/015配置；不读取dev样本。
- 输出：终端节点哈希/ID/shape/W/缺失处理与共同预算一致性回执。
- 检查：全部缓存页逐份验证（实际页数见回执）、smoke通过，单列尚未准备的dev节点缓存；约数秒，不编码、不训练、不评分。

## route-v2-exp2（EXP-015冻结正式D比较；2026-10-06授权执行）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp2
```

- 输入：`configs/experiments/route_v2_exp2_D.yaml`、EXP-014已存A/B/C预测、冻结页/问题缓存和同规则节点缓存。训练/验证节点与独立dev节点均已准备，开跑前必须通过配置绑定的preflight回执并复核哈希。
- 输出：新建`runs/retrieval/route_v2_exp2_D/<timestamp>/`五件套、各seed日志/权重、D−C/D−A/D−B及Top-5差值；逐epoch训练侧gate和残差仅诊断。
- 检查：全部D权重由val确定后统一dev评分一次；C仅复用原预测，不重训或重评。显存12GiB，输入/数值/协议不符立即停，失败保留；运行时长按首轮实测估计，不自动调参或后续实验。

## route-v2-d-smoke（固定训练样本技术验收）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-d-smoke
```

- 输入：`20261006_153418`固定16题/19unit清单、原页/问题缓存、新d_nodes_v1；不加载任何训练权重，不评val/dev。
- 输出：独立`artifacts/route_v2_d_smoke/<timestamp>/metrics.json`、`steps.jsonl`、`D_smoke.pt`，失败回执保留；权重不得用于正式D起点。
- 检查：seed42、AdamW lr1e-3/weight_decay0.01、全19unit平均梯度200步，GPU float32、12GiB上限；损失/梯度/参数、第一步与后续上游信号、空patch/提示token、gate/归一化patch变化、训练定位宏平均、耗时和显存。无NaN/Inf；失败不扩大预算，预计数分钟以内，以实测为准。

## route-v2-d-tests（D组合接口定向验收）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-d-tests
```

- 输入：合成节点/patch、现有V2融合与评分测试，不访问开发集。
- 输出：ruff/pytest终端结果，临时测试产物。
- 检查：零初始化一致、空patch、padding、字段/类型/坐标对齐和后续上游梯度；不运行全仓19个旧ruff问题。预计数秒至数十秒。

## route-v2-d-nodes（仅训练/内部验证节点缓存）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-d-nodes
```

- 输入：source_train可训练页与source_val可评测页的全部既有候选；仅本地BGE-M3 revision 5617a9f61b028005a4858fdac845db406aefb181。正文/标题/公式选text，图/表选ocr_text，禁止vlm_text回退。官方来源见EXP-015准备记录。
- 输出：独立`artifacts/route_v2_data/d_nodes_v1/`，逐页文本向量、类型/归一化坐标、W_raw/W_attn/cover_mass、节点ID和文本哈希；运行与覆盖率回执在`artifacts/route_v2_data/d_nodes_runs/<timestamp>/`。旧缓存拒绝覆盖。
- 检查：原始数据和候选对应、模型本地文件哈希、有限归一化1024维向量；缺模型/来源或显存超12GiB即停。float32、CLS池化、最大512token（截断计数）、batch2；不编码图像、不准备dev文本；耗时实测，中断不发布半成品。

## route-v2-exp1-result-check（已保存结果只读复核）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp1-result-check
```

- 输入：`runs/retrieval/route_v2_exp1/20261006_162042/` 的冻结配置、逐轮日志、选择回执、权重与已保存预测。
- 输出：终端核验回执，无模型前向、训练、开发集重评分或输入改写。
- 检查：相同候选与分母、严格早停/平局、checkpoint哈希及选择先于开发评测、三seed逐题配对bootstrap重算与保存统计完全一致；预计数秒。

## route-v2-exp1-tests（正式runner相关合成测试）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp1-tests
```

- 输入：正式runner与合成测试；不访问真实开发集、不编码。
- 输出：ruff 与 pytest 结果；测试临时目录。
- 检查：角色限制、训练页排除、评测资格、尾组平均、早停和平局、检查点门、逐题宏平均、三seed配对、零初始化一致和非有限中止全部通过；预计数十秒。

## route-v2-exp1（EXP-014，冻结A/B/C正式比较）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp1
```

- 输入：`configs/experiments/route_v2_exp1.yaml` 冻结配置及其绑定的核验回执；原 data-roles-v1/regions-v1/问题与页缓存。只更新 source_train；source_val 选择；全部3个seed选择完成后一次 source_dev 比较。
- 输出：新建 `runs/retrieval/route_v2_exp1/<timestamp>/`，正式五件套、代码快照/工作区差异、输入哈希、每轮日志/曲线、独立最佳权重、逐题分数及选择回执；失败保留目录，不恢复重跑。
- 检查：运行前定向测试通过；身份/数值/显存12GiB硬门；所有方法同题同候选同指标。实际耗时按每轮日志外推，不承诺固定时长；预计分钟至数十分钟。结束只报告开发结果与预定推进标准，不自动训练D或调参。命令内部全程离线且禁止同步依赖。

## route-v2-exp1-verify（正式训练前只读输入核验）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-exp1-verify
```

- 输入：现有 data-roles-v1、regions-v1、问题/页面缓存、坐标与 smoke 回执；不打开外部测试，不运行其他辅助任务。
- 输出：`artifacts/route_v2_data/exp1_verification/<timestamp>/verification.json`，含逐文件哈希和角色/排除核验。只读既有输入。
- 检查：ID、角色、源哈希、缓存模型与页面签名、有限性、既有排除计数全部通过；失败即停止。预计数分钟，取决于磁盘哈希耗时，无模型编码或评分。

## route-v2-queries（本地冻结问题向量缓存，2026-10-06 授权）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-queries
```

- 输入：`data-roles-v1` 四角色清单和证明、MMDocIR 原始 annotations；仅提取三个非隔离角色的问题文本。精确核对物理行/题下标、全局 ID、文档 ID 和冻结源哈希。只用本地 `vidore/colpali`、其基础权重和现有 uv 环境，离线且不同步依赖。
- 输出：`artifacts/route_v2_data/query_cache_v1/source_queries.pt`；独立 `runs/<timestamp>/run_info.json` 记录模型/processor 身份、哈希、token、shape/dtype、batch 耗时和峰值显存。已有缓存严格校验复用；不兼容即停，不覆盖。首 batch=1，后续 batch=2；实际耗时以运行记录为准，中断只留下独立运行目录，不发布半成品缓存。
- 检查：预期 1613 题（以 manifest 为准），完整 ID 覆盖、三角色计数、非零有限向量、保留十个增广 token；模型缺失、ID 不一致、异常向量或显存不足即停。不同角色仅编码，不评分，不读取外部测试，不编码页面。

## route-v2-cache-tests（缓存与 smoke 相关定向检查）

```powershell
powershell.exe -NoProfile -File tasks.ps1 route-v2-cache-tests
```

- 输入：缓存映射/完整性验证、smoke 数值中止、现有划分/区域/定位的合成测试。
- 输出：终端 ruff 与 pytest 结果；临时测试文件，无真实模型编码或实验训练。
- 检查：全部通过；约数十秒。内部使用 `uv run --offline --no-sync`，不安装依赖。

## route-v2-smoke（管线可学习性验证，task；不是效果实验）

```powershell
./tasks.ps1 route-v2-smoke
```

- 输入：上一步全部产物 + `artifacts/route_v2_data/query_cache_v1/source_queries.pt`（非隔离来源题的问题向量，至少含固定 16 题；格式见脚本 `QUERY_SCHEMA`；使用已授权的 `route-v2-queries` 生成并校验）。
- 输出：`artifacts/route_v2_smoke/<timestamp>/preconditions.json`；全部前置通过时另有 `adapter.pt`、`smoke_result.json`、`metrics.json`；出现非有限训练数值时保存 `failure.json` 并立即中止。
- 检查：前置失败时退出码 2、不训练、不替换输入。通过时看 `smoke_result.json` 的 loss、grad_norm、`mean_gap`、`nonfinite_steps`。CPU，预计数分钟。smoke 结果永不进论文。

## route-v2-data-tests（身份与划分合成检查）

```powershell
uv run --offline --no-sync ruff check scripts/acquire_route_v2_external.py scripts/audit_route_v2_identity.py scripts/verify_route_v2_candidates.py src/layoutpatch/datasets/route_v2_split.py tests/datasets/test_route_v2_split.py tests/datasets/test_identity_verification.py
uv run --offline --no-sync pytest tests/datasets/test_route_v2_split.py tests/datasets/test_identity_verification.py
```

- 输入：合成身份/图像/划分；不读取真实问题或gold。
- 输出：终端结果；约数秒。
- 检查：不同来源角色隔离、全局ID保持、未知证据不自动通过、图像重编码控制与正文判据。

### 底层等价（备查）4/4：internal（本地全文近重复）

```powershell
uv run --offline --no-sync ruff check scripts/audit_route_v2_internal_duplicates.py tests/datasets/test_internal_identity.py
uv run --offline --no-sync pytest tests/datasets/test_internal_identity.py
uv run --offline --no-sync python scripts/audit_route_v2_internal_duplicates.py
```

- 输入：本地20395页OCR、已生成图像指纹；不读取答案/gold。
- 输出：`artifacts/route_v2_data/internal_identity_v1.json`及阈值策略；约数分钟。
- 检查：正文三词组Jaccard、低频倒排和图像候选；区别整文档重复、多页共享、单页模板和未知。不得由单个版权页认定整文档相同；划分侧保守处理未消解重叠。

## route-v2 单元检查（CPU合成数据，不是效果实验）

```powershell
uv run --offline --no-sync pytest tests/layout/test_schema.py tests/datasets/test_input_policy.py tests/datasets/test_route_v2_split.py tests/datasets/test_route_v2_regions.py tests/evaluation/test_region_labels.py tests/evaluation/test_region_metrics.py tests/evaluation/test_page_aware_iou.py tests/evaluation/test_localization.py tests/retrieval/test_fusion_shapes.py tests/retrieval/test_fusion_v2.py tests/retrieval/test_phase1c.py tests/retrieval/test_route_v2_scoring.py
```

- 输入：上述测试的合成张量及pytest临时目录数据；现有uv环境，不同步或下载依赖。
- 输出：终端通过/失败；只写pytest临时产物，不写真实数据、权重或runs。
- 检查：类型/OCR来源、新旧输入兼容、文档/页ID一致、空patch/mask、覆盖输入、小残差及同页IoU；通过不表示效果提升，完整质量门仍为check。

## version（冒烟，已实现）

```powershell
uv run lp version
```

- 输入：无
- 输出：`layoutpatch 0.1.0`
- 检查：环境搭建后第一条验证命令（不需要 GPU / 数据 / 网络）

## mmdocir-prepare（已实现，批次 M2）

```powershell
./tasks.ps1 mmdocir-prepare
```

- 输入：MMDocIR evaluation 原始数据（布局见 `docs/01-quickstart.md`）
- 输出：`data/processed/mmdocir_evaluation/{documents,pages,nodes,queries}.parquet` + `page_images/`
- 检查：对数 313 / 20395 / 170338 / 1658；`tasks.ps1` 内置断言

## mmdocir-smoke（已实现，批次 M3）

```powershell
./tasks.ps1 mmdocir-smoke
```

- 输入：`configs/experiments/mmdocir_colpali_smoke.yaml`（2 文档限流）+ embedding cache
- 输出：`runs/retrieval/mmdocir_colpali_smoke/<timestamp>/` 五件套
- 检查：`torch.cuda.is_available()=True`；smoke 结果不进论文

## mmdocir-colpali-full（已实现，批次 M3，EXP-001）

```powershell
./tasks.ps1 mmdocir-colpali-full
uv run lp evaluate --run runs/retrieval/mmdocir_colpali/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ `artifacts/colpali/` embedding cache
- 输出：`runs/retrieval/mmdocir_colpali/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：Page R@5 与旧仓库 EXP-002 的 0.8390 偏差 < 0.005 → 迁移验收通过；
  签名命中则复用缓存，不命中 GPU 重算并覆盖写回

## mmdocir-bge-m3-full（已实现，批次 M3，EXP-003）

```powershell
./tasks.ps1 mmdocir-bge-m3-full
uv run lp evaluate --run runs/retrieval/mmdocir_bge_m3_page/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ 本地 `BAAI/bge-m3`（`local_files_only=True` 可加载）
- 输出：`runs/retrieval/mmdocir_bge_m3_page/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：`run_info.json` 的 `actual_retrievers` 必须含 `dense:BAAI/bge-m3` 且不含 `dense:tfidf_fallback`；`require_model: true` 下模型缺席必须报错而不是降级；登记条件见小论文执行规范 `docs/PAPER_SPEC.md` 第 7.2 节 Phase 1A（query 数=1658 五件套齐全）

## mmdocir-hybrid-full（已实现，批次 M3，EXP-004）

```powershell
./tasks.ps1 mmdocir-hybrid-full
uv run lp evaluate --run runs/retrieval/mmdocir_hybrid_page/latest
```

- 输入：全量 parquet（313/20395/170338/1658）+ 本地 `BAAI/bge-m3`（Hybrid 内 dense 分支同 EXP-003 口径）
- 输出：`runs/retrieval/mmdocir_hybrid_page/<timestamp>/` 五件套（evaluate 后补 metrics.json/summary.md）
- 检查：`run_info.json` 的 `retriever_type=hybrid_page` 且 `retriever=hybrid_page`（RRF 融合 `page_methods=[bm25,dense]`，k=60）；dense 分支同样禁 TF-IDF 降级；登记条件同第 7.2 节

## phase1b-audit（已实现，批次 M4，坐标审计硬 Gate）

```powershell
uv run python scripts/run_phase1b_audit.py            # 全量机器门限 + 20 张叠图
uv run python scripts/run_phase1b_audit.py --limit-pages 50   # 快速试扫
```

- 输入：`data/processed/mmdocir_evaluation/nodes.parquet` + `data/interim/mmdocir_evaluation/page_images/`
- 输出：`artifacts/audit/mmdocir_evaluation/audit.json`（机器门限数值）+
  `artifacts/audit/mmdocir_evaluation/overlays/*.jpg`（≥20 张 patch 网格+布局框叠图）
- 检查（`docs/PAPER_SPEC.md` 第 6 节）：越界率 < 1%；无页级覆盖为 0 的异常页；
  人工抽查叠图回答"表格线/栏边界是否对齐"，任何一页不通过 → 停工修数据链。
  人工判读口径（2026-09-16 已固定）：看彩色框围没围住真实文字/表格
  （红=表格/橙=段落/绿=图），不看框边压没压蓝色网格线；
  页顶小字/页底文字/页码未被框住属官方标注稀疏，不是错位（用户已确认 `2021700463_p69` 通过）。

## phase1b-stratify（已实现，批次 M4，EXP-005 关门补证）

```powershell
uv run python scripts/run_phase1b_stratify.py --k 5 --iou 0.5
```

- 输入：EXP-001 run 的 `predictions.parquet`（Top-5）+ `nodes.parquet` + `region_labels.parquet`（2638 行：matched 2523 + unmapped 115；题级 matched 1598/unmapped_only 60；`page_size` 冻结只读）+ `queries.parquet`（问题类型）
- 输出：`artifacts/diagnosis/mmdocir_evaluation/` 下 `stratification.json`（分层表，`meta` 含 k/iou/面积均值定义/三分位点）+ `cases.json`（成功 10/失败 10/中间态 10 + `meta` 三档定义）+ `crosstab.json` + `addressability.json` + `oracle.json` + `strat_area_hist.png/json` + `strat_cov_hist.png/json` + `overlays_cases/*.jpg`（极值 20）+ `overlays_cases_mid/*.jpg`（中间态 10）
- 检查（小论文执行规范 `docs/PAPER_SPEC.md` 第 7.3 节）：分层键=问题类型归一化/面积均值三分位/OCR 密度均值三分位；成功=A 类 IoU 最高 10；失败=B 类 IoU 最低 10；中间态=B 类多样贪心 10；C_topk=0 为定义性结果不许写成发现；记录页 `experiments/2026-09-17-exp-005-gate-closeout.md` + registry EXP-005 行

## phase1c-baselines（已实现，批次 5，EXP-006）

```powershell
./tasks.ps1 phase1c-smoke
./tasks.ps1 phase1c-baselines
```

- 输入：EXP-001 Top-5 + `nodes.parquet` + `region_labels.parquet`（冻结只读）+ 冻结 ColPali 缓存（页向量缓存-only，query 文本塔 GPU 编码）
- 输出：`artifacts/baselines/mmdocir_1c/phase1c_smoke.json`（冒烟 10A/0B）+ `phase1c.json`（全量 1343A/45B：Snappy max/mean/iou + 固定 coverage/iou_mass + 分组 P25/P50/P75）+ `phase1c_picks.json`（1388 题逐题五档 picks，供 Text 双轨）+ `phase1c_probes.json`（`run_phase1c_probes.py` 清洗探针：cuda:0，n=19 去 warmup，权重基座 5653.3MB；query 编码 mean 38.1ms；七档选框合计 243.0ms，P75 191.7ms 最贵；单页单点不可推广）
- 检查（小论文执行规范 `docs/PAPER_SPEC.md` 第 7.4 节）：A Top-1 选框准确率（最高 0.3187 fixed:iou_mass）+ B 消解率（固定五档全 0.0）；B 分母为严格 45（非 47=45B+2A）；group 的 B 碰框率虚高不计消解；`page_size` 三用途行号见 EXP-006§3；记录页 `experiments/2026-09-17-exp-006-phase1c.md` + registry EXP-006 行

## phase1b-abcd（已实现，批次 M4，EXP-002）

```powershell
uv run python -c "from layoutpatch.evaluation.region_diagnosis import diagnose; d = diagnose(k=5); print(d.a_page_hit_region_hit, d.b_page_hit_region_miss, d.c_page_miss_region_hit, d.d_page_miss_region_miss)"
```

- 输入：EXP-001 run 的 `predictions.parquet`（Top-5）+ `nodes.parquet`（页内候选框）+ `region_labels.parquet`（2638 行 gold 区域）
- 输出：`artifacts/diagnosis/mmdocir_evaluation/abcd_diagnosis.json`
- 检查（`docs/PAPER_SPEC.md` 第 7.3 节）：A 页中区中 / B 页中区不中 / C 页不中区中 / D 都不中；
  当前值 A=1345/B=45/C=0/D=268，B 占页命中 3.24%；IoU 口径 `bbox_iou`≥0.5（0.3/0.5/0.7 敏感性 0.8154/0.8112/0.8100）；
  与 EXP-001 差 1 题为 gold 页口径差异（`mmdocir_01342`）；记录页 `experiments/2026-09-16-exp-002-abcd-diagnosis.md` + registry 第二行

## phase2r-arxivqa（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-arxivqa
```

- 输入：已编码的 ArxivQA `train_fit`/`train_dev` 页向量缓存；`dev_eval` id。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa/dev_eval.json`
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-dude（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-dude
```

- 输入：已编码的 DUDE `train_fit` 3330 页、`train_dev` 422 页。ColPali 与 bge 都必须非空。不读 `test_eval`。
- 输出：`artifacts/phase2r/dude/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_dude/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-arxivqa-dude（已实现，方案 A，不是全融合）

```powershell
./tasks.ps1 phase2r-arxivqa-dude
```

- 输入：已有缓存里的 ArxivQA 与 DUDE `train_fit`/`train_dev` 页。缺页即停，不新编页。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa_dude/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_arxivqa_dude/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## phase2r-gap-audit（只读，不训练）

```powershell
uv run python scripts/audit_phase2r_gaps.py
```

- 输入：三份冻结 `ranker.pt`、`dev_eval_region_401.txt`、当前 `region_labels.parquet`。不读 `test_eval`。
- 输出：`experiments/s2_splits/phase2r_gap_proof.json`、`phase2r_per_question.jsonl`、`phase2r_per_question_summary.json`。
- 检查：401 题单等于现行 matched 题；六个 Area 汇总数与三份旧 `metrics.json` 逐位一致。不改权重。

## phase2r-arxivqa-notext（无文本对照，不替换当前头）

```powershell
./tasks.ps1 phase2r-arxivqa-notext
```

- 输入：已有 ArxivQA 页缓存。缓存数量不是 8341 就停。不编新页。不读 `test_eval`。
- 输出：`artifacts/phase2r/arxivqa_notext/ranker.pt`，以及 `runs/retrieval/mmdocir_phase2r_arxivqa_notext/<timestamp>/` 五件套。
- 检查：历史任务；2-R 已停止；不得重跑，不得读 test_eval。

## fusion-arxivqa（第一次正式融合训练，ArxivQA 单域）

```powershell
./tasks.ps1 fusion-arxivqa
```

- 输入：已有 ArxivQA `train_fit`/`train_dev` 页向量与 query 缓存；训练 parquet 真实框；`dev_eval` id。不读 `test_eval`。不编码新页。不加载 ColPali。
- 输出：`artifacts/fusion/arxivqa/` 的 fusion checkpoint，以及 `runs/retrieval/mmdocir_fusion_arxivqa/<timestamp>/` 五件套。
- 检查：监督只有页级正负页；不覆盖任何 `ranker.pt`；区域分母 401，页级分母 415；未过 geom:area 则只记 dev 失败，不读 test_eval。

## region-ann-pilot（40 题本地标注流程，不训练）

```powershell
./tasks.ps1 region-ann-pilot
```

- 输入：`experiments/region_annotation/arxivqa_pilot_manifest.jsonl` + `pilot_materials/samples/*/page.png|overlay.png`。不读 `dev_eval` / `test_eval`。不改 template / manifest。不自动填框。不覆盖已有 `labels_annotator_A.jsonl` / `labels_annotator_B.jsonl`。v1 结果用独立文件，例如 `labels_annotator_A_v1.jsonl`。
- 输出：`pilot_materials/workbook.html` + `workbook.js`。人工标签由浏览器导出为独立 A/B 文件。检查可用 `uv run python scripts/region_ann_pilot.py check --annotator A|B`，或 `--labels` 指向临时/归档文件。
- 检查：40 题 PNG 都能打开；报告缺失字段、重复题目、非法/重复 `box_id`、状态冲突、无候选与选框冲突、题目元数据是否被改。`pending` 的 `cover_ok` / `no_candidate` / `cross_box` 必须为 `null`。多个独立 `full` 框允许 `cross_box=false`。浏览器不会写回仓库文件。
