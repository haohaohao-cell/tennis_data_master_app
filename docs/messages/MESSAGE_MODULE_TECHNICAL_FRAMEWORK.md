# 消息模块技术框架

## 1. 文档目的

本文档描述消息模块的技术架构、数据边界、接口契约、关键链路、可靠性要求和演进计划。内容以当前仓库实现为基线，不把尚未接入的 WebSocket、移动推送供应商或端到端加密描述为现有能力。

适用范围：

- 移动端消息中心：通知、聊天、消息请求、未读角标。
- 单聊和基础群聊。
- 消息发送、历史查询、搜索、已读、回复、撤回、置顶、免打扰、隐藏。
- 通知事件、站内通知和 Push 意图判断。

不在本文档范围内：Admin 消息运营后台、完整客服工单系统、音视频通话、端到端加密协议。

## 2. 当前架构概览

```text
Expo App
  ├─ app/(tabs)/messages.tsx       消息中心
  ├─ app/chat/[id].tsx             会话详情
  ├─ api/messages.ts               REST 类型与调用封装
  └─ api/messageNotificationRoute.ts 通知目标路由
          │ HTTPS + Bearer
          ▼
FastAPI /api/v1
  └─ backend/app/messages/router.py
          │ 参数校验 / 鉴权后调用
          ▼
  backend/app/messages/service.py
          │ 事务、权限、计数、序列号、通知事件
          ▼
SQLite
  ├─ chat_conversations
  ├─ chat_conversation_members
  ├─ chat_messages
  ├─ chat_message_attachments
  ├─ chat_message_media
  ├─ chat_message_requests
  ├─ notification_events
  ├─ user_notifications
  └─ user_inbox_counters
```

当前客户端使用前台轮询：消息中心约 8 秒一次，聊天详情约 3 秒一次；服务端已提供 reconciliation 接口用于修复轮询期间已加载消息的状态变化。Push 目前停留在后端 Push intent 契约和偏好判断层，尚未连接 APNs/FCM 投递服务。

## 3. 分层职责

### 3.1 移动端表现层

文件：`app/app/(tabs)/messages.tsx`、`app/app/chat/[id].tsx`

- 管理通知 / 聊天 / 请求三个视图。
- 维护加载、空数据、错误、重试和未登录状态。
- 聊天页维护本地消息合并、发送中、失败重试、引用回复、撤回和滚动定位。
- 只使用服务端返回的通知 `target` 做跳转，不根据任意 URL 或文案猜测路由。

移动端不得承担服务端权威状态计算。未读数、已读水位、屏蔽关系、会话排序和消息序号均以服务端结果为准。

### 3.2 API 适配层

文件：`app/api/messages.ts`、`app/api/messageNotificationRoute.ts`

- 提供 TypeScript 请求函数和响应类型。
- 统一处理访问令牌、超时和可重试错误。
- `client_message_id` 用于发送幂等和本地消息与服务端消息合并。
- 适配层不保存业务状态，不直接修改 UI 状态。

### 3.3 后端路由层

文件：`backend/app/messages/router.py`

- 统一挂载 `/api/v1/messages` 和 `/api/v1/notifications` 相关用户接口。
- 通过 `get_current_user` 完成 Bearer 鉴权。
- 使用 Pydantic response model 固化跨端契约。
- 不在路由层编排事务或拼接 SQL。

### 3.4 后端服务层

文件：`backend/app/messages/service.py`

- 负责会话创建、成员校验、隐私策略、双向拉黑校验。
- 在同一数据库事务中写入消息、更新会话最新消息、递增成员未读计数、恢复隐藏会话，并生成通知事件。
- 负责已读水位单调推进、消息撤回、回复目标可见性和对象引用校验。
- 负责 Push intent 的偏好、免打扰和消息类型判断，但不负责第三方推送调用。

### 3.5 持久化层

数据库脚本：`backend/db/social_message_schema.sql`

SQLite 是当前开发和单实例部署的事实存储。所有时间字段使用服务端 UTC；所有业务主键使用 UUID 字符串；消息顺序使用会话内 `message_seq`，不能使用客户端时间排序作为权威顺序。

