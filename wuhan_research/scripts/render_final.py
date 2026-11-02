"""Render all grid panels with fixed input footprint, then create review sheets."""
import json
from pathlib import Path
import numpy as np,pandas as pd,rasterio
from rasterio.windows import Window
import run_analysis as a
from PIL import Image,ImageOps,ImageDraw

r=a.ROOT
with rasterio.open(r/'data/classification.tif') as d:
    left,bottom,right,top=d.bounds;a.COVER_EXTENT=[left,right,bottom,top]
    cl=d.read(1);valid=cl>0;profile=d.profile;H,W=d.shape;dx,dy=d.res
ids=[0,1,3,4,5,6,8];display=np.zeros_like(cl)
for j,i in enumerate(ids[1:],1):display[cl==i]=j
a.mapfig('06_蓝绿空间整体分布图','武汉地区蓝绿空间研究｜蓝绿空间整体（含耕地、湿地）分布',np.where(valid,display,np.nan),a.COVER_EXTENT,[a.COLORS[i] for i in ids],['非蓝绿空间']+[a.NAMES[i] for i in ids[1:]],note='蓝绿整体：水体、耕地、林地、草地、湿地\n排除建设用地与裸地\n湿地独立保留，不重复分配')
for scale in a.C['grid_sizes_m']:
    df=pd.read_csv(r/'tables'/f'grid_{scale}.csv');nr=int(df.row.max()+1);nc=int(df.col.max()+1)
    extent=[left,left+nc*scale,bottom,bottom+nr*scale]
    for h,m in enumerate(a.MET):
        breaks=list(a.C['density_breaks_percent']);breaks[-1]+=1e-5
        arr=df[m+'_pct'].to_numpy().reshape(nr,nc)[::-1];idx=np.digitize(arr,breaks);idx=np.where(arr==0,0,idx);idx=np.where(np.isfinite(arr),idx,np.nan)
        a.mapfig({'blue':'03','green':'05','blue_green':'07'}[m]+'_'+m+f'_密度_{scale}m',a.CN[m]+f'面积占比｜{scale} m 网格',idx,extent,['#f7f7f7','#e2f0d9','#b8d9ba','#7fb6aa','#3b8d95','#145569'],['0%','>0–<10%','10–<25%','25–<50%','50–<75%','75–100%'],note='密度＝目标面积÷有效分类面积\n按像元—网格精确面积加权\n缺失与真实零值分开\n边缘格用实际有效面积作分母')
        for st,code,colors,labels in [('lc',str(8+h).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3','#e8a06a','#9a91bf'],['无法计算／未纳入','不显著','高—高 HH','低—低 LL','高—低 HL','低—高 LH']),('gc',str(11+h).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3'],['无法计算／未纳入','不显著','显著热点','显著冷点'])]:
            v=df[m+'_'+st].to_numpy().reshape(nr,nc)[::-1]+1
            a.mapfig(code+'_'+m+'_'+st+f'_{scale}m',a.CN[m]+(' LISA' if st=='lc' else ' Gi* 热点')+f'｜{scale} m',v,extent,colors,labels,note='显著性：BH-FDR q < 0.05\n双侧条件置换，9999 次\nQueen邻域；固定随机种子\n有效覆盖≥95%，边缘比例≥25%\n空间集聚不等于生态质量')
        # Native-grid density remains separate. Aligned display raster repeats grid values,
        # not a re-estimation of statistics at 15 m.
        density=df[m+'_pct'].to_numpy().reshape(nr,nc)
        pr=profile.copy();pr.update(dtype='float32',nodata=-9999,count=1,compress='LZW')
        with rasterio.open(r/'data'/f'{m}_density_{scale}_aligned15m.tif','w',**pr) as out:
            cols=np.minimum(((np.arange(W)+.5)*dx/scale).astype(int),nc-1)
            for y0 in range(0,H,256):
                y1=min(H,y0+256);rows=np.minimum((((H-np.arange(y0,y1)-.5)*dy)/scale).astype(int),nr-1)
                val=density[rows[:,None],cols[None,:]];val=np.where(valid[y0:y1],val,-9999)
                out.write(np.nan_to_num(val,nan=-9999).astype('float32'),1,window=Window(0,y0,W,y1-y0))
    # A3 Moran supplementary plots, same inference already saved.
    import matplotlib.pyplot as plt
    mo=pd.read_csv(r/'tables/global_moran.csv')
    for m in a.MET:
        v=df[df.eligible==1];one=mo[(mo.scale_m==scale)&(mo.indicator==m)&(mo.edge_rule=='main')].iloc[0]
        f,ax=plt.subplots(figsize=(16.535,11.693));ax.scatter(v[m+'_z'],v[m+'_lag'],s=8,alpha=.35,c='#3f7b74');ax.axhline(0,c='grey',lw=.7);ax.axvline(0,c='grey',lw=.7)
        xx=np.array([v[m+'_z'].min(),v[m+'_z'].max()]);ax.plot(xx,one.I*xx,c='#c3534a');ax.set(xlabel='标准化面积占比 z',ylabel='不含自身的空间滞后 Wz',title=f'{a.CN[m]}｜{scale} m Moran 散点图\nI={one.I:.4f}; 双侧置换p={one.p_perm_2s:.4f}; n={int(one.n)}')
        f.text(.12,.025,'分析范围为输入影像覆盖区；数据年份待补充。Queen行标准化；9999次置换；不代表生态质量。',fontsize=13);a.savefig(f,f'Moran_{m}_{scale}')

# Every actual exported map appears in a labelled sheet. Individual PNG/PDF retained.
files=sorted((r/'maps').glob('*.png'));manifest=[]
for start in range(0,len(files),6):
    batch=files[start:start+6];sheet=Image.new('RGB',(1800,3*470),'white');draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(batch):
        with Image.open(p) as im:
            manifest.append({'file':p.name,'pixels':list(im.size),'dpi':im.info.get('dpi'),'byte_size':p.stat().st_size})
            thumb=ImageOps.contain(im.convert('RGB'),(880,420))
        x=(j%2)*900+(900-thumb.width)//2;y=(j//2)*470+30
        sheet.paste(thumb,(x,y));draw.text(((j%2)*900+12,(j//2)*470+8),f'{start+j+1:02d} / {p.stem.encode("ascii",errors="replace").decode()}',fill='black')
    sheet.save(r/'qa'/f'map_review_{start//6+1:02d}.jpg',quality=90)
a.save_json(r/'qa/map_file_checks.json',manifest)
print('Final maps and aligned density rasters rendered:',len(files),flush=True)
