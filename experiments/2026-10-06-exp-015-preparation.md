# 2026-10-06 EXP-015 布局D实现准备与训练侧验收

> 非正式EXP运行；状态：训练侧可运行验收通过，EXP-015配置working，正式训练未启动。保留EXP-014全部产物，不重训C或重评source_dev。

## 1. 文本来源与取值规则

固定官方证据：[MMDocIR Evaluation数据卡](https://huggingface.co/datasets/MMDocIR/MMDocIR_Evaluation_Dataset/blob/bdcb36ecb3eee73667180ee3fb24fe433f6dd2a4/README.md)，revision `bdcb36ecb3eee73667180ee3fb24fe433f6dd2a4`，Miscellaneous Document Files / 3. MMDocIR Layout-related files：

- `text`: `for text/equation layouts only, raw text extracted using OCR tools`
- `ocr_text`: `for table/figure layouts only, raw text extracted using OCR tools`
- `vlm_text`: `for table/figure layouts only, text description using VLM`

[官方encode.py](https://github.com/mmdocrag/MMDocIR/blob/main/encode.py)的get_layouts对图/表选择指定mode，其他类型取text。论文2501.08828第3.2节说明MinerU生成版面类型与框。以上足以区分OCR原文和VLM描述，但未给逐节点OCR引擎及版本，不能将“采用MinerU版面”扩写成“每个字符都由已知MinerU版本OCR生成”。本轮未下载数据或解析模型，没有扩展文献审计。

规则唯一版本`mmdocir-official-ocr-by-type-v1`：正文/标题/公式取text；图/表取ocr_text；strip首尾空白；空/null标missing、保留节点，缓存零文本向量并仍过可训练投影；不混入vlm_text，不跨字段回退。未知类型文本来源未明则停。title沿官方非图表分支，本次实际没有独立title/UNK候选。旧`ocr_text_with_source`适配规则保持不变，新规则仅供D。

## 2. 训练/内部验证覆盖率与缓存

范围：source_train局部loss可用且非page_overlap_excluded的页、source_val eval_ready页；每页全部既有解析候选。页选择只决定本轮计算范围，节点构造不按gold框筛选，节点与P′不依赖当前问题。没有读取dev候选文本或外部测试。

|角色/类型|节点|选取字段非空|
|---|---:|---:|
|train text|5334|5100|
|train image|581|366|
|train table|346|345|
|train equation|28|28|
|val text|5136|5024|
|val image|451|157|
|val table|80|80|
|val equation|16|16|

train=5839/6289（92.844649%）；val=5277/5683（92.855886%）；合计11116/11972（约92.85%），1067页，缺失856节点。按type及所有三个字段的完整非空计数在text_audit.json中。无VLM文本被编码。

缓存：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/d_nodes_v1/`。
成功编码回执目录：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/d_nodes_runs/20261006_214918/`，含`text_audit.json`、`run_info.json`。
manifest SHA256：`4514800ee81cad1343635e27bbe6edad73e880e44f30af32224ffed7ec2160d6`。缓存总计158408799 bytes，逐页绑定节点ID、类型/框/页面尺寸、来源字段、文本SHA256、缺失与截断信息，文件SHA256回读通过；输入哈希包括原版面文件、角色清单和regions-v1。

既有本地BAAI/bge-m3 revision `5617a9f61b028005a4858fdac845db406aefb181`，模型文件SHA256全部存manifest。SentenceTransformer，原CLS池化1024维、L2归一化、float32、max_seq_length512、batch2；冻结编码器。63节点截断，编码102.1402645999915秒，程序131.5208738000074秒；峰值allocated2326348800 bytes、reserved2355101696 bytes。

首次准备因脚本只接受safetensors格式而失败，记录保留：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_data/d_nodes_runs/20261006_214437/`。实际既有权重为pytorch_model.bin，修正本地文件格式检查后成功，未下载替换模型。

## 3. D接口与可训练参数

`src/layoutpatch/retrieval/route_v2_layout.py`将原TextLayoutEncoder与原SparseLocalFusionV2直接组合，不重造结构。文本[M,1024]，坐标[M,6]→正弦72维，类型[M]沿6类ID，boolean mask[M]；节点[M,128]；patch[1024,128]。W_raw[1024,M]为cover，W_attn非空行归一化，cover_mass[1024,1]为原始行和，TopK=4、稳定下标平局。几何只使用候选自己的bbox/page_size。

forward_page输入[1031,128]，仅替换前1024图像行，末7提示行原值拼接；空patch逐值不变。只有节点编码器与融合器可训练：190592+82818=273410参数；C为66176参数。BGE-M3与ColPali均冻结。smoke/正式D从新初始化，不加载C或旧融合权重。

公共train_epoch、score_unit增加可选layout字段；C没有该字段时调用路径保持不变。LayoutInputs以(doc_id,page)缓存节点，同页不同问题共享；不接收gold作为前向输入。正式train_seed支持模型工厂与方法标签，复用原早停/优化器/评分。EXP-014实际代码快照不变。

## 4. 合成检查与真实技术smoke

定向检查范围：来源分支、坐标/类型/文本对应、D初始=B、空patch、padding、提示保留、后续上游梯度，以及公共训练接口与C回归。只运行本轮相关Ruff/pytest，未修或重跑全仓19旧错误。

真实smoke完整目录：`C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/artifacts/route_v2_d_smoke/20261006_220102/`，含`metrics.json`、`steps.jsonl`、`D_smoke.pt`。固定原16题/19unit、seed42、GPU float32、AdamW lr1e-3、weight_decay0.01、200步全批平均；没有val/dev评分、挑题或增加预算。

关键metrics原文字段：

```json
{
  "questions": 16,
  "units": 19,
  "steps": 200,
  "parameters": 273410,
  "node_parameters": 190592,
  "fusion_parameters": 82818,
  "training_seconds": 33.939813199976925,
  "elapsed_seconds": 37.188904100010404,
  "peak_allocated_bytes": 133305856,
  "peak_reserved_bytes": 216006656,
  "passed": true
}
```

|指标|初始|最终|
|---|---:|---:|
|loss|1.715434375562166|0.5203833830984015|
|正负patch平均分差|0.010067371945632132|0.7652438345708346|
|正负patch最大分差|−0.02931629356585051|0.13604409443704704|
|gate均值|0.04742586985230446|0.09031886607408524|
|归一化patch变化L2均值|1.4700044737026019e-08|0.8142322301864624|
|归一化patch变化L2最大|1.2829752904508496e-07|1.7806333303451538|
|训练主指标题宏平均|0.4375|1.0|
|训练Cov@5题宏平均|0.8446093961536287|1.0|
|训练gold召回@5题宏平均|0.85|1.0|

最终gate范围[0.042205046862363815,0.214563250541687]。归一化patch变化不是未经归一化的MLP输出范数，不混称。第一步仅末残差Linear获得非零梯度，符合零初始化；后续text_proj/coord_proj/type_emb/fuse/value/gate均非零，逐参数首步梯度、后续最大梯度与最终参数差完整存metrics。例：text_proj.weight后续最大梯度0.400127649307251，coord_proj.weight1.344374179840088，type_emb.weight0.1632404625415802，gate.weight0.20114557445049286；全部要求参数均变化。无NaN/Inf，空patch与提示token原值保留，显存低于12GiB。

这些数字仅为固定训练样本技术验收，不比较D/C泛化、不证明创新；smoke权重禁止用于正式初始化。

## 5. EXP-015唯一候选配置与剩余条件

`configs/experiments/route_v2_exp2_D.yaml`（working，可冻结候选）及`scripts/run_route_v2_exp2.py`已准备；task已登记但本轮未执行。训练/验证节点缓存回验及与EXP-014共同预算参数对比通过。

- 同数据/排除、评分、局部损失τ0.25，seed0/1/2、30epoch、4unit累积、同AdamW/裁剪/val严格早停；D各seed新初始化。
- C只复用EXP-014保存的三seed预测，A/B同样复用，绝不重训或重评分C。
- 逐题三seed D均值减逐题三seed C均值；文档聚类bootstrap2000次/seed0，最小收益0.01且95%下界>0，同报D−A/D−B。
- 保留8.1节全部主辅指标、面积、随机期望、Oracle、M≥2和面积分位数；明确报告Cov@5/gold召回@5/area_sum@5退化，参数和实际文本编码/训练/评分成本同报。
- source_dev须在全部D权重确定后统一评分一次，是新的开发比较，非独立测试；外部测试不运行。

**唯一数据准备阻塞：本轮未授权编码的source_dev节点文本缓存尚缺。** 后续明确授权正式EXP-015时，须使用同字段规则、同BGE-M3身份和编码参数仅补dev节点缓存并绑定哈希；不得凭开发表现修改规则。正式入口在该缓存缺失时于任何D正式训练之前停止。当前不能声称正式实验已可直接执行，也不把D超过C等同新颖性成立。

## 6. 交付状态

没有扩标、换数据、重编码页面、重训C或外部评测；没有启动EXP-015正式D训练。旧输入、模型与EXP-014结果保留。最终定向检查原文：`All checks passed!`、`30 passed in 2.74s`；缓存回验`passed=true`，11972节点/1067页全部通过。中途本轮新增文件的导入格式与未使用变量错误已修复，没有触及19个旧脚本错误。
