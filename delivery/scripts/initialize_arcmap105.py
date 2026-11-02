# -*- coding: utf-8 -*-
"""Runs locally with licensed ArcMap Python; no cloud-generated MXD claim."""
from __future__ import print_function
import os,sys,json,csv,codecs,argparse,traceback
try:
    text_type=unicode
except NameError:
    text_type=str

def select_template(root,arcpy,explicit=None):
    if explicit and os.path.isfile(explicit):return explicit
    candidate=os.path.join(root,'Blank_Template.mxd')
    if os.path.isfile(candidate):return candidate
    install=arcpy.GetInstallInfo().get('InstallDir','')
    search=[os.path.join(install,'MapTemplates'),os.path.join(os.environ.get('APPDATA',''),'ESRI','Desktop10.5','ArcMap','Templates')]
    for folder in search:
        if not isinstance(folder,text_type):folder=folder.decode(sys.getfilesystemencoding() or 'mbcs')
        if not os.path.isdir(folder):continue
        for dirname,subdirs,files in os.walk(folder):
            for name in files:
                if name.lower().endswith('.mxd') and any(k in name.lower() for k in ['blank','empty',u'空白']):return os.path.join(dirname,name)
    try:
        import Tkinter as tk
        import tkFileDialog as fd
        import tkMessageBox as mb
    except ImportError:
        import tkinter as tk
        from tkinter import filedialog as fd,messagebox as mb
    win=tk.Tk();win.withdraw()
    mb.showinfo(u'选择真实空白地图模板',u'本机没有找到空白MXD模板。\n请先在ArcMap中新建空白地图，保存为Blank_Template.mxd，再在下一窗口选择它。\n本程序不会伪造MXD。',parent=win)
    selected=fd.askopenfilename(parent=win,title=u'选择在ArcMap保存的真实空白MXD',filetypes=[('ArcMap map document','*.mxd')]);win.destroy()
    if not selected:raise RuntimeError('A real blank MXD template is required. Data and ready-colored views remain usable without MXD.')
    return selected

