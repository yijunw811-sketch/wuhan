import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch,Rectangle
from matplotlib.font_manager import FontProperties
ROOT=Path(__file__).resolve().parents[1]
C=json.loads((ROOT/'config/kde.json').read_text())
C['map_page_inches']=C['map_inches']
MAPS=[]
CN={'blue':'蓝色空间','green':'绿色空间（含耕地）','blue_green':'蓝绿空间整体（含耕地、湿地）','wetland':'湿地'}
FONT=ROOT/'scripts/fonts/NotoSansCJK-Regular.ttc'
if not FONT.exists():FONT=ROOT.parent/'wuhan_research/scripts/fonts/NotoSansCJK-Regular.ttc'
if not FONT.exists():FONT=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
if FONT.exists():
    matplotlib.font_manager.fontManager.addfont(str(FONT));plt.rcParams['font.family']=FontProperties(fname=str(FONT)).get_name()
plt.rcParams['axes.unicode_minus']=False
plt.rcParams['pdf.fonttype']=42

def savefig(f,name):
    f.savefig(ROOT/'maps'/f'{name}.png',dpi=C.get('map_dpi',300),facecolor='white')
    f.savefig(ROOT/'maps'/f'{name}.pdf',dpi=C.get('map_dpi',300),facecolor='white')
    plt.close(f); MAPS.append(name)

def mapfig(name,title,array,extent,colors,labels,boundaries=None,note=''):
    f=plt.figure(figsize=tuple(C.get('map_page_inches',[16.535,11.693])));ax=f.add_axes([.055,.145,.69,.76]);side=f.add_axes([.77,.23,.22,.55]);side.axis('off')
    cmap=ListedColormap(colors);cmap.set_bad('#eeeeee')
    if boundaries is None: boundaries=np.arange(-.5,len(colors)+.5)
    ax.imshow(array,extent=extent,cmap=cmap,norm=BoundaryNorm(boundaries,len(colors)),interpolation='nearest',origin='upper')
    view=globals().get('COVER_EXTENT',extent)
    ax.set_aspect('equal');ax.set_xlim(view[:2]);ax.set_ylim(view[2:]);ax.tick_params(labelsize=9);ax.ticklabel_format(style='plain');ax.set_xlabel('东坐标 / m');ax.set_ylabel('北坐标 / m')
    ax.annotate('N',xy=(.94,.97),xytext=(.94,.88),xycoords='axes fraction',ha='center',fontsize=17,arrowprops=dict(facecolor='#333333',width=2,headwidth=8))
    x=extent[0]+.05*(extent[1]-extent[0]);y=extent[2]+.045*(extent[3]-extent[2]);length=10000
    for j in range(2):ax.add_patch(Rectangle((x+j*length/2,y),length/2,700,facecolor='black' if j==0 else 'white',edgecolor='black',lw=.6))
    ax.text(x,y+1500,'0',fontsize=9);ax.text(x+length,y+1500,'10 km',ha='center',fontsize=9)
    side.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(colors,labels)],loc='upper left',frameon=False,fontsize=11,labelspacing=1.5)
    side.text(.02,.02,note+'\n\n投影：WGS 84 / UTM 49N\nEPSG:32649\n数据年份待补充',fontsize=10,va='bottom',linespacing=1.8)
    f.suptitle(title,fontsize=23,y=.96)
    f.text(.075,.065,'数据来源：用户提供的 ENVI 土地利用 RGB 分类影像及配色表。\n分析范围为输入影像覆盖区；并非武汉市都市区正式规划边界。15 m 为像元间距，不代表分类精度。',fontsize=11,linespacing=1.7)
    savefig(f,name)
