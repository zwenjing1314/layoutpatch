# SciEGQA外部定位准备（2026-10-07）

## 固定八页最后工程验收（最新；视觉/几何通过，完整文本接口阻塞）

### 叠图视觉检查

已通过Read工具逐张视觉检查目录`@artifacts/route_v2_external/preparation_v1/20261007_200400/overlays/`中固定page_id为2309.06983_p1/p2/p3/p4/p5/p6/p7/p9的8张PNG（由助手目视复核，不冒称用户人工签字）。8/8页未见错页、旋转、整体偏移或异常裁剪；页脚显示的源页号分别为2、3、4、5、6、7、8、10，与固定page_id一致。框线较粗、标签较小，按要求只记录不改变候选规则。p4、p5、p6、p7等页面底部出现自然分页连续文本，内容在页面边界处结束，不属于叠图工具截断；未发现框超出画布或把相邻页内容错误合并。

### 官方原图下载与映射

- 本轮已执行登记任务`@tasks.ps1 route-v2-external-images`，没有重复安装、模型下载、MinerU解析或训练。固定官方地址和revision为`9bdca77be633cc3259d7e3739d35b38ab00bf5d9`；实际压缩包`@data/raw/sciegqa_bench/9bdca77be633cc3259d7e3739d35b38ab00bf5d9/Images.tar`大小 **1,127,372,800 bytes**，SHA256 **`aa8f7e6f5c27fb914a2b36f6accc63fdd48f549f97c2212e03f2b6a85e67b368`**，与授权值一致。下载耗时记录为394.578秒；只提取固定8个archive member。
- 固定8页原图均为 **2550×3300**，EXIF orientation均为1；对应PDF渲染图均为 **1224×1584**。PDF几何仍为612×792 point、rotation=0、MediaBox=CropBox=[0,0,612,792]。8/8页内容映射通过，不是只按宽高判断：前景框边界差最大0.00052，前景内容IoU最低0.9628，灰度相关最低0.9985，最佳低分辨率位移均为(0,0)。
- 映射证据与逐页回执：`@artifacts/route_v2_external/preparation_v1/20261007_221908/image_mapping_audit.json`、`@artifacts/route_v2_external/preparation_v1/20261007_221908/page_receipts.json`；8张提取原图位于该任务配置指定的固定原图目录。没有发现无法解释的裁剪、旋转或内容差异。

### 坐标和候选接口最终核对

- 最终逐页回执及汇总：`@artifacts/route_v2_external/preparation_v1/20261007_231625_final_review/`。真实PDF/渲染/候选/原始解析哈希及页身份一致；8页原标注bbox与rel_bbox的转换一致性通过，未计算候选与gold重叠。源原图到渲染变换为x、y均乘0.48；该变换由内容对齐证据支持，不仅来自尺寸比。
- SciEGQA gold `rel_bbox`为0–1000，MinerU块框为0–1归一化xyxy；50条候选的几何、类型和页身份结构通过。本次只允许这8页必要的标注坐标元数据，不处理或输出问答，不用gold改变候选。
- **完整接口需要补接，撤回本轮早期“无需修改”的表述。** 对照冻结`@configs/experiments/route_v2_exp2_D.yaml`和实际`@src/layoutpatch/retrieval/route_v2_layout.py`：`node_text`对text/title/equation选`text`，对image/table选`ocr_text`。外部导出只把解析文本放在`text`，`ocr_text=null`；合成检查证明图表会丢失非空解析文本。实际8页只包含text/title，故本样本没有真实丢失，不代表图表路径通过。
- 原D必须保留真实图表/正文解析文本，先补显式的外部文本来源适配及合成回归；不能把原生PDF混合文本直接重命名为OCR，不能以空字符串替代已有文本，也不能回退到生成描述。当前来源标记仅能说明Basic/auto可能选择原生PDF或OCR，逐span来源仍未解析；本轮未改旧字段选择器、冻结比较、旧候选或权重，未声称该问题已经修好。
- `page_layout`实际构造已逐页检查：`text=[M,1024]`、`coords=[M,6]`、`types=[M]`、布尔`mask=[M]`、`W_raw/W_attn=[1024,M]`。使用零占位向量只测结构，没有编码或模型前向。当前单页变长M，无padding；真实空文本节点仍mask=true，文本向量应置零并保留缺失标记；未来批处理padding须mask=false，既有融合实现会在softmax前屏蔽。真实向量缓存尚未生成/验收。
- 首个临时PowerShell范围核对错误地用页面宽度限制y坐标，误报15条；按x/y各自边界纠正后0异常，随后登记任务通过实际消费者完成核对。早期缺字段检查仅为临时摘要，不作为完整接口通过证据。正文不粘贴文本或标注框。

