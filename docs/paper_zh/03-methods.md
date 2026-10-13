# 3 任务定义与方法

## 3.1 任务定义与表示

本文研究正确页面条件下的文档证据区域排序。给定问题 \(q\)、对应的证据页面 \(I\) 以及解析器生成的候选集合 \(\mathcal R=\{R_j\}_{j=1}^{M}\)，模型计算候选相关分数，并按分数降序输出排序。训练阶段还给定该问题在页面上的标注证据集合 \(\mathcal G=\{G_k\}_{k=1}^{K}\)。布局输入包含页面的完整候选节点，不依据当前问题或标注证据选择节点。该任务限于既有候选区域，不涉及从文档库召回页面、生成任意坐标框或生成答案。

冻结 ColPali 的视觉与问题编码部分，分别获得图像 patch 表示 \(P=[p_i]_{i=1}^{N}\in\mathbb R^{N\times d}\) 和问题 token 表示 \(Q=[q_t]_{t=1}^{T}\in\mathbb R^{T\times d}\)，其中 \(N=1024\)、\(d=128\)，\(T\) 为有效问题 token 数。局部区域评分只使用图像 patch，不使用页面表示中的提示 token。页面只进行一次整页视觉编码，后续适配与排序复用该表示，不对各候选分别进行视觉编码。

记 \(\nu(z)=z/\|z\|_2\) 为非零向量的逐行 \(\ell_2\) 归一化。问题评分前排除范数不超过 \(10^{-6}\) 的 token 行，再归一化保留行；该处理不依据语义类别删除有效 token。归一化相似度、页级 MaxSim 和 patch 相关分数分别定义为

\[
S_{ti}(P)=\nu(q_t)^\top\nu(p_i),
\tag{1}
\]
\[
u_{\mathrm{page}}(Q,P)=\sum_{t=1}^{T}\max_{1\le i\le N}S_{ti}(P),
\tag{2}
\]
\[
s_i(Q,P)=\max_{1\le t\le T}S_{ti}(P).
\tag{3}
\]

