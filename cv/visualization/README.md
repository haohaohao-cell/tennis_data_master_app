# Visualization 模块

把分析结果绘制到视频帧上，不参与检测和数据计算。

| 文件 | 作用 |
| --- | --- |
| `overlays.py` | 球场点、击球提示和综合分析面板 |
| `minimap.py` | 在视频中绘制俯视球场、球员、球和落点 |
| `player_stats.py` | 绘制双方速度与击球统计 |
| `tennis.py` | 绘制跟踪框、球场线和基础 minimap 元素 |

输入通常是 OpenCV 的 BGR 帧以及 `pipeline` 产生的分析结果；输出是已绘制帧或视频文件。
