"""Validate the new ROI results and build actual FileGDB; no ArcGIS claims."""
from pathlib import Path
import json,sys
import numpy as np,pandas as pd,geopandas as gpd,rasterio,pyogrio
from statsmodels.stats.multitest import multipletests
import matplotlib.pyplot as plt
from PIL import Image,ImageOps,ImageDraw
import fitz
import run_study as s

r=s.OUT;a=s.a;scope=gpd.read_file(r/'data/results.gpkg',layer='scope');s.ROI=scope.geometry.iloc[0];a.CRS=scope.crs
report={};mo=pd.read_csv(r/'tables/global_moran.csv')
for scale in [500,1000,2000]:
    d=pd.read_csv(r/'tables'/f'grid_{scale}.csv')
    assert d.GRID_ID.is_unique and abs(d.scope_m2.sum()-s.ROI.area)<.01
    assert np.allclose(d.scope_m2,d.valid_m2,atol=.01)
    for m in a.MET:
        assert d[m+'_pct'].dropna().between(0,100).all()
        v=d[d.eligible==1];one=mo[(mo.scale_m==scale)&(mo.indicator==m)&(mo.edge_rule=='main')].iloc[0]
        f,ax=plt.subplots(figsize=(16.535,11.693));ax.scatter(v[m+'_z'],v[m+'_lag'],s=7,alpha=.35,c='#3f7b74');ax.axhline(0,c='grey',lw=.7);ax.axvline(0,c='grey',lw=.7)
        xx=np.array([v[m+'_z'].min(),v[m+'_z'].max()]);ax.plot(xx,one.I*xx,c='#c3534a')
        ax.set(xlabel='研究范围内标准化面积占比 z',ylabel='不含自身的空间滞后 Wz',title=f'{a.CN[m]}｜{scale} m Moran 散点图\nI={one.I:.4f}；双侧置换p={one.p_perm_2s:.4f}；n={int(one.n)}')
        f.text(.12,.025,'研究范围：用户提供边界；数据年份待补充。Queen行标准化、9999次置换。空间集聚不等于生态质量。',fontsize=12)
        a.savefig(f,f'Moran_{m}_{scale}')
    for kind in ['full','clip']:
        p=r/'data'/f'grid_{scale}_{kind}.shp';g=gpd.read_file(p);assert g.crs==scope.crs and g.geometry.is_valid.all()
        assert all(len(c)<=10 for c in g.columns if c!='geometry')
        assert list(g.GRID_ID)==list(d.GRID_ID if kind=='full' else d.loc[d.scope_m2>0,'GRID_ID'])
        if kind=='clip':assert abs(g.area.sum()-s.ROI.area)<.01
        for ext in ['.shp','.shx','.dbf','.prj','.cpg']:assert p.with_suffix(ext).exists()
    report[str(scale)]={'full_rows':len(d),'clipped_rows':int((d.scope_m2>0).sum()),'eligible':int(d.eligible.sum()),'area_and_grid_ID_checks':'PASS'}
for p in list((r/'tables').glob('grid_*.csv'))+list((r/'tables').glob('edge_sensitivity*.csv')):
    d=pd.read_csv(p)
    for m in a.MET:
        for stat in ['l','g']:
            pp=d[m+'_'+stat+'p'].to_numpy();qq=d[m+'_'+stat+'q'].to_numpy();cc=d[m+'_'+stat+'c'].to_numpy();ok=np.isfinite(qq)
            assert np.allclose(qq[ok],multipletests(pp[ok],method='fdr_bh')[1],atol=1e-12)
            assert np.all((cc[ok]>0)==(qq[ok]<.05)) and np.all(cc[~ok]==-1)
        z=d[m+'_z'];lag=d[m+'_lag'];lc=d[m+'_lc'];gc=d[m+'_gc'];gz=d[m+'_gz']
        assert ((z[lc==1]>=0)&(lag[lc==1]>=0)).all() and ((z[lc==2]<0)&(lag[lc==2]<0)).all()
        assert ((z[lc==3]>=0)&(lag[lc==3]<0)).all() and ((z[lc==4]<0)&(lag[lc==4]>=0)).all()
        assert (gz[gc==1]>0).all() and (gz[gc==2]<0).all()
report['all_FDR_families_and_legends']='PASS'
f,axes=plt.subplots(1,3,figsize=(16.535,11.693))
for i,m in enumerate(a.MET):
    v=mo[(mo.indicator==m)&(mo.edge_rule=='main')];axes[i].plot(v.scale_m,v.I,'o-',c='#367d78');axes[i].set(title=a.CN[m],xlabel='网格尺度 / m',ylabel="全局 Moran's I");axes[i].grid(alpha=.2)
