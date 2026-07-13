# Analytics 模块

根据检测结果计算比赛统计，不负责模型推理或数据落库。

| 文件 | 作用 |
| --- | --- |
| `rally.py` | 将击球、落点和球员数据汇总为 rally 统计 |
| `shot_speed.py` | 根据击球到落点的距离和时间估算球速 |
| `player_distance.py` | 将球员位置映射到真实球场并累计跑动距离 |
| `conversions.py` | 像素距离与实际距离的简单换算 |

输入通常来自 `tracking`、`events` 和 `court`，结果由 `pipeline` 交给 `builders`。
