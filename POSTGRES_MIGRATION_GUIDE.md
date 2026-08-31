# SQLite 转 PostgreSQL 操作手册

本文用于将本项目旧的 SQLite 数据库迁移到 PostgreSQL。请从仓库根目录执行命令。

迁移工具会以只读方式打开 SQLite 源文件，不会删除或修改源数据库。目标 PostgreSQL 会创建表并写入数据；迁移前请先备份两个数据库。

## 一、前置条件

需要准备：

- Windows PowerShell 7（命令使用 `pwsh` 语法）。
- Conda 环境 `tennis`。
- PostgreSQL 服务已安装、已启动，并且当前用户有创建数据库或连接目标数据库的权限。
- 要迁移的 SQLite 文件，例如 `backend/db/tennis_data_master.sqlite3`。

检查 PostgreSQL 是否可用：

```powershell
psql --version
createdb --version
```

如果命令找不到，请把 PostgreSQL 的 `bin` 目录加入 PATH，通常类似：

```text
C:\Program Files\PostgreSQL\17\bin
```

确认 PostgreSQL 服务正在运行：

```powershell
Get-Service *postgres*
```

## 二、准备 Python 环境

每个需要执行 Python、迁移或验证命令的 PowerShell 窗口，都先运行：

```powershell
conda activate tennis
pip install -r backend/requirements.txt
```

如果 `conda activate` 提示尚未初始化，请先执行一次：

```powershell
conda init powershell
```

然后关闭并重新打开 PowerShell 7，再执行 `conda activate tennis`。

## 三、创建 PostgreSQL 数据库

下面命令连接 PostgreSQL 默认的 `postgres` 数据库，并创建项目数据库：

```powershell
psql -U postgres -h localhost -p 5432 -d postgres -c "CREATE DATABASE tennis_data_master;"
```

如果提示数据库已存在，可以跳过这一步。不要执行 `DROP DATABASE`，除非已经确认目标数据库中的数据可以删除。

## 四、配置目标数据库连接

在同一个 PowerShell 窗口设置连接地址。推荐使用 `TENNIS_DATABASE_URL`；`TENNIS_POSTGRES_DSN` 是兼容旧配置的别名。

```powershell
$env:TENNIS_DATABASE_URL = "postgresql://postgres:你的密码@localhost:5432/tennis_data_master"
```

如果 PostgreSQL 用户不需要密码，也可以使用：

```powershell
$env:TENNIS_DATABASE_URL = "postgresql://postgres@localhost:5432/tennis_data_master"
```

密码中如果包含 `@`、`:`、`/`、`#` 或其他 URL 保留字符，需要先进行 URL 编码。例如密码 `p@ssword` 应写成 `p%40ssword`。

检查当前窗口是否已经设置连接地址，但不要把完整密码打印到日志或提交到 Git：

```powershell
if (-not $env:TENNIS_DATABASE_URL -and -not $env:TENNIS_POSTGRES_DSN) {
    throw "请先设置 TENNIS_DATABASE_URL"
}
Write-Output "PostgreSQL DSN 已设置"
```

`.env` 文件目前不会被后端自动读取，因此只创建 `.env` 不会自动生效。最简单的方式是在启动后端和执行迁移的同一个 PowerShell 窗口中设置上述环境变量。

## 五、迁移前检查 PostgreSQL

先执行只读环境检查，确认数据库、用户和权限正确：

```powershell
python scripts/inspect_postgres_environment.py
```

检查结果至少应满足：

- 能连接目标数据库。
- `can_connect_database` 为 `true`。
- `can_create_in_schema` 为 `true`。
- 数据库和用户是你预期的目标，而不是其他项目的数据库。

## 六、初始化 PostgreSQL 表结构

该命令创建后端 `public` schema 和 CV 使用的 `cv_analysis` schema：

```powershell
python scripts/init_postgres_db.py
```

如果只需要后端表、不需要 CV 表：

```powershell
python scripts/init_postgres_db.py --cv-schema ""
```

该命令可以重复执行，不会因为已有表而覆盖数据。

## 七、迁移前 dry-run

默认 SQLite 文件路径是：

```text
backend/db/tennis_data_master.sqlite3
```

先进行只读审计和 dry-run。该步骤不会连接或写入 PostgreSQL：

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dry-run `
  --report migration-dry-run.json
```

检查输出中的 `source_issues`。正常情况下应为空数组：

```json
"source_issues": []
```

如果 SQLite 文件不在默认位置，替换 `--sqlite` 后面的路径：

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite D:\data\tennis_data_master.sqlite3 `
  --dry-run `
  --report migration-dry-run.json
```

## 八、执行正式迁移

确认 dry-run 没有问题后，执行正式迁移：

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dsn $env:TENNIS_DATABASE_URL `
  --report migration-report.json
