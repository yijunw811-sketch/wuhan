"""New user ROI: exact boundary-pixel/grid intersection, all spatial analyses."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/wuhan_study_mpl');os.environ.setdefault('MPLBACKEND','Agg')
from pathlib import Path
import json,math,sys,shutil,hashlib
import numpy as np,pandas as pd,geopandas as gpd,rasterio,shapely
from rasterio.features import rasterize
from scipy.ndimage import binary_dilation
from shapely.geometry import box
from pyproj import Transformer
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from matplotlib.colors import ListedColormap,BoundaryNorm
import analysis_core as a

BASE=Path(__file__).resolve().parents[1];C=json.loads((BASE/'config/analysis.json').read_text());OUT=Path(C['output_root'])
if not OUT.is_absolute():OUT=(BASE/'config'/OUT).resolve()
for d in ['data','maps','tables','methods','qa','input','config','scripts']:(OUT/d).mkdir(parents=True,exist_ok=True)
a.ROOT=OUT;a.C=C;a.QA={};a.FIELDS=[];a.MOR=[];a.SCALE=[];a.MAPS=[]
SOURCE=(BASE/'config'/C['input_classification']).resolve();BOUNDARY=(BASE/'config'/C['input_boundary']).resolve()

def polygon_path(geom):
    geom=shapely.orient_polygons(geom)
    polygons=list(geom.geoms) if geom.geom_type=='MultiPolygon' else [geom]
    vv=[];codes=[]
    for p in polygons:
        for ring in [p.exterior,*p.interiors]:
            xy=np.array(ring.coords)[:,:2];vv.extend(xy);codes.extend([MPath.MOVETO]+[MPath.LINETO]*(len(xy)-2)+[MPath.CLOSEPOLY])
    return MPath(np.array(vv),np.array(codes))

ORIGINAL_MAP=a.mapfig
def mapfig(*args,**kwargs):
    # Temporarily intercept save to apply a genuine vector clip, including holes.
    old=a.savefig
    def save(f,name):
        for ax in f.axes:
            for im in ax.images:im.set_clip_path(PathPatch(polygon_path(ROI),transform=ax.transData))
        for t in f.texts:
            if t.get_text().startswith('数据来源：'):
                t.set_text('数据来源：用户RGB分类影像、配色表及研究范围边界。数据年份待补充。\n研究范围按用户边界确定；未核定其行政或规划边界属性。15 m为源像元间距，不代表分类精度。')
        old(f,name)
    a.savefig=save
    try:ORIGINAL_MAP(*args,**kwargs)
    finally:a.savefig=old
a.mapfig=mapfig

def prep():
    global ROI,CL,FRACTION,PARTIAL,PROFILE,EXTENT,H,W,T
    g=gpd.read_file(BOUNDARY);assert g.crs and len(g)>0
    op=Transformer.from_crs(g.crs,32649,always_xy=True)
    a.QA['coordinate_operation']={'description':op.description,'accuracy_m':op.accuracy,'definition':op.definition,'no_external_control_points':True}
    fixes=[];geoms=[]
    for i,p in enumerate(g.geometry):
        before=shapely.force_2d(p);after=shapely.make_valid(before)
        assert after.geom_type in ['Polygon','MultiPolygon'] and after.is_valid
        fixes.append({'feature':i,'valid_before':bool(before.is_valid),'reason':shapely.is_valid_reason(before),'source_area_before_m2':before.area,'source_area_after_m2':after.area,'delta_m2':after.area-before.area,'drop_Z_for_2D_analysis':bool(p.has_z),'kept':True})
        geoms.append(after)
    repaired=g.copy();repaired.geometry=geoms;utm=repaired.to_crs(32649)
    utm=utm.rename(columns={'Shape_Area':'SRC_AREA','Shape_Leng':'SRC_LEN'});utm['AREA_UTM']=utm.area
    ROI=shapely.union_all(utm.geometry.to_numpy())
    original=g.copy();original.to_file(OUT/'data/study_original.gpkg',layer='original',driver='GPKG')
    with rasterio.open(SOURCE) as d:
        a.CRS=d.crs;T=d.transform;H,W=d.shape;PROFILE=d.profile;EXTENT=[d.bounds.left,d.bounds.right,d.bounds.bottom,d.bounds.top];a.COVER_EXTENT=EXTENT
        footprint=box(*d.bounds);outside=ROI.difference(footprint).area
        assert outside<.01,'Study boundary extends beyond classified coverage; handle missing coverage explicitly'
        ROI=ROI.intersection(footprint);CL=d.read(1)
    scope=gpd.GeoDataFrame({'NAME':['用户研究范围'],'AREA_M2':[ROI.area]},geometry=[ROI],crs=a.CRS)
    scope.to_file(OUT/'data/study_scope.shp',encoding='UTF-8');scope.to_file(OUT/'data/results.gpkg',layer='scope',driver='GPKG')
    scope.to_file(OUT/'data/valid_scope.shp',encoding='UTF-8');scope.to_file(OUT/'data/results.gpkg',layer='valid_scope',driver='GPKG')
    utm.to_file(OUT/'data/results.gpkg',layer='repaired_features',driver='GPKG')
    center=rasterize([(ROI,1)],out_shape=(H,W),transform=T,dtype='uint8')
    line=rasterize([(ROI.boundary,1)],out_shape=(H,W),transform=T,dtype='uint8',all_touched=True)
    candidate=binary_dilation(line.astype(bool),iterations=1)
    FRACTION=center.astype(float);rs,cs=np.where(candidate);PARTIAL=[]
    for st in range(0,len(rs),2048):
        rr=rs[st:st+2048];cc=cs[st:st+2048]
        x=T.c+cc*15;y=T.f-rr*15
        cells=shapely.box(x,y-15,x+15,y)
        clipped=shapely.intersection(cells,ROI);areas=shapely.area(clipped)
        frac=np.clip(areas/225.,0,1);FRACTION[rr,cc]=frac
        for r,c,f,p in zip(rr,cc,frac,clipped):
            if 1e-12<f<1-1e-12:PARTIAL.append((int(r),int(c),float(f),p))
    assert np.all((CL[FRACTION>0]>=1)&(CL[FRACTION>0]<=8))
    error=abs(FRACTION.sum()*225-ROI.area);assert error<C['area_tolerance_m2'],error
    np.savez_compressed(OUT/'data/exact_fraction.npz',fraction=FRACTION)
    a.raster_write(OUT/'data/study_fraction.tif',FRACTION,PROFILE,-9999,'float32')
    study=np.where(FRACTION>0,CL,0).astype('uint8');a.raster_write(OUT/'data/classification.tif',study,PROFILE,0)
    with rasterio.open(OUT/'data/classification.tif','r+') as d:d.write_colormap(1,{i:tuple(int(a.COLORS[i].lstrip('#')[j:j+2],16) for j in (0,2,4)) for i in range(9)})
    for m,ids in C['groups'].items():a.raster_write(OUT/'data'/f'{m}_mask.tif',np.where(FRACTION>0,np.isin(CL,ids),255),PROFILE,255)
    a.raster_write(OUT/'data/blue_green_types.tif',np.where(FRACTION>0,np.where(np.isin(CL,C['groups']['blue_green']),CL,0),255),PROFILE,255)
    rows=[]
    for i in range(1,9):
        area=float(FRACTION[CL==i].sum())*225
        rows.append({'CLASS_ID':i,'SRC_NAME':C['source_names'][str(i)],'DISPLAY_NAME':a.NAMES[i],'touched_pixels':int(((CL==i)&(FRACTION>0)).sum()),'equivalent_full_pixels':area/225,'area_m2':area,'area_km2':area/1e6,'percent':area/ROI.area*100})
    tab=pd.DataFrame(rows);a.csvout(tab,OUT/'tables/class_area.csv')
    groups={m:float(tab[tab.CLASS_ID.isin(ids)].area_m2.sum()) for m,ids in C['groups'].items()}
    assert abs(groups['blue_green']-groups['blue']-groups['green']-groups['wetland'])<.001
    a.csvout(pd.DataFrame([dict(type=m,area_km2=v/1e6,percent=v/ROI.area*100) for m,v in groups.items()]),OUT/'tables/group_areas.csv')
    a.csvout(pd.DataFrame([dict(row=r,col=c,CLASS_ID=int(CL[r,c]),fraction=f,area_m2=p.area) for r,c,f,p in PARTIAL]),OUT/'qa/boundary_pixels.csv')
    a.QA['boundary']={'source_CRS':str(g.crs),'analysis_CRS':str(a.CRS),'repairs':fixes,'study_area_m2':ROI.area,'outside_image_m2':outside,'exact_fraction_area_error_m2':error,'partial_pixels':len(PARTIAL),'tiny_feature_kept':True,'source_classification_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    return groups,tab

def grids(groups):
    left,right,bottom,top=EXTENT
    for scale in C['grid_sizes_m']:
        print('Study grids',scale,flush=True);OX=a.overlap(W,15,scale);OY=a.overlap(H,15,scale);nr,nc=OY.shape[0],OX.shape[0]
        areas=np.zeros((nr,nc,9))
        for y0 in range(0,H,256):
            y1=min(H,y0+256);cl=CL[H-y1:H-y0][::-1];fr=FRACTION[H-y1:H-y0][::-1];yy=OY[:,y0:y1]
            for i in range(1,9):areas[:,:,i]+=yy@((OX@((cl==i)*fr).T).T)
        # Fractional pixel mass is spatially nonuniform where BOTH boundary and
        # grid cut a pixel. Correct those allocations using actual intersections.
        for r,c,f,p in PARTIAL:
            px=left+c*15;py=top-(r+1)*15;ix0=max(0,int((px-left)//scale));iy0=max(0,int((py-bottom)//scale))
            ix1=min(nc-1,int(np.nextafter((px+15-left)/scale,-np.inf)));iy1=min(nr-1,int(np.nextafter((py+15-bottom)/scale,-np.inf)))
            if ix0==ix1 and iy0==iy1:continue
            for iy in range(iy0,iy1+1):
                for ix in range(ix0,ix1+1):
                    cell=box(left+ix*scale,bottom+iy*scale,left+(ix+1)*scale,bottom+(iy+1)*scale)
                    nominal=max(0,min(px+15,left+(ix+1)*scale)-max(px,left+ix*scale))*max(0,min(py+15,bottom+(iy+1)*scale)-max(py,bottom+iy*scale))*f
                    areas[iy,ix,int(CL[r,c])]+=p.intersection(cell).area-nominal
        areas[np.abs(areas)<1e-9]=0;assert areas.min()>-1e-5
        full=[box(left+c*scale,bottom+r*scale,left+(c+1)*scale,bottom+(r+1)*scale) for r in range(nr) for c in range(nc)]
        clips=shapely.intersection(np.array(full,dtype=object),ROI);scopearea=shapely.area(clips);valid=areas.sum(2).ravel()
        maxerr=float(np.max(abs(scopearea-valid)));assert maxerr<.01,maxerr
        cover=np.divide(valid,scopearea,out=np.full_like(valid,np.nan),where=scopearea>0);edge=scopearea/scale**2
        df=pd.DataFrame({'GRID_ID':[f'S{scale}_R{r:03d}C{c:03d}' for r in range(nr) for c in range(nc)],'row':np.repeat(np.arange(nr),nc),'col':np.tile(np.arange(nc),nr),'scope_m2':scopearea,'valid_m2':valid,'valid_cov':cover,'edge_frac':edge})
        for m,ids in C['groups'].items():
            target=areas[:,:,ids].sum(2).ravel();pct=np.divide(target,valid,out=np.full_like(target,np.nan),where=valid>1e-8)*100
            pct=np.clip(pct,0,100);df[m+'_m2']=target;df[m+'_pct']=pct
            assert abs(target.sum()-groups[m])<.01
            tr=rasterio.transform.from_origin(left,bottom+nr*scale,scale,scale)
            a.raster_write(OUT/'data'/f'{m}_density_{scale}.tif',np.nan_to_num(pct.reshape(nr,nc)[::-1],nan=-9999),PROFILE,-9999,'float32',tr)
        base=df.copy();df['eligible']=((cover>=.95-1e-8)&(edge>=.25)&(valid>0)).astype(int)
        df['status']=np.where(scopearea<=0,'OUTSIDE',np.where(cover<.95-1e-8,'LOW_COVER',np.where(edge<.25,'EDGE_SMALL','OK')))
        df=a.inference(df,nr,nc,scale);a.csvout(df,OUT/'tables'/f'grid_{scale}.csv')
        a.export_vectors(df,full,scale,'full');sel=scopearea>0;a.export_vectors(df.loc[sel].copy(),list(clips[sel]),scale,'clip')
        for threshold in C['edge_sensitivity_min_fractions']:
            alt=base.copy();alt['eligible']=((cover>=.95-1e-8)&(edge>=threshold)&(valid>1e-8)).astype(int)
            alt=a.inference(alt,nr,nc,scale,f'edge_{threshold}');a.csvout(alt,OUT/'tables'/f'edge_sensitivity_{scale}_{threshold}.csv')
        a.QA[f'area_{scale}']={'raster_exact_m2':FRACTION.sum()*225,'grid_m2':valid.sum(),'polygon_m2':ROI.area,'max_per_grid_error_m2':maxerr,'absolute_total_error_m2':abs(valid.sum()-ROI.area),'boundary_grid_double_cut':'exact geometry correction','tolerance_m2':.01}
        extent=[left,left+nc*scale,bottom,bottom+nr*scale]
        for j,m in enumerate(a.MET):
            arr=df[m+'_pct'].to_numpy().reshape(nr,nc)[::-1];ix=np.digitize(arr,[0,10,25,50,75,100.00001]);ix=np.where(arr==0,0,ix);ix=np.where(np.isfinite(arr),ix,np.nan)
            a.mapfig({'blue':'03','green':'05','blue_green':'07'}[m]+'_'+m+f'_网格面积占比_{scale}m',a.CN[m]+f'网格面积占比｜{scale} m',ix,extent,['#f7f7f7','#e2f0d9','#b8d9ba','#7fb6aa','#3b8d95','#145569'],['0%','>0–<10%','10–<25%','25–<50%','50–<75%','75–100%'],note='按用户研究范围精确计算边缘面积\n目标面积÷有效分类面积\n此图为网格面积占比；核密度另交\n绿色含耕地；湿地独立纳入整体')
            for stat,num,colors,labels in [('lc',str(8+j).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3','#e8a06a','#9a91bf'],['无法计算／未纳入','不显著','高—高 HH','低—低 LL','高—低 HL','低—高 LH']),('gc',str(11+j).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3'],['无法计算／未纳入','不显著','显著热点','显著冷点'])]:
                v=df[m+'_'+stat].to_numpy().reshape(nr,nc)[::-1]+1
                v=np.where(scopearea.reshape(nr,nc)[::-1]>0,v,np.nan)
                a.mapfig(num+'_'+m+'_'+stat+f'_{scale}m',a.CN[m]+(' LISA' if stat=='lc' else ' Gi* 热点')+f'｜{scale} m',v,extent,colors,labels,note='用户研究范围内重新计算\nQueen；9999次双侧条件置换\nBH-FDR q<0.05；边缘比例≥25%\n有效分类覆盖率≥95%\n空间集聚不等于生态质量')

def maps(groups,tab):
    data=np.where(FRACTION>0,CL,np.nan)
    a.mapfig('01_研究范围土地利用分类','武汉地区蓝绿空间研究｜研究范围内分类',data,EXTENT,a.COLORS,a.NAMES,note='边界：用户提供，已转换投影\n分类未经滤波、去斑或修改\n边界像元面积按实际相交计算\n标准最新现行性尚未在线核实')
    for name,m in [('02_蓝色空间分布','blue'),('04_绿色空间分布','green'),('06_蓝绿整体分布','blue_green'),('14_湿地分布','wetland')]:
        if m=='blue_green':
            ids=[0,1,3,4,5,6,8];display=np.zeros_like(CL)
            for j,i in enumerate(ids[1:],1):display[CL==i]=j
            val=np.where(FRACTION>0,display,np.nan);colors=[a.COLORS[i] for i in ids];labels=['非蓝绿空间']+[a.NAMES[i] for i in ids[1:]]
        else:val=np.where(FRACTION>0,np.isin(CL,C['groups'][m]),np.nan);colors=['#f1f0ed',{'blue':'#3182bd','green':'#71a35a','wetland':'#55b6a2'}[m]];labels=['有效研究范围内非目标类别',a.CN[m]]
        a.mapfig(name,a.CN[m]+'分布｜用户研究范围',val,EXTENT,colors,labels,note='研究范围外为NoData\n绿色包含耕地\n湿地独立纳入蓝绿整体\n原始小面保留，未擅自删除')
    f,ax=plt.subplots(figsize=(16.535,11.693));ax.barh(tab.DISPLAY_NAME,tab.area_km2,color=a.COLORS[1:]);ax.set_xlabel('面积 / km²');ax.set_title('用户研究范围内分类面积与比例｜数据年份待补充')
    for i,r in tab.iterrows():ax.text(r.area_km2+5,i,f'{r.area_km2:.2f} km² / {r.percent:.2f}%',va='center')
    ax.set_xlim(0,tab.area_km2.max()*1.35);f.tight_layout();a.savefig(f,'15_分类面积与比例')

def run():
    groups,tab=prep();maps(groups,tab);grids(groups)
    a.csvout(pd.DataFrame(a.MOR),OUT/'tables/global_moran.csv');a.csvout(pd.DataFrame(a.SCALE),OUT/'tables/scale_edge_comparison.csv');a.csvout(pd.DataFrame(a.FIELDS),OUT/'methods/field_dictionary.csv')
    a.save_json(OUT/'qa/validation.json',a.QA);a.save_json(OUT/'qa/map_manifest.json',a.MAPS)
    print('STUDY ANALYSIS COMPLETE',len(a.MAPS),'map pairs',flush=True)
if __name__=='__main__':run()
