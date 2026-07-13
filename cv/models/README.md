# Models 模块

存放项目直接使用的神经网络实现和本地权重。

| 目录 | 作用 |
| --- | --- |
| [`ball_tracking/`](ball_tracking/README.md) | TrackNet 球检测、训练与视频推理 |
| [`court_detection/`](court_detection/README.md) | 球场关键点热图网络 |
| `weights/` | `.pt` 模型权重，通常不纳入版本控制 |

默认权重路径统一定义在 `cv.config`。模型输出的清理、事件判断和业务数据组装分别属于 `tracking`、`events` 和 `builders`。
