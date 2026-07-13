# Net Hit 模块

根据球相对球网的位置、速度变化和短时丢失，判断可能的触网事件。

| 文件 | 作用 |
| --- | --- |
| `detector.py` | 轨迹清理、打分、事件合并和公共配置 |
| `video.py` | 从视频提取球轨迹并执行检测 |
| `track_io.py` | 读取 JSON 或 CSV 轨迹 |
| `cli.py` | 独立命令行入口 |

核心入口是 `detect_net_hits(coords, config)`；结果为 `NetHitEvent` 列表。检测依赖准确的球网线，阈值单位为图像像素。
