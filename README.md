# 武汉地区蓝绿空间研究成果

## 更新：蓝色、绿色及蓝绿整体核密度图

按最新要求已新增面积加权四次核KDE，主搜索半径1km，补充500m和2km，主图采用边缘校正；单位ha/km²，原15m分类参与核计算，输出90m密度面。**此前网格面积占比保留为另一种指标，不改称核密度。**

**[下载核密度专用成果包](kde/wuhan_kde_results.zip)** · [核密度主图、方法与预览](kde/README.md)

KDE仅描述分布集聚，不继承原网格Moran/LISA/Gi*的显著性。包内含可在ArcMap10.5直接加载的浮点GeoTIFF及着色显示GeoTIFF。

## 下载全部成果

**[点击下载完整仓库 ZIP](https://github.com/yijunw811-sketch/wuhan/archive/refs/heads/main.zip)**

也可点击本页绿色 **Code → Download ZIP**。解压后的 `wuhan_research/` 包含完整成果目录，可直接使用；无需合并分卷。

原成果ZIP约127 MiB，超过GitHub单文件100 MiB限制，因此本仓库保存该成果包的全部解压内容，未删减原始输入、分析数据或地图。GitHub下载ZIP的字节及SHA256与原ZIP不同，实际文件内容可按 `wuhan_research/qa/file_manifest.csv` 核验。

## 成果内容

- 原始RGB影像、配色表、恢复的整数分类、蓝/绿/湿地/蓝绿掩膜与类型GeoTIFF。
- 500m、1km、2km精确面积加权密度；完整与裁剪网格Shapefile、GeoPackage及CSV。
- 全局Moran、LISA、Gi*、9999次置换、BH-FDR及边缘敏感性结果。
- 43组A3横版300DPI PNG/PDF、脚本、配置、依赖版本、中文字体及质量核查。
- 可选本机ArcMap10.5/Python2.7导入脚本（云端未执行）。

[结果摘要](wuhan_research/methods/results_summary.md) · [分析方法](wuhan_research/methods/methods.md) · [全部地图](wuhan_research/maps) · [字段字典](wuhan_research/methods/field_dictionary.csv)

![主要地图预览](main_preview.jpg)

## 关键结果与限制

有效影像面积4659.3792 km²；蓝色14.5130%，广义绿色（含耕地）45.9039%，独立湿地1.0743%，蓝绿整体61.4912%。分析范围为输入影像覆盖区，不是武汉市都市区正式规划边界。

分类依据按自然资发〔2023〕234号对应整理，最新现行性尚未在线核实。数据年份待补充，无独立分类精度样本；未在ArcMap本机打开验证。空间占比集聚不等于生态质量或生态服务。

## 复现

需要Python3.12，解压后：

```bash
cd wuhan_research
bash scripts/run.sh
```

配置见 `config/analysis.json`，固定依赖见 `scripts/requirements.txt`。需有依赖下载网络；当前云机器可复用已安装的依赖。正式主尺度为1km；500m/2km用于敏感性比较。

## ArcGIS Desktop 10.5 补充交付

**[下载真实GDB及ArcGIS专用数据包](arcgis105/wuhan_arcgis105.zip)** · [GDB说明与本机MXD生成入口](arcgis105/README.md)

GDB已在云端实际创建并回读核验。云端没有ArcGIS，未生成真实MXD；需要在本机ArcMap10.5执行随包脚本，加载GDB和栅格后保存并验证MXD。
