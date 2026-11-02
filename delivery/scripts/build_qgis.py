"""Actual QGIS 3.40 self-contained project with embedded datasets and layouts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/wuhan_qgis_cache')
from pathlib import Path
import shutil,json,math,zipfile,xml.etree.ElementTree as ET
from qgis.core import *
from qgis.PyQt.QtCore import Qt,QSize
from qgis.PyQt.QtGui import QColor,QFont,QFontDatabase

ROOT=Path('/workspace/client_delivery');OUT=ROOT/'QGIS';OUT.mkdir(exist_ok=True)
app=QgsApplication([],False);app.initQgis()
QFontDatabase.addApplicationFont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
p=QgsProject.instance();p.setFileName(str(OUT/'Wuhan_Study.qgz'));p.setTitle('武汉地区蓝绿空间研究｜客户交付工程（用户研究范围）')
p.setCrs(QgsCoordinateReferenceSystem('EPSG:32649'));p.setFilePathStorage(Qgis.FilePathType.Relative)
meta=p.metadata();meta.setTitle(p.title());meta.setAbstract('研究范围为用户边界；面积3255.587236 km²（原影像投影平面）。年份待补充；蓝绿整体55.5090%。主密度为1km面积加权四次核、边缘校正，单位ha/km²。Moran/LISA/Gi*另基于网格面积占比。分类标准最新现行性未在线核实；无独立精度样本；CGCS2000/WGS84采用默认近似转换。所有数据内嵌，无外部服务。');p.setMetadata(meta)
attached={}
def attach(src,name=None):
    src=Path(src);name=name or src.name
    if str(src) not in attached:
        f=p.createAttachedFile(name);shutil.copyfile(src,f);attached[str(src)]=f
    return attached[str(src)]
GPKG=attach(OUT/'project_data.gpkg','project_data.gpkg')
groups={};layers={};theme_targets=[]
def group(key,name):
    g=p.layerTreeRoot().addGroup(name);g.setExpanded(False);groups[key]=g;return g
for key,name in [('aux','00 研究范围与显示辅助（保持开启）'),('kde','01 主核密度｜1 km｜ha/km²'),('land','02 土地利用与蓝绿分布'),('local','03 LISA 与 Gi*｜1 km｜q<0.05'),('sens','04 核密度半径比较与原始值'),('grid','05 网格面积占比（不是核密度）'),('stat','06 其他尺度 LISA / Gi*'),('raw','07 完整网格、原始数值与覆盖比例'),('tables','08 统计表、类别对应与字段字典')]:group(key,name)
CN={'blue':'蓝色空间','green':'绿色空间（含耕地）','blue_green':'蓝绿整体（含耕地、湿地）','wetland':'湿地'}
PAL={'blue':['#f7f7f7','#e3f1fa','#b3d4e9','#74abd1','#337cad','#124a75'],'green':['#f7f7f7','#edf4cf','#c9df9c','#8ec17a','#4a9656','#1c6337'],'blue_green':['#f7f7f7','#e2f1e8','#b5dbcd','#76b7aa','#3b8f8e','#145969'],'wetland':['#f7f7f7','#e0f3eb','#b7dfcf','#7cc4ad','#3d9e85','#176b57']}
CLASS=['','#3182bd','#b6b4b1','#cedc8a','#55b6a2','#6baed6','#347d4c','#d7bd93','#8fbc75']
NAMES={1:'河流类水体（原长江类）',2:'建设用地（合并类）',3:'耕地',4:'湿地',5:'湖泊类水体（合并类）',6:'林地',7:'裸地（合并类）',8:'草地'}
def add(layer,key,g):
    assert layer.isValid(),(key,layer.source())
    p.addMapLayer(layer,False);groups[g].addLayer(layer);layers[key]=layer;return layer
def vector(table,name,key,g):return add(QgsVectorLayer(GPKG+'|layername='+table,name,'ogr'),key,g)
def raster(file,name,key,g):
    f=attach(ROOT/'ArcMap105/Data'/file,file)
    l=QgsRasterLayer(f,name,'gdal');return add(l,key,g)
def fillsymbol(color,outline=False):return QgsFillSymbol.createSimple({'color':color,'outline_style':'solid' if outline else 'no','outline_color':'#555555','outline_width':'0.24'})
scope=vector('scope','研究范围轮廓（用户提供）','scope','aux');scope.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'255,255,255,0','outline_color':'#555555','outline_width':'0.22'}))
mask=vector('display_mask','范围外白色遮罩（仅显示辅助）','mask','aux');mask.renderer().setSymbol(fillsymbol('#ffffff'));mask.setReadOnly(True)
mask.setFlags(mask.flags() & ~QgsMapLayer.LayerFlag.Identifiable)
extent=QgsRectangle(scope.extent());extent.scale(1.045)
p.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent,p.crs()))
def palette(l,classes):
    cs=[QgsPalettedRasterRenderer.Class(int(v),QColor(c),label) for v,c,label in classes]
    l.setRenderer(QgsPalettedRasterRenderer(l.dataProvider(),1,cs));l.triggerRepaint()
def density(l,pal=PAL['blue_green'],unit='ha/km²'):
    ramp=QgsColorRampShader(0,100);ramp.setColorRampType(QgsColorRampShader.Type.Discrete)
    upper=[0,math.nextafter(10,-math.inf),math.nextafter(25,-math.inf),math.nextafter(50,-math.inf),math.nextafter(75,-math.inf),100]
    labels=['0','>0–<10','10–<25','25–<50','50–<75','75–100']
    ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(v,QColor(c),label+' '+unit) for v,c,label in zip(upper,pal,labels)])
    shader=QgsRasterShader();shader.setRasterShaderFunction(ramp);ren=QgsSingleBandPseudoColorRenderer(l.dataProvider(),1,shader);ren.setClassificationMin(0);ren.setClassificationMax(100);l.setRenderer(ren)
def categories(l,field,codes):
    l.setRenderer(QgsCategorizedSymbolRenderer(field,[QgsRendererCategory(v,fillsymbol(color),name) for v,color,name in codes]))
def percent(l,field,pal):
    root=QgsRuleBasedRenderer.Rule(None)
    rules=[(f'"{field}" = 0','0%',pal[0]),(f'"{field}" > 0 AND "{field}" < 10','>0–<10%',pal[1])]
    rules += [(f'"{field}" >= {lo} AND "{field}" '+('<=' if hi==100 else '<')+f' {hi}',f'{lo}–'+('' if hi==100 else '<')+f'{hi}%',co) for lo,hi,co in zip([10,25,50,75],[25,50,75,100],pal[2:])]
    for expr,label,color in rules:root.appendChild(QgsRuleBasedRenderer.Rule(fillsymbol(color),filterExp=expr,label=label))
    l.setRenderer(QgsRuleBasedRenderer(root))

land=raster('land_classification.tif','土地利用分类（内部1–8类）','land','land');palette(land,[(i,CLASS[i],NAMES[i]) for i in range(1,9)])
theme_targets.append(('01 土地利用分类',land,'分类恢复；原类别不作用途细分；数据年份待补充。'))
for m in ['blue','green','blue_green','wetland']:
    l=raster('land_'+m+'_mask.tif',CN[m]+'分布',m+'_mask','land');palette(l,[(0,'#f1f0ed','有效研究范围内非目标类别'),(1,{'blue':'#3182bd','green':'#71a35a','blue_green':'#398f82','wetland':'#55b6a2'}[m],CN[m])])
    theme_targets.append(({'blue':'02 蓝色空间分布','green':'04 绿色空间分布','blue_green':'06 蓝绿整体分布','wetland':'14 湿地分布'}[m],l,'目标1；有效非目标0；范围外NoData。绿色含耕地，湿地独立纳入蓝绿整体。'))
l=raster('land_blue_green_types.tif','蓝绿类型（保留水体/耕地/林草/湿地）','types','land');palette(l,[(0,'#f1f0ed','有效研究范围内非蓝绿')]+[(i,CLASS[i],NAMES[i]) for i in [1,3,4,5,6,8]])
theme_targets=[(name,l if name.startswith('06 ') else target,note) for name,target,note in theme_targets]
for m in ['blue','green','blue_green','wetland']:
    for h in [1000,500,2000]:
        for version in ['edge_corrected','raw']:
            key=f'kde_{m}_{h}_{version}';main=m!='wetland' and h==1000 and version=='edge_corrected'
            label=CN[m]+f'核密度｜h={h}m｜'+('边缘校正' if version=='edge_corrected' else '原始截断')+'｜ha/km²'
            l=raster(f'kde_kde_{m}_h{h}_{version}.tif',label,key,'kde' if main else 'sens');density(l,PAL[m])
            if main:theme_targets.append(({'blue':'03 蓝色空间核密度','green':'05 绿色空间核密度','blue_green':'07 蓝绿整体核密度'}[m],l,'面积加权四次核；搜索半径1km；边缘校正。\n单位ha/km²；源15m核计算、输出90m面积均值。\n核密度为描述性集聚，不代表显著性。'))
LISA=[(-1,'#dadada','无法计算／未纳入'),(0,'#f7f7f7','不显著'),(1,'#c44343','高—高 HH'),(2,'#467db3','低—低 LL'),(3,'#e8a06a','高—低 HL'),(4,'#9a91bf','低—高 LH')]
GI=[(-1,'#dadada','无法计算／未纳入'),(0,'#f7f7f7','不显著'),(1,'#c44343','显著热点'),(2,'#467db3','显著冷点')]
for scale in [1000,500,2000]:
    for j,m in enumerate(['blue','green','blue_green']):
        l=vector(f'grid_{scale}_clip',CN[m]+f'网格面积占比｜{scale}m（非核密度）',f'area_{m}_{scale}','grid');percent(l,m+'_pct',PAL[m])
        for suffix,codes,typ in [('lc',LISA,'LISA'),('gc',GI,'Gi*')]:
            key=f'{suffix}_{m}_{scale}';l=vector(f'grid_{scale}_clip',CN[m]+f' {typ}｜{scale}m',key,'local' if scale==1000 else 'stat');categories(l,m+'_'+suffix,codes)
            if scale==1000:theme_targets.append((f'{8+j if suffix=="lc" else 11+j:02d} {CN[m]}{typ}',l,'Queen邻接；9999次双侧条件置换。\n局部主图：BH-FDR q<0.05。\n绿色含耕地；蓝绿整体含独立湿地。\n空间集聚不等于生态质量。'))
for scale in [500,1000,2000]:
    vector(f'grid_{scale}_full',f'{scale}m完整规则网格（含范围外）',f'full_{scale}','raw')
    for m in ['blue','green','wetland','blue_green']:
        l=raster(f'land_{m}_density_{scale}.tif',CN[m]+f'原生网格占比栅格｜{scale}m',f'native_{m}_{scale}','raw');density(l,PAL[m],'%')
for name in ['land_study_fraction.tif','kde_study_coverage_90m.tif']+[f'kde_kernel_exposure_h{h}.tif' for h in [500,1000,2000]]:
    l=raster(name,name.replace('.tif',''),name,'raw')
for table,name in [('class_area','分类面积'),('group_areas','蓝绿面积与比例'),('global_moran','全局Moran统计'),('scale_edge_comparison','尺度与边缘敏感性'),('class_crosswalk','分类标准对应（代码为文本）'),('field_dictionary','字段中文对照'),('kde_surface_statistics','核密度面统计')]:vector(table,name,'table_'+table,'tables')
# Field aliases apply consistently across all views of the same underlying data.
dictionary=QgsVectorLayer(GPKG+'|layername=field_dictionary','dictionary','ogr')
aliases={str(f['full_field']):str(f['description']) for f in dictionary.getFeatures()}
aliases.update({'AREA_M2':'研究范围投影面积（m²）','AREA_UTM':'EPSG:32649投影面积（m²）','SRC_AREA':'原属性面积（EPSG:4547，m²）','SRC_LEN':'原属性长度（EPSG:4547，m）','STD_CODE':'标准代码（文本，保留前导零）'})
for l in p.mapLayers().values():
    if isinstance(l,QgsVectorLayer):
        for name,alias in aliases.items():
            i=l.fields().indexFromName(name)
            if i>=0:l.setFieldAlias(i,alias)

root=p.layerTreeRoot();model=QgsLayerTreeModel(root)
def visible(target):
    root.setItemVisibilityCheckedRecursive(False)
    for l in [scope,mask,target]:root.findLayer(l.id()).setItemVisibilityCheckedParentRecursive(True)
for name,target,note in sorted(theme_targets):
    visible(target);record=QgsMapThemeCollection.createThemeFromCurrentState(root,model);p.mapThemeCollection().insert(name,record)
visible(layers['kde_blue_green_1000_edge_corrected']);groups['kde'].setExpanded(True)
groups['kde'].setIsMutuallyExclusive(True,2)

def label(layout,text,x,y,w,h,size=10,bold=False):
    item=QgsLayoutItemLabel(layout);item.setText(text);item.setFont(QFont('Microsoft YaHei',size,QFont.Weight.Bold if bold else QFont.Weight.Normal));layout.addLayoutItem(item);item.attemptMove(QgsLayoutPoint(x,y));item.attemptResize(QgsLayoutSize(w,h));return item
for title,target,note in sorted(theme_targets):
    lay=QgsPrintLayout(p);lay.initializeDefaults();lay.setName(title);lay.pageCollection().page(0).setPageSize('A3',QgsLayoutItemPage.Orientation.Landscape)
    page=lay.renderContext();page.setDpi(300)
    label(lay,'武汉地区蓝绿空间研究｜'+title,18,7,390,17,18,True)
    m=QgsLayoutItemMap(lay);lay.addLayoutItem(m);m.attemptMove(QgsLayoutPoint(18,31));m.attemptResize(QgsLayoutSize(282,239));m.setCrs(p.crs());m.setLayers([scope,mask,target]);m.setKeepLayerSet(True);m.setKeepLayerStyles(True);m.zoomToExtent(extent);m.setFrameEnabled(True)
    legend=QgsLayoutItemLegend(lay);lay.addLayoutItem(legend);legend.setTitle('图例');legend.setAutoUpdateModel(False);legend.model().rootGroup().clear();node=legend.model().rootGroup().addLayer(target);legend.setLinkedMap(m);legend.setStyleFont(QgsLegendStyle.Style.SymbolLabel,QFont('Microsoft YaHei',9));legend.setStyleFont(QgsLegendStyle.Style.Subgroup,QFont('Microsoft YaHei',10));legend.attemptMove(QgsLayoutPoint(310,44));legend.attemptResize(QgsLayoutSize(99,150));legend.setWrapString('｜')
    node.setUseLayerName(False);node.setName(target.name().split('｜')[0])
    nodes=legend.model().layerLegendNodes(node)
    if nodes and str(nodes[0].data(Qt.ItemDataRole.DisplayRole)).startswith('Band '):
        QgsMapLayerLegendUtils.setLegendNodeOrder(node,list(range(1,len(nodes))));legend.model().refreshLayerLegend(node)
    label(lay,'N\n↑',283,34,12,20,15,True)
    label(lay,'格网北',279,55,20,8,7)
    scale=QgsLayoutItemScaleBar(lay);scale.setStyle('Single Box');scale.setLinkedMap(m);scale.applyDefaultSize();scale.setUnits(Qgis.DistanceUnit.Kilometers);scale.setUnitLabel('km');scale.setUnitsPerSegment(5);scale.setNumberOfSegments(2);scale.setNumberOfSegmentsLeft(0);scale.setFont(QFont('Microsoft YaHei',8));lay.addLayoutItem(scale);scale.attemptMove(QgsLayoutPoint(29,256))
    label(lay,note+'\n\n投影：WGS 84 / UTM 49N\nEPSG:32649；数据年份待补充',310,197,99,69,9)
    label(lay,'数据来源：用户分类影像与研究边界；范围面积3255.59 km²（投影平面）。数据年份待补充。\n范围的行政/规划属性未独立核定；15m为源像元间距，不代表分类精度。',18,277,390,15,8)
    p.layoutManager().addLayout(lay)
p.writeEntry('Gui','SelectionColorRedPart',255);p.writeEntry('Gui','SelectionColorGreenPart',110)
assert p.write(),'QGZ write failed'
layouts=p.layoutManager().layouts();first=next(l for l in layouts if l.name().startswith('07 '))
assert QgsLayoutExporter(first).exportToPdf(str(OUT/'QGIS_layout_preview.pdf'),QgsLayoutExporter.PdfExportSettings())==QgsLayoutExporter.ExportResult.Success
settings=QgsMapSettings();settings.setLayers([scope,mask,layers['kde_blue_green_1000_edge_corrected']]);settings.setDestinationCrs(p.crs());settings.setExtent(extent);settings.setOutputSize(QSize(1400,1250));settings.setBackgroundColor(QColor('white'));job=QgsMapRendererParallelJob(settings);job.start();job.waitForFinished();assert job.renderedImage().save(str(OUT/'QGIS_canvas_preview.png'))
count=len(p.mapLayers());identifiers=[p.attachmentIdentifier(f) for f in p.attachedFiles()]
p.clear();moved=ROOT/'moved_QGIS';moved.mkdir(exist_ok=True);shutil.copyfile(OUT/'Wuhan_Study.qgz',moved/'Wuhan_Study.qgz');assert p.read(str(moved/'Wuhan_Study.qgz'))
bad=[l.name() for l in p.mapLayers().values() if not l.isValid()];assert not bad,bad
assert len(p.mapLayers())==count and len(p.layoutManager().layouts())==14
assert all('/workspace/client_delivery/ArcMap105' not in l.source() for l in p.mapLayers().values())
sources=[{'name':l.name(),'provider':l.providerType(),'valid':l.isValid(),'source_resolved_in_temp':l.source().startswith('/tmp/')} for l in p.mapLayers().values()]
with zipfile.ZipFile(OUT/'Wuhan_Study.qgz') as z:
    xml=z.read(next(n for n in z.namelist() if n.endswith('.qgs'))).decode();ds=[e.text or '' for e in ET.fromstring(xml).iter('datasource') if e.text]
    assert all(x.startswith('attachment:') for x in ds),[x for x in ds if not x.startswith('attachment:')]
report={'QGIS':Qgis.QGIS_VERSION,'project':'Wuhan_Study.qgz','layer_count':count,'layouts':14,'themes':p.mapThemeCollection().mapThemes(),'embedded_attachments':len(identifiers),'external_data_dependencies':0,'moved_single_file_reopen':'PASS','all_layers_valid':True,'native_layout_pdf_export':'PASS','canvas_render':'PASS','project_bytes':(OUT/'Wuhan_Study.qgz').stat().st_size,'layers':sources}
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='layers'},ensure_ascii=False,indent=2),flush=True)
