# Tennis CV

`cv` 按业务职责组织，`cv/scripts` 只提供稳定公共入口和旧路径兼容层。

## 公共入口

```python
from cv.scripts.run_inference_v2 import run_inference_v2
from cv.scripts.db_operations import TennisAnalysisRepository
```

`run_inference_v2(...)` 仍返回 `(shots_payload, points_payload)`，JSON 与数据库字段保持不变。

## 模块划分

| 目录 | 职责 |
| --- | --- |
| `pipeline` | 端到端推理编排 |
| `segmentation` | point 分段、缓存和视频切分 |
| `builders` | 帧、shot、point payload 与坐标填补 |
| `tracking` | 球、球员、身份、弹跳和轨迹处理 |
| `court` | 球场检测、参考系、单应变换和坐标映射 |
| `events` | 击球、发球、出界和触网检测 |
| `analytics` | rally、球速和跑动距离统计 |
| `persistence` | SQLite schema、连接和 repository |
| `visualization` | 视频标注、minimap 和统计绘制 |
| `io` | 视频与 JSON 读写 |
| `models` | 模型实现与本地权重 |
| `cli` | 可直接通过 `python -m` 执行的命令入口 |
| `legacy` | 已停用但保留的旧推理实现 |

## 算法文档

- [击球检测算法](events/HIT_DETECTION.md)：轨迹突变、前后窗口、人球距离、远近端透视补偿和候选去抖。
- [落点检测算法](tracking/BOUNCE_DETECTION.md)：垂直突变、方向夹角、局部极大值抑制、落点细化和界内外判断。

## 数据目录

- `data/input`: 后端上传和本地待分析视频，不纳入版本控制。
- `data/output`: 推理生成文件，不纳入版本控制。
- `data/samples`: 用于回归和调试的受控样例。
- `models/weights`: 本地模型权重；除已存在的样例权重外默认忽略。
- `experiments`: notebook 和实验材料，不参与生产导入。

## CLI

```bash
python -m cv.cli.inference --input_video_path /path/to/match.mp4
python -m cv.cli.split_points --source-video /path/to/match.mp4
python -m cv.cli.init_db
```

旧的 `python -m cv.scripts.run_inference_v2` 等命令继续可用。