def initialize(root,template=None,force=False):
    import arcpy
    if not isinstance(root,text_type):root=root.decode(sys.getfilesystemencoding() or 'mbcs')
    root=os.path.abspath(root);output=os.path.join(root,'Wuhan_Study.mxd')
    arcpy.env.overwriteOutput=True
    if os.path.isfile(output) and not force:
        saved=arcpy.mapping.MapDocument(output)
        broken=arcpy.mapping.ListBrokenDataSources(saved);del saved
        if not broken:return output
    gdb=os.path.join(root,'Data','Wuhan_Study.gdb')
    if not arcpy.Exists(gdb):raise RuntimeError('Missing Data/Wuhan_Study.gdb. Extract the complete ZIP first.')
    template=select_template(root,arcpy,template)
    mxd=arcpy.mapping.MapDocument(template);frames=arcpy.mapping.ListDataFrames(mxd)
    if not frames:raise RuntimeError('Template must contain a data frame')
    for frame in frames:
        for layer in arcpy.mapping.ListLayers(mxd,'',frame):
            try:arcpy.mapping.RemoveLayer(frame,layer)
            except Exception:pass
        for table in arcpy.mapping.ListTableViews(mxd,'',frame):arcpy.mapping.RemoveTableView(frame,table)
    frame=frames[0];frame.name=u'武汉蓝绿空间研究';frame.spatialReference=arcpy.SpatialReference(32649)
    mxd.relativePaths=True;mxd.activeView=frame.name;mxd.title=u'武汉地区蓝绿空间研究（用户研究范围版）'
    mxd.summary=u'用户研究范围内蓝绿空间分类、面积加权核密度和空间统计整合工程'
    mxd.tags='Wuhan,BlueGreen,KDE,UserStudyArea'
    mxd.description=u'蓝绿整体55.5090%；研究范围3255.59km2（投影平面）；数据年份待补充。显示RGB层供查看；定量分析请用数值栅格和GDB字段。'
    aliases={};dictionary=os.path.join(root,'Documents','field_dictionary.csv')
    with open(dictionary,'rb') as f:
        f.read(3)
        for row in csv.DictReader(f):aliases.setdefault(row['layer'],{})[row['full_field']]=row['description'].decode('utf-8')
    arcpy.env.workspace=gdb
    for name in sorted(arcpy.ListFeatureClasses() or []):
        fc=os.path.join(gdb,name)
        for field in arcpy.ListFields(fc):
            if field.name in aliases.get(name,{}):arcpy.AlterField_management(fc,field.name,new_field_alias=aliases[name][field.name])
        layer=arcpy.mapping.Layer(fc);layer.name=u'[属性/矢量] '+name;layer.visible=False;arcpy.mapping.AddLayer(frame,layer,'BOTTOM')
    for name in sorted(arcpy.ListTables() or []):arcpy.mapping.AddTableView(frame,arcpy.mapping.TableView(os.path.join(gdb,name)))
    counter=0
    for name in sorted(os.listdir(os.path.join(root,'Data'))):
        if not name.lower().endswith('.tif'):continue
        tmp='value_{0}'.format(counter);counter+=1;arcpy.MakeRasterLayer_management(os.path.join(root,'Data',name),tmp)
        layer=arcpy.mapping.Layer(tmp);layer.name=u'[原始数值] '+name[:-4];layer.visible=False;arcpy.mapping.AddLayer(frame,layer,'BOTTOM')
    catalog=json.load(codecs.open(os.path.join(root,'layer_catalog.json'),'r','utf-8'))
    native=os.path.join(root,'Native_Layers')
    if not os.path.isdir(native):os.makedirs(native)
    # Main and sensitivity view files carry actual stored RGB/palette colors.
    for item in [x for x in catalog if x['section']!='aux']+[x for x in catalog if x['section']=='aux']:
        tmp='display_{0}'.format(counter);counter+=1;path=os.path.join(root,*item['file'].split('/'))
        arcpy.MakeRasterLayer_management(path,tmp);layer=arcpy.mapping.Layer(tmp);layer.name=item['name'];layer.visible=bool(item['visible'])
        arcpy.mapping.AddLayer(frame,layer,'TOP' if item['section']=='aux' else 'BOTTOM')
        arcpy.SaveToLayerFile_management(tmp,os.path.join(native,os.path.splitext(os.path.basename(path))[0]+'.lyr'),'RELATIVE')
    frame.extent=arcpy.Describe(os.path.join(gdb,'scope')).extent
    version=arcpy.GetInstallInfo().get('Version','')
    if version.startswith('10.5'):mxd.saveACopy(output)
    else:mxd.saveACopy(output,'10.5')
    del mxd
    check=arcpy.mapping.MapDocument(output);broken=arcpy.mapping.ListBrokenDataSources(check)
    report={'actual_arcgis_version':version,'MXD_created_on_this_machine':True,'mxd':os.path.basename(output),'relative_paths':True,'broken_sources':len(broken),'view_layers':len(catalog),'source_data':'User research boundary version'}
    del check
    with codecs.open(os.path.join(root,'ArcMap_initialization_report.json'),'w','utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    if broken:raise RuntimeError('Created MXD contains broken sources: '+str(len(broken)))
    return output

def package_map(output):
    import arcpy
    version=arcpy.GetInstallInfo().get('Version','')
    if not version.startswith('10.5'):return False
    target=os.path.join(os.path.dirname(output),'Wuhan_Study.mpk')
    staging=os.path.join(os.path.dirname(output),'Wuhan_Study_build.mpk')
    try:
        arcpy.PackageMap_management(output,staging)
        if not os.path.isfile(staging) or os.path.getsize(staging)==0:return False
        if os.path.isfile(target):os.remove(target)
        os.rename(staging,target)
        return True
    except Exception:
        if os.path.isfile(staging):os.remove(staging)
        message=arcpy.GetMessages()
        if not isinstance(message,text_type):message=message.decode('utf-8','replace')
        with codecs.open(os.path.join(os.path.dirname(output),'MapPackage_error.txt'),'w','utf-8') as f:
            f.write(message)
        return False

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--template');p.add_argument('--force',action='store_true');p.add_argument('--open',action='store_true');p.add_argument('--package',action='store_true')
    args=p.parse_args()
    try:
        output=initialize(args.root,args.template,args.force);print('MXD ready:',output)
        if args.package:print('Native single-file MPK created:',package_map(output))
        if args.open:os.startfile(output)
    except Exception:
        log=os.path.join(args.root,'ArcMap_initialization_error.txt')
        message=traceback.format_exc()
        if not isinstance(message,text_type):message=message.decode('utf-8','replace')
        with codecs.open(log,'w','utf-8') as f:f.write(message)
        print('Initialization failed. See ArcMap_initialization_error.txt. Native MXD creation needs licensed ArcGIS and a real blank MXD.');sys.exit(1)
