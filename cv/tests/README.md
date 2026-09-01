# Tests 模块

这里放置不需要大型模型权重或完整比赛视频的回归测试。

```bash
python -m unittest discover -s cv/tests
```

当前覆盖配置路径、payload 构建、point 分段、触网几何和 PostgreSQL repository。需要数据库的回归测试必须配置 `TENNIS_DATABASE_URL`，SQLite 文件仅用于迁移输入验证。
