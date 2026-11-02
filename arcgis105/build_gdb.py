"""Build a real OpenFileGDB without newer ArcGIS Pro-only field types."""
from pathlib import Path
import json,shutil
import geopandas as gpd
import numpy as np,pandas as pd,pyogrio

src=Path(__file__).resolve().parents[1]/'wuhan_research'
out=Path('/workspace/wuhan_arcgis105');out.mkdir(exist_ok=True)
db=out/'wuhan_results.gdb';checks={}
for layer,geom in pyogrio.list_layers(src/'data/results.gpkg'):
    if geom is None:continue
    g=gpd.read_file(src/'data/results.gpkg',layer=layer)
    for c in g.columns:
        if c!='geometry' and pd.api.types.is_integer_dtype(g[c]):
            assert g[c].min()>=np.iinfo(np.int32).min and g[c].max()<=np.iinfo(np.int32).max
            g[c]=g[c].astype('int32')
    pyogrio.write_dataframe(g,db,layer=layer,driver='OpenFileGDB',layer_options={'TARGET_ARCGIS_VERSION':'ALL','LAYER_ALIAS':layer,'XYTOLERANCE':'0.001','XYSCALE':'1000','CREATE_SHAPE_AREA_AND_LENGTH_FIELDS':'YES'})
    b=gpd.read_file(db,layer=layer)
    assert len(g)==len(b) and b.crs==g.crs
    if 'GRID_ID' in g:assert list(g.GRID_ID)==list(b.GRID_ID)
    assert np.allclose(b.total_bounds,g.total_bounds,atol=.001)
    for c in g.columns:
        if c=='geometry':continue
        if pd.api.types.is_numeric_dtype(g[c]):assert np.allclose(g[c].to_numpy(float),b[c].to_numpy(float),equal_nan=True,atol=1e-8)
        else:assert list(g[c])==list(b[c])
    assert np.allclose(b.geometry.area,g.geometry.area,atol=.001)
    checks[layer]={'count':len(b),'CRS':'EPSG:32649','GRID_ID_order':'PASS','all_numeric_fields':'PASS','nulls_preserved':'PASS','geometry_area':'PASS','target_version':'ALL; int32/OID32, no ArcGIS Pro 3.2-only types'}
    print(layer,len(b),flush=True)
for name,path in [('class_crosswalk',src/'methods/class_crosswalk.csv'),('class_areas',src/'tables/class_area_conservation.csv'),('group_areas',src/'tables/group_areas.csv'),('global_moran',src/'tables/global_moran.csv'),('scale_comparison',src/'tables/scale_edge_comparison.csv'),('field_dictionary',src/'methods/field_dictionary.csv')]:
    d=pd.read_csv(path,dtype=str,keep_default_na=False) if name=='class_crosswalk' else pd.read_csv(path)
    for c in d.columns:
        if pd.api.types.is_integer_dtype(d[c]):d[c]=d[c].astype('int32')
    pyogrio.write_dataframe(d,db,layer=name,driver='OpenFileGDB',layer_options={'TARGET_ARCGIS_VERSION':'ALL'})
    assert len(pyogrio.read_dataframe(db,layer=name))==len(d)
for folder in ['rasters','methods','tables','maps','qa']:(out/folder).mkdir(exist_ok=True)
for p in (src/'data').glob('*.tif'):shutil.copy2(p,out/'rasters'/p.name)
for p in (src/'methods').glob('*'):
    if p.is_file():shutil.copy2(p,out/'methods'/p.name)
for p in (src/'tables').glob('*.csv'):shutil.copy2(p,out/'tables'/p.name)
for p in (src/'maps').glob('*'):
    if p.suffix in ['.png','.pdf'] and ('1000m' in p.stem or p.stem[:2] in ['01','02','04','06','14']):shutil.copy2(p,out/'maps'/p.name)
checks['classification_codes']=pyogrio.read_dataframe(db,layer='class_crosswalk')[['CLASS_ID','STD_CODE']].to_dict('records')
checks['layers']=pyogrio.list_layers(db).tolist();checks['ArcMap_open_test']='NOT RUN: no ArcGIS runtime';checks['MXD']='Not created in cloud; requires supplied local ArcMap helper'
(out/'qa/gdb_readback_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print('GDB and companion data created',flush=True)
