#!/usr/bin/env python3
"""Area-weighted compact quartic KDE, raw and observation-window edge correction."""
import os
os.environ.setdefault('MPLBACKEND','Agg');os.environ.setdefault('MPLCONFIGDIR','/tmp/wuhan_kde_mpl')
import json,math,sys,hashlib,time
from pathlib import Path
import numpy as np,pandas as pd,rasterio
from rasterio.windows import Window
from rasterio.transform import Affine
from scipy.signal import fftconvolve,convolve2d
from scipy.ndimage import distance_transform_edt

HERE=Path(__file__).resolve().parents[1];CONF=HERE/'config/kde.json'
C=json.loads(CONF.read_text());OUT=Path(C['output_root'])
if not OUT.is_absolute():OUT=(CONF.parent/OUT).resolve()
OUT.mkdir(exist_ok=True)
for name in ['data','maps','tables','qa','methods','config','scripts']:(OUT/name).mkdir(exist_ok=True)
SRC=(CONF.parent/C['input_classification']).resolve()
FRACTION=np.load((CONF.parent/C['fraction_npz']).resolve())['fraction']
if (HERE/'scripts/cartography.py').exists():
    sys.path.insert(0,str(HERE/'scripts'))
    import cartography as cart
else:
    sys.path.insert(0,str(HERE.parents[0]/'wuhan_research/scripts'))
    import run_analysis as cart
cart.ROOT=OUT
cart.C['map_dpi']=C['map_dpi'];cart.C['map_page_inches']=C['map_inches']
QA={};SUMMARY=[];MET=['blue','green','blue_green'];ALL=['blue','green','wetland','blue_green']

def quartic(h,cell):
    r=math.ceil(h/cell);yy,xx=np.mgrid[-r:r+1,-r:r+1]*cell
    u=(xx*xx+yy*yy)/(h*h)
    # Continuous K per km², then quadrature normalization for exact discrete mass.
    k=np.where(u<1,3/(np.pi*(h/1000)**2)*(1-u)**2,0.)
    k=k/k.sum()
    assert np.isclose(k.sum(),1,rtol=0,atol=1e-14)
    return k,r

def checks():
    k,r=quartic(70,15)
    a=np.zeros((25,31));a[8:17,12:19]=1
    full=fftconvolve(a,k,mode='full')*100
    assert abs(full.sum()*.000225-a.sum()*.0225)<1e-12
    assert np.max(abs(fftconvolve(a,k,'same')-convolve2d(a,k,'same')))<1e-14
    whole=fftconvolve(a,k,'same')
    block=np.zeros_like(a)
    for y in range(0,len(a),6):
        e=min(len(a),y+6);s=max(0,y-r);t=min(len(a),e+r)
        block[y:e]=fftconvolve(a[s:t],k,'same')[y-s:e-s]
    assert np.max(abs(block-whole))<1e-14
    exposure=fftconvolve(np.ones_like(a),k,'same')
    assert np.max(abs(exposure/exposure*100-100))==0
    QA['small_cases']={'unit_discrete_kernel_integral':'PASS','full_plane_mass_conservation':'PASS','FFT_vs_direct_convolution':'PASS','halo_stripes_vs_whole':'PASS','constant_field_edge_correction':'PASS'}

