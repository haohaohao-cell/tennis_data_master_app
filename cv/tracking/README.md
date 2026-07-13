# Tracking 模块

负责球与球员的连续跟踪，以及轨迹清理和落点检测。

| 文件 | 作用 |
| --- | --- |
| `ball.py` | 封装 TrackNet，支持流式检测和整段轨迹处理 |
| `person.py` | YOLO 检测结果接入 DeepSORT 并筛选场上角色 |
| `player_identity.py` | 在跟踪 ID 变化时保持双方球员身份稳定 |
| `player.py` | 保留批量球员检测与筛选接口 |
| `trajectory.py` | 分段、去离群点和缺失坐标插值 |
| `bounce.py` | 根据轨迹方向和局部突变检测落点 |
| `bbox.py` | 包围框位置与距离辅助函数 |

落点算法详见 [BOUNCE_DETECTION.md](BOUNCE_DETECTION.md)。本模块输出轨迹和候选事件，比赛语义分类由 `events` 负责。
