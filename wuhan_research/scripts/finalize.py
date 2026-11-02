"""Independent output readback, inference checks, summary, manifest and archive."""
import json,sys,hashlib,zipfile,shutil
from pathlib import Path
import numpy as np,pandas as pd,rasterio,geopandas as gpd,pyogrio
from statsmodels.stats.multitest import multipletests
from PIL import Image
import fitz

r=Path(__file__).resolve().parents[1];qa={};met=['blue','green','blue_green']
area=pd.read_csv(r/'tables/class_area_conservation.csv');groups=pd.read_csv(r/'tables/group_areas.csv');mor=pd.read_csv(r/'tables/global_moran.csv');comp=pd.read_csv(r/'tables/scale_edge_comparison.csv')
assert (area.pixel_difference==0).all()
assert abs(groups.set_index('type').loc['blue_green','area_km2']-groups.query("type!='blue_green'").area_km2.sum())<1e-8
for scale in [500,1000,2000]:
 d=pd.read_csv(r/'tables'/f'grid_{scale}.csv');assert d.GRID_ID.is_unique
 for m in met:
  assert d[m+'_pct'].dropna().between(0,100+1e-9).all()
  for method in ['l','g']:
   p=d[m+'_'+method+'p'].to_numpy();q=d[m+'_'+method+'q'].to_numpy();ok=np.isfinite(q)
   assert np.allclose(q[ok],multipletests(p[ok],method='fdr_bh')[1],atol=1e-12)
   c=d[m+'_'+method+'c'].to_numpy();assert np.all((c[ok]>0)==(q[ok]<.05))
   assert np.all(c[~ok]==-1)
  ell=d.eligible.to_numpy()==1;z=d[m+'_z'].to_numpy();lag=d[m+'_lag'].to_numpy();lc=d[m+'_lc'].to_numpy()
  assert np.all((z[lc==1]>=0)&(lag[lc==1]>=0));assert np.all((z[lc==2]<0)&(lag[lc==2]<0));assert np.all((z[lc==3]>=0)&(lag[lc==3]<0));assert np.all((z[lc==4]<0)&(lag[lc==4]>=0))
  gz=d[m+'_gz'].to_numpy();gc=d[m+'_gc'].to_numpy();assert np.all(gz[gc==1]>0) and np.all(gz[gc==2]<0)
 qa[str(scale)]={'rows':len(d),'eligible':int(d.eligible.sum()),'excluded':int((d.eligible==0).sum()),'FDR_and_legend_recomputed':'PASS','isolated':int(((d.eligible==1)&(d.neighbors==0)).sum())}
 for kind in ['full','clip']:
  p=r/'data'/f'grid_{scale}_{kind}.shp'
  for ext in ['.shp','.shx','.dbf','.prj','.cpg']:assert p.with_suffix(ext).exists()
  g=gpd.read_file(p);assert list(g.GRID_ID)==list(d.GRID_ID);assert all(len(c)<=10 for c in g.columns if c!='geometry')
  assert g.crs.to_epsg()==32649 and g.geometry.is_valid.all()
  if kind=='clip':assert abs(g.geometry.area.sum()-area.area_m2.sum())<.001
for layer,geom in pyogrio.list_layers(r/'data/results.gpkg'):
 g=gpd.read_file(r/'data/results.gpkg',layer=layer);assert len(g)>0
 if geom is not None:assert g.crs.to_epsg()==32649
 else:assert g.loc[g.CLASS_ID=='3','STD_CODE'].iloc[0]=='01'
qa['GPKG_layers']=pyogrio.list_layers(r/'data/results.gpkg').tolist()
for p in (r/'data').glob('*.tif'):
 with rasterio.open(p) as d:
  assert d.crs.to_epsg()==32649
  for _,w in d.block_windows(1):d.read(1,window=w)
qa['all_raster_blocks_read']=True
maps=[]
for p in sorted((r/'maps').glob('*.png')):
 with Image.open(p) as im:
  size=im.size;assert abs(size[0]-4960)<=2 and abs(size[1]-3507)<=2
  assert all(abs(x-300)<.1 for x in im.info.get('dpi',(0,0)))
  im.verify()
 with fitz.open(p.with_suffix('.pdf')) as doc:
  assert len(doc)==1;page=doc[0]
  assert abs(page.rect.width-1190.52)<1 and abs(page.rect.height-841.896)<1
  assert page.get_text().strip() and page.get_fonts()
  pix=page.get_pixmap(matrix=fitz.Matrix(.25,.25));assert pix.width>0
 maps.append({'name':p.stem,'PNG_size':size,'PDF_parsed_and_rendered':True,'A3_landscape_300DPI':True})
