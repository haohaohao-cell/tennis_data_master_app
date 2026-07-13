# Tests 模块

这里放置不需要大型模型权重或完整比赛视频的回归测试。

```bash
python -m unittest discover -s cv/tests
```

当前覆盖配置路径、payload 构建、point 分段、触网几何和 SQLite repository。修改这些公共契约时应同步更新对应测试。
