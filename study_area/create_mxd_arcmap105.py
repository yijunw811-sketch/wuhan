# -*- coding: utf-8 -*-
"""Real MXD creation: run in ArcMap 10.5 Python 2.7, not cloud Python."""
from __future__ import print_function
import os,sys,csv,argparse

def create_mxd(root,template='CURRENT',output=None,styles=None):
    import arcpy
    arcpy.env.overwriteOutput=True
    root=os.path.abspath(root)
    gdb=os.path.join(root,'data','wuhan_results.gdb')
    if not arcpy.Exists(gdb):raise RuntimeError('Real wuhan_results.gdb was not found')
    if template!='CURRENT' and not os.path.isfile(template):raise RuntimeError('Provide an existing blank MXD or run with CURRENT inside ArcMap')
    if output is None:output=os.path.join(root,'project','wuhan_overview.mxd')
    if not os.path.isdir(os.path.dirname(output)):os.makedirs(os.path.dirname(output))
    mxd=arcpy.mapping.MapDocument(template)
    frames=arcpy.mapping.ListDataFrames(mxd)
    if not frames:raise RuntimeError('The MXD template needs at least one data frame')
    frame=frames[0];frame.name=u'武汉地区蓝绿空间研究';frame.spatialReference=arcpy.SpatialReference(32649)
    mxd.relativePaths=True
    # Restore descriptive aliases using full GDB field names, not short DBF names.
    aliases={};dictionary=os.path.join(root,'methods','field_dictionary.csv')
    with open(dictionary,'rb') as f:
        f.read(3)
        for row in csv.DictReader(f):aliases.setdefault(row['layer'],{})[row['full_field']]=row['description'].decode('utf-8')
    for scale in [500,1000,2000]:
        for kind in ['full','clip']:
            name='grid_{0}_{1}'.format(scale,kind);fc=os.path.join(gdb,name)
            for fld in arcpy.ListFields(fc):
                if fld.name in aliases.get(name,{}):arcpy.AlterField_management(fc,fld.name,new_field_alias=aliases[name][fld.name])
            lyr=arcpy.mapping.Layer(fc);lyr.name=name;lyr.visible=False
            arcpy.mapping.AddLayer(frame,lyr,'BOTTOM')
    fc=os.path.join(gdb,'grid_1000_clip')
    # These are editable views with complete result fields. A real supplied .lyr
    # may be applied; without one, no fake thematic styling is claimed.
    for metric in ['blue','green','blue_green']:
        for method in ['LISA','Gistar']:
            name=metric+'_'+method+'_1000m';tmp='tmp_'+name
            arcpy.MakeFeatureLayer_management(fc,tmp,'eligible = 1')
            lyr=arcpy.mapping.Layer(tmp);lyr.name=name;lyr.visible=False
            if styles:
                style=os.path.join(styles,name+'.lyr')
                if os.path.isfile(style):arcpy.ApplySymbologyFromLayer_management(lyr,style)
            arcpy.mapping.AddLayer(frame,lyr,'TOP')
    for name in ['blue_density_1000','green_density_1000','blue_green_density_1000','blue_mask','green_mask','wetland_mask','blue_green_mask','classification']:
        path=os.path.join(root,'data',name+'.tif')
        arcpy.MakeRasterLayer_management(path,'r_'+name)
        lyr=arcpy.mapping.Layer('r_'+name);lyr.name=name;lyr.visible=(name=='classification')
        arcpy.mapping.AddLayer(frame,lyr,'BOTTOM')
    for name in ['scope','valid_scope']:
        lyr=arcpy.mapping.Layer(os.path.join(gdb,name));lyr.visible=False;arcpy.mapping.AddLayer(frame,lyr,'TOP')
    for name in ['class_crosswalk','class_areas','group_areas','global_moran','scale_comparison','field_dictionary']:
        arcpy.mapping.AddTableView(frame,arcpy.mapping.TableView(os.path.join(gdb,name)))
    frame.extent=arcpy.Describe(os.path.join(gdb,'scope')).extent
    mxd.title=u'武汉地区蓝绿空间研究'
    mxd.description=u'研究范围为用户提供边界；数据年份待补充。绿色含耕地，蓝绿整体含独立湿地。'
    # Optional KDE sibling package, downloaded and extracted next to this package.
    kde_root=os.path.join(os.path.dirname(root),'wuhan_study_kde')
    for metric in ['blue','green','blue_green']:
        name='display_KDE_'+metric+'_h1000_RGB'
        path=os.path.join(kde_root,'data',name+'.tif')
        if os.path.isfile(path):
            arcpy.MakeRasterLayer_management(path,'new_'+name);lyr=arcpy.mapping.Layer('new_'+name);lyr.name=name;lyr.visible=(metric=='blue_green');arcpy.mapping.AddLayer(frame,lyr,'TOP')
    mxd.saveACopy(output)
    # A real ArcMap-generated MXD is reopened here; this check only runs locally.
    del mxd
    saved=arcpy.mapping.MapDocument(output)
    broken=arcpy.mapping.ListBrokenDataSources(saved)
    if broken:raise RuntimeError('MXD saved, but broken sources require repair: '+str(len(broken)))
    del saved
    print('Created and reopened real MXD:',output)
    print('Thematic fields and q<0.05 classes are present. Apply local unique-value styles as needed; final publication maps are in maps/.')
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Requires ArcGIS Desktop 10.5 Python 2.7 with licensed arcpy')
    p.add_argument('--root',default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument('--template',required=True,help='Existing real blank MXD, saved in ArcMap')
    p.add_argument('--output',default=None)
    p.add_argument('--styles',default=None,help='Optional directory of real .lyr styles')
    args=p.parse_args();create_mxd(args.root,args.template,args.output,args.styles)
