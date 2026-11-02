#!/usr/bin/env python3
"""RGB recovery, exact area allocation, reproducible conditional inference and maps."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/wuhan_mpl')
os.environ.setdefault('MPLBACKEND','Agg')
import json, sys, math, hashlib, shutil, csv, time
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from scipy import sparse, stats
import geopandas as gpd
from shapely.geometry import box
from statsmodels.stats.multitest import multipletests
from numba import njit
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch, Rectangle
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[1]
C=json.loads((ROOT/'config/analysis.json').read_text())
for dr in ['data','maps','tables','methods','qa','arcmap_import']: (ROOT/dr).mkdir(exist_ok=True)
SEED=C['seed']; P=C['permutations']; ALPHA=C['alpha']
NAMES=['缺失数据','河流类水体（原长江类）','建设用地（合并类）','耕地','湿地','湖泊类水体（合并类）','林地','裸地（合并类）','草地']
COLORS=C.get('class_colors',['#eeeeee','#3182bd','#b6b4b1','#cedc8a','#55b6a2','#6baed6','#347d4c','#d7bd93','#8fbc75'])
MET=['blue','green','blue_green']; CN={'blue':'蓝色空间','green':'绿色空间（含耕地）','blue_green':'蓝绿空间整体（含耕地、湿地）','wetland':'湿地'}
FIELDS=[]; QA={}; MOR=[]; SCALE=[]; MAPS=[]

def save_json(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=lambda a:a.item() if hasattr(a,'item') else str(a)),encoding='utf-8')
def csvout(df,p): df.to_csv(p,index=False,encoding='utf-8-sig')
def raster_write(path,arr,profile,nodata,dtype='uint8',transform=None):
    pr=dict(profile);pr.update(driver='GTiff',count=1,dtype=dtype,nodata=nodata,compress='LZW',tiled=True,blockxsize=256,blockysize=256,BIGTIFF='IF_SAFER')
    if transform is not None: pr.update(transform=transform,height=arr.shape[0],width=arr.shape[1])
    with rasterio.open(path,'w',**pr) as dst: dst.write(arr.astype(dtype),1)

def overlap(n,step,grid):
    """Sparse grid-by-pixel overlap lengths, origin at lower left; no sampling."""
    ng=math.ceil(n*step/grid); rr=[];cc=[];vv=[]
    for j in range(n):
        a=j*step;b=a+step
        for i in range(int(a//grid),min(ng,math.ceil(b/grid))):
            q=min(b,(i+1)*grid)-max(a,i*grid)
            if q>0: rr.append(i);cc.append(j);vv.append(q)
    return sparse.csr_matrix((vv,(rr,cc)),shape=(ng,n))

def queen(rows,cols,selected):
    lookup={int(v):i for i,v in enumerate(selected)}; rr=[];cc=[]
    for i,v in enumerate(selected):
        r,c=divmod(int(v),cols)
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr==dc==0: continue
                y,x=r+dr,c+dc
                if 0<=y<rows and 0<=x<cols and y*cols+x in lookup:
                    rr.append(i);cc.append(lookup[y*cols+x])
    return sparse.csr_matrix((np.ones(len(rr)),(rr,cc)),shape=(len(selected),len(selected)))

@njit(cache=True)
def local_mc(x,z,ptr,indices,perms,seed):
    """Conditional randomization: focal fixed, k distinct draws from n-1."""
    n,m=x.shape; out=np.full((n,m,8),np.nan)
    for i in range(n):
        np.random.seed((seed+i*1009)%2147483647)
        k=ptr[i+1]-ptr[i]
        if k==0 or n<=k+1: continue
        pick=np.empty(k,np.int64)
        for h in range(m):
            lag=0.; sm=x[i,h]
            for b in range(ptr[i],ptr[i+1]):
                j=indices[b];lag+=z[j,h]/k;sm+=x[j,h]
            obs=z[i,h]*lag
            # Exact conditional moments of neighbor sum sampled without replacement.
            mu=(np.sum(x[:,h])-x[i,h])/(n-1)
            ss=np.sum((x[:,h]-mu)**2)-(x[i,h]-mu)**2
            var=(ss/(n-1))*k*((n-1-k)/(n-2))
            mean=x[i,h]+k*mu
            out[i,h,0]=obs;out[i,h,1]=lag;out[i,h,2]=sm/np.sum(x[:,h]) if np.sum(x[:,h])>0 else np.nan
            out[i,h,3]=(sm-mean)/np.sqrt(var) if var>0 else np.nan
            out[i,h,6]=sm;out[i,h,7]=mean
        ci=np.zeros(m);cg=np.zeros(m)
        for p in range(perms):
            for b in range(k):
                while True:
                    j=np.random.randint(n-1)
                    if j>=i: j+=1
                    duplicate=False
                    for a in range(b):
                        if pick[a]==j: duplicate=True
                    if not duplicate: break
                pick[b]=j
            for h in range(m):
                lag=0.;sm=x[i,h]
                for b in range(k):lag+=z[pick[b],h]/k;sm+=x[pick[b],h]
                ei=-z[i,h]*z[i,h]/(n-1)
                if abs(z[i,h]*lag-ei)>=abs(out[i,h,0]-ei)-1.e-12: ci[h]+=1
                if abs(sm-out[i,h,7])>=abs(out[i,h,6]-out[i,h,7])-1.e-10: cg[h]+=1
        for h in range(m):
            out[i,h,4]=(ci[h]+1)/(perms+1);out[i,h,5]=(cg[h]+1)/(perms+1)
    return out

def inference(df,nr,nc,scale,tag='main'):
    sel=np.flatnonzero(df['eligible'].to_numpy()); A=queen(nr,nc,sel)
    k=np.asarray(A.sum(axis=1)).ravel(); W=sparse.diags(np.divide(1,k,out=np.zeros_like(k),where=k>0))@A
    assert (A.diagonal()==0).all() and (A-A.T).nnz==0
    # Retain islands in files, mark local unavailable; global excludes no-neighbor units explicitly.
    df['neighbors']=0;df.loc[sel,'neighbors']=k.astype(int)
    x=df.loc[sel,[m+'_pct' for m in MET]].to_numpy(float); n=len(x)
    if n<4: return df
    mean=x.mean(axis=0);sd=x.std(axis=0);good=sd>1e-12
    z=np.divide(x-mean,sd,out=np.zeros_like(x),where=good)
    result=local_mc(x,z,A.indptr,A.indices,P,SEED+scale)
    lag=W@z
    # Global normal approximation follows random-normality variance, separate from permutation.
    s0=W.sum();s1=float((W+W.T).multiply(W+W.T).sum()/2);s2=float(np.square(np.asarray(W.sum(0)).ravel()+np.asarray(W.sum(1)).ravel()).sum())
    ei=-1/(n-1);v=(n*n*s1-n*s2+3*s0*s0)/((n*n-1)*s0*s0)-ei*ei
    denom=np.square(z).sum(axis=0); obs=n/s0*np.sum(z*lag,axis=0)/np.where(denom>0,denom,np.nan)
    rng=np.random.default_rng(SEED+scale);cnt=np.zeros(3,int)
    for _ in range(P):
        zp=z[rng.permutation(n)];ip=n/s0*np.sum(zp*(W@zp),axis=0)/np.where(denom>0,denom,np.nan)
        cnt+=abs(ip-ei)>=abs(obs-ei)-1e-14
    for h,m in enumerate(MET):
        for suffix in ['li','lp','lq','gi','gz','gp','gq','z','lag']:df[m+'_'+suffix]=np.nan
        for suffix in ['lc','gc']:df[m+'_'+suffix]=-1
        if not good[h]: continue
        lp=result[:,h,4];gp=result[:,h,5];lq=np.full(n,np.nan);gq=np.full(n,np.nan)
        ok=np.isfinite(lp); lq[ok]=multipletests(lp[ok],method='fdr_bh')[1]
        okg=np.isfinite(gp)&np.isfinite(result[:,h,3]);gq[okg]=multipletests(gp[okg],method='fdr_bh')[1]
        lc=np.where((z[:,h]>=0)&(lag[:,h]>=0),1,np.where((z[:,h]<0)&(lag[:,h]<0),2,np.where(z[:,h]>=0,3,4)))
        lc=np.where(np.isfinite(lq),np.where(lq<ALPHA,lc,0),-1)
        gc=np.where(np.isfinite(gq),np.where(gq<ALPHA,np.where(result[:,h,3]>0,1,2),0),-1)
        vals={'li':result[:,h,0],'lp':lp,'lq':lq,'gi':result[:,h,2],'gz':result[:,h,3],'gp':gp,'gq':gq,'lc':lc,'gc':gc,'z':z[:,h],'lag':lag[:,h]}
        for s,a in vals.items():df.loc[sel,m+'_'+s]=a
        zz=(obs[h]-ei)/math.sqrt(v) if v>0 else np.nan
        MOR.append(dict(scale_m=scale,edge_rule=tag,indicator=m,n=n,islands=int((k==0).sum()),I=obs[h],expected_I=ei,z_normal=zz,p_normal_2s=2*stats.norm.sf(abs(zz)),p_perm_2s=(cnt[h]+1)/(P+1),permutations=P,seed=SEED+scale))
        SCALE.append(dict(scale_m=scale,edge_rule=tag,indicator=m,n=n,HH=int((lc==1).sum()),LL=int((lc==2).sum()),HL=int((lc==3).sum()),LH=int((lc==4).sum()),hot=int((gc==1).sum()),cold=int((gc==2).sum()),unavailable=int((lc==-1).sum())))
        if tag=='main':
            f,ax=plt.subplots(figsize=(8,7));ax.scatter(z[:,h],lag[:,h],s=3,alpha=.35,color='#3f7b74');ax.axhline(0,c='grey',lw=.6);ax.axvline(0,c='grey',lw=.6)
            xx=np.array([z[:,h].min(),z[:,h].max()]);ax.plot(xx,obs[h]*xx,c='#c3534a');ax.set(xlabel='标准化面积占比 z',ylabel='不含自身的空间滞后 Wz',title=f'{CN[m]}｜{scale} m Moran 散点图\nI={obs[h]:.4f}; p置换(双侧)={(cnt[h]+1)/(P+1):.4f}; n={n}')
            f.tight_layout();savefig(f,f'Moran_{m}_{scale}')
    QA[f'weights_{scale}_{tag}']={'n':n,'islands':int((k==0).sum()),'symmetric_binary':True,'self_Moran':0,'self_Gistar':1,'order':'eligible dataframe order; GRID_ID exported','fdr_family':'indicator x scale x method x edge scenario','seed_local':'np.random.seed((seed+scale+local_index*1009)%2147483647) per unit','seed_global':'numpy default_rng(seed+scale)'}
    return df

FONT=str(ROOT/'scripts/fonts/NotoSansCJK-Regular.ttc')
if not Path(FONT).exists():FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
if Path(FONT).exists():
    matplotlib.font_manager.fontManager.addfont(FONT)
    plt.rcParams['font.family']=FontProperties(fname=FONT).get_name()
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

def export_vectors(df,geoms,scale,kind):
    g=gpd.GeoDataFrame(df.copy(),geometry=geoms,crs=CRS)
    layer=f'grid_{scale}_{kind}'
    g.to_file(ROOT/'data/results.gpkg',layer=layer,driver='GPKG')
    # Explicit, stable unique field map; no automatic DBF truncation.
    fmap={c:('GRID_ID' if c=='GRID_ID' else f'F{i:03d}') for i,c in enumerate(df.columns)}
    assert len(set(fmap.values()))==len(fmap) and max(map(len,fmap.values()))<=10
    FIELDS.extend([dict(layer=layer,full_field=c,shp_field=s,description=field_desc(c),null_policy='numeric NULL/-1 class; see eligible/status; zero is real',units=field_unit(c)) for c,s in fmap.items()])
    sg=g.rename(columns=fmap)
    sg.to_file(ROOT/'data'/f'{layer}.shp',driver='ESRI Shapefile',encoding='UTF-8')
    (ROOT/'data'/f'{layer}.cpg').write_text('UTF-8')
    back=gpd.read_file(ROOT/'data'/f'{layer}.shp');assert len(back)==len(g) and back.crs==g.crs
    assert set(back.columns)==set(sg.columns)
    assert np.allclose(back.total_bounds,g.total_bounds,atol=1e-7)
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]): assert np.allclose(back[fmap[c]].to_numpy(float),df[c].to_numpy(float),equal_nan=True,atol=1e-6)
    QA[layer]={'reread':True,'rows':len(back),'unique_short_fields':True,'crs':str(back.crs),'numeric_roundtrip_tolerance':1e-6}

def field_unit(c):
    return 'm²' if c.endswith('_m2') else '%' if c.endswith('_pct') else 'proportion' if c.endswith('_cov') or c.endswith('_frac') else 'dimensionless'
def field_desc(c):
    special={'GRID_ID':'稳定网格编号；尺度+由南向北行号+由西向东列号','row':'行号，0起始，南向北','col':'列号，0起始，西向东','eligible':'正式统计资格，1纳入、0排除','status':'OK/EDGE_SMALL/LOW_COVER/OUTSIDE；范围内缺失不作为真实零','edge_frac':'研究范围交集面积/完整方格面积','valid_cov':'有效分类面积/范围交集面积','scope_m2':'研究范围内面积','valid_m2':'有效分类面积','neighbors':'纳入统计子图内Queen邻居数'}
    suf={'li':'局部Moran I','lp':'局部Moran双侧条件置换p','lq':'局部Moran BH校正q','lc':'LISA：-1无法计算，0不显著，1HH，2LL，3HL，4LH','gi':'Gi*，含自身一次的二值邻域和/全域指标和','gz':'Gi*条件零分布标准化值；方向判据','gp':'Gi*双侧条件置换p','gq':'Gi* BH校正q','gc':'热点：-1无法计算，0不显著，1热点，2冷点','z':'指标全域标准化值','lag':'行标准化Queen空间滞后，不含自身'}
    if c in special:return special[c]
    for m in ['blue_green','wetland','green','blue']:
        if c.startswith(m+'_'):
            s=c[len(m)+1:];return CN[m]+' '+suf.get(s,{'pct':'有效面积占比','m2':'面积'}.get(s,s))
    return c

def run():
    global CRS,COVER_EXTENT
    inp=Path(C['input_tiff']); inp=inp if inp.is_absolute() else ROOT/inp
    print('Reading',inp,flush=True)
    with rasterio.open(inp) as src:
        CRS=src.crs;profile=src.profile;H,W=src.height,src.width;t=src.transform
        assert src.count==3 and t.b==0 and t.d==0 and t.a>0 and t.e<0
        left,bottom,right,top=src.bounds;dx,dy=src.res;area=dx*dy
        extent=[left,right,bottom,top];COVER_EXTENT=extent
        cl=np.zeros((H,W),np.uint8);source_counts=np.zeros(9,np.int64);unknown={};valid_count=0
        rgb={tuple(v):int(k) for k,v in C['rgb_mapping'].items()}
        for _,win in src.block_windows(1):
            rgbdata=src.read(window=win);mask=np.all(src.read_masks(window=win)>0,axis=0);valid_count+=int(mask.sum())
            block=np.zeros(mask.shape,np.uint8)
            for color,i in rgb.items():
                hit=mask&np.all(rgbdata==np.array(color)[:,None,None],axis=0);block[hit]=i;source_counts[i]+=hit.sum()
            bad=mask&(block==0)
            if bad.any():
                u,cnt=np.unique(rgbdata[:,bad].T,axis=0,return_counts=True)
                for a,n in zip(u,cnt):unknown[str(a.tolist())]=unknown.get(str(a.tolist()),0)+int(n)
            r,c=int(win.row_off),int(win.col_off);cl[r:r+block.shape[0],c:c+block.shape[1]]=block
        save_json(ROOT/'qa/unknown_rgb.json',unknown)
        if unknown:raise ValueError('Unknown RGB present; stop rather than silently reclassify')
        assert int(source_counts.sum())==valid_count
        raster_write(ROOT/'data/classification.tif',cl,profile,0)
        with rasterio.open(ROOT/'data/classification.tif','r+') as d:d.write_colormap(1,{i:tuple(int(COLORS[i].lstrip('#')[j:j+2],16) for j in (0,2,4)) for i in range(9)})
        valid=cl>0
        for m,ids in C['groups'].items():raster_write(ROOT/'data'/f'{m}_mask.tif',np.where(valid,np.isin(cl,ids),255),profile,255)
        types=np.where(np.isin(cl,C['groups']['blue_green']),cl,0).astype('uint8');types[~valid]=255
        raster_write(ROOT/'data/blue_green_types.tif',types,profile,255)
        scope=gpd.GeoDataFrame({'NAME':['影像覆盖区'],'AREA_M2':[(right-left)*(top-bottom)]},geometry=[box(left,bottom,right,top)],crs=CRS)
        scope.to_file(ROOT/'data/scope.shp',encoding='UTF-8');scope.to_file(ROOT/'data/results.gpkg',layer='scope',driver='GPKG')
        if valid.all(): vg=scope.copy()
        else:
            from rasterio.features import shapes
            from shapely.geometry import shape
            vg=gpd.GeoDataFrame(geometry=[shape(g) for g,v in shapes(valid.astype('uint8'),mask=valid,transform=t) if v==1],crs=CRS).dissolve()
        vg.to_file(ROOT/'data/valid_scope.shp',encoding='UTF-8');vg.to_file(ROOT/'data/results.gpkg',layer='valid_scope',driver='GPKG')
        rows=[]
        for i in range(1,9):
            recovered=int((cl==i).sum());assert recovered==source_counts[i]
            rows.append(dict(CLASS_ID=i,SRC_NAME=C['source_names'][str(i)],DISPLAY_NAME=NAMES[i],before_pixels=int(source_counts[i]),after_pixels=recovered,pixel_difference=0,area_m2=recovered*area,area_km2=recovered*area/1e6,percent=recovered/valid_count*100))
        table=pd.DataFrame(rows);csvout(table,ROOT/'tables/class_area_conservation.csv')
        groups={m:sum(source_counts[i] for i in ids)*area for m,ids in C['groups'].items()}
        assert groups['blue_green']==groups['blue']+groups['green']+groups['wetland']
        csvout(pd.DataFrame([{'type':m,'area_km2':a/1e6,'percent':a/(valid_count*area)*100} for m,a in groups.items()]),ROOT/'tables/group_areas.csv')
        QA['classification']={'pixels':valid_count,'unknown_pixels':0,'nodata_pixels':int((~valid).sum()),'class_area_m2':valid_count*area,'blue_green_union_m2':groups['blue_green'],'disjoint_group_sum_m2':groups['blue']+groups['green']+groups['wetland'],'no_cleaning':True,'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest()}
        mapfig('01_土地利用分类图','武汉地区蓝绿空间研究｜土地利用分类对应图',cl,extent,COLORS,NAMES,note='依据用地用海分类体系对应整理\n非土地调查法定成果\n原始类别精确恢复，未清理或平滑\n标准最新现行性尚未在线核实')
        for name,m in [('02_蓝色空间分布图','blue'),('04_绿色空间分布图','green'),('06_蓝绿空间整体分布图','blue_green'),('14_湿地分布图','wetland')]:
            if m=='blue_green':
                showids=[0,1,3,4,5,6,8];display=np.zeros_like(types)
                for j,i in enumerate(showids):display[types==i]=j
                display=np.where(valid,display,np.nan)
                mapfig(name,'武汉地区蓝绿空间研究｜'+CN[m]+'分布',display,extent,[COLORS[i] for i in showids],['非蓝绿空间']+[NAMES[i] for i in showids[1:]],note='蓝绿整体：水体、耕地、林地、草地、湿地\n排除建设用地与裸地\n湿地独立保留，不重复分配')
            else:
                arr=np.where(valid,np.isin(cl,C['groups'][m]),np.nan)
                mapfig(name,'武汉地区蓝绿空间研究｜'+CN[m]+'分布',arr,extent,['#f1f0ed',{'blue':'#3182bd','green':'#71a35a','wetland':'#55b6a2'}[m]],['有效范围内非目标类别',CN[m]],note='二值目标分布\n绿色空间包含耕地\n湿地独立纳入蓝绿整体')
        for scale in C['grid_sizes_m']:
            print('Grid',scale,flush=True);OX=overlap(W,dx,scale);OY=overlap(H,dy,scale);nr,nc=OY.shape[0],OX.shape[0]
            areas=np.zeros((nr,nc,9));
            # Block on raster rows; allocate all boundary pixels by exact overlap lengths.
            for y0 in range(0,H,256):
                y1=min(H,y0+256);data=cl[H-y1:H-y0][::-1];yy=OY[:,y0:y1]
                for i in range(1,9): areas[:,:,i]+=yy@((OX@(data==i).T).T)
            full=[box(left+c*scale,bottom+r*scale,left+(c+1)*scale,bottom+(r+1)*scale) for r in range(nr) for c in range(nc)]
            clipped=[g.intersection(scope.geometry.iloc[0]) for g in full]
            total=areas.sum(2).ravel();scopearea=np.array([g.area for g in clipped]);edge=scopearea/scale**2;cover=np.divide(total,scopearea,out=np.zeros_like(total),where=scopearea>0)
            df=pd.DataFrame({'GRID_ID':[f'S{scale}_R{r:03d}C{c:03d}' for r in range(nr) for c in range(nc)],'row':np.repeat(np.arange(nr),nc),'col':np.tile(np.arange(nc),nr),'scope_m2':scopearea,'valid_m2':total,'valid_cov':cover,'edge_frac':edge})
            for m,ids in C['groups'].items():
                df[m+'_m2']=areas[:,:,ids].sum(2).ravel();df[m+'_pct']=np.divide(df[m+'_m2'],total,out=np.full_like(total,np.nan),where=total>0)*100
                assert np.allclose(df[m+'_m2'].sum(),groups[m],rtol=1e-12,atol=.001)
                a=df[m+'_pct'].to_numpy();assert np.all((a[np.isfinite(a)]>=-1e-10)&(a[np.isfinite(a)]<=100+1e-10))
                tr=from_origin(left,bottom+nr*scale,scale,scale)
                raster_write(ROOT/'data'/f'{m}_density_{scale}.tif',np.nan_to_num(a.reshape(nr,nc)[::-1],nan=-9999),profile,-9999,'float32',tr)
            assert abs(total.sum()-valid_count*area)<.001
            QA[f'area_{scale}']={'raster_valid_m2':valid_count*area,'grid_valid_m2':total.sum(),'absolute_error_m2':abs(total.sum()-valid_count*area),'tolerance_m2':.001,'method':'separable sparse pixel-grid overlap; block rows 256','all_percent_0_100':True}
            base=df.copy();df['eligible']=((cover>=C['valid_coverage_threshold'])&(edge>=C['edge_min_fraction'])&(total>0)).astype(int)
            df['status']=np.where(cover<C['valid_coverage_threshold'],'LOW_COVER',np.where(edge<C['edge_min_fraction'],'EDGE_SMALL','OK'))
            df=inference(df,nr,nc,scale)
            csvout(df,ROOT/'tables'/f'grid_{scale}.csv');export_vectors(df,full,scale,'full');export_vectors(df,clipped,scale,'clip')
            # Predeclared edge sensitivity with the same inference, no significance-driven selection.
            for threshold in C['edge_sensitivity_min_fractions']:
                alt=base.copy();alt['eligible']=((cover>=C['valid_coverage_threshold'])&(edge>=threshold)&(total>0)).astype(int)
                alt=inference(alt,nr,nc,scale,f'edge_{threshold}');csvout(alt,ROOT/'tables'/f'edge_sensitivity_{scale}_{threshold}.csv')
            gextent=[left,left+nc*scale,bottom,bottom+nr*scale]
            # Clip plotted extent to the input footprint; retain complete cells as separate data.
            for h,m in enumerate(MET):
                num={'blue':'03','green':'05','blue_green':'07'}[m]
                breaks=list(C['density_breaks_percent']);breaks[-1]+=1e-5
                arr=df[m+'_pct'].to_numpy().reshape(nr,nc)[::-1];idx=np.digitize(arr,breaks,right=False);idx=np.where(arr==0,0,idx)
                idx=np.where(np.isfinite(arr),idx,np.nan)
                cmap=['#f7f7f7','#e2f0d9','#b8d9ba','#7fb6aa','#3b8d95','#145569']
                mapfig(num+'_'+m+f'_密度_{scale}m',CN[m]+f'面积占比｜{scale} m 网格',idx,gextent,cmap,['0%','>0–<10%','10–<25%','25–<50%','50–<75%','75–100%'],note='密度＝目标面积÷有效分类面积\n按像元—网格精确面积加权\n灰色缺失与白色真实零值分开\n边缘格用实际有效面积作分母')
                for stat,code,colors,labels in [('lc',str(8+h).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3','#e8a06a','#9a91bf'],['无法计算／未纳入','不显著','高—高 HH','低—低 LL','高—低 HL','低—高 LH']),('gc',str(11+h).zfill(2),['#dadada','#f7f7f7','#c44343','#467db3'],['无法计算／未纳入','不显著','显著热点','显著冷点'])]:
                    a=df[m+'_'+stat].to_numpy().reshape(nr,nc)[::-1]+1
                    title=CN[m]+(' LISA' if stat=='lc' else ' Gi* 热点')+f'｜{scale} m'
                    mapfig(code+'_'+m+'_'+stat+f'_{scale}m',title,a,gextent,colors,labels,note='主图显著性：BH-FDR q < 0.05\n双侧条件置换，9999 次\nQueen邻域；固定随机种子\n主规则：有效覆盖≥95%\n边缘覆盖比例≥25%\n空间集聚不等于生态质量')
    csvout(pd.DataFrame(MOR),ROOT/'tables/global_moran.csv');csvout(pd.DataFrame(SCALE),ROOT/'tables/scale_edge_comparison.csv');csvout(pd.DataFrame(FIELDS),ROOT/'methods/field_dictionary.csv')
    # Formal A3 supplementary tables/charts.
    f,ax=plt.subplots(figsize=(16.535,11.693));ax.barh(table.DISPLAY_NAME,table.area_km2,color=COLORS[1:]);ax.set_xlabel('面积 / km²');ax.set_title('分类面积与占比｜分析范围为输入影像覆盖区；数据年份待补充',fontsize=19)
    for i,r in table.iterrows():ax.text(r.area_km2+10,i,f'{r.area_km2:.2f} km² / {r.percent:.2f}%',va='center')
    ax.set_xlim(0,table.area_km2.max()*1.35);f.tight_layout();savefig(f,'15_分类面积比例')
    f,axes=plt.subplots(1,3,figsize=(16.535,11.693));st=pd.DataFrame(SCALE);mo=pd.DataFrame(MOR)
    for i,m in enumerate(MET):
        v=mo[(mo.indicator==m)&(mo.edge_rule=='main')];axes[i].plot(v.scale_m,v.I,'o-',color='#367d78');axes[i].set(title=CN[m],xlabel='网格尺度 / m',ylabel="全局 Moran's I");axes[i].grid(alpha=.2)
    f.suptitle('尺度比较｜500 m、1 km、2 km｜主尺度预先指定为1 km',fontsize=20);f.tight_layout();savefig(f,'16_尺度比较')
    for p in (ROOT/'data').glob('*.tif'):
        with rasterio.open(p) as d:
            assert d.crs==CRS
            for _,win in d.block_windows(1):d.read(1,window=win)
            QA['read_'+p.name]={'shape':d.shape,'crs':str(d.crs),'nodata':d.nodata,'compression':str(d.compression),'read_all_blocks':True}
    from PIL import Image
    for name in MAPS:
        p=ROOT/'maps'/f'{name}.png'
        with Image.open(p) as im: im.verify()
    save_json(ROOT/'qa/validation.json',QA);save_json(ROOT/'qa/map_manifest.json',MAPS)
    print('COMPLETE',len(MAPS),'map pairs',flush=True)

if __name__=='__main__':raise SystemExit('Use run_study.py for the user study boundary')
