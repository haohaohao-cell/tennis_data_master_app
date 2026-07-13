# CLI 模块

这里是命令行薄封装，实际逻辑位于对应业务模块。

```bash
python -m cv.cli.inference --input_video_path /path/to/match.mp4
python -m cv.cli.split_points --source-video /path/to/match.mp4
python -m cv.cli.net_hit --help
python -m cv.cli.init_db
```

| 文件 | 转发到 |
| --- | --- |
| `inference.py` | `cv.pipeline` |
| `split_points.py` | `cv.segmentation` |
| `net_hit.py` | `cv.events.net_hit` |
| `init_db.py` | `cv.persistence` |

新增命令时，CLI 只处理参数和退出码，业务实现放在领域模块中。
