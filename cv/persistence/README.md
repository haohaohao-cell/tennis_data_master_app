# Persistence 模块

使用 PostgreSQL 的独立 `cv_analysis` schema 保存用户、上传任务、point 和 shot 数据。

| 文件 | 作用 |
| --- | --- |
| `connection.py` | 从进程级 PostgreSQL 连接池借还连接并设置 schema |
| `core_tables.py` | 创建 `users`、`uploads` 表 |
| `points_schema.py` | 创建 `points` 表 |
| `shots_schema.py` | 创建 `shots` 表 |
| `schema.py` | 初始化或重建全部表 |
| `repository.py` | 统一的 CRUD 和整批分析结果读写接口 |

推荐从 `TennisAnalysisRepository` 访问数据。连接串使用 `TENNIS_CV_DATABASE_URL`，未设置时回退到后端的 `TENNIS_DATABASE_URL`；schema 使用 `TENNIS_CV_DATABASE_SCHEMA`（默认 `cv_analysis`）。构造函数中的旧 `db_path` 参数仅为兼容保留，不会创建本地数据库文件。

连接池默认大小为 1-4，可通过 `TENNIS_CV_DATABASE_POOL_MIN_SIZE` 和
`TENNIS_CV_DATABASE_POOL_MAX_SIZE` 调整；修改 DSN、schema 或池大小时会自动重建池。

已有 `match_analysis.sqlite` 时，使用 `scripts/migrate_cv_sqlite_to_postgres.py` 只读迁移；该脚本不会删除或修改源文件，`--dry-run` 只统计源表行数。
