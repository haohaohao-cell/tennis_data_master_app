# Local PostgreSQL Message Setup

使用 PostgreSQL 17 本地项目数据库 `tennis_data_master`。执行前在同一个 PowerShell 进程设置 `TENNIS_DATABASE_URL`；不要把密码写入脚本、报告或聊天记录。

```powershell
$env:TENNIS_DATABASE_HOST = "localhost"
$env:TENNIS_DATABASE_PORT = "5432"
$env:TENNIS_DATABASE_NAME = "tennis_data_master"
$env:TENNIS_DATABASE_URL = "postgresql://postgres@localhost:5432/tennis_data_master"
# Use your local PostgreSQL user/password as appropriate; do not commit the DSN.
python scripts/inspect_postgres_environment.py
python scripts/init_postgres_db.py --schema message_<timestamp>
python scripts/migrate_stage9_outbox.py --schema message_<timestamp>
```

只允许 `localhost`/`127.0.0.1`、端口 `5432`、数据库 `tennis_data_master` 和新隔离 Schema。若环境变量不可见、身份不匹配、数据库不可连接或权限不足，停止所有 PostgreSQL 写入并先修正环境或权限。迁移脚本是 additive、可重复执行，不执行 DROP、TRUNCATE、批量 DELETE 或覆盖式导入。

历史数据导入前应按根目录 `POSTGRES_MIGRATION_GUIDE.md` 完成只读完整性审计，并将迁移报告和校验报告写入新的带时间戳文件。失败回滚依赖事务回滚和删除本轮新建隔离 Schema，必须由用户审查后执行，不得触碰历史源文件或其他 Schema。
