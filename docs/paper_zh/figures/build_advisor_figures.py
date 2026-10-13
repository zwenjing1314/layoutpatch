from pathlib import Path
import html

ROOT=Path(__file__).resolve().parent
FONT='Microsoft YaHei, SimHei, sans-serif'

class SVG:
    def __init__(self,w,h):
        self.w,self.h=w,h
        self.items=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#374151"/></marker></defs><rect width="100%" height="100%" fill="white"/>']
    def rect(self,x,y,w,h,fill='#f8fafc',stroke='#64748b',r=8,dash=False):
        self.items.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"'+(' stroke-dasharray="7 5"' if dash else '')+'/>')
    def text(self,x,y,s,size=22,bold=False,color='#111827',anchor='middle'):
        for k,line in enumerate(s.split('\n')):
            val=html.escape(line)
            for src,base,sub in [('W_raw','W','raw'),('W_attn','W','attn'),('P′_C','P′','C'),('P′_D','P′','D'),('f_D','f','D')]:
                val=val.replace(src,base+'<tspan baseline-shift="sub" font-size="70%">'+sub+'</tspan>')
            self.items.append(f'<text x="{x}" y="{y+k*(size*1.35)}" font-family="{FONT}" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{anchor}" fill="{color}">{val}</text>')
    def line(self,x1,y1,x2,y2,dash=False,arrow=False,color='#374151',width=2):
        self.items.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="7 5"' if dash else '')+(' marker-end="url(#arr)"' if arrow else '')+'/>')
    def box(self,x,y,w,h,s,fill='#f8fafc',size=23,dash=False):
        self.rect(x,y,w,h,fill=fill,dash=dash)
        n=len(s.split('\n'));self.text(x+w/2,y+h/2-(n-1)*size*.675+size*.35,s,size)
    def save(self,name):
        (ROOT/name).write_text('\n'.join(self.items)+ '\n</svg>',encoding='utf-8')

f=SVG(1500,650)
f.box(35,35,230,75,'问题 q',fill='#eaf2fb',size=26)
f.line(265,72,405,72,arrow=True)
f.text(335,50,'问题编码',19)
f.box(410,35,290,75,'问题 token 表示 Q',fill='#eaf2fb')
f.text(65,160,'给定正确页面 I',25,True,anchor='start')
f.rect(65,182,270,340,fill='#fff',stroke='#6b7280',r=0)
f.rect(85,205,230,40,fill='#e5e7eb',stroke='none',r=0)
for y in [270,291,312,344,365]:f.line(85,y,305,y,color='#b7bec8',width=7)
f.rect(85,393,98,95,fill='#e5e7eb',stroke='none',r=0)
for y in [405,426,447,468]:f.line(202,y,310,y,color='#b7bec8',width=7)
f.line(335,335,405,335,arrow=True)
f.text(370,300,'整页编码',18)
f.text(65,555,'自绘页面，仅说明输入条件',20,anchor='start')
f.rect(420,182,270,340,fill='#fff',stroke='#6b7280',r=0)
for x in range(420,691,30):f.line(x,182,x,522,color='#cbd5e1',width=1)
for y in range(182,523,34):f.line(420,y,690,y,color='#cbd5e1',width=1)
f.rect(438,214,227,68,fill='none',stroke='#2563eb',r=0)
f.rect(438,316,105,92,fill='none',stroke='#2563eb',r=0)
f.rect(560,419,105,70,fill='none',stroke='#2563eb',r=0)
f.text(548,203,'P：patch 网格',21,bold=True)
f.text(553,258,'候选 R₁',21,color='#1d4ed8')
f.text(490,358,'R₂',21,color='#1d4ed8')
f.text(611,450,'Rⱼ',21,color='#1d4ed8')
f.text(555,547,'解析候选叠加于网格\n网格为示意；实际 N = 1024',18)
f.line(690,335,770,335,arrow=True)
f.box(785,205,325,95,'空间对应与相关评分',fill='#eff6ff',size=24)
f.box(785,320,325,80,'候选区域分数 rⱼ',size=24)
f.line(948,300,948,320,arrow=True)
f.text(948,451,'空间对应：W_raw / W_attn',21)
f.text(948,487,'固定评分：IoU 权重 aⱼᵢ',21)
f.text(948,525,'二者用途与归一化不同',21,bold=True)
f.line(700,72,948,72);f.line(948,72,948,205,arrow=True)
f.line(1110,360,1170,360,arrow=True)
f.box(1185,255,280,190,'排序输出\n按 rⱼ 降序排列\n不展示成功预测',size=25)
f.text(750,620,'示意图，非实验样本；蓝框为解析候选示意，不代表 gold 或正确预测',22)
f.save('figure-1-task.svg')