- 本轮最终定向Ruff通过、11项合成测试通过（1.58秒）；覆盖内容错页/旋转拒绝、完整archive成员身份、0–1000转换、图表文本丢失复现、空文本非padding与空页。未重跑训练smoke或旧元数据审计；只修本轮新增脚本的未使用变量/导入顺序问题，不修19个旧Ruff问题。最终检查任务保护哈希及Git差异确认原比较、解析冻结配置和训练依赖锁未改。

### 全量边界与下一步（未执行）

最终状态为`fixed_eight_geometry_reviewed_external_text_contract_blocked`。8/8视觉、8/8原图内容映射及必要标注坐标一致性通过，仍**不具备全量准备条件**：原D的图表文本接入/来源未解决，完整全量任务尚未实现。固定图像任务的exit0只表示图像部分完成，不能替代最终接口验收。

后续全量计划必须遍历manifest全部837唯一证据页，逐页核对PDF/原图archive完整相对路径与成员唯一性、文档/页号/index、哈希、rotation/MediaBox/CropBox、原图尺寸和内容对齐，再检查解析候选类型/坐标/文本来源及页身份。异常页保留回执并阻塞准入，全部1623题/1941unit保留；不能将本单文档8页的结果推广为全837页通过。

尚缺外部文本适配、全量任务实现/登记/授权、全部页与问题视觉/文本向量缓存及磁盘/时间预算核定。已有PDF/Images.tar与解析模型可复用，不要求再下载；数据许可仍单独未解决。此前暂列的全量任务名未实现，已撤回可执行建议。下一条真实登记的命令是`route-v2-external-final-review`（完整语法见`@docs/02-commands.md`），只用于接口修复后的固定8页复核，不是全量入口；当前继续运行仍会报告文本阻塞。

## 固定八页续接结果（历史；当时导出完成，视觉与原图映射待验）

本次仅执行用户授权的独立uv解析环境核验及固定八页工程准备，未研究或修改实验路线。两份元数据回执的脚本访问已恢复；固定清单哈希与下文记录一致，没有重建清单或重新选页。冻结比较配置中的旧安装禁令/零页状态作为历史快照保留；本次独立授权与执行参数另见`@configs/tools/mineru_external_pages_v1.yaml`，未改原比较计划。

### 工具与模型身份

