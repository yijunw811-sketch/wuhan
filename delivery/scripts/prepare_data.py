"""Recreate client-format data copies from the verified current study outputs."""
from pathlib import Path
import shutil,pandas as pd,pyogrio,geopandas as gpd
from shapely.geometry import box
ROOT=Path('/workspace/client_delivery');Q=ROOT/'QGIS';A=ROOT/'ArcMap105';S=Path('/workspace/wuhan_study');K=Path('/workspace/wuhan_study_kde')
for folder in [Q,A/'Data',A/'Views',A/'Documents',A/'Tables',A/'Scripts']:folder.mkdir(parents=True,exist_ok=True)
shutil.copy2(S/'data/results.gpkg',Q/'project_data.gpkg');shutil.copytree(S/'data/wuhan_results.gdb',A/'Data/Wuhan_Study.gdb',dirs_exist_ok=True)
for prefix,source in [('land',S/'data'),('kde',K/'data')]:
    for f in source.glob('*.tif'):
        if not f.name.startswith('display_'):shutil.copy2(f,A/'Data'/f'{prefix}_{f.name}')
for f in (S/'tables').glob('*.csv'):shutil.copy2(f,A/'Tables'/f.name)
shutil.copy2(K/'tables/kde_surface_statistics.csv',A/'Tables/kde_surface_statistics.csv')
for f in (S/'methods').glob('*'):
    if f.is_file():shutil.copy2(f,A/'Documents'/f.name)
for name in ['validation.json','coordinate_operation.json','output_readback_checks.json']:shutil.copy2(S/'qa'/name,A/'Documents'/name)
shutil.copy2(K/'qa/kde_validation.json',A/'Documents/kde_validation.json');shutil.copy2(S/'main_preview.jpg',A/'Documents/main_preview.jpg')
for f in list((S/'maps').glob('01_*.pdf'))+[K/'maps'/f'KDE_{m}_h1000_edge_corrected.pdf' for m in ['blue','green','blue_green']]:shutil.copy2(f,A/'Documents'/f.name)
for f in list((S/'tables').glob('*.csv'))+[K/'tables/kde_surface_statistics.csv',S/'methods/class_crosswalk.csv',S/'methods/field_dictionary.csv']:
    df=pd.read_csv(f,dtype=str,keep_default_na=False) if f.stem=='class_crosswalk' else pd.read_csv(f)
    if f.stem=='class_crosswalk':
        for field in ['SRC_ID','CLASS_ID']:df[field]=df[field].astype('int32')
    pyogrio.write_dataframe(df,Q/'project_data.gpkg',layer=f.stem,driver='GPKG')
roi=gpd.read_file(S/'data/results.gpkg',layer='scope').geometry.iloc[0]
frame=box(roi.bounds[0]-2000,roi.bounds[1]-2000,roi.bounds[2]+2000,roi.bounds[3]+2000)
gpd.GeoDataFrame({'ROLE':['Display mask only; not land use']},geometry=[frame.difference(roi)],crs=32649).to_file(Q/'project_data.gpkg',layer='display_mask',driver='GPKG')
df=pyogrio.read_dataframe(A/'Data/Wuhan_Study.gdb',layer='class_crosswalk')
for field in ['SRC_ID','CLASS_ID']:df[field]=df[field].astype('int32')
pyogrio.write_dataframe(df,A/'Data/Wuhan_Study.gdb',layer='class_crosswalk',driver='OpenFileGDB',layer_options={'TARGET_ARCGIS_VERSION':'ALL'})
print('Prepared client data; integer IDs and text standard codes preserved')
