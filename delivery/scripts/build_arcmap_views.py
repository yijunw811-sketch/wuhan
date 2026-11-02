"""Precolored, real georeferenced views for ArcMap 10.5, without fake LYRs/MXDs."""
from pathlib import Path
import json
import numpy as np,pandas as pd,rasterio
from rasterio.features import rasterize
import geopandas as gpd

ROOT=Path('/workspace/client_delivery/ArcMap105');DATA=ROOT/'Data';VIEW=ROOT/'Views'
with rasterio.open(DATA/'land_classification.tif') as d:CL=d.read(1);PR=d.profile;T=d.transform;H,W=d.shape;B=d.bounds
VALID=CL>0;CAT=[]
PAL={'blue':['#f7f7f7','#e3f1fa','#b3d4e9','#74abd1','#337cad','#124a75'],'green':['#f7f7f7','#edf4cf','#c9df9c','#8ec17a','#4a9656','#1c6337'],'blue_green':['#f7f7f7','#e2f1e8','#b5dbcd','#76b7aa','#3b8f8e','#145969']}
CN={'blue':'蓝色空间','green':'绿色空间（含耕地）','blue_green':'蓝绿整体（含耕地、湿地）','wetland':'湿地'}
CLASS=['#eeeeee','#3182bd','#b6b4b1','#cedc8a','#55b6a2','#6baed6','#347d4c','#d7bd93','#8fbc75']
def rgb_write(name,codes,colors,valid,profile,label,section,default=False):
    cmap=np.array([[int(c.lstrip('#')[i:i+2],16) for i in [0,2,4]] for c in colors],dtype='uint8');pr=profile.copy();pr.update(driver='GTiff',count=3,dtype='uint8',nodata=0,photometric='RGB',interleave='pixel',compress='LZW',tiled=True,blockxsize=256,blockysize=256)
    path=VIEW/(name+'.tif')
    with rasterio.open(path,'w',**pr) as d:
        for row in range(0,codes.shape[0],256):
            end=min(row+256,codes.shape[0]);a=cmap[codes[row:end]];a[~valid[row:end]]=0;d.write(a.transpose(2,0,1),window=rasterio.windows.Window(0,row,codes.shape[1],end-row))
        d.colorinterp=(rasterio.enums.ColorInterp.red,rasterio.enums.ColorInterp.green,rasterio.enums.ColorInterp.blue);d.update_tags(ROLE='DISPLAY_ONLY_RGB; analytical values remain in Data and FileGDB',SOURCE_STUDY='User supplied boundary')
    CAT.append(dict(file='Views/'+path.name,name=label,section=section,visible=default))
rgb_write('01_Land_Use',CL,CLASS,VALID,PR,'01 土地利用分类','main')
for m,ids in {'blue':[1,5],'green':[3,6,8],'wetland':[4]}.items():
    color={'blue':'#3182bd','green':'#71a35a','wetland':'#55b6a2'}[m]
    rgb_write('Distribution_'+m,np.isin(CL,ids).astype('uint8'),['#f1f0ed',color],VALID,PR,CN[m]+'分布','main')
types=np.where(np.isin(CL,[1,3,4,5,6,8]),CL,0);rgb_write('06_BG_Types',types,CLASS,VALID,PR,'06 蓝绿空间类型分布','main')
for h in [1000,500,2000]:
    for m in ['blue','green','blue_green']:
        for version in ['edge_corrected','raw']:
            with rasterio.open(DATA/f'kde_kde_{m}_h{h}_{version}.tif') as d:
                a=d.read(1);pr=d.profile;valid=a!=d.nodata
            codes=np.digitize(a,[0,10,25,50,75,100.0001]);codes=np.where(a==0,0,codes);codes=np.where(valid,codes,0)
            key=f'KDE_{m}_{h}_{version}';label=CN[m]+f'核密度 h={h}m｜'+('边缘校正' if version=='edge_corrected' else '原始值')+'（ha/km²）'
            rgb_write(key,codes,PAL[m],valid,pr,label,'main' if h==1000 and version=='edge_corrected' else 'sensitivity',m=='blue_green' and h==1000 and version=='edge_corrected')
for h in [1000,500,2000]:
    table=pd.read_csv(ROOT/'Tables'/f'grid_{h}.csv');nr=int(table.row.max()+1);nc=int(table.col.max()+1)
    rr=np.minimum((((H-np.arange(H)-.5)*15)/h).astype(int),nr-1);cc=np.minimum((((np.arange(W)+.5)*15)/h).astype(int),nc-1)
    for m in ['blue','green','blue_green']:
        for method,colors in [('lc',['#dadada','#f7f7f7','#c44343','#467db3','#e8a06a','#9a91bf']),('gc',['#dadada','#f7f7f7','#c44343','#467db3'])]:
            matrix=table[m+'_'+method].to_numpy().reshape(nr,nc).astype(int)+1
            image=matrix[rr[:,None],cc[None,:]].astype('uint8')
            rgb_write(f'{method}_{m}_{h}',image,colors,VALID,PR,CN[m]+(' LISA' if method=='lc' else ' Gi*')+f'｜{h}m｜q<0.05','main' if h==1000 else 'sensitivity')
for key,data,color,label in [('00_StudyBoundary',rasterize([(gpd.read_file(DATA/'Wuhan_Study.gdb',layer='scope').geometry.iloc[0].boundary,1)],out_shape=(H,W),transform=T,all_touched=True,dtype='uint8'),(50,50,50,255),'研究范围轮廓（保持开启）'),('00_OutsideMask',(~VALID).astype('uint8'),(255,255,255,255),'范围外留白（显示辅助，保持开启）')]:
    pr=PR.copy();pr.update(dtype='uint8',count=1,nodata=0)
    with rasterio.open(VIEW/(key+'.tif'),'w',**pr) as d:d.write(data,1);d.write_colormap(1,{0:(0,0,0,0),1:color})
    CAT.insert(0,dict(file='Views/'+key+'.tif',name=label,section='aux',visible=True))
(ROOT/'layer_catalog.json').write_text(json.dumps(CAT,ensure_ascii=False,indent=2));print('Created',len(CAT),'ready-colored map views')
