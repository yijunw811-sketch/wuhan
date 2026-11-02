# -*- coding: utf-8 -*-
"""Run only in ArcGIS Desktop 10.5 Python 2.7; requires a real blank MXD."""
from __future__ import print_function
import os,sys,csv,codecs,argparse
import arcpy

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True,help='Extracted result folder')
    p.add_argument('--template',required=True,help='Existing valid blank MXD template')
    p.add_argument('--out',required=True,help='Writable local output directory')
    p.add_argument('--symbology',default=None,help='Optional genuine raster .lyr supplied by user')
    args=p.parse_args()
    if not os.path.isfile(args.template):raise RuntimeError('Valid blank MXD template required')
    if not os.path.isdir(args.out):os.makedirs(args.out)
    arcpy.env.overwriteOutput=True
    gdb=os.path.join(args.out,'wuhan_results.gdb')
    if not arcpy.Exists(gdb):arcpy.CreateFileGDB_management(args.out,'wuhan_results.gdb')
    aliases={}
    with open(os.path.join(args.root,'methods','field_dictionary.csv'),'rb') as f:
        if sys.version_info[0]<3:
            f.read(3)
            for row in csv.DictReader(f):aliases.setdefault(row['layer'],{})[row['shp_field']]=row['description'].decode('utf-8')
        else:
            for row in csv.DictReader(codecs.iterdecode(f,'utf-8-sig')):aliases.setdefault(row['layer'],{})[row['shp_field']]=row['description']
    mxd=arcpy.mapping.MapDocument(args.template)
    frames=arcpy.mapping.ListDataFrames(mxd)
    if not frames:raise RuntimeError('Template must have a data frame')
    frame=frames[0]
    for filename in sorted(os.listdir(os.path.join(args.root,'data'))):
        src=os.path.join(args.root,'data',filename);base=os.path.splitext(filename)[0]
        if filename.lower().endswith('.shp'):
            dst=os.path.join(gdb,base);arcpy.CopyFeatures_management(src,dst)
            for fld in arcpy.ListFields(dst):
                if fld.name in aliases.get(base,{}):arcpy.AlterField_management(dst,fld.name,new_field_alias=aliases[base][fld.name])
            if base in ['grid_1000_clip','scope']:arcpy.mapping.AddLayer(frame,arcpy.mapping.Layer(dst),'BOTTOM')
        elif filename.lower().endswith('.tif'):
            arcpy.CopyRaster_management(src,os.path.join(gdb,base))
            if base in ['classification','blue_green_density_1000_aligned15m']:
                temp='r_'+base;arcpy.MakeRasterLayer_management(os.path.join(gdb,base),temp);lyr=arcpy.mapping.Layer(temp)
                if args.symbology:arcpy.ApplySymbologyFromLayer_management(lyr,args.symbology)
                arcpy.mapping.AddLayer(frame,lyr,'BOTTOM')
    scope=os.path.join(gdb,'scope')
    if arcpy.Exists(scope):frame.extent=arcpy.Describe(scope).extent
    mxd.saveACopy(os.path.join(args.out,'wuhan_overview.mxd'))
    del mxd
    print('Local import completed. Check class labels, NULL values and styles in ArcMap.')

if __name__=='__main__':main()