```

迁移特性：

- SQLite 源文件以只读模式打开。
- 按外键依赖顺序分批导入数据。
- 目标中已有完全相同的主键记录时跳过。
- 目标中已有相同主键但内容不同时报告冲突，不会覆盖目标记录。
- 失败后可以修复问题并重复执行，已成功导入的相同记录会被跳过。

如果只迁移某张或某几张表，可以重复使用 `--table`：

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dsn $env:TENNIS_DATABASE_URL `
  --table users `
  --table social_posts `
  --table post_media `
  --report migration-report.json
```

## 九、验证迁移结果

迁移完成后执行：

```powershell
python scripts/validate_postgres_migration.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dsn $env:TENNIS_DATABASE_URL `
  --report validation-report.json
```

重点检查：

- 各表的 `source` 和 `target` 行数是否一致。
- 是否存在 `missing_expected` 表。
- 外键检查是否通过。
- `unique_checks` 中的重复数是否为 `0`。
- 消息、附件、媒体、通知和未读计数检查是否有异常。

验证报告和迁移报告都是本地审计文件，已被 Git 忽略。不要把包含数据库连接信息或敏感数据的报告提交到仓库。

## 十、可选：修复未读计数缓存

迁移验证可能报告 `user_inbox_counters` 或会话未读数存在 cache drift。迁移工具不会自动覆盖这些派生缓存。先执行只读检查：

```powershell
python scripts/reconcile_inbox_counters.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dsn $env:TENNIS_DATABASE_URL `
  --report inbox-dry-run.json
```

确认报告中的差异确实需要修复后，再执行：

```powershell
python scripts/reconcile_inbox_counters.py `
  --sqlite backend/db/tennis_data_master.sqlite3 `
  --dsn $env:TENNIS_DATABASE_URL `
  --execute `
  --report inbox-reconcile.json
```

## 十一、CV 历史 SQLite 数据（如果存在）

后端主数据库迁移不会自动复制 CV 的历史 SQLite 文件。若存在历史 CV 数据库，需要单独迁移到 `cv_analysis` schema：

```powershell
python scripts/migrate_cv_sqlite_to_postgres.py `
  --sqlite cv/data/output/match_analysis.sqlite `
  --dsn $env:TENNIS_DATABASE_URL `
  --schema cv_analysis `
  --dry-run
```

确认 dry-run 正常后，去掉 `--dry-run` 执行正式导入：

```powershell
python scripts/migrate_cv_sqlite_to_postgres.py `
  --sqlite cv/data/output/match_analysis.sqlite `
  --dsn $env:TENNIS_DATABASE_URL `
  --schema cv_analysis
```

## 十二、媒体文件不会随数据库迁移

迁移脚本只迁移数据库记录，不复制以下文件：

- 视频原文件。
- 视频缩略图。
- 消息媒体文件。
- CV 分析输出文件。

这些文件需要单独备份并放到同学电脑上对应的存储目录。数据库中的路径必须与实际文件位置一致，否则页面可能显示记录但无法播放视频或显示缩略图。

## 十三、启动后端验证接口

迁移和验证完成后，在仍然设置了 `TENNIS_DATABASE_URL` 的 PowerShell 窗口启动后端：

```powershell
conda activate tennis
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

另开一个 PowerShell 窗口访问：

```powershell
Invoke-WebRequest http://localhost:8000/health
```

然后用移动端或 API 客户端登录，检查：

- `/api/v1/me/profile-content` 不再返回 PostgreSQL `GroupingError`。
- 个人动态、比赛、训练和课程数量与迁移前一致。
- 带媒体的帖子和活动可以正常显示缩略图或视频路径。

## 十四、常见问题

### `TENNIS_DATABASE_URL must be configured`

说明当前 PowerShell 窗口没有设置 DSN。重新执行第四节的 `$env:TENNIS_DATABASE_URL = ...`。环境变量只对当前窗口和从该窗口启动的进程有效。

### `password authentication failed`

检查 PostgreSQL 用户名、密码和数据库名。密码包含特殊字符时，确认已经 URL 编码；也可以先使用 `psql` 验证同一用户能否连接。

### `database does not exist`

先执行第三节的数据库创建命令，或使用 PostgreSQL 管理工具创建 `tennis_data_master`。

### `permission denied for schema public`

使用有 `CREATE` 权限的数据库用户执行初始化，或者由数据库管理员授予目标用户权限后再重试。

### 迁移报告出现 conflicts

这表示目标中相同主键的记录内容不同。脚本不会覆盖这些记录。先保留报告，确认哪一侧数据正确，再人工处理冲突，之后重新执行迁移。

### PostgreSQL 已有数据，是否可以重新迁移

可以重复执行。完全相同的主键记录会跳过；不同内容会报告冲突。不要为了重试而删除整个数据库或执行 `TRUNCATE`。

