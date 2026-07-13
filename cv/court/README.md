# Court 模块

负责识别球场关键点，并在视频像素坐标与标准球场坐标之间转换。

| 文件 | 作用 |
| --- | --- |
| `detector.py` | 传统球场线检测与跟踪 |
| `keypoints.py` | 使用关键点模型预测球场并计算变换矩阵 |
| `reference.py` | 定义标准球场尺寸、线段和参考图 |
| `homography.py` | 根据关键点计算单应矩阵 |
| `mapping.py` | 将球的位置映射到球场平面 |
| `postprocess.py` / `utils.py` | 热图、直线和几何辅助函数 |
| `legacy_reference.py` | 旧导入路径使用的参考球场实现 |

主要输出是关键点和单应矩阵，供 `tracking`、`analytics`、`events` 与可视化模块使用。