f=SVG(1600,1060)
f.text(800,40,'平行方法分支与局部布局融合',28,True)
f.box(25,85,275,66,'共同冻结输入：P、Q',fill='#eaf2fb',size=23)
f.box(340,85,650,66,'共同候选框；固定评分 = patch 分数 + IoU 加权平均',size=22)
ys=[210,325,440,555]
labels=['B 冻结传播','C / C-wide','D / D-no-text','E 事后补充']
for y,l in zip(ys,labels):f.text(30,y+35,l,23,True,anchor='start')
f.box(250,ys[0],175,65,'原始 P')
f.box(500,ys[0],465,65,'固定评分：输入 Q 与候选框',fill='#eff6ff')
f.line(425,ys[0]+32,500,ys[0]+32,arrow=True)
f.box(1040,ys[0],210,65,'候选排序 rᴮ');f.line(965,ys[0]+32,1040,ys[0]+32,arrow=True)
f.box(250,ys[1],175,65,'原始 P');f.box(490,ys[1],225,65,'普通 patch 适配',fill='#eef5ef')
f.box(770,ys[1],135,65,'P′_C');f.box(960,ys[1],230,65,'固定评分');f.box(1245,ys[1],230,65,'候选排序 rᶜ')
for a,b in [(425,490),(715,770),(905,960),(1190,1245)]:f.line(a,ys[1]+32,b,ys[1]+32,arrow=True)
f.box(250,ys[2],175,65,'P + 布局节点');f.box(490,ys[2],225,65,'局部融合',fill='#eef5ef')
f.box(770,ys[2],135,65,'P′_D');f.box(960,ys[2],230,65,'固定评分');f.box(1245,ys[2],230,65,'候选排序 rᴰ')
for a,b in [(425,490),(715,770),(905,960),(1190,1245)]:f.line(a,ys[2]+32,b,ys[2]+32,arrow=True)
f.box(250,ys[3],465,65,'原始 P + Q + 候选坐标与类型');f.box(770,ys[3],420,65,'池化与问题交互 → 候选分数修正',fill='#fff5e8',size=21)
f.box(1245,ys[3],230,65,'候选排序 rᴱ')
f.line(715,ys[3]+32,770,ys[3]+32,arrow=True);f.line(1190,ys[3]+32,1245,ys[3]+32,arrow=True)
f.text(1280,646,'E 以 rᴮ 为基值，不生成 P′',21)
f.rect(35,685,1100,255,fill='#f8fafc',stroke='#64748b',r=10)
f.text(65,725,'D 的局部融合放大',25,True,anchor='start')
f.box(65,752,280,60,'pᵢ + 节点 hⱼ + W_attn',size=20)
f.box(400,752,260,60,'局部注意力与值汇总 δᵢ',size=21)
f.box(730,752,220,60,'残差 MLP f_D',size=22)
f.line(345,782,400,782,arrow=True);f.line(660,782,730,782,arrow=True)
f.box(400,850,290,60,'gate：pᵢ、δᵢ、ρᵢ → gᵢ',size=21)
f.box(770,850,320,60,'ν(pᵢ + gᵢ f_D(δᵢ))',size=23)
f.line(530,812,530,850,arrow=True);f.line(690,880,770,880,arrow=True);f.line(950,782,1055,782);f.line(1055,782,1055,850,arrow=True)
# The inset is labeled explicitly; no connector crosses the independent E branch.
f.rect(1160,710,405,230,fill='#fff',stroke='#9ca3af',dash=True)
f.text(1362,750,'训练监督支路',24,True)
f.text(1362,790,'gold 框 → 正负标签',23)
f.line(1362,805,1362,830,dash=True,arrow=True)
f.text(1362,857,'C/D：patch 级损失',23)
f.text(1362,897,'E：候选级损失',23)
f.text(800,991,'C 与 D 均从原始 P 出发；D-no-text 仅将文本输入置零，保留文本支路',22)
f.text(800,1027,'gold 仅用于训练标签和损失，不进入推理输入；各方法独立输出排序',22)
f.save('figure-2-methods.svg')
print('SVG figures created')
