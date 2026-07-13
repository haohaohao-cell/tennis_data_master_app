# Persistence 模块

使用 SQLite 保存用户、上传任务、point 和 shot 数据。

| 文件 | 作用 |
| --- | --- |
| `connection.py` | 建立连接并开启外键约束 |
| `core_tables.py` | 创建 `users`、`uploads` 表 |
| `points_schema.py` | 创建 `points` 表 |
| `shots_schema.py` | 创建 `shots` 表 |
| `schema.py` | 初始化或重建全部表 |
| `repository.py` | 统一的 CRUD 和整批分析结果读写接口 |

推荐从 `TennisAnalysisRepository` 访问数据。默认数据库路径是 `cv/data/output/match_analysis.sqlite`，由 `cv.config` 定义。
