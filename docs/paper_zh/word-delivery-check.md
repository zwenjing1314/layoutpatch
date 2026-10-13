# 中文小论文 Word 导师阅读稿交付检查

完成日期：2026-10-12。本稿用于导师阅读，未声称符合任何期刊投稿模板；未发送给导师。

## 交付与来源

- Word：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/paper-advisor-v1.docx
- 图文对照稿：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/manuscript-illustrated.md
- 正文唯一入口为 @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/manuscript-revised.md；原稿及分节稿保留。
- 审阅依据：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/review-round1.md；文献依据：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/references-evidence.md。
- 本轮仅生成写作与图表产物，未新增实验、读取预测、重评分、训练、调参或改动旧结果。

## 参考版式与中文调整

参考 PDF：@C:/Users/WenJing/Desktop/论文第三阶段阅读/Spatially-Grounded Document Retrieval via Patch-to-Region Relevance Propagation.pdf。

已检查首页及第5、10、15页，覆盖正文、公式、表格与图片。PDF为21页，页面尺寸612×792 pt（US Letter），单栏，正文左右留白约18 mm；标题居中，标题层次编号加粗，公式居中、编号靠右，表题在表格上方、图注在图片下方，表格使用较少横线。仅借鉴版式关系，不复制作者、单位、标志或论文内容。

导师稿采用Letter单栏，左右页边距20.32 mm，上19.05 mm、下18.29 mm；正文宋体10.5 pt，标题黑体，英文Times New Roman，公式Cambria Math，正文1.18倍行距。表格字体8.5—9 pt，使用浅色表头和细网格帮助核读。没有编造作者与单位。

## 图表与可编辑性

两图由SVG矢量工具自绘，非AI生成；保留SVG与构建源文件，Word实际嵌入高清PNG。

| 图 | 支持的论点与边界 | 源文件与Word兼容版本 |
|---|---|---|
| 图1 任务与空间对应示意 | 问题与整页图像分别编码；解析候选叠加于patch网格；空间对应与IoU评分权重不同；只展示排序接口 | @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/figure-1-task.svg；@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/figure-1-task.png（5000×2167 px） |
| 图2 方法结构与局部融合 | B固定评分、C/D平行适配、D注意力/残差MLP/gate、E事后直接排序；gold仅用于训练监督 | @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/figure-2-methods.svg；@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/figure-2-methods.png（5333×3533 px） |

图1及图注明确“示意图，非实验样本”，候选蓝框不表示gold或成功预测。未制作真实案例或重复结果柱状图。图2移除了会穿越E分支的放大连线，避免误读为方法串联。

六张既有表加一张数据角色表，均为原生、可编辑Word表格；符号表移至附录A，正文引用同步调整。

| 新编号 | 内容 | 既有来源与处理 |
|---|---|---|
| 表1 | 方法差异 | 原表3-2；统一名称、输入、监督粒度与E事后标记 |
| 表2 | 数据角色与实际分母 | 依据现有第4节新增；分别列文档数、题数、唯一页数、题—页单元数；缺字段为“—”，不推算 |
| 表3 | source_dev开发结果 | 原表5-1；保留全部方法、三seed均值与标准差、Top-5指标 |
| 表4 | 原冻结外部结果 | 原表5-2；保留面积、全部原冻结方法和不利结果 |
| 表5 | 原冻结外部三项比较 | 原表5-3；保留普通95%与Bonferroni 98.333%区间及差值方向 |
| 表6 | E事后补充外部结果 | 原表5-4；单独呈现，唯一补充95%配对区间保留在紧邻正文 |
| 表7 | 主要符号与维度 | 原表3-1；放附录A |

21组带编号的显示公式及行内数学均转换为可编辑OMML公式（共162个数学对象），没有公式截图或LaTeX源码。图表和公式交叉引用使用一致的可编辑文字编号；目前未转换为Word自动交叉引用域，后续插删图表需同步编号。

## 发现与修正

