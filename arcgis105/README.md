# ArcGIS Desktop 10.5 专用交付

提供真实文件地理数据库 `.gdb`、配套GeoTIFF、主尺度地图与本机MXD生成脚本。云端使用GDAL OpenFileGDB创建地理数据库，目标选项为 `ALL`，整数转为32位，未使用ArcGIS Pro 3.2专用BigInteger等类型。数据已在云端回读核验，但未通过ArcMap本机打开验证。

**[下载 ArcGIS 10.5 专用数据包](wuhan_arcgis105.zip)**

## 实际包含什么

- `wuhan_results.gdb`：6个完整/裁剪网格要素类、影像范围、有效范围；分类对应、面积、Moran、尺度比较及字段字典等属性表。完整数值和NULL保留，分类标准代码为文本，保留前导零。
- `rasters/`：真实GeoTIFF分类、掩膜、类型与密度。云端OpenFileGDB写出矢量和表，本包栅格独立存放，未声称已写进GDB栅格数据集。
- `maps/`：正式主尺度PNG/PDF，可直接查看；`tables/`、`methods/`、`qa/`保留统计表、定义和验证结果。
- `create_mxd_arcmap105.py`：需要在本机ArcGIS Desktop 10.5自带Python2.7/arcpy中执行的真实MXD生成入口。

## MXD尚需本机ArcMap生成

**压缩包不包含云端生成的MXD。** 当前云端没有ArcGIS，不能生成或验证真实`.mxd`，也未伪造同名文件。

解压完整包并保持目录结构，在ArcMap 10.5中新建空白地图，打开Python窗口。假设解压到 `D:\wuhan_arcgis105`，执行：

```python
import sys
sys.path.insert(0, r'D:\wuhan_arcgis105')
import create_mxd_arcmap105 as w
w.create_mxd(r'D:\wuhan_arcgis105', template='CURRENT')
```

将生成并重新打开核验 `D:\wuhan_arcgis105\project\wuhan_overview.mxd`。脚本设置投影、字段别名、范围、相对路径，加载分类、掩膜、密度、三尺度网格、主尺度LISA/Gi*视图和属性表，并检查断开的数据源。默认显示分类栅格，其他分析层保留供切换编辑。

也可在ArcMap保存有效空白 `blank.mxd` 后，从ArcGIS自带Python运行：

```bat
"C:\Python27\ArcGIS10.5\python.exe" create_mxd_arcmap105.py --root "D:\wuhan_arcgis105" --template "D:\blank.mxd"
```

专题图层已有分类结果字段，但没有真实`.lyr`时不会伪称自动复现全部专题符号。可在图层属性中按`blue_lc`/`green_lc`/`blue_green_lc`或对应`_gc`做唯一值符号；类别定义见字段字典。脚本可用`styles`参数加载用户提供的真实`.lyr`。正式云端地图不依赖本机MXD。

分析范围为输入影像覆盖区；数据年份待补充。分类依据按自然资发〔2023〕234号整理，最新现行性尚未在线核实；没有独立分类精度样本。GDB和MXD工程本身不改变这些限制。