f.suptitle('用户研究范围内尺度比较｜500 m、1 km、2 km｜主尺度预定为1 km',fontsize=19);f.text(.1,.025,'研究范围：用户边界；数据年份待补充；统计基于精确面积加权的网格占比，非核密度显著性。',fontsize=11);f.tight_layout(rect=[0,.06,1,.94]);a.savefig(f,'16_网格尺度比较')
db=r/'data/wuhan_results.gdb';gdb=[]
for layer,geom in pyogrio.list_layers(r/'data/results.gpkg'):
    if geom is None:continue
    g=gpd.read_file(r/'data/results.gpkg',layer=layer)
    for c in g.columns:
        if c!='geometry' and pd.api.types.is_integer_dtype(g[c]):g[c]=g[c].astype('int32')
    pyogrio.write_dataframe(g,db,layer=layer,driver='OpenFileGDB',layer_options={'TARGET_ARCGIS_VERSION':'ALL','XYTOLERANCE':'0.001','XYSCALE':'10000000','XORIGIN':'0','YORIGIN':'0'})
    back=gpd.read_file(db,layer=layer);assert len(back)==len(g) and back.crs==g.crs and back.geometry.is_valid.all()
    geom_error=float(np.max(abs(back.area-g.area)));assert geom_error<.1,geom_error
    for c in g.columns:
        if c=='geometry':continue
        if pd.api.types.is_numeric_dtype(g[c]):assert np.allclose(g[c].to_numpy(float),back[c].to_numpy(float),equal_nan=True,atol=1e-8)
        else:assert list(g[c])==list(back[c])
    gdb.append({'layer':layer,'rows':len(back),'all_attributes_and_NULLs':'PASS','geometry_area_max_error_m2':geom_error})
for layer,p in [('class_areas',r/'tables/class_area.csv'),('group_areas',r/'tables/group_areas.csv'),('global_moran',r/'tables/global_moran.csv'),('scale_comparison',r/'tables/scale_edge_comparison.csv'),('class_crosswalk',r/'methods/class_crosswalk.csv'),('field_dictionary',r/'methods/field_dictionary.csv')]:
    g=pd.read_csv(p,dtype=str,keep_default_na=False) if layer=='class_crosswalk' else pd.read_csv(p)
    for c in g.columns:
        if pd.api.types.is_integer_dtype(g[c]):g[c]=g[c].astype('int32')
    pyogrio.write_dataframe(g,db,layer=layer,driver='OpenFileGDB',layer_options={'TARGET_ARCGIS_VERSION':'ALL'})
    assert len(pyogrio.read_dataframe(db,layer=layer))==len(g)
report['GDB']=gdb
for p in (r/'data').glob('*.tif'):
    with rasterio.open(p) as d:
        assert d.crs==scope.crs
        for _,win in d.block_windows(1):d.read(1,window=win)
report['GeoTIFF_full_read']='PASS';report['ArcMap_open_test']='NOT RUN: no ArcGIS';report['real_MXD']='NOT CREATED IN CLOUD'
maps=sorted((r/'maps').glob('*.png'));mc=[]
for st in range(0,len(maps),6):
    sheet=Image.new('RGB',(1800,1410),'white');draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(maps[st:st+6]):
        with Image.open(p) as im:
            assert abs(im.width-4960)<=2 and abs(im.height-3507)<=2;t=ImageOps.contain(im.convert('RGB'),(890,430))
        sheet.paste(t,((j%2)*900+(900-t.width)//2,(j//2)*470+30));draw.text(((j%2)*900+10,(j//2)*470+5),p.stem.encode('ascii',errors='replace').decode(),fill='black')
        with fitz.open(p.with_suffix('.pdf')) as pdf:
            assert len(pdf)==1 and pdf[0].get_text().strip();pdf[0].get_pixmap(matrix=fitz.Matrix(.2,.2))
        mc.append({'file':p.stem,'PNG_A3_300DPI':'PASS','PDF_parse_render':'PASS'})
    sheet.save(r/'qa'/f'map_review_{st//6+1:02d}.jpg',quality=91)
report['maps']=mc;(r/'qa/output_readback_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('PASS: exact ROI areas, full/clip grids, FDR, real FileGDB, raster readback;',len(maps),'map pairs')