qa['maps']=maps;qa['ArcMap105_open_test']='NOT RUN: ArcGIS unavailable';qa['standard_currentness']='NOT VERIFIED ONLINE: official portal denied by network policy';qa['independent_accuracy']='NOT AVAILABLE: no validation samples'
(r/'qa/final_output_checks.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2))
# Supersede initial blocked input audit rather than leave contradictory status.
audit=json.loads((r/'qa/input_audit.json').read_text());audit.update(tiff_available=True,tiff_transferred_via='RAR attachment 5558934 bytes; decompressed unchanged',analysis_executed=True,prior_direct_tiff_transfer_error='32 MiB transfer limit; resolved using user RAR')
audit.pop('tiff_transfer_error',None);(r/'qa/input_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
(r/'qa/STATUS.txt').write_text('实际RGB恢复、三尺度精确面积统计、全局Moran、LISA、Gi*、BH-FDR、边缘敏感性、43组PNG/PDF及输出回读检查已完成。\n官方分类标准最新现行性未在线核实。ArcMap本机打开验证未执行。独立分类精度无法验证。\n',encoding='utf-8')
main=mor.query("scale_m==1000 and edge_rule=='main'")
lines=['# 武汉地区蓝绿空间研究：结果摘要','','分析范围为输入影像覆盖区，非武汉市都市区正式规划边界。数据年份待补充。','',f'总有效面积：{area.area_km2.sum():.6f} km²；20,708,352个有效像元，无未知颜色、无NoData。原始输入未修改，未清理分类。','','## 各类面积','', '| 原类别／显示类别 | 面积 km² | 占比 % |','|---|---:|---:|']
for _,v in area.iterrows():lines.append(f'| {v.DISPLAY_NAME} | {v.area_km2:.6f} | {v.percent:.4f} |')
lines+=['','## 蓝绿口径','']
for _,v in groups.iterrows():lines.append(f'- {v.type}：{v.area_km2:.6f} km²，{v.percent:.4f}%。')
lines+=['','蓝绿整体＝蓝色＋广义绿色（含耕地）＋独立湿地；没有重复分配。','','## 主尺度空间统计','','1km；Queen邻接，Moran行标准化且不含自身，Gi*另设二值Queen及自身权重1一次；9999次置换。局部主图按指标×尺度×统计方法独立BH-FDR，q<0.05。全局双侧置换p与解析p分列。']
for _,v in main.iterrows():lines.append(f'- {v.indicator}：全局I={v.I:.6f}，双侧置换p={v.p_perm_2s:.4f}，n={int(v.n)}。')
lines+=['','三个尺度均呈显著正空间自相关；蓝色空间I随尺度增大减小，绿色及蓝绿整体也存在尺度变化。地图显示蓝色高值集聚沿影像中部弯曲河流类水体及部分较大湖泊类斑块分布；广义绿色、蓝绿整体较高占比主要在影像外围，较低占比集中于中部建设用地较集中的地带。这里使用影像相对位置，不虚构行政边界或地名。','', '1km局部显著单元计数：']
for _,v in comp.query("scale_m==1000 and edge_rule=='main'").iterrows():lines.append(f'- {v.indicator}：HH {v.HH}、LL {v.LL}、HL {v.HL}、LH {v.LH}；Gi*热点 {v.hot}、冷点 {v.cold}。')
lines+=['','蓝色指标在当前双侧条件置换及BH规则下未检出显著冷点；这不表示不存在低蓝色面积占比区域。条件Gi*的标准化值及方向判据不是ArcGIS默认无条件解析Z，详见方法。空间集聚不直接表示生态质量、生态服务或发展潜力。','','## 标准与限制','','按已知正式文件《国土空间调查、规划、用途管制用地用海分类指南》（自然资发〔2023〕234号）对应整理；**最新现行性尚未在线核实**，官方门户访问被网络策略403拒绝。耕地/林地/草地/湿地只对应一级；建设、裸地及水体语义不能唯一确认处不赋唯一STD_CODE。无独立验证样本，不能给出分类精度；15m不等于分类准确率达到15m。','','已重读GeoTIFF、Shapefile及GeoPackage；所有地图PNG验证、PDF解析渲染完成。ArcMap10.5脚本未在云端运行，未声称通过ArcMap打开验证。','','## 下载后复现','','解压完整成果包，保留目录结构，执行：','','```bash','bash scripts/run.sh','```','','Python3.12及开源依赖版本见scripts/requirements.txt和environment_versions.json。当前云环境复用/workspace/wuhan_python；其他机器建立本地.venv并安装固定版本。需能下载依赖；不依赖ArcGIS或付费API。参数在config/analysis.json。输入影像已随包保留。全过程约数分钟至十余分钟，视机器和制图速度而定。','', '主图请选择文件名含1000m的密度、LISA、热点图；500m/2000m为敏感性，非按显著单元更多选定。完整网格full与裁剪网格clip、字段字典及完整CSV可通过GRID_ID连接。']
(r/'methods/results_summary.md').write_text('\n'.join(lines),encoding='utf-8')
(r/'README.md').write_text('\n'.join(lines),encoding='utf-8')
# Record hash of every delivered file; omit transient Python/font caches.
def deliver(p):return p.is_file() and not any(x in p.parts for x in ['.mplconfig','__pycache__','.venv']) and p.name!='file_manifest.csv'
import csv
files=sorted(p for p in r.rglob('*') if deliver(p))
with (r/'qa/file_manifest.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['relative_path','bytes','sha256'])
 for p in files:w.writerow([str(p.relative_to(r)),p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()])
out=r.parent/'wuhan_research_complete.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(r.rglob('*')):
  if deliver(p):z.write(p,arcname='wuhan_research/'+str(p.relative_to(r)))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print('VERIFIED',len(maps),'map pairs;',out,'bytes',out.stat().st_size)
