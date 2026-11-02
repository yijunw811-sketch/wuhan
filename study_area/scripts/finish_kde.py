"""Verify KDE units/integrals, render bandwidth chart, prepare ArcMap RGB views."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd,rasterio
from rasterio.enums import ColorInterp
import run_kde as k
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from PIL import Image,ImageOps,ImageDraw
import fitz

r=k.OUT;q=json.loads((r/'qa/kde_validation.json').read_text())
with rasterio.open(r/'data/study_coverage_90m.tif') as cov:coverage90=cov.read(1)
palettes={'blue':['#f7f7f7','#e3f1fa','#b3d4e9','#74abd1','#337cad','#124a75'],'green':['#f7f7f7','#edf4cf','#c9df9c','#8ec17a','#4a9656','#1c6337'],'blue_green':['#f7f7f7','#e2f1e8','#b5dbcd','#76b7aa','#3b8f8e','#145969']}
f,axs=plt.subplots(3,3,figsize=tuple(k.C['map_inches']))
for j,h in enumerate(k.C['bandwidth_radius_m']):
    errors={}
    for version in ['raw','edge_corrected']:
        aa={}
        for m in k.ALL:
            with rasterio.open(r/'data'/f'kde_{m}_h{h}_{version}.tif') as d:aa[m]=np.where(d.read(1)==k.C['nodata'],0,d.read(1)).astype(float)
        err=float(np.max(abs(aa['blue_green']-aa['blue']-aa['green']-aa['wetland'])));assert err<2e-5;errors[version]=err
        if version=='raw':
            for m,a in aa.items():
                expected=q[str(h)]['cropped_raw_mass_ha'][m]
                actual=float((a*coverage90).sum())*(k.C['output_cell_size_m']/1000)**2
                assert abs(actual-expected)<max(.001,expected*1e-7)
    q[str(h)]['float32_90m_union_max_error']=errors
    q[str(h)]['90m_raw_integral_matches_15m_integral']='PASS; max(0.001 ha, 1e-7 relative)'
    for i,m in enumerate(k.MET):
        with rasterio.open(r/'data'/f'kde_{m}_h{h}_edge_corrected.tif') as d:
            a=d.read(1);breaks=list(k.C['density_breaks_ha_per_km2']);breaks[-1]+=1e-4
            b=np.digitize(a,breaks);b=np.where(a==0,0,b);extent=[d.bounds.left,d.bounds.right,d.bounds.bottom,d.bounds.top]
            axs[i,j].imshow(b,extent=extent,cmap=ListedColormap(palettes[m]),norm=BoundaryNorm(np.arange(-.5,6.5),6),interpolation='nearest');axs[i,j].set_aspect('equal');axs[i,j].set_title(k.cart.CN[m]+f' | h={h} m',fontsize=12);axs[i,j].set_xticks([]);axs[i,j].set_yticks([])
            if h==k.C['main_bandwidth_m']:
                rgb=(ListedColormap(palettes[m])(b)[:,:,:3]*255).round().astype('uint8');pr=d.profile.copy();pr.update(count=3,dtype='uint8',nodata=0,photometric='RGB',interleave='pixel');rgb[coverage90<=0]=0
                with rasterio.open(r/'data'/f'display_KDE_{m}_h1000_RGB.tif','w',**pr) as dst:
                    dst.write(rgb.transpose(2,0,1));dst.colorinterp=(ColorInterp.red,ColorInterp.green,ColorInterp.blue);dst.update_tags(ROLE='Display-only RGB; quantitative data in kde_*_edge_corrected.tif')
f.suptitle('研究范围内蓝绿空间核密度｜半径比较（主结果 1 km；边缘校正）',fontsize=20)
f.text(.10,.045,'统一分级（ha/km²）：0、>0–<10、10–<25、25–<50、50–<75、75–100。四次核，按分类像元面积加权。',fontsize=12)
f.text(.10,.022,'数据来源：用户RGB分类影像；年份待补充。研究范围为用户提供边界；带宽不是网格尺度或分类精度，深色不代表统计显著性。',fontsize=11)
f.subplots_adjust(left=.08,right=.96,bottom=.09,top=.91,hspace=.18,wspace=.12);k.cart.savefig(f,'KDE_搜索半径敏感性比较')
preview=Image.new('RGB',(2200,1560),'white')
names=[r/'maps'/f'KDE_{m}_h1000_edge_corrected.png' for m in k.MET]+[r/'maps/KDE_搜索半径敏感性比较.png']
for i,p in enumerate(names):
    with Image.open(p) as im:t=ImageOps.contain(im.convert('RGB'),(1100,780));preview.paste(t,((i%2)*1100,(i//2)*780))
preview.save(r/'main_preview.jpg',quality=94)
files=sorted((r/'maps').glob('*.png'));map_checks=[]
for st in range(0,len(files),6):
    sheet=Image.new('RGB',(1800,1410),'white');draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(files[st:st+6]):
        with Image.open(p) as im:
            assert abs(im.size[0]-4960)<=2 and abs(im.size[1]-3507)<=2
            t=ImageOps.contain(im.convert('RGB'),(890,430))
        sheet.paste(t,((j%2)*900+(900-t.width)//2,(j//2)*470+30));draw.text(((j%2)*900+10,(j//2)*470+5),p.stem,fill='black')
        with fitz.open(p.with_suffix('.pdf')) as doc:
            assert len(doc)==1 and doc[0].get_text().strip()
            assert abs(doc[0].rect.width-1190.52)<1
            doc[0].get_pixmap(matrix=fitz.Matrix(.2,.2))
        map_checks.append({'file':p.stem,'PNG_A3_300DPI':'PASS','PDF_parse_render':'PASS'})
    sheet.save(r/'qa'/f'map_review_{st//6+1:02d}.jpg',quality=92)
q['map_checks']=map_checks
(r/'qa/kde_validation.json').write_text(json.dumps(q,ensure_ascii=False,indent=2))
print('PASS: union additivity, raw integral, 90m aggregation, PNG/PDF readback;',len(files),'map pairs')

# Area-weighted surface means within partial 90m cells; not class proportions.
table=pd.read_csv(r/'tables/kde_surface_statistics.csv')
for idx,row in table.iterrows():
    with rasterio.open(r/'data'/f"kde_{row.indicator}_h{row.bandwidth_m}_{row.version}.tif") as d:
        values=d.read(1);values=np.where(values==k.C['nodata'],0,values)
    table.loc[idx,'area_weighted_mean']=float((values*coverage90).sum()/coverage90.sum())
table.to_csv(r/'tables/kde_surface_statistics.csv',index=False,encoding='utf-8-sig')
