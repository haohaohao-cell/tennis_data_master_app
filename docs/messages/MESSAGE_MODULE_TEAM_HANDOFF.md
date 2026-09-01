# Message Module Team Handoff

消息模块支持消息专用图片和视频媒体：intent、分块写入、完整性校验、完成、取消、鉴权读取、消息事务绑定、首帧缩略图和清理。Stage 11D 已提供认证、设备绑定、单实例 WebSocket 唤醒通道；REST sync 仍是权威恢复路径。Stage 12 已实现文本编辑、reaction、受控转发和基础群成员/角色治理；Stage 13 已实现业务对象卡片、读取时权限水合和安全对象转发；Stage 14 已实现会话内搜索、举报审核、通知/指标基础及受保护导出与删除请求编排；Stage 16B 已将测试导出存储和进程内 realtime 分发收敛为可替换依赖边界。真实 Push、SSE、视频转码、复杂群治理、多实例 fan-out、生产对象存储、账户硬删除、自动匿名化和 AI 自动审核仍未实现。

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
`ffprobe`/`ffmpeg` 缺失时视频校验或缩略图生成返回稳定失败码；类型检查
必须以当次 `npx tsc --noEmit` 的实际输出为准，不将历史错误或历史通过结论
当作当前工作区证据。

本地 SQLite 默认文件是已确认的可信迁移源，但每次迁移仍须以只读方式审计文件指纹、
表结构、外键和计数。审计命令必须带上已批准的 SHA-256；任何派生 cache drift 都不得
在源库中修复或覆盖。

默认消息媒体限制为：图片 15 MiB、图片/视频 4,000 万像素、视频 200 MiB、
视频最长 5 分钟，媒体未完成时默认保留 24 小时；这些值可通过后端环境变量
调整。当前文件系统媒体存储和性能数据均为本地测试能力，不代表生产容量。

所有本地报告、数据库、WAL/SHM 和媒体文件不得提交；密码、完整 DSN、storage key 和绝对敏感路径不得进入代码、文档或日志。

阶段十一 A 已完成架构设计，阶段十一 B 已实现并通过 SQLite 和本地 PostgreSQL 验证：公开多设备
sync 使用独立的 `user_sync_events`、设备注册/撤销和 per-device checkpoint，
不复用内部 Outbox 的 processed 状态。两种数据库验证互不替代。Stage 11D 的
WebSocket 只推送提交后的最小 wake-up envelope，不持有消息数据且无多实例 fan-out。
Fake Push 仅支持测试用 `channel='push'`；当前仍没有 APNs/FCM、SSE、真实 Push
token 或真实设备服务。PostgreSQL 证据仅适用于本地隔离 schema，发布候选审计不代表
已部署或已完成生产数据库验证。当前 dirty workspace 包含 Stage 11--16B 代码、测试、
文档和审计材料；提交前以 `docs/STAGE17_REPOSITORY_AUDIT.md` 的分类为准。
