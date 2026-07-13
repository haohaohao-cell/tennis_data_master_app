# Events 模块

从球和球员轨迹中识别网球事件。

| 文件 | 作用 |
| --- | --- |
| `hit_detection.py` | 检测击球帧 |
| `in_out.py` | 判断落点界内或界外 |
| `serve.py` | 识别发球及发球类型 |
| `shot_classifier.py` | 分类正手、反手、截击、扣杀等击球 |
| `net_hit/` | 检测触网事件，可独立运行 |
| `legacy_hit_detection.py` | 保留旧击球算法供兼容和对照 |

击球算法的参数和判定过程见 [HIT_DETECTION.md](HIT_DETECTION.md)，触网子模块见 [net_hit/README.md](net_hit/README.md)。