- 复用中断前已建好的独立环境`@artifacts/route_v2_external/preparation_v1/mineru_tool_v1/.venv/`，解释器来源登记为项目`@.venv/Scripts/python.exe`；实际Python 3.11.16，base prefix为`@C:/Users/WenJing/AppData/Roaming/uv/python/cpython-3.11-windows-x86_64-none`，不是Anaconda。本次续接未重装依赖或下载数据/模型，不修改训练环境及其锁文件。
- 实际MinerU **4.0.10**、onnxruntime **1.30.0**、docvortex **0.5.10**。固定Basic、ONNX、auto文本模式；七个新解析进程实际会话均为`CPUExecutionProvider`，解析时离线、未使用GPU。
- 模型：`opendatalab/MinerU-4_models_onnx`，revision **`358310b4f64b95f9fefc372ad899356e4111f376`**。已核对本地各文件SHA256、下载元数据revision及对应LFS SHA256/Git blob SHA1。原下载日志13文件，实际落盘 **858204914 bytes**；这是模型文件大小，不是测得网络流量，网络协议/重试字节未计量。本次续接下载量为0。
- 旧安装日志阶段耗时resolved 7.84秒、prepared 56.61秒、installed 2.69秒；完整安装墙钟未保存。旧模型下载进度为`13/13 [04:47]`（287秒，仅日志显示精度），不冒称完整墙钟测量。日志保存在`@artifacts/route_v2_external/preparation_v1/mineru_tool_v1/`，未向聊天打印完整日志。
- 官方来源：[固定发布包](https://pypi.org/project/mineru/4.0.10/)、[输出文档](https://opendatalab.github.io/MinerU/reference/output_files/)、[固定模型卡](https://huggingface.co/opendatalab/MinerU-4_models_onnx/blob/358310b4f64b95f9fefc372ad899356e4111f376/README.md)。包许可标识为`LicenseRef-MinerU-Open-Source-License`：Apache 2.0基础加商业门槛（月活超过1亿或月收入超过2000万美元）及线上服务署名义务，不能写成纯Apache 2.0。模型卡要求继续遵循原组件许可；没有核实到独立统一LICENSE，不能声称所有模型均为纯Apache 2.0。数据许可仍未明确。

### 固定输入、续接与逐页结果

本次成功产物目录：`@artifacts/route_v2_external/preparation_v1/20261007_200400/`。固定文档`2309.06983`，源PDF 1-based页号2、3、4、5、6、7、8、10。复用`@artifacts/route_v2_external/preparation_v1/20261007_184934/`的PDF、八张渲染图及第一页原始解析；PDF已与原tar内唯一对应成员逐字节哈希核对，没有重复解包或渲染。

| 固定page_id | 源页号 | 候选数 | 本次解析进程耗时（秒） | 本进程峰值工作集（bytes） | 状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2309.06983_p1 | 2 | 3 | null | null | 复用旧原始解析；旧逐页资源未保存 |
| 2309.06983_p2 | 3 | 7 | 4.099294 | 641826816 | 新解析成功 |
| 2309.06983_p3 | 4 | 7 | 3.959645 | 648966144 | 新解析成功 |
| 2309.06983_p4 | 5 | 5 | 3.953097 | 657506304 | 新解析成功 |
| 2309.06983_p5 | 6 | 8 | 3.894712 | 635064320 | 新解析成功 |
| 2309.06983_p6 | 7 | 6 | 3.983679 | 689655808 | 新解析成功 |
| 2309.06983_p7 | 8 | 7 | 4.025472 | 641294336 | 新解析成功 |
| 2309.06983_p9 | 10 | 7 | 3.981422 | 665264128 | 新解析成功 |

八页候选导出8/8、共50候选、生成8张叠图；七页新解析、一页复用，本次续接失败0。精确逐页资源见`@artifacts/route_v2_external/preparation_v1/20261007_200400/page_metrics.json`和该目录各页回执，汇总见`@artifacts/route_v2_external/preparation_v1/20261007_200400/audit.json`。七页耗时合计 **27.897秒**，最大解析进程峰值工作集 **657.71 MiB**（689655808 bytes，不是显存或全系统峰值）；ONNX会话加载合计6.491秒、工具导入合计5.285秒，二者均为七个逐页进程的累计，不是单次模型加载时间，已包含在上述进程耗时中。

旧失败保留：`@artifacts/route_v2_external/preparation_v1/20261007_184758/`因输出父目录创建错误`WinError 3`失败；`@artifacts/route_v2_external/preparation_v1/20261007_184934/`已产出第一页，但旧适配器按旧输出结构查找JSON失败。后者总运行8.428秒不是第一页解析耗时，不能用来补造旧页资源记录。修正目录创建与新结构适配后只补余下七页，旧产物未覆盖。

### 坐标与接口检查边界

- 当前输出为`docvortex.middle` schema 2.0；`docvortex_layout`扩展version 1提供PDF point尺寸和源0-based页索引。块框是左上角原点、x向右/y向下的 **0–1归一化xyxy**，不是旧`pdf_info`像素框。
- 八页均为612×792 point、MediaBox=CropBox=[0,0,612,792]、rotation=0；复用渲染1224×1584像素、144 dpi，即point到像素2倍。归一化框按渲染宽高分别相乘，不剪裁、不根据gold修框。源页身份、PDF/解析画布、框有限值/顺序/边界及到448×448模型画布的字段转换检查通过；坏框/越界/重复框/无候选页均为0。
- 候选仅取顶层块，保留原块身份和独立重复框政策；解析器未接收问题、答案或gold。auto模式文本可能来自原生PDF或OCR，逐span来源未拆分，明确标注`MinerU_basic_auto_native_PDF_or_OCR_per_span_unresolved_no_VLM_description`，`ocr_text/vlm_text`留null，不能称纯OCR文本，也不能冒称与MMDocIR原生成版本相同。
- 接口验收仅覆盖候选字段、类型和既有坐标转换；没有运行排序、效果指标或Oracle，没有检查/生成向量缓存，外部文本编码规则仍待明确。
- **视觉检查0/8，完整坐标验收未完成。** Read工具读取精确文件`@artifacts/route_v2_external/preparation_v1/20261007_200400/overlays/2309.06983_p1.png`返回原始短错误`permission denied`。`@.cursorignore`仍排除PNG及新产物目录，仅精确放行先前两份JSON；这是Cursor读取限制，未确认Windows ACL故障，也不是命令执行审批失败。已停止图像查看，没有复制文件、改ACL、安全设置或换入口绕过。
- 原SciEGQA发布图像尺寸及其与PDF渲染坐标的映射仍未核验；数据集0–1000的rel_bbox定义不等于本解析器0–1框契约。上述机器通过只说明解析器到当前渲染图的结构映射，不说明标注框与候选处于已验证的共同坐标系。原始图像映射保持unverified，不能称外部测试输入就绪。

### 预算、检查与停止

全837页只按七个逐页解析进程均值外推：`27.8973205 / 7 × 837 / 60 ≈ 55.60分钟`。这只是**解析环节粗估**；固定同一文档的小样本不代表全库，首复用页无计时，不包含未测的渲染/视觉编码/安装下载/人工验收，也不据此承诺完整端到端预算或全库候选量。

本次已运行登记的status、tool-status、contract、tests、pages入口；安装是在中断前完成，本次仅核验复用，不把缺少完整执行链的安装记录包装成已登记安装任务。定向Ruff通过、6项合成测试通过（1.47秒）；元数据旧测试/审计不重跑，不修19个旧Ruff问题，不运行全仓check。执行回执确认冻结比较配置、训练依赖声明/锁文件、既有权重身份清单前后哈希未变；未加载或修改训练权重。

解析参数见`@configs/tools/mineru_external_pages_v1.yaml`；可追溯产物包括`@artifacts/route_v2_external/preparation_v1/20261007_200400/tool_manifest.json`、`@artifacts/route_v2_external/preparation_v1/20261007_200400/input_identity.json`、`@artifacts/route_v2_external/preparation_v1/20261007_200400/render_manifest.json`、`@artifacts/route_v2_external/preparation_v1/20261007_200400/candidates.jsonl`、`@artifacts/route_v2_external/preparation_v1/20261007_200400/coordinate_audit.json`及`@artifacts/route_v2_external/preparation_v1/20261007_200400/overlays/`。工程登记为EXTERNAL-PREP-PAGES，效果指标列空白，不冒充正式效果实验。

结论：当前状态`eight_pages_exported_visual_review_pending`，`full_preparation_ready=false`。下一步仅为受控放行八张叠图或由用户人工复核，并补齐原始图像坐标映射；本轮已停止，不训练、不评分、不算Oracle、不扩大下载或启动837页全量。

## 历史：17:12后续授权与执行阻塞

以下各节保留当时状态，旧“未安装/八页未启动/只能训练环境”不代表上方最新续接结果；历史元数据与比较冻结事实继续有效。

用户已明确授权在项目内独立uv工具环境安装必要MinerU依赖/配套模型，并仅处理既有manifest固定八页；本次授权取代下文关于“待批准”和“只能使用训练环境”的旧准备限制。训练环境依赖/锁文件、比较配置和模型权重保持不变。

本次未完成八页验收：访问指定`@artifacts/route_v2_external/preparation_v1/20261007_155402/manifest.json`和`@artifacts/route_v2_external/preparation_v1/20261007_155402/audit.json`时，读取工具均返回`permission denied`。没有获得回执内容，未绕过限制、重新选页或启动依赖步骤。需先恢复这两份文件的受控访问；该错误不代表文件缺失或数据不合法。

官方核查的有限结论：官方[安装说明](https://github.com/opendatalab/MinerU/blob/master/docs/en/quick_start/index.md)声明4.0稳定系列支持Python >=3.10,<3.15及Windows；[后端说明](https://github.com/opendatalab/MinerU/blob/master/docs/en/usage/tiers.md)明确Basic可使用ONNX/CPU而不需VLM；[模型来源](https://github.com/opendatalab/MinerU/blob/master/docs/en/usage/model_source.md)给出`MinerU-4_models_onnx`及Basic专用下载入口。网页是可变master，尚未绑定发布提交；具体补丁版本、发布包身份、许可和输出坐标契约核查未完成，不能视作安装准入已全部通过。

本轮执行的环境查询为`uv python find 3.12; uv pip index versions mineru`：前者指向`@C:/Users/WenJing/anaconda3/python.exe`，未使用该解释器；后者返回`error: unrecognized subcommand 'index'`，未安装任何版本。官方GitHub最新发布API返回HTTP403；未据此猜测版本。没有创建工具环境、下载安装包/模型或运行八页；安装/下载耗时及量、解析耗时/内存/候选数均无实测值。普通网页获取不计模型下载量。无新增实验入口或适配代码，不重复测试已通过逻辑。

当前尚不具备全量准备条件。以下保留上一轮已核验的比较冻结与元数据记录，不作为本次八页执行结果。

## 状态与比较冻结

比较计划已冻结；输入流水线被本地解析器缺失阻塞，未执行八页渲染/解析/缓存验证、训练或外部效果评分。配置：`@configs/experiments/route_v2_external_v1.yaml`。

- 主候选D-no-text由EXP-016的source_dev结果选出，尚无独立验证；原D作为文本对照，另保留A面积、B冻结传播、C普通适配器、C-wide。既有论文贡献结论不改。
- 四种训练方法各保留seed0/1/2的source_val最佳权重，不选开发集最佳seed、不载smoke、不重训。程序由冻结配置及registry精确取得运行与选择回执，仅校验必要字段和文件哈希，未加载权重张量。
- 十二权重身份清单：`@artifacts/route_v2_external/preparation_v1/20261007_152240/weights.json`，SHA256 `5a1bc2a05dfdd5b7287862a6b04928f30b0d90612b6cc2abb77aad7c4bebbe0f`，已绑定到配置。清单含每seed路径/哈希/选择epoch、原运行目录/配置及选择回执哈希，不含预测。
- 外部主比较固定为D-no-text−A/B/C-wide；沿用文档bootstrap2000次、seed0、原95%区间，三项Bonferroni补充98.333%区间（近似覆盖）。D-no-text−D/C仅次要探索分析，不事后升为主比较。题内页平均再题宏平均，训练方法先逐题三seed平均；全部主辅指标、随机/Oracle、M≥2分母、面积统计及辅助McNemar在未来正式测试时保留，本轮均未计算。

## 固定数据与格式

HF `Yuwh07/SciEGQA-Bench`，revision `9bdca77be633cc3259d7e3739d35b38ab00bf5d9`；全部1623题，未删除失败题。JSONL/PDF.tar校验和与既有获取回执一致，不下载数据。任务仅为给定正确页的固定候选框定位，非全库检索。

最终只读元数据回执：`@artifacts/route_v2_external/preparation_v1/20261007_155402/audit.json`；清单：`@artifacts/route_v2_external/preparation_v1/20261007_155402/manifest.json`，SHA256 `387b2f498ec4bb54abb7aab0a149ef46aa7856c284d2472541d61a7940d0347d`。程序实际清点80文档、837唯一证据页、1941问题—页单元；1305题单页、318题双页。837来自集合去重，未硬编码；1941是题—页单元数，不能当作唯一页数。

- 当前原始字段为`query/answer/doc_name/category/evidence_page/bbox/rel_bbox/subimg_type`，无自带query_id，采用绑定源哈希的行号ID。未输出问题、答案、gold坐标或类型内容。
- 固定[数据卡](https://huggingface.co/datasets/Yuwh07/SciEGQA-Bench/blob/9bdca77be633cc3259d7e3739d35b38ab00bf5d9/README.md)确认evidence_page为1-based，对应PNG文件名；bbox为像素xyxy，按证据页嵌套，每页可多框。
- [官方转换代码](https://github.com/yuwenhan07/SciEGQA/blob/4552a0e957d1091129118c1666d1ff5f76f74aad/generate/local_generate/data_transfer.py)明确rel_bbox为0–1000坐标，不是0–1。该代码的BBox-DocVQA兼容字段`bbox_docvqa_id`与`sciegqa_id`、`messages/images`属于转换输出，并非当前原始JSON字段；原始输入不能直接按旧转换封装加载。未获得另一个固定旧原始发布版本，不能声称原始新旧字段完全相同或仅文件改名。
- 第一次格式检查误用0–1，错误地标记1623题；该回执保留在`@artifacts/route_v2_external/preparation_v1/20261007_154120/`，不得当数据缺陷引用。按官方0–1000定义修正后，所有1623题通过字段/嵌套/有限值/框顺序及相对边界检查，失败题数0。只是格式合法，不代表实际渲染坐标映射通过。
- manifest保留doc_id、源页号、内部0-based页索引、官方图像相对路径、全部题身份与失败字段。原图尺寸和渲染变换尚未实测，明确为null并标pending，不从gold推算尺寸，不做猜测坐标换算。

## 候选解析器来源及唯一当前直接阻塞

MMDocIR使用官方布局parquet，版面类型/框来自MinerU的证据沿用已核查的`@experiments/2026-10-06-exp-015-preparation.md`第1节。原生成版本、模型revision及参数不可追溯；逐节点OCR引擎版本也未给出。因此外部新流水线即使也叫MinerU，仍不能声称与训练候选完全同配置。Snappy式传播只是评分规则，未将其当前默认OCR称为论文原始配置。

只核查项目唯一`.venv`的包元数据、`@.venv/Scripts/mineru.exe`、`@.venv/Scripts/magic-pdf.exe`及用户目录的两个明确配置文件。mineru/magic-pdf均未安装，执行文件/配置不存在；已有PyMuPDF1.28.2，只能用于PDF读取/渲染，不能作为同等版面/OCR候选的替代。没有扫描整个磁盘，没有试用其它解析器或生成占位候选。

当前直接阻塞：没有可执行、模型身份已绑定的MinerU候选生成流水线。解除后仍须完成原始图像坐标与PDF渲染坐标的工程映射验收；本轮没有把它标成已验证。

具体待批准方案（未实施）：采用MinerU 4.0 Basic的ONNX CPU解析，固定其补丁版本、模型revision和全部参数，独立于gold处理八张整页，输出页块框、类型与文本。它属于新外部解析配置，不冒充MMDocIR原版；不用VLM描述替代OCR。按[官方工具说明](https://github.com/opendatalab/MinerU)，Basic ONNX模型约0.8GB、最低内存约2GB、可CPU运行；这些是工具文档估计，非本机实测。缺少MinerU/ONNX依赖、配套模型和配置；模型是否另有缓存未作全盘搜索，不能断言所有磁盘均不存在。

批准后只能在既有uv环境登记并锁定依赖，先检查与现有Torch/ColPali兼容性，不能自动降级旧依赖。旧权重/结果保持不变；回退为移除新增依赖声明和新缓存、恢复本轮阻塞状态（实际删除另行确认）。本轮没有安装、下载或开始部署。

## 八页验证与完整预算

八个唯一证据页已按doc_id、整数页号升序从完整manifest固定选出；选择只使用证据页身份，不使用答案、gold框大小/覆盖或模型表现。八页ID保存在manifest，不输出标注内容。

- 实际完成：渲染0/8，解析0/8，候选坐标及缓存接口未运行。
- 八页实际耗时、峰值显存、候选数量：均未测，记null而不是0秒、0显存或零候选。
- 阻塞原因：解析器前置条件缺失；因此未启动依赖步骤。最后0.168秒仅为元数据/哈希核验耗时，不是八页处理耗时。
- 全量范围：837唯一证据页，所有方法必须共用同一渲染、候选及1623题/1941unit分母；失败记录不能静默删除。
- 尚无八页计时，无法给出可靠全量分钟数/显存/候选量。后续测得单次加载L、八页端到端T8后，仅作粗估`L+(T8-L)×837/8`（倍数104.625），并声明固定前八页并非随机性能样本。磁盘同理依实际八页输出均值估计。新模型下载预算约0.8GB另计，依赖占用和本机处理耗时待批准后实测；全量解析/视觉编码仍未获本轮授权。

## 检查与停止

新增适配相关Ruff通过、5项定向测试通过（最终1.44秒）：4项合成测试覆盖多页/页号/坐标格式、失败题保留和选页独立性，1项检查最终冻结YAML可解析且比较清单、指标与执行禁令一致。未处理19个旧Ruff问题，未运行全仓检查，收尾未重跑数据审计。新增入口`route-v2-external-tests`与`route-v2-external-audit`登记在`@docs/02-commands.md`；准备状态以`EXTERNAL-PREP`登记，指标列留空，不冒充正式效果实验。

数据许可仍未明确：数据卡没有开放许可证，论文许可不替代数据许可。本轮只做本地元数据准备，不再分发数据。没有外部方法效果、Oracle或命中率，也没有全量解析/编码。比较计划冻结不等于测试输入就绪；在解析器与映射验收完成前停止。
