# -*- coding: utf-8 -*-
"""Run in ArcMap 10.5's Python 2.7; creates an actual MXD locally."""
from __future__ import print_function
import os,argparse

def create_kde_mxd(root,template='CURRENT',output=None):
    import arcpy
    arcpy.env.overwriteOutput=True
    root=os.path.abspath(root)
    mxd=arcpy.mapping.MapDocument(template);frame=arcpy.mapping.ListDataFrames(mxd)[0]
    frame.spatialReference=arcpy.SpatialReference(32649);mxd.relativePaths=True
    for metric in ['blue','green','blue_green']:
        for h in [500,1000,2000]:
            for version in ['raw','edge_corrected']:
                name='kde_{0}_h{1}_{2}'.format(metric,h,version)
                path=os.path.join(root,'data',name+'.tif')
                arcpy.MakeRasterLayer_management(path,name);lyr=arcpy.mapping.Layer(name);lyr.name=name;lyr.visible=False;arcpy.mapping.AddLayer(frame,lyr,'BOTTOM')
        name='display_KDE_'+metric+'_h1000_RGB';path=os.path.join(root,'data',name+'.tif')
        arcpy.MakeRasterLayer_management(path,name);lyr=arcpy.mapping.Layer(name);lyr.name=name;lyr.visible=(metric=='blue_green');arcpy.mapping.AddLayer(frame,lyr,'TOP')
    frame.extent=arcpy.Describe(os.path.join(root,'data','kde_blue_green_h1000_edge_corrected.tif')).extent
    mxd.title=u'武汉地区蓝绿空间核密度分析'
    if output is None:output=os.path.join(root,'wuhan_KDE.mxd')
    mxd.saveACopy(output);del mxd
    saved=arcpy.mapping.MapDocument(output)
    if arcpy.mapping.ListBrokenDataSources(saved):raise RuntimeError('Saved MXD has broken sources')
    del saved;print('Created and reopened real MXD:',output)
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=os.path.dirname(os.path.abspath(__file__)));p.add_argument('--template',required=True);p.add_argument('--output',default=None)
    a=p.parse_args();create_kde_mxd(a.root,a.template,a.output)
