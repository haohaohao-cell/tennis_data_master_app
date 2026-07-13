# Segmentation 模块

把整场视频按有效回合切分为 point 片段。

| 文件 | 作用 |
| --- | --- |
| `points.py` | 纯分段规则、配置、筛选和摘要生成 |
| `video.py` | 管理推理缓存，并调用 ffmpeg 输出片段视频 |

`SegmentationConfig` 控制无球、无球员、无球场和最短片段等阈值。`points.py` 不依赖模型，适合单元测试；实际切视频需要本机安装 `ffmpeg`。
