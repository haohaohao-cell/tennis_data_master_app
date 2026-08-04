# Net Hit 模块

根据球相对球网的位置、速度变化和短时丢失，判断可能的触网事件。生产推理管线默认使用自动定位的弯曲网带；手工水平网线入口保留用于兼容和对照。

| 文件 | 作用 |
| --- | --- |
| `detector.py` | 轨迹清理、打分、事件合并和公共配置 |
| `video.py` | 从视频提取球轨迹并执行检测 |
| `track_io.py` | 读取 JSON 或 CSV 轨迹 |
| `curved_geometry.py` | 自动定位可见球网的上下边界 |
| `curved_detector.py` | 基于弯曲网带的触网事件检测 |
| `curved_video.py` | 使用视频和球场模型定位球网，不重复球追踪 |
| `cli.py` | 独立命令行入口 |

核心生产入口是 `detect_curved_net_hits(coords, net_model, config)`；结果为 `CurvedNetHitEvent` 列表。`run_curved_net_hit_detection()` 可从视频自动获得 `net_model`。当已有 GridTrackNet 轨迹 JSON 时，可运行：

```bash
python -m cv.cli.net_hit --input-video match.mp4 --auto-net --ball-track-json match_ball_coords_raw.json
```

JSON 中的 `ball_coords[*].pixel` 必须与视频逐帧对齐。旧入口 `detect_net_hits(coords, config)` 仍要求调用方提供球网线。