`backend/db/schema.sql` 是新 SQLite 数据库的完整基线，其中包含
`user_notification_preferences`。`backend/db/social_message_schema.sql` 是运行时对已有数据库执行的幂等消息升级，保留同一表定义以补齐旧库。执行
`python scripts/init_sqlite_db.py --db <数据库路径>` 会调用该运行时升级路径；重复执行安全，完成后可用 `PRAGMA foreign_key_check` 验证。

## 4. 核心领域模型

### 4.1 会话

`chat_conversations` 表示会话本体：

- `conversation_type`: `direct` 或 `group`。
- Direct 使用 `direct_pair_key` 保证双方唯一会话。
- Group 可绑定 `group_type`、`context_type`、`context_id`，支持课程、训练或业务上下文扩展。
- `last_message_id`、`last_message_seq`、`last_message_preview`、`last_message_at` 用于会话列表快速展示。

### 4.2 会话成员

`chat_conversation_members` 表示用户在会话中的个人状态：

- 成员状态：`active`、`left`、`removed`。
- 已读水位：`last_read_message_id`、`last_read_message_seq`、`last_read_at`。
- 未读计数：`unread_count`。
- 用户偏好：`pinned_at`、`muted_until`、`archived_at`。

置顶、免打扰和隐藏必须保持成员级别，不能写到会话本体，否则会错误影响另一位用户。

### 4.3 消息

`chat_messages` 是不可变顺序记录，主要字段包括：

- `message_seq`: 会话内单调递增序号。
- `message_type`: 文本、媒体、业务对象分享、分析卡片、系统事件等。
- `text_content`、`payload_json`：内容和扩展负载。
- `target_object_type/id`、`context_object_type/id`：对业务对象的通用引用，不直接拥有业务对象。
- `reply_to_message_id`：同一会话中的回复关系。
- `client_message_id`：客户端幂等键。
- `status`: `sent`、`revoked`、`deleted`。

撤回采用中性 tombstone，不删除原行，不改变序号，不回滚已读或未读水位；撤回消息不进入历史搜索。

### 4.4 附件

`chat_message_attachments` 保存媒体和对象卡片的展示元数据。消息表只引用业务对象，不把 Post、Activity、Video 或 Lesson 的业务字段复制进来。附件展示前必须再次执行当前用户的对象访问权限检查。

`chat_message_media` 是消息专用图片和视频媒体表，独立维护 owner、上传状态、私有 storage key、缩略图 key、缩略图状态、清理时间/错误、实际 MIME/大小/尺寸、幂等键和过期时间；不与 Post、Activity 或通用视频上传表建立隐式复用。清理默认为 dry-run，只有显式 execute 才会删除消息媒体根目录下的安全候选文件。

消息媒体上传 API 为 `/messages/media/upload-intents`、`/messages/media/{media_id}/file`、`complete`、`cancel`、元数据读取和鉴权内容读取。生命周期为 `created → uploading → uploaded → attached`，异常分支为 `failed`、`expired`、`deleted`。文件传输不在数据库事务内；完成阶段校验真实图片格式和尺寸并生成 JPEG 缩略图，或以 `ffprobe` 校验真实视频流、容器、编解码、尺寸、时长和校验和，再以 `ffmpeg` 生成首帧缩略图。图片仅允许 JPEG、PNG、WebP、GIF，限制 15 MB 和 4,000 万像素；视频仅允许受支持容器，限制 200 MiB、5 分钟和 4,000 万像素；不接受 SVG、音频或任意文件。缩略图失败不改变已校验原图状态，记录 `thumbnail_status` 和失败码。

`client_upload_id` 只负责上传意图幂等，`client_message_id` 只负责消息幂等。上传完成不会创建消息；发送 `image` 或 `video` 消息时服务端重新校验媒体属于当前用户、状态为 `uploaded` 且未绑定，并在同一消息事务中绑定附件、更新会话和未读。App 对视频持久化这两个独立 ID 和可恢复的本地文件元数据；重启后重用它们，并以 `client_message_id` 恢复发送结果，避免重复绑定。媒体绑定后只允许当前 active 会话成员读取，撤回/删除或成员退出后返回不可用；响应永不返回内部 storage key。

