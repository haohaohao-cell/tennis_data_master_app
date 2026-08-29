# Message Module Team Handoff

消息模块支持消息专用图片和视频媒体：intent、分块写入、完整性校验、完成、取消、鉴权读取、消息事务绑定、首帧缩略图和清理。Push、WebSocket/SSE、实时同步、视频转码、消息反应、转发和复杂群治理仍未实现。

`chat_message_media` 是媒体生命周期和已验证文件元数据的唯一消息媒体表；`chat_message_attachments` 是消息到媒体或对象卡片的关系表。消息视频不使用 Post、Activity、`videos` 或 `app/api/uploads.ts`。`client_upload_id` 只负责上传幂等，`client_message_id` 只负责消息幂等。

SQLite 用于旧数据读取、迁移输入和轻量回归；PostgreSQL 是配置数据库 URL 后的写入权威。迁移前必须通过只读完整性审计确认 SQLite 源库，并将派生 inbox cache drift 显式记录；不得静默修复或覆盖源文件。

常用检查：

```powershell
python scripts/audit_stage9_source_integrity.py --expected-sha256 <approved_source_sha256>
python backend/tests/message_video_upload_api.py
python backend/tests/message_media_upload_api.py
python backend/tests/message_outbox_api.py
python -m compileall -q backend
```

App 依赖安装和类型检查：

```powershell
Set-Location app
npm ci
& .\node_modules\.bin\tsc.cmd --noEmit
python tests/message_video_static.py
python tests/message_image_static.py
```

消息后端全量回归应在独立子进程中清除 `TENNIS_DATABASE_URL` 和
`TENNIS_POSTGRES_DSN`，为每个测试提供临时 `TENNIS_DB_PATH`；不得让回归测试
读取默认 SQLite。PostgreSQL 回归则只使用本地 `tennis_messages_test`、
`test_user` 和新建的 `message_*` 隔离 Schema，并通过 DSN 的 `search_path`
显式选择 Schema。

常见错误：未配置 PostgreSQL 环境变量时停止数据库操作；
`ffprobe`/`ffmpeg` 缺失时视频校验或缩略图生成返回稳定失败码；类型检查错误
必须区分消息模块错误和其他页面错误。当前 App 类型检查仍有 profile 页面
的既有错误，不能写成全项目 typecheck 通过。

本地 SQLite 默认文件是已确认的可信迁移源，但每次迁移仍须以只读方式审计文件指纹、
表结构、外键和计数。审计命令必须带上已批准的 SHA-256；任何派生 cache drift 都不得
在源库中修复或覆盖。

默认消息媒体限制为：图片 15 MiB、图片/视频 4,000 万像素、视频 200 MiB、
视频最长 5 分钟，媒体未完成时默认保留 24 小时；这些值可通过后端环境变量
调整。当前文件系统媒体存储和性能数据均为本地测试能力，不代表生产容量。

所有本地报告、数据库、WAL/SHM 和媒体文件不得提交；密码、完整 DSN、storage key 和绝对敏感路径不得进入代码、文档或日志。