式（2）对每个问题 token 选择最相似 patch 后求和，输出一个页面分数；式（3）对每个 patch 选择最大的问题 token 相似度，输出 \(N\) 维分数向量。二者最大化方向不同，候选区域分数还需进一步汇总。使用适配表示时，以对应 \(P'\) 替换式（1）和式（3）中的 \(P\)。保持 patch 数与维度允许沿用原评分接口，但不构成页面召回性能保持的证据。

**表3-1 主要符号与维度**

| 符号 | 维度或取值 | 含义 |
|---|---|---|
| \(P,Q\) | \(N\times d,\ T\times d\) | 原始图像 patch 与有效问题 token 表示；\(N=1024,d=128\) |
| \(P'_C,P'_D\) | \(N\times d\) | C、D 分别从原始 \(P\) 生成的适配表示 |
| \(B_i,R_j,G_k\) | 四维边界框 | patch、候选与标注证据区域；几何计算采用统一坐标系 |
| \(M,K\) | 非负整数 | 页面候选数与该问题在页面上的标注证据数 |
| \(S_{ti},s_i,u_{\mathrm{page}}\) | 标量 | token–patch 相似度、patch 相关分数、页级 MaxSim |
| \(A=[a_{ji}]\) | \(M\times N\) | 评分权重，\(a_{ji}=\operatorname{IoU}(R_j,B_i)\)；区别于方法 A |
| \(W_{\mathrm{raw}}=[w_{ij}]\) | \(N\times M\) | 原始 patch–布局节点非负空间对应权重 |
| \(W_{\mathrm{attn}}=[\bar w_{ij}]\) | \(N\times M\) | 按 patch 行归一化的空间注意力权重 |
| \(\rho_i,\mu_j\) | 标量 | \(W_{\mathrm{raw}}\) 的第 \(i\) 行和、第 \(j\) 列和 |
| \(e_j,c_j,z_j,h_j\) | \(1024,\ 6,\ 1,\ 128\) | 节点文本向量、坐标、类型编号、编码后的节点向量 |
| \(\phi(c_j)\) | \(72\) | 六维坐标的正弦/余弦编码 |
| \(\mathcal N_i,\alpha_{ij},\delta_i,g_i\) | 集合、标量、\(128\)、标量 | 局部邻居、注意力权重、汇总向量、gate 值 |
| \(v_j,x_j,l_j\) | 各为 \(128\) | E 的候选视觉向量、逐维问题交互、布局向量 |
| \(r_j^A,r_j^B,r_j^C,r_j^D,r_j^E\) | 标量 | 各方法输出的候选分数 |
| \(\mathcal I_+,\mathcal I_-,\mathcal I_0\) | patch 索引集合 | 正例、负例与忽略 patch |
| \(\mathcal J_+,\mathcal J_-\) | 候选索引集合 | 参与 E 损失的正例与负例候选 |
| \(\tau\) | \(0.25\) | 多正例损失的温度 |

## 3.2 面积规则与冻结传播

面积规则 A 不使用问题或视觉表示，以页面坐标下的候选面积作为分数。对于 \(R_j=(x_{1j},y_{1j},x_{2j},y_{2j})\)，有

\[
r_j^A=\max(0,x_{2j}-x_{1j})\max(0,y_{2j}-y_{1j}).
\tag{4}
\]

冻结传播 B 将候选框与 patch 框映射到统一的模型坐标系，以二者的 IoU 汇总式（3）：

\[
a_{ji}=\operatorname{IoU}(R_j,B_i),\qquad
r_j^B=\frac{\sum_{i=1}^{N}a_{ji}s_i(Q,P)}
                 {\sum_{i=1}^{N}a_{ji}}.
\tag{5}
\]

式（5）为权重归一化的平均分数，不是未归一化累计分数。与全部 patch 的 IoU 权重均为零的候选赋分 \(-\infty\)。C 和 D 沿用此汇总方式，只替换 patch 表示。面积规则则保留为无需训练且不依赖问题的几何参照。

## 3.3 普通 patch 适配器及容量参照

普通适配器 C 对每个 patch 使用共享的残差网络。令 \(x_i=\nu(p_i)\)，则

\[
p'_{C,i}=\nu(x_i+f_C(x_i)),\qquad
f_C(x)=L_{2,C}\!\left(\operatorname{GELU}
         \left(L_{1,C}(\operatorname{LN}(x))\right)\right).
\tag{6}
\]

\(\operatorname{LN}\) 为 LayerNorm，两个带偏置线性层分别为 \(128\rightarrow256\) 和 \(256\rightarrow128\)。末层权重与偏置初始化为零，因此初始输出为原 patch 的归一化表示。适配器不输入问题、节点文本、坐标、类型或空间权重；问题在后续评分与训练损失中参与。

C-wide 保留式（6），将隐藏宽度由256扩大到1062。C/C-wide 与 D 是平行方案，均从原始 \(P\) 出发，C 不接在 D 后面。候选分数 \(r_j^C\) 由式（5）将 \(s_i(Q,P)\) 替换为 \(s_i(Q,P'_C)\) 得到。

## 3.4 布局条件 patch 适配

### 3.4.1 布局输入与空间权重

D 将页面候选区域表示为布局节点。第 \(j\) 个节点包含文本向量 \(e_j\in\mathbb R^{1024}\)、类型编号 \(z_j\) 和六维坐标

\[
c_j=(x_{1j},y_{1j},x_{2j},y_{2j},x_{2j}-x_{1j},y_{2j}-y_{1j}).
\tag{7}
\]

这里的边界框先映射并裁剪到 \(448\times448\) 模型坐标系，再除以448。训练来源的文本、标题及公式读取 text 字段，图像与表格读取 ocr_text 字段；外部节点使用解析器提供的 text 字段并记录来源。模块接收预先获得的文本向量，不在融合时重新编码文本。

记原始非负空间对应矩阵为 \(W_{\mathrm{raw}}=[w_{ij}]\in\mathbb R^{N\times M}\)，由页面框与 patch 网格的空间对应计算得到，不依赖问题或标注证据。对 patch 框 \(B_i\) 与布局节点框 \(R_j\)，本实现采用 patch 覆盖率

\[
w_{ij}=\frac{\operatorname{Area}(B_i\cap R_j)}{\operatorname{Area}(B_i)}.
\tag{8}
\]

框先按页面宽高分别缩放到 \(448\times448\) 模型坐标并裁剪到画布；退化节点返回全零行。D 使用其行归一化结果：

\[
\rho_i=\sum_{j=1}^{M}w_{ij},\qquad
\bar w_{ij}=
\begin{cases}
w_{ij}/\rho_i,&\rho_i>0,\\
0,&\rho_i=0.
\end{cases}
\tag{9}
\]

\(\rho_i\) 为原始空间权重累计量，不是去重后的联合面积覆盖率；重叠节点可使其大于1。\(W_{\mathrm{raw}}\) 与 \(W_{\mathrm{attn}}\) 用于布局融合或候选池化，\(A=[a_{ji}]\) 则专门用于式（5）的候选评分。本文明确区分这些矩阵的用途、归一化方向与索引。

### 3.4.2 节点编码

对每个坐标分量使用6个频率，得到72维编码。令 \(\omega_b=10000^{-b/6}\)，\(b=0,\ldots,5\)，则

\[
\phi(c_j)=\operatorname{Concat}_{a=1}^{6}
\left([\sin(c_{j,a}\omega_b)]_{b=0}^{5},
      [\cos(c_{j,a}\omega_b)]_{b=0}^{5}\right).
\tag{10}
\]

文本、位置与类型分别编码为128维，拼接后投影并归一化：

\[
h_j=\nu\!\left(L_{\mathrm{fuse}}
   [L_{\mathrm{text}}(e_j);
    L_{\mathrm{coord}}(\phi(c_j));
    E_{\mathrm{type}}(z_j)]\right).
\tag{11}
\]

分号表示拼接；三个线性投影的维度分别为 \(1024\rightarrow128\)、\(72\rightarrow128\)、\(384\rightarrow128\)。无效填充节点由掩码置零，并从注意力中排除。D 的未知类型编号0采用 embedding 的 padding 项。节点编码器与融合器可训练，预先提供的文本输入表示不在该模块内更新。

### 3.4.3 注意力、残差与 gate

对第 \(i\) 个 patch，按 \(\bar w_{ij}\) 降序选择最多4个有效且空间权重为正的节点，构成 \(\mathcal N_i\)。相等权重按原节点索引排序，节点输入按 layout_id 排序。对非空邻居集合计算

\[
\ell_{ij}=\frac{p_i^\top h_j}{\sqrt d}
                +\log(\bar w_{ij}+\varepsilon),\qquad
\alpha_{ij}=\frac{\exp(\ell_{ij})}
                 {\sum_{k\in\mathcal N_i}\exp(\ell_{ik})},
\quad j\in\mathcal N_i,
\tag{12}
\]

其中 \(\varepsilon=10^{-6}\)。注意力输入为原始 \(p_i\)，不额外替换为 C 中归一化的 \(x_i\)。节点经无偏置的 \(128\rightarrow128\) 值投影后汇总：

\[
\delta_i=\sum_{j\in\mathcal N_i}\alpha_{ij}L_{\mathrm{value}}(h_j).
\tag{13}
\]

残差网络与标量 gate 分别为

\[
f_D(\delta)=L_{2,D}\!\left(\operatorname{GELU}
                 (L_{1,D}(\operatorname{LN}(\delta)))\right),
\qquad
g_i=\sigma(L_{\mathrm{gate}}([p_i;\delta_i;\rho_i])).
\tag{14}
\]

其中 \(L_{1,D}:128\rightarrow256\)、\(L_{2,D}:256\rightarrow128\)，\(L_{\mathrm{gate}}:257\rightarrow1\)，\(\sigma\) 为 sigmoid。残差末层权重与偏置初始化为零；gate 权重为零、偏置为 \(-3\)。输出定义为

\[
p'_{D,i}=
\begin{cases}
\nu(p_i+g_i f_D(\delta_i)),&\mathcal N_i\neq\varnothing,\\
p_i,&\mathcal N_i=\varnothing.
\end{cases}
\tag{15}
\]

无有效邻居时直接保留原 patch。\(P'_D\) 只依赖页面及布局，不依赖当前问题；区域排序仍由 \(s_i(Q,P'_D)\) 经式（5）得到 \(r_j^D\)，因而使用问题信息。页面级组合接口保持图像 patch 数与维度，并将提示 token 按原值接回。

D-no-text 保留同一结构，仅将文本输入 \(e_j\) 置零。文本投影及其偏置仍存在，故该变体不是删除文本分支，零输入也不保证文本分支输出为零。坐标、类型、空间权重与节点掩码保持原输入。

## 3.5 事后补充候选排序对照 E

E 是原冻结实验之后引入的事后补充对照，保留原始 \(P\)，直接学习候选分数修正，不生成 \(P'\)。本文将其作为具体比较方案，不将普通 MLP 结构本身作为创新主张。

E 使用 \(W_{\mathrm{raw}}\) 的候选列权重池化视觉信息。对有效且 \(\mu_j=\sum_iw_{ij}>0\) 的候选，计算

\[
\tilde v_j=\frac{\sum_{i=1}^{N}w_{ij}p_i}{\mu_j},
\qquad v_j=\nu(\tilde v_j).
\tag{16}
\]

式（15）先对原始 \(P\) 加权平均，再归一化候选向量；不先逐 patch 归一化，也不使用 D 的行归一化 \(W_{\mathrm{attn}}\)。问题交互为

\[
x_{j,a}=\max_{1\le t\le T}[\nu(q_t)_a v_{j,a}],
\quad a=1,\ldots,d.
\tag{17}
\]

该操作按特征维度分别取最大值，输出 \(x_j\in\mathbb R^{128}\)，不是标准 MaxSim 的标量最大点积。布局分支将坐标投影与类型 embedding 相加：

\[
l_j=L_{\mathrm{coord},E}(\phi(c_j))+E_{\mathrm{type},E}(z_j).
\tag{18}
\]

位置投影为 \(72\rightarrow128\)，类型 embedding 包含6个编号，E 不使用节点文本。拼接 \(x_j,v_j,l_j\) 后，经 \(384\rightarrow680\rightarrow1\) 的 MLP 生成修正项；隐藏层使用 GELU：

\[
r_j^E=r_j^B+f_E([x_j;v_j;l_j]).
\tag{19}
\]

MLP 末层权重与偏置初始化为零，使初始分数等于 B。\(Q,P,v_j,x_j\) 为冻结特征，训练更新位置投影、类型 embedding 与分数 MLP。填充候选不参与排序；空间权重列和为零的候选不施加修正，保留 B 分数。

## 3.6 监督标签与训练目标

### 3.6.1 C/D 的 patch 级损失

C/C-wide 与 D/D-no-text 使用标注证据框构造 patch 标签。标注框映射并裁剪到模型坐标系后去除零面积框；patch 中心位于任一有效标注框内（含边界）者为正例 \(\mathcal I_+\)，与所有标注框交集面积均为零者为负例 \(\mathcal I_-\)，其余与证据相交但中心不在证据内者为忽略 \(\mathcal I_0\)。正例判定优先，三类互斥。

令 \(\hat s_i=s_i(Q,P')\)，则

\[
\mathcal L_{\mathrm{patch}}
=-\log\frac{\sum_{i\in\mathcal I_+}\exp(\hat s_i/\tau)}
                 {\sum_{i\in\mathcal I_+\cup\mathcal I_-}\exp(\hat s_i/\tau)},
\qquad \tau=0.25.
\tag{20}
\]

忽略 patch 不进入分子或分母。题—页单元必须同时提供正、负 patch 才可计算局部损失。式（19）直接优化 patch 分数，固定的 IoU 候选汇总不直接进入训练损失。

### 3.6.2 E 的候选级损失

E 按候选与标注证据的 IoU 构造标签：与任一标注框 IoU 不小于0.5者为正例，其余候选为负例。结合有效候选与非空空间权重条件，得到参与损失的正、负集合 \(\mathcal J_+,\mathcal J_-\)。损失使用最终候选分数：

\[
\mathcal L_{\mathrm{cand}}
=-\log\frac{\sum_{j\in\mathcal J_+}\exp(r_j^E/\tau)}
                 {\sum_{j\in\mathcal J_+\cup\mathcal J_-}\exp(r_j^E/\tau)},
\qquad \tau=0.25.
\tag{21}
\]

E 从满足原 D 训练条件的来源单元中进一步筛选训练单元：候选集合须有正、负例，且排除空空间权重候选后仍有正、负监督对象。参与损失的分数须有限，不满足训练条件的单元不用于更新。

两类损失均提高正例集合的总概率，不保证每个正例都取得高分。C/D 与 E 使用同来源标注，但监督粒度、标签构造和实际训练子集不同；接近的登记参数量也不等于有效容量完全匹配。因此，本比较不是仅改变表示修正位置的严格单因素实验。实际训练分母与配置在实验设置节报告。

## 3.7 方法差异表与流程图草案

**表3-2 方法差异**

| 方法 | 适配/排序模块输入 | 可训练部分 | 输出与候选评分 | 监督粒度 | 登记参数量 |
|---|---|---|---|---|---:|
| A | 候选框 | 无 | 面积分数；不使用问题 | 无 | 0 |
| B | 原始 \(P,Q\)、评分权重 \(A\) | 无 | patch 分数经 IoU 加权平均得到 \(r^B\) | 无 | 0 |
| C | 适配输入原始 \(P\)；评分使用 \(Q,A\) | 共享 patch 适配器，隐藏宽度256 | \(P'_C\)；沿用 B 评分形式 | patch 级 | 66176 |
| C-wide | 同 C | 同 C，隐藏宽度1062 | 同 C | patch 级 | 273318 |
| D | 原始 \(P\)、文本、坐标、类型、\(W_{\mathrm{attn}},\rho\)；评分使用 \(Q,A\) | 节点编码、值投影、残差 MLP、gate | \(P'_D\)；沿用 B 评分形式 | patch 级 | 273410 |
| D-no-text | 同 D，文本输入置零而支路保留 | 同 D | 同 D | patch 级 | 273410 |
| E（事后补充） | 原始 \(P,Q,W_{\mathrm{raw}}\)、坐标、类型及 \(r^B\) | 位置投影、类型 embedding、分数 MLP | 直接输出 \(r^E\)，不生成 \(P'\) | 候选级 | 272593 |

参数量沿用第1轮材料的登记值，网络维度已与本轮实现核对；本轮未运行参数计数。空间权重用于表示融合或池化，IoU 评分权重用于固定候选汇总，不能互换。

**图3-1 方法流程图草案**

~~~mermaid
flowchart TB
    Page["正确页面"] --> VEnc["冻结视觉编码：整页一次"]
    VEnc --> P["原始 P：1024 × 128"]
    Query["问题"] --> QEnc["冻结问题编码"]
    QEnc --> Q["有效问题 token Q：T × 128"]
    Page --> Parser["既有页面候选与布局输入"]
    Parser --> Boxes["候选框 R"]
    Parser --> Nodes["文本、六维坐标、类型与掩码"]
    Boxes --> Raw["原始空间对应 W_raw"]
    Raw --> Attn["按 patch 行归一化 W_attn"]
    Raw --> Mass["行和 rho：gate 输入"]
    Boxes --> Iou["独立评分矩阵 A：候选与 patch 的 IoU"]
    Boxes --> Area["A：候选面积分数"]

    P --> SB["B：patch 分数"]
    Q --> SB
    SB --> RB["IoU 加权平均：r_B"]
    Iou --> RB

    P --> C["C / C-wide：共享 patch 适配器"]
    C --> PC["P'_C"]
    PC --> SC["C：patch 分数"]
    Q --> SC
    SC --> RC["IoU 加权平均：r_C"]
    Iou --> RC

    Nodes --> NEnc["D 节点编码；D-no-text 仅将文本输入置零"]
    NEnc --> Fuse["最多4个有效邻居的注意力与值汇总"]
    P --> Fuse
    Attn --> Fuse
    Fuse --> Gate["残差 MLP 与 gate"]
    P --> Gate
    Mass --> Gate
    Gate --> PD["P'_D：有邻居时更新，无邻居时保留 P"]
    PD --> SD["D：patch 分数"]
    Q --> SD
    SD --> RD["IoU 加权平均：r_D"]
    Iou --> RD

    subgraph EBranch["E：事后补充直接排序对照"]
        Pool["W_raw 按候选列池化原始 P，再归一化 v"]
        Inter["逐维问题交互 x"]
        EL["坐标投影与类型 embedding 相加得到 l"]
        EMLP["MLP：384 → 680 → 1"]
        RE["r_E = r_B + 分数修正"]
        Pool --> Inter
        Pool --> EMLP
        Inter --> EMLP
        EL --> EMLP
        EMLP --> RE
    end
    P --> Pool
    Raw --> Pool
    Q --> Inter
    Nodes -->|"仅坐标与类型"| EL
    RB --> RE

    Gold["标注证据：仅训练监督"] -.-> PL["中心判正、零交集判负、其余忽略"]
    PL -.-> LP["C/D：patch 级损失"]
    SC -.-> LP
    SD -.-> LP
    Gold -.-> CL["候选 IoU ≥ 0.5 标签及有效性筛选"]
    Boxes -.-> CL
    CL -.-> LE["E：候选级损失"]
    RE -.-> LE

    Area --> Rank["各方法分别输出候选排序"]
    RB --> Rank
    RC --> Rank
    RD --> Rank
    RE --> Rank
~~~

实线表示计算依赖，虚线表示训练监督。C、D 分别从原始 \(P\) 出发，E 复用 B 分数；标注证据不进入推理期布局输入。各方法分别输出排序，图末端不表示分数集成。

---

## 写作核对备注（不并入论文正文）

1. **已核对范围。** 本轮先读取 @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/writing-status.md 与 @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/docs/paper_zh/outline-and-claims.md，再定点读取以下指定实现；未运行训练、测试、参数计数或评分。

   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_scoring.py：问题处理、patch/IoU/候选/面积评分、PatchAdapter、局部损失。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/layout/nodes.py：坐标编码与 TextLayoutEncoder。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/fusion/sparse_fusion.py：V2 结构与 forward、常量及头注。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_layout.py：文本规则、page_layout、候选对应校验与 LayoutPatchD。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_attribution.py：InputAblatedD、make_variant。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/route_v2_candidate.py：E 的结构、池化、交互、标签、损失与 training_filter_audit。
   - @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/datasets/route_v2_regions.py：patch_labels、训练单元就绪判定。

2. **头注与训练记录的核对。** @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/retrieval/fusion/sparse_fusion.py 文件头称“v2 class has no trained checkpoint”，但 @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/experiments/2026-10-06-exp-015-route-v2-D.md 明确记录 D 由 `TextLayoutEncoder` 与 `SparseLocalFusionV2(top_k=4)` 组合，并训练融合 V2；因此该头注属于过时文档注释。本文按 EXP-015 的正式训练记录描述，未修改代码或注释，也未进行权重审计。
3. **精度修正。** valid_query 保留范数大于 \(10^{-6}\) 的行，不是严格只删除全零行。D 的注意力与残差输入是原始 patch，无邻居保留原向量；E 先池化原始 patch 再归一化。正文已按实现表述，这些不是已发现的运行错误。
4. **W_raw 定义已补齐。** @C:/Users/WenJing/Documents/WorkTransfer/layoutpatch/src/layoutpatch/layout/correspondence.py 的 `correspondence_row` 明确采用 patch 覆盖率 \(\operatorname{Area}(P_i\cap R_j)/\operatorname{Area}(P_i)\)，并在非空 patch 行上归一化；本文新增式（8）及其坐标缩放说明。它仍不同于候选评分用的 patch—候选 IoU。
5. **输入来源待核实。** 已确认文本宽度1024与字段规则，但未读取文本向量生成路径、类型映射和页面切分定义；文本编码器型号/冻结配置、类型编号细目与提示 token 精确切分待原记录核实，未补造。
6. **训练调用与排序待核实。** E 筛选函数检查排除空 W 后仍有正负候选，但实际训练调用的损失掩码及其与运行记录的对应未读取，待实验轮核实。最终候选并列排序不在已读评分函数中，不能由 D 邻居排序推断。登记参数量、训练分母、模型选择与统计结果留待实验轮核对。