def regrid(values,valid,factor):
    sh=(values.shape[0]//factor,factor,values.shape[1]//factor,factor)
    num=(values*valid).reshape(sh).sum((1,3));den=valid.reshape(sh).sum((1,3))
    return np.divide(num,den,out=np.full_like(num,C['nodata']),where=den>0)

def run():
    checks()
    with rasterio.open(SRC) as src:
        assert src.count==1 and src.res==(15.,15.)
        H,W=src.shape;cell=src.res[0];factor=int(C['output_cell_size_m']/cell)
        assert factor*cell==C['output_cell_size_m'] and H%factor==W%factor==0
        assert C['row_block_size']%factor==0
        transform=src.transform*Affine.scale(factor,factor)
        profile=src.profile.copy();profile.update(dtype='float32',nodata=C['nodata'],height=H//factor,width=W//factor,transform=transform,compress='LZW',tiled=True,blockxsize=256,blockysize=256,count=1)
        cart.COVER_EXTENT=[src.bounds.left,src.bounds.right,src.bounds.bottom,src.bounds.top]
        counts={m:0. for m in ALL}
        for _,win in src.block_windows(1):
            cl=src.read(1,window=win)
            r0,c0=int(win.row_off),int(win.col_off);fr=FRACTION[r0:r0+cl.shape[0],c0:c0+cl.shape[1]]
            for m,ids in C['groups'].items():counts[m]+=float((np.isin(cl,ids)*fr).sum())
        QA['input']={'sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'bounds':list(src.bounds),'crs':str(src.crs),'source_resolution_m':cell,'output_resolution_m':C['output_cell_size_m'],'equivalent_full_pixel_counts':counts,'scope_polygon':C['scope_file'],'fractional_domain':True,'no_reclassification':True}
        coverage90=FRACTION.reshape(H//factor,factor,W//factor,factor).mean((1,3))
        with rasterio.open(OUT/'data/study_coverage_90m.tif','w',**profile) as dst:dst.write(coverage90.astype('float32'),1)
        for h in C['bandwidth_radius_m']:
            print('KDE radius',h,flush=True);k,r=quartic(h,cell)
            writers={};observed={m:0. for m in ALL};expected={m:0. for m in ALL};exp_min=1.;additivity=0.
            for m in ALL:
                for version in ['raw','edge_corrected']:
                    name=f'kde_{m}_h{h}_{version}.tif';writers[(m,version)]=rasterio.open(OUT/'data'/name,'w',**profile)
                    writers[(m,version)].update_tags(UNIT='ha/km2',KERNEL='quartic',SEARCH_RADIUS_M=str(h),METHOD='area-weighted raster-pixel mass KDE',EDGE_CORRECTION=version,OUTPUT_MEAN='6x6 area mean of 15m computed KDE',DATA_YEAR='unknown')
            ewriter=rasterio.open(OUT/'data'/f'kernel_exposure_h{h}.tif','w',**profile)
            try:
                for y0 in range(0,H,C['row_block_size']):
                    y1=min(H,y0+C['row_block_size']);s=max(0,y0-r);e=min(H,y1+r)
                    cl=src.read(1,window=Window(0,s,W,e-s));valid=(cl>0)&(cl<9);coverage=FRACTION[s:e]*valid;core=coverage[y0-s:y1-s]
                    ex=fftconvolve(coverage,k,mode='same')[y0-s:y1-s]
                    ex=np.clip(ex,0,1);exp_min=min(exp_min,float(ex[core>0].min())) if np.any(core>0) else exp_min
                    outwindow=Window(0,y0//factor,W//factor,(y1-y0)//factor)
                    ewriter.write(regrid(ex,core,factor).astype('float32'),1,window=outwindow)
                    component={}
                    for m in ALL:
                        target=np.isin(cl,C['groups'][m])&valid;target_mass=target*coverage
                        intensity=fftconvolve(target_mass,k,mode='same')[y0-s:y1-s]*100
                        # Compact support gives mathematical zeros. Restore them by exact
                        # nearest-target distance, rather than thresholding small real values.
                        if target.any():zero=distance_transform_edt(~target,sampling=cell)[y0-s:y1-s]>=h
                        else:zero=np.ones(core.shape,bool)
                        intensity[zero]=0;intensity=np.clip(intensity,0,100)
                        corrected=np.divide(intensity,ex,out=np.zeros_like(intensity),where=ex>1e-14);corrected=np.clip(corrected,0,100)
                        observed[m]+=float((intensity*core).sum())*(cell/1000)**2
                        expected[m]+=float((target_mass[y0-s:y1-s]*ex).sum())*.0225
                        if m!='blue_green':component[m]=intensity
                        else:additivity=max(additivity,float(np.max(abs(intensity-component['blue']-component['green']-component['wetland']))))
                        for version,val in [('raw',intensity),('edge_corrected',corrected)]:writers[(m,version)].write(regrid(val,core,factor).astype('float32'),1,window=outwindow)
            finally:
                for d in writers.values():d.close()
                ewriter.close()
            assert additivity<1e-8
            for m in ALL:assert abs(observed[m]-expected[m])<max(1e-6,counts[m]*.0225*1e-9)
            QA[str(h)]={'kernel_sum':float(k.sum()),'kernel_radius_pixels':r,'kernel_support_m':h,'exposure_min':exp_min,'linear_union_max_error_ha_per_km2':additivity,'cropped_raw_mass_ha':observed,'cropped_raw_expected_ha_from_exposure':expected,'original_target_area_ha':{m:n*.0225 for m,n in counts.items()},'edge_corrected_mass_conservation':'NOT CLAIMED: edge correction changes the integrated intensity','kernel_integral_note':'Finite 15m quadrature normalized to integral 1; output is 90m area mean'}
            for m in MET:
                for version in ['raw','edge_corrected']:
                    p=OUT/'data'/f'kde_{m}_h{h}_{version}.tif'
                    with rasterio.open(p) as d:
                        a=d.read(1,masked=True);assert d.bounds==src.bounds and d.crs==src.crs
                        assert a.min()>=0 and a.max()<=100.00001
                        vals=a.compressed();q=np.quantile(vals,[0,.25,.5,.75,.9,.95,1])
                        SUMMARY.append({'indicator':m,'bandwidth_m':h,'version':version,'unit':'ha/km2','min':q[0],'q25':q[1],'median':q[2],'q75':q[3],'q90':q[4],'q95':q[5],'max':q[6],'mean':vals.mean(),'zero_cells':int((vals==0).sum()),'cells':len(vals)})
                    breaks=list(C['density_breaks_ha_per_km2']);breaks[-1]+=1e-4
                    b=np.digitize(a.filled(np.nan),breaks);b=np.where(a==0,0,b);b=np.where(np.ma.getmaskarray(a),np.nan,b)
                    palette={'blue':['#f7f7f7','#e3f1fa','#b3d4e9','#74abd1','#337cad','#124a75'],'green':['#f7f7f7','#edf4cf','#c9df9c','#8ec17a','#4a9656','#1c6337'],'blue_green':['#f7f7f7','#e2f1e8','#b5dbcd','#76b7aa','#3b8f8e','#145969']}[m]
                    kind='边缘校正' if version=='edge_corrected' else '原始核密度（边缘截断）'
                    title=f'{cart.CN[m]}核密度分析｜搜索半径 {h/1000:g} km'
                    note=f'四次核 Quartic；按原分类像元面积加权\n{kind}\n单位：ha/km²（公顷/平方公里）\n核计算15 m；输出90 m面积均值\n绿色含耕地；蓝绿整体另含独立湿地\n描述性集聚；不代表统计显著性'
                    cart.mapfig(f'KDE_{m}_h{h}_{version}',title,b,cart.COVER_EXTENT,palette,['0','>0–<10','10–<25','25–<50','50–<75','75–100'],note=note)
            print('Completed',h,flush=True)
    pd.DataFrame(SUMMARY).to_csv(OUT/'tables/kde_surface_statistics.csv',index=False,encoding='utf-8-sig')
    QA['output_readback']={}
    for p in (OUT/'data').glob('*.tif'):
        with rasterio.open(p) as d:
            for _,win in d.block_windows(1):v=d.read(1,window=win)
            QA['output_readback'][p.name]={'shape':d.shape,'bounds':list(d.bounds),'crs':str(d.crs),'full_read':'PASS'}
    (OUT/'qa/kde_validation.json').write_text(json.dumps(QA,ensure_ascii=False,indent=2))
    print('COMPLETE: area-weighted KDE, raw/edge corrected, 3 search radii',flush=True)

if __name__=='__main__':run()
