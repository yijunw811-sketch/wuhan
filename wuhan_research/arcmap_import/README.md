# ArcMap 10.5 本机导入（可选，未在云端运行）

需要 Windows、ArcGIS Desktop 10.5、自带 Python 2.7 和可用 arcpy、可写输出目录，以及您在 ArcMap 中创建并保存的有效空白 MXD 模板。

示例：`C:\Python27\ArcGIS10.5\python.exe import_arcmap105.py --root D:\wuhan_research --template D:\blank.mxd --out D:\wuhan_local`

脚本把顶层 data 内Shapefile和GeoTIFF导入真实文件地理数据库，依字典设置字段别名，在模板的第一个数据框加载1km总览网格、范围、分类和蓝绿密度，保存总览MXD。仅在提供真实且适配的 .lyr 时尝试应用符号。云端PNG/PDF已独立完成，不依赖这一步。导入后需在本机核查类别配色、栅格NoData、DBF缺失值及图层顺序；脚本不声称完整复现云端地图排版。

未伪造 .gdb、.mxd 或 .lyr；云端没有ArcGIS，未执行本脚本或通过ArcMap打开验证。