`post_share` 使用同一对象引用模型，不复制完整 Post 正文或原始媒体路径。消息响应仅在当前会话成员通过实时 Post 权限检查后提供最小 `share_card`（标题、截断摘要、作者、可见性和可选视频缩略图）；对象被删除、隐藏、未发布、被拉黑或当前不可见时返回不含内容的 `unavailable` 状态。历史、reconcile 和搜索在一页内批量读取 Post、权限关系和封面，避免按消息数增长的 Post hydration 查询；单消息发送仍只读取其自身卡片。数据库和运行时异常必须向上暴露，不能伪装为对象不可用。会话内 Post 分享使用与普通消息相同的会话事务锁，并必须携带 `client_message_id`，以避免网络重试重复写消息、未读数、隐藏会话恢复和 share 计数。本能力不调用 Post 或网球日记上传接口；`video_share` 等后续类型复用对象卡片协议，但本期不实现 UI。

消息响应同时提供通用 `business_object_card` 外壳，作为对象卡片的权威状态来源；它以 `kind`、有限 `object_type`、`object_id`、`state`、最小展示字段、`metadata` 和安全不可用原因为基础。`social_post` 已实现实时权限 hydration；`video`、`tennis_activity`、`lesson` 和 `analysis` 当前返回无内容的 `unsupported`，直到各对象提供消息读取权限适配器。旧 `share_card` 仅为 `post_share` 兼容字段，由同一 hydration 结果派生。

Post 分享幂等键作用域为 `(authenticated_user_id, client_message_id)`。会话分享必须携带非空键；同一键只有在 Post、分享目标类型、会话、channel、message_text、消息类型、对象引用和 payload 全部一致时才是安全重试，服务端返回第一次提交的 share/message 和原始对象引用。任一字段不同返回 HTTP 409 `CLIENT_MESSAGE_ID_CONFLICT`，不返回旧记录或卡片，也不产生消息、未读、隐藏会话恢复、通知或 `share_count` 副作用。数据库部分唯一索引负责并发最终保护，应用层负责完整身份比较。旧 SQLite 升级会添加 nullable 幂等字段；检测到既有重复键时启动明确失败，不删除数据。幂等重试仍按当前 Post 权限 hydration `business_object_card`；冲突响应不包含旧卡片。Post 分享本身不复用 Post 上传接口，也不接入实时或 Push。

### 4.5 消息请求

`chat_message_requests` 表达陌生人发起的请求，状态为 `pending`、`accepted`、`declined`、`blocked` 或 `canceled`。接受请求时在事务中创建或复用 Direct 会话，并结束 pending 状态。

### 4.6 通知

通知采用两层模型：

1. `notification_events`：一次业务事件。
2. `user_notifications`：某个接收者的可见、已读和展示状态。

消息请求既有独立请求计数，也可能存在关联通知记录；客户端使用服务端提供的聚合字段避免重复展示。

## 5. API 分组

### 会话与请求

```text
POST /messages/direct-conversations
POST /messages/groups
GET  /messages/conversations
GET  /messages/conversations/search
POST /messages/requests
GET  /messages/requests
POST /messages/requests/{id}/accept
POST /messages/requests/{id}/decline
```

### 会话状态

```text
POST   /messages/conversations/{id}/pin
DELETE /messages/conversations/{id}/pin
POST   /messages/conversations/{id}/mute
DELETE /messages/conversations/{id}/mute
POST   /messages/conversations/{id}/hide
DELETE /messages/conversations/{id}/hide
POST   /messages/conversations/{id}/read
```

### 消息读写

```text
GET  /messages/conversations/{id}/messages
POST /messages/conversations/{id}/messages
POST /messages/conversations/{id}/messages/reconcile
GET  /messages/conversations/{id}/messages/search
POST /messages/conversations/{id}/messages/{message_id}/recall
```

### 计数、通知与偏好

```text
GET   /messages/unread-counts
GET   /notifications
POST  /notifications/{user_notification_id}/read
POST  /notifications/read-all
GET   /notifications/preferences
PATCH /notifications/preferences
```

分页当前使用 page/page_size 或 before_seq；消息历史和消息搜索以 `before_seq` 作为稳定向前游标。后续新增接口应优先使用游标，而不是依赖 offset 分页。

