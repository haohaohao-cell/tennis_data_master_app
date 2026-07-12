# 旧工具路径兼容层

本目录中的模块只转发到新的领域包：

- 击球、发球、界内外判断：`cv.events`
- rally、球速、跑动距离和单位转换：`cv.analytics`
- JSON 与视频读写：`cv.io`
- bbox：`cv.tracking.bbox`
- 球场映射：`cv.court.mapping`
- 统计绘制：`cv.visualization`

新代码不要再向 `my_utils` 添加实现。