1. 候选池化段引用“式（15）”改为“式（16）”；patch损失解释中的“式（19）”改为“式（20）”，与相邻既有公式一致。
2. 退化节点对应“全零行”容易与正文定义的N×M矩阵方向冲突，改为“退化节点的空间对应权重为零”，不改计算式。
3. 第4.4节原句称E的checkpoint选择分母与C/D不同，但第4.2节及本节均明确使用source_val的374题、448单元。修订为选择分母相同；不同训练子集、监督粒度及模型结构仍保留。依据仅为唯一入口稿内的明确记录，未开展额外审计。
4. 长小数按已有精确值舍入为四位小数，未从舍入均值重算差值。精度整理严格排除参考文献，恢复并核对六条完整arXiv标识，防止误将文献标识作为小数舍入。
5. 初次公式转换使Word为求和符号附加空操作数占位；调整OMML转换后占位消失。分段函数改用可伸展括号，长公式按既有语义分隔换行，公式编号保留右对齐。
6. 去除默认标题装饰线，修正标题中文字体、图中P′/W/f的下标，并解除图注与后续章节的不必要分页联动。原大型Mermaid草案已被实际图片替换。
7. 清理“本轮”“第1轮”等局部工程措辞；Word正文未混入写作核对备注、本地路径、任务指令或待办清单。

## 渲染与结构核验结果

技能原始render_docx.py已实际调用，直接转换因环境缺少LibreOffice soffice.exe而失败。随后用本机Microsoft Word的ExportAsFixedFormat导出实际Word文件的PDF，再由documents技能render_docx.py的rasterize流程及随附Poppler以160 dpi渲染全部页面；不是用另一个排版系统重建替代PDF。

- 最终稿17页，已逐页查看；后续仅改动参考文献标识的最后一次导出中，第16页重新查看，其余16页图像哈希与前次一致。
- 已检查正文与标题层次、中文与数学字体、上下标、分式及分段括号、21个连续公式编号、两张图的文字和箭头、全部表格与图注、页码及文献页面。
- 未发现公式截断、图表越界、缺字、标题孤行、表格拆分跨页或图片模糊。不可拆分的整图/整表前保留必要留白。
- DOCX结构核验：7张原生表格、2个实际嵌入图像、162个可编辑数学对象、公式编号（1）—（21）完整、6个临时引用键与6条文末参考文献一一对应。
- 最终Word文件948627 bytes。完整arXiv标识为2407.01449、2512.02660、2510.27261、2501.08828、2511.15090、2204.08387。
- 保留面积与Top-5不利结果、D及E的seed波动；E未回填原冻结三项比较族。原冻结结论与E补充结论分开。

渲染页面与验证PDF：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/word-render/；结构核验记录：@C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/figures/delivery-verification.json。

## 尚存限制与未决项

- SciEGQA数据许可仍待核实；Snappy、RegionRAG及SciEGQA未独立核实的正式出版状态仍按既有预印本信息引用。本轮未扩大文献检索。
- 内部候选解析原版本不可完整追溯，已作为局限披露；不将“完全对齐解析配置”列为必须执行的任务。E训练调用中全部掩码细节仍属于既有待核实项，未追加事实。
- 页面召回、候选生成器或完整任务链性能、完整系统成本及所述机制假设未验证；固定候选Oracle上限分析与生成器评估已区分。
- 本稿仍使用临时引用键；跨设备缺少宋体、黑体或Cambria Math时可能重排。当前环境的实际Word渲染已经检查，但未验证其他Word版本或替代办公套件。

## 建议导师重点反馈

1. “正确页面后的固定候选排序”这一研究边界与实证比较定位是否足够清楚，贡献表述是否适合当前证据规模？
2. 原冻结实验的主指标收益、面积/Top-5边界与E事后补充发现，是否形成了连贯且克制的论证？
3. 方法比较中不同监督粒度、训练子集及候选来源的说明是否充分，哪些方法或讨论段落还需精简？