## 6. 关键业务链路

### 6.1 发送消息

```text
客户端生成 client_message_id
  → 本地插入 sending 状态
  → POST 消息接口
  → 服务端校验成员、拉黑、消息类型、回复目标和对象权限
  → 事务写入 chat_messages / attachments
  → 更新会话最新消息
  → 更新其他成员 unread_count 和 user_inbox_counters
  → 清除 active 成员 archived_at
  → 生成 Push intent（若符合偏好和免打扰）
  → 返回权威消息
  → 客户端按 client_message_id 合并本地记录
```

同一 `client_message_id` 的重试必须返回第一次已提交的消息，不能重复递增未读数或重复产生业务副作用。

### 6.2 读取与已读

聊天页拉取最近消息后，客户端只把实际观察到的最大 `message_seq` 发送给 `/read`。服务端只允许已读水位前进，不允许回退。Direct 会话返回对方已读水位，客户端据此推导“已读”状态。

### 6.3 轮询与一致性修复

轮询响应可能覆盖发送或撤回期间的本地变更，因此客户端需要：

- 保存请求发出时的消息快照；
- 保护本地 sending/failed 和刚发生 mutation 的记录；
- 对已加载的持久化消息调用 reconcile；
- 最终以服务端记录替换本地临时记录。

未来接入 WebSocket/Push 时，实时事件只负责唤醒和增量更新，REST 历史接口仍是断线补偿和最终一致性的依据。

## 7. 安全与隐私边界

- 所有用户接口要求 Bearer 鉴权和 active user 校验。
- 会话历史、已读和 reconcile 仅限当前 active member。
- Direct 发送前执行双向 block 检查；被拉黑时允许按产品策略保留历史查看，但禁止继续发送。
- 消息请求遵循接收方 `direct_message_policy` 和 `allow_message_requests`。
- 回复目标必须属于同一会话且对当前成员可访问；跨会话目标返回统一错误，不泄露目标内容。
- 撤回消息只对原发送者生效，媒体、群消息和系统消息不能按 Direct 文本撤回规则处理。
- Push payload 只包含最小路由和标识字段，不包含手机号、邮箱、消息正文、附件内容或私有业务对象数据。
- 附件和分享卡片必须在读取时重新检查源对象权限，避免“消息已授权但对象已变为不可见”造成越权。

## 8. 一致性、性能与可靠性要求

### 数据一致性

- 消息写入、会话预览、成员未读计数和消息请求状态变更必须在同一事务中完成。
- 计数表是可重建缓存，定期提供校准任务或管理脚本，避免异常中断造成角标漂移。
- 服务端 UTC 是所有时间计算的唯一依据，客户端不应自行判断 mute 是否过期。

### 性能基线

- 会话列表查询先过滤 active membership 和非隐藏会话，再按 pinned/activity/时间排序。
- 消息历史按 `conversation_id + message_seq` 索引访问，默认单页不超过 100 条。
- 附件批量 hydration，避免逐消息查询附件。
- Post business object 卡片按消息页批量 hydration；发送者、回复和附件也必须保持固定数量查询增长。
- 搜索优先使用索引；数据规模扩大后迁移 SQLite FTS5 或独立搜索服务。

### 可靠性

- 发送请求必须带 `client_message_id`，客户端超时后可安全重试。
- 网络错误、408、425、429 和 5xx 可重试；鉴权、权限和校验错误不可盲目重试。
- App 恢复前台时重新拉取未读数和当前会话，不能只依赖 Push。
- 实时通道必须支持断线重连、退避和游标补偿。

## 9. 可观测性与测试

建议统一记录以下指标，并携带 request id、user id（脱敏）、conversation id 和 message type：

- 发送成功率、P50/P95 发送延迟、超时率、重试率。
- Push intent 决策分布、供应商投递率、点击率。
- 未读计数校准差异、重复消息率、reconcile 命中率。
- 搜索耗时、历史加载耗时、WebSocket 重连次数。
- 举报、拉黑、消息请求接受/拒绝转化率。

测试分层：

- Schema/服务层：事务、幂等、并发、权限、计数和时间边界。
- API：请求模型、状态码、响应契约、分页和错误脱敏。
- App 静态测试：发送重试、回复、撤回、路由、轮询合并。
- 集成测试：离线发送后恢复、Push 点击、隐藏会话恢复、对象权限失效。

现有相关测试位于 `backend/tests/message_*` 和 `app/tests/message_*`，新增能力应沿用这些测试命名和 fixture 模式。

## 10. 演进路线

### P0：一致性与基础体验

1. 底部消息角标统一使用 `messages_tab_badge_count`。
2. 增加隐藏会话管理和未读发现入口。
3. 在设置页接入通知偏好。
4. 增加计数校准和关键链路监控。

### P1：实时与离线

1. 接入 APNs/FCM 投递服务，复用现有 Push intent。
2. 接入 WebSocket 或 SSE，使用 `message_seq`/事件游标补偿。
3. 建立本地 outbox，支持 App 重启后的自动重试。
4. 统一会话、通知和消息的游标分页。

### P2：网球业务消息

1. Post、Activity、视频片段、课程和 AI 分析卡片分享。
2. 富媒体上传、缩略图和失败重试。
3. 群成员、群角色、邀请和退出管理。
4. 消息内对象权限失效和过期状态的统一展示。

### P3：规模化与治理

1. FTS5/独立搜索索引和消息定位。
2. 已发送/已送达/已读、输入状态和在线状态。
3. 反骚扰、频控、敏感内容审核和批量举报处理。
4. PostgreSQL 迁移基础设施已提供；生产配置 DSN 后以 PostgreSQL 为唯一写入权威数据库，实时事件、Push 和搜索仍需作为独立能力建设。

## 11. 变更原则

- `shared/api-schema/social-messages.md` 是跨端契约的权威文档。
- 变更字段、枚举或计数语义时，同时更新 backend schemas、App API 类型、测试和本技术框架。
- 数据库结构变更必须提供可执行迁移脚本，并说明 SQLite 现有数据兼容策略。
- SQLite 到 PostgreSQL 使用 `scripts/migrate_sqlite_to_postgres.py`，支持只读源、dry-run、分批重跑、冲突报告和导入后校验；原 SQLite 文件保留用于恢复和对比。
- 消息序号、幂等键、未读计数、会话最后消息和消息媒体绑定继续在事务边界内更新；`chat_message_media` 与 Post/网球日记上传表保持隔离。
- 新增用户可见页面、面板或弹层时同步更新 `docs/ui/UI_NAMING_REGISTRY.md`。
- 保持消息表与 Post、Activity、Video、Lesson 等业务表解耦，通过受控引用和读取时权限校验连接业务。

## 12. 消息视频媒体

消息视频沿用 `chat_message_media` 生命周期表和
`chat_message_attachments` 关系表，不进入 Post、Activity 或业务视频表。
上传使用流式 SHA-256、`ffprobe` 实际媒体探测和 `ffmpeg` 首帧缩略图；缩略图
失败不影响已验证原视频。读取时重新执行成员、消息状态、绑定和文件存在性
检查，API 永不返回 storage key。

## 13. 离线发送与事件基础

本模块提供客户端本地草稿/Outbox、服务端 `outbox_events`、发送恢复查询和
授权事件游标。客户端本地 `local_id`、`device_id`、重试计数、退避时间和
错误细节不上传；`client_message_id` 在发送用户作用域内保证幂等。App 重启
或回前台时把 `sending` 恢复成 `queued`，超时先按 client key 查询权威消息。

服务端在消息、会话预览、未读事实、收件箱缓存、媒体绑定和通知副作用同一
事务中写入 `message.created` Outbox 事件；事件写入失败则整体回滚。事件游标
按 `(created_at, event_id)` 排序，多设备分别保存游标；历史消息继续按
`message_seq` 补偿。领取使用租约字段，PostgreSQL 采用 `FOR UPDATE SKIP LOCKED`
和事务级锁，SQLite 仅承诺本地写入互斥。当前不接入真实事件消费者。

Push provider、WebSocket/SSE、消息反应、转发、输入状态、在线状态、
端到端加密和复杂群治理仍未实现。
