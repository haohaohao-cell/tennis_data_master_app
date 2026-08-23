# 网球全局数据字典

版本：v0.1  
建立日期：2026-07-22  
来源文档：

- `docs/data/网球数据库设计.md`
- `docs/data/网球数据方案简明版.md`

本文件是网球数据系统的全局数据字典，用于约束后端、前端、App、数据库、CV、算法服务、逐帧数据文件和接口载荷中的字段命名、单位、枚举、含义和派生关系。后续开发如新增字段、指标、枚举或算法结果，应优先更新本文件，再同步代码和数据库迁移。

---

## 一、使用原则

1. 同一数据项在数据库、后端 DTO、前端类型、App 模型、CV 输出和接口文档中必须使用同一个字段名。
2. 当前核心落库字段以 `users`、`coach_applications`、`coach_profiles`、`admin_users`、`admin_credentials`、`auth_identities`、`auth_sessions`、`auth_verification_codes`、`lessons`、`lesson_students`、`tennis_activities`、`videos`、`video_shares`、`social_posts`、`social_post_stats`、`post_reactions`、`post_favorites`、`post_comments`、`post_shares`、`post_media`、`user_follows`、`user_social_stats`、`user_blocks`、`user_privacy_settings`、`user_notification_preferences`、`user_post_views`、`user_post_hides`、`chat_conversations`、`chat_conversation_members`、`chat_messages`、`chat_message_attachments`、`chat_message_requests`、`notification_events`、`user_notifications`、`user_inbox_counters`、`content_reports`、`points`、`shots` 为准。
3. Web 看板指标、趋势、诊断、视频片段、可视化点和明细页计算字段，除非出现在四张核心表中，否则均为 `非落库字段`。
4. `非落库字段` 可以由数据库字段、`frame_data.jsonl`、算法结果或接口聚合计算得到，不要求第一版新增数据库列。
5. `NULL` 表示未采集、未标注、不适用或历史数据缺失；`unknown` 表示已完成分析但无法可靠分类。
6. 布尔字段中，`NULL`、`false`、`true` 含义必须严格区分。`NULL` 不是 `false`。
7. 比例统一保存为 `0～1`，评分统一保存为 `0～100`，置信度统一保存为 `0～1`。

---

## 二、数据分层

| 数据层 | 是否持久化 | 主要载体 | 说明 |
| --- | --- | --- | --- |
| 认证、登录身份、会话与后台权限 | 落库 | `users`、`admin_users`、`admin_credentials`、`auth_identities`、`auth_sessions`、`auth_verification_codes` | App 内部用户、后台管理员授权、后台登录凭据、手机号/微信/Apple 等登录身份、设备会话和验证码记录 |
| 教练身份申请与资料 | 落库 | `coach_applications`、`coach_profiles`、`users` | 普通用户申请认证教练或非职业教练，管理员审核后生成或更新用户扩展教练身份 |
| 用户、活动、课程、视频与动态 | 落库 | `users`、`lessons`、`lesson_students`、`tennis_activities`、`videos`、`video_shares`、`social_posts`、`social_post_stats`、`post_media` | 用户身份、个人活动、课程关系、原始视频资产、分享、动态和动态统计 |
| 社交关系、内容流行为、聊天与通知 | 落库 | `post_reactions`、`post_favorites`、`post_comments`、`post_shares`、`user_follows`、`user_social_stats`、`user_blocks`、`user_privacy_settings`、`user_notification_preferences`、`user_post_views`、`user_post_hides`、`chat_conversations`、`chat_conversation_members`、`chat_messages`、`chat_message_attachments`、`chat_message_requests`、`notification_events`、`user_notifications`、`user_inbox_counters`、`content_reports` | Post 点赞/收藏/评论/分享、关注/互关、拉黑、隐私、Push 投递偏好、浏览/隐藏、私信、群聊、陌生人消息请求、未读计数、通知事件、用户通知收件箱和举报 |
| 分与击球事实 | 落库 | `points`、`shots` | 每分、每拍、触球、落点、结果、置信度 |
| 逐帧 CV 数据 | 文件持久化 | `frame_data.jsonl` | 每帧检测、跟踪、单应矩阵、球员位置、CV 置信度 |
| 统计指标 | 非落库字段 | API 聚合结果 | Web/App 看板和历史趋势使用 |
| 诊断与建议 | 非落库字段 | 算法/API 结果 | P1/P2 规则或 AI 诊断结果 |
| 可视化点 | 非落库字段 | API 聚合结果 | 热力图、落点图、移动轨迹、击球位置图 |
| 视频片段 | 非落库字段 | API 聚合结果 | 高光、问题片段、战术片段 |

---

## 三、命名规则与单位

### 1. 字段命名

| 规则 | 约定 |
| --- | --- |
| 字段格式 | 统一使用 `snake_case` |
| 数量 | `_count` |
| 比例 | `_rate` |
| 评分 | `_score` |
| 平均值 | `avg_` |
| 最大值 | `max_` |
| 标准差 | `_std` |
| 时间 | `_ms` |
| 距离 | `_m` |
| 场地坐标 | `_x_m`、`_y_m` |
| 面积 | `_m2` |
| 速度 | `_mps` |
| 像素 | `_px` |

### 2. 全局单位

| 数据 | 单位 | 字段后缀 |
| --- | --- | --- |
| 场地坐标 | 米 | `_x_m`、`_y_m` |
| 距离 | 米 | `_m` |
| 面积 | 平方米 | `_m2` |
| 球速、球员速度 | 米/秒 | `_mps` |
| 角度 | 度 | `_deg` |
| 视频内时间 | 毫秒 | `_ms` |
| 视频宽高 | 像素 | `_px` |
| 帧编号 | 从 0 开始 | `_frame` |
| 比例 | 0～1 | `_rate` |
| 评分 | 0～100 | `_score` |
| 置信度 | 0～1 | `confidence` 或 `_confidence` |

### 3. 跨端类型映射

| 数据库类型 | 后端/API 建议 | 前端/App 建议 | 说明 |
| --- | --- | --- | --- |
| UUID | string | string | 所有 ID 对外传输为字符串 |
| TIMESTAMPTZ | ISO 8601 string | string/Date | 保留时区信息 |
| BIGINT | int64 | number/string | 前端若有精度风险可用 string |
| INTEGER/SMALLINT | int | number | 计数、帧号、序号 |
| REAL/DOUBLE PRECISION | float | number | 速度、坐标、比例、置信度 |
| VARCHAR/TEXT/CHAR | string | string | 枚举也以 string 传输 |
| BOOLEAN | boolean/null | boolean/null | `NULL` 表示未判断或不适用 |

---

## 四、坐标系约定

所有上传记录使用相同的场地坐标系：

- 原点：球网中心在地面的投影点。
- `x` 轴：沿球网方向。
- `y` 轴：沿球场长度方向。
- 坐标不随摄像机位置变化。
- 坐标不随球员换边变化。
- 坐标由单应矩阵从图像坐标转换得到。
- 标准球场尺寸写在后端公共配置中，不需要每次上传都存储。

球员位置统一使用：人体检测框底边中心经过当前有效单应矩阵转换后的场地坐标。

`contact_projected_x_m` 和 `contact_projected_y_m` 是空中球通过地面单应矩阵得到的二维投影，不表示真实三维触球位置。

---

## 五、球员槽位

当前只处理单打。每次上传中的两个球员统一表示为：

```text
A
B
```

A、B 是本次上传中的球员槽位，不一定是注册用户。

示例：

```text
player_a_user_id = 当前登录用户
player_b_user_id = NULL
player_b_name = "训练对手"
```

---

## 六、全局枚举

### 1. 用户、视频与业务对象枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `status` | `active`、`disabled`、`deleted` | 用户状态 |
| `profile_completed` | `true`、`false` | 用户资料是否已完善 |
| `auth_provider` | `phone`、`wechat`、`apple` | 登录身份来源；当前仅实现 `phone` |
| `verification_purpose` | `login`、`bind_identity` | 验证码用途；当前仅实现登录验证码 |
| `playing_hand` | `right`、`left`、`unknown` | 用户主要持拍手 |
| `is_coach` | `true`、`false` | 用户是否处于兼容教练状态；完整身份以 `coach_profiles` 和最新 `coach_applications` 为准 |
| `coach_status` | `pending`、`active`、`disabled`、`rejected` | 兼容教练状态；审核中写 `pending`，通过写 `active`，暂停写 `disabled` |
| `coach_type` | `certified`、`non_professional` | 教练类型：认证教练、非职业教练 |
| `coach_application_status` | `pending`、`approved`、`rejected`、`canceled` | 教练身份申请审核状态 |
| `coach_profile_status` | `active`、`suspended`、`revoked` | 已通过教练身份的生效状态 |
| `admin_role` | `owner`、`admin`、`operator`、`viewer` | 后台管理员角色 |
| `admin_status` | `active`、`disabled` | 后台管理员授权状态 |
| `activity_type` | `casual_hit`、`match`、`serve_training`、`forehand_training`、`backhand_training`、`multi_ball_drill`、`stroke_recording`、`post_match_review`、`lesson_practice`、`coach_demo`、`other` | 个人网球活动类型 |
| `activity_location_source` | `device_gps`、`video_metadata`、`manual_legacy`、`unavailable` | Tennis Activity 定位来源 |
| `activity_coordinate_system` | `wgs84`、`gcj02` | Tennis Activity 定位坐标系 |
| `location_resolve_source` | `area_city_boundary`、`unavailable` | 经纬度解析行政区来源 |
| `visibility` | `inherit`、`private`、`friends`、`specified_users`、`lesson_coach`、`lesson_participants`、`public` | 视频可见性；`inherit` 只用于 `videos.visibility` |
| `default_visibility` | `private`、`friends`、`specified_users`、`lesson_coach`、`lesson_participants`、`public` | 网球活动默认可见性 |
| `post_visibility` | `private`、`friends`、`followers`、`specified_users`、`public` | 社交动态可见性 |
| `post_review_status` | `pending`、`approved`、`rejected` | 社交动态审核状态 |
| `post_location_scope` | `none`、`region`、`city` | 社交动态公开位置粒度 |
| `upload_status` | `pending`、`uploading`、`uploaded`、`failed`、`canceled` | 视频文件上传生命周期状态 |
| `analysis_status` | `uploaded`、`queued`、`processing`、`completed`、`failed`、`canceled` | 视频分析任务状态 |
| `lesson_type` | `private`、`group`、`camp`、`trial`、`other` | 课程类型 |
| `lesson_status` | `draft`、`scheduled`、`completed`、`canceled` | 课程状态 |
| `attendance_status` | `planned`、`attended`、`absent`、`canceled` | 学生出勤状态 |
| `share_target_type` | `user`、`lesson_coach`、`lesson_students`、`lesson_participants`、`public_link` | 视频显式分享目标类型 |
| `share_permission` | `view`、`comment`、`annotate`、`download` | 视频分享权限 |
| `share_status` | `active`、`revoked`、`expired` | 视频分享状态 |
| `post_status` | `draft`、`published`、`hidden`、`deleted` | 社交动态状态 |
| `media_type` | `video`、`video_clip`、`image`、`data_card` | 动态媒体类型 |
| `post_reaction_type` | `like` | Post 互动反应类型；第一版只实现点赞 |
| `post_interaction_status` | `active`、`canceled` | Post 点赞和收藏事实状态 |
| `post_comment_status` | `active`、`deleted`、`hidden` | Post 评论状态 |
| `post_share_target_type` | `conversation`、`user`、`external`、`copy_link` | Post 分享目标类型 |
| `follow_status` | `active`、`canceled` | 关注关系状态 |
| `direct_message_policy` | `everyone`、`following`、`friends` | 用户私信接收策略 |
| `message_request_status` | `pending`、`accepted`、`declined`、`blocked`、`canceled` | 陌生人消息请求状态 |
| `report_target_type` | `user`、`social_post`、`post_comment`、`chat_message`、`chat_conversation`、`video` | 举报目标类型 |
| `report_reason_type` | `spam`、`harassment`、`inappropriate`、`fraud`、`privacy`、`other` | 举报原因类型 |
| `report_status` | `pending`、`reviewing`、`resolved`、`rejected` | 举报处理状态 |
| `conversation_type` | `direct`、`group` | 私信或群聊 |
| `conversation_group_type` | `friend_group`、`lesson_group`、`training_group`、`coach_course_group`、`custom` | 群聊业务类型 |
| `conversation_member_role` | `owner`、`admin`、`member`、`coach`、`student` | 群聊成员角色 |
| `conversation_member_status` | `active`、`left`、`removed` | 会话成员状态 |
| `message_type` | `text`、`image`、`video`、`audio`、`file`、`post_share`、`video_share`、`activity_share`、`lesson_share`、`analysis_card`、`system_event`、`custom` | 通用消息类型 |
| `message_status` | `sent`、`revoked`、`deleted` | 消息状态 |
| `notification_category` | `interaction`、`system`、`ai`、`coach`、`lesson` | 通知分类 |
| `notification_event_type` | `follow`、`post_like`、`post_comment`、`comment_reply`、`mention`、`video_shared`、`ai_analysis_completed`、`lesson_created`、`lesson_updated`、`coach_application_reviewed`、`system_announcement`、`custom` | 通知事件类型 |
| `camera_view_angle` | `overhead`、`horizontal` | 机位垂直视角 |
| `camera_view_position` | `side`、`rear`、`front`、`rear_side`、`front_side` | 机位水平方位 |

### 2. 球员与计分枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `player_slot` | `A`、`B` | 通用球员槽位 |
| `server_slot` | `A`、`B` | 发球方 |
| `winner_slot` | `A`、`B` | 得分方 |
| `hitter_slot` | `A`、`B` | 击球者 |
| `point_winner_slot` | `A`、`B` | 由某拍结束该分时的得分方 |
| `primary_player_slot` | `A`、`B` | 用户主要关注球员，可为 `NULL` |
| `serve_number` | `1`、`2` | 非发球拍必须为 `NULL` |
| `serve_court_side` | `deuce`、`ad` | 非落库分组维度 |

### 3. 分结果枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `point_result` | `ace`、`service_winner`、`winner`、`forced_error`、`unforced_error`、`double_fault`、`unknown` | 每分统计结果 |
| `ending_reason` | `net`、`out`、`unreturned`、`unknown` | 每分层面的粗粒度结束原因 |

`ending_reason = out` 只表示这一分以出界结束。出底线或出边线的细分保存在终结拍的 `shots.error_type = long / wide`。

`ending_reason = unreturned` 表示对手没有完成合法回球，不要求视频中必须检测到第二次弹跳。`point_result = ace`、`service_winner` 或 `winner` 时都可以使用 `ending_reason = unreturned`，三者区别由 `point_result` 表达。

如果轨迹层面确实检测到第二次弹跳，保存在终结拍的 `shots.trajectory_end_type = second_bounce`，不要求同步写入 `points.ending_reason`。

### 4. 每拍结果枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `shot_role` | `serve`、`return`、`rally` | 本拍在回合中的角色 |
| `stroke_type` | `serve`、`groundstroke`、`volley`、`overhead`、`unknown` | 击球技术类型 |
| `stroke_side` | `forehand`、`backhand`、`unknown` | 击球侧 |
| `bounce_result` | `in`、`out`、`unknown` | 第一次落点是否有效 |
| `trajectory_end_type` | `opponent_hit`、`second_bounce`、`net`、`out`、`lost`、`video_end`、`unknown` | 本拍球轨迹如何结束 |
| `shot_result` | `continue`、`winner`、`error`、`serve_fault`、`let`、`unknown` | 本拍统计结果 |
| `error_forcedness` | `forced`、`unforced`、`unknown` | 受迫或非受迫 |
| `error_type` | `net`、`long`、`wide`、`unknown` | 具体失误形式 |

### 5. 非落库分析枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `rally_state` | `attack`、`neutral`、`defense`、`unknown` | 每拍回合状态 |
| `serve_direction` | `wide`、`body`、`t`、`unknown` | 发球方向 |
| `depth_zone` | `shallow`、`middle`、`deep` | 击球深度区域 |
| `shot_direction` | `crosscourt`、`down_the_line`、`center`、`unknown` | 击球线路。后续如增加边线、大角度等值，需先更新本枚举 |
| `scope_type` | `video`、`activity`、`lesson`、`set`、`game`、`point`、`history` | 统计范围 |
| `comparison_type` | `previous`、`recent_five`、`monthly`、`best`、`opponent`、`activity` | 历史对比维度 |
| `insight_type` | `strength`、`weakness`、`trend`、`warning`、`recommendation` | 诊断类型 |
| `clip_type` | `winner`、`forced_error`、`unforced_error`、`longest_rally`、`fastest_serve`、`high_quality_rally`、`typical_problem`、`tactical_pattern` | 视频片段类型 |

### 6. 球员风格标签

| 字段 | 可选值 |
| --- | --- |
| `player_style_labels` | `stable_baseliner`、`aggressive_baseliner`、`counterpuncher`、`serve_dominant`、`forehand_dominant`、`long_rally_player`、`short_point_player`、`placement_control_player`、`speed_power_player` |

---

## 七、数据库落库字段字典

### 1. `users` 用户表

一条记录代表一个 App 用户。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `user_id` | UUID | 否 | 自动生成 | 用户主键 | 主键 |
| `nickname` | VARCHAR(50) | 否 |  | 用户昵称 |  |
| `avatar_path` | TEXT | 是 |  | 头像文件路径 | 用户上传头像使用 `/storage/avatars/...` 公开路径 |
| `phone` | VARCHAR(30) | 是 |  | 手机号 | 非空时唯一 |
| `email` | VARCHAR(255) | 是 |  | 邮箱 | 非空时唯一，大小写不敏感 |
| `status` | VARCHAR(20) | 否 | `active` | 用户状态 | `active`、`disabled`、`deleted` |
| `profile_completed` | BOOLEAN | 否 | `false` | 用户资料是否已完善 | `true`、`false` |
| `playing_hand` | VARCHAR(10) | 否 | `right` | 用户主要持拍手 | `right`、`left`、`unknown` |
| `is_coach` | BOOLEAN | 否 | `false` | 是否具备教练身份 | `true`、`false` |
| `coach_status` | VARCHAR(20) | 是 |  | 教练身份状态 | `pending`、`active`、`disabled`、`rejected` |
| `coach_verified_at` | TIMESTAMPTZ | 是 |  | 教练认证时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `status IN ('active', 'disabled', 'deleted')`
- `profile_completed IN (true, false)`
- `playing_hand IN ('right', 'left', 'unknown')`
- `is_coach IN (true, false)`
- `coach_status IN ('pending', 'active', 'disabled', 'rejected') OR coach_status IS NULL`
- `is_coach = false` 时 `coach_status IS NULL`
- `PRIMARY KEY (user_id)`
- `UNIQUE INDEX lower(email) WHERE email IS NOT NULL AND deleted_at IS NULL`
- `UNIQUE INDEX phone WHERE phone IS NOT NULL AND deleted_at IS NULL`

说明：

- `users.user_id` 是系统内部用户主键，所有视频、活动、课程、动态等业务对象必须引用该字段。
- `users.phone` 是用户资料或手机号登录身份的冗余展示字段，不替代 `auth_identities` 中的登录身份记录。
- `users.avatar_path` 保存用户头像的公开访问路径；第一版本地上传头像由后端写入 `/storage/avatars/{user_id}/...`。
- 手机号、微信 openid、Apple subject 等外部身份都不应作为业务数据主键。
- 教练身份不是独立账号；`users.is_coach`、`users.coach_status`、`users.coach_verified_at` 只作为兼容字段和列表筛选字段。前端身份展示、后端权限判断和后台审核必须优先读取 `coach_profiles` 与最新 `coach_applications`。

### 1.1. `coach_applications` 教练身份申请表

一条记录代表某个普通用户提交的一次教练身份申请。被拒绝后再次申请应创建新记录，不能覆盖历史审核记录。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `coach_application_id` | UUID | 否 | 自动生成 | 教练申请主键 | 主键 |
| `applicant_user_id` | UUID | 否 |  | 申请用户 | FK: `users.user_id` |
| `application_type` | VARCHAR(30) | 否 |  | 申请类型 | `certified`、`non_professional` |
| `status` | VARCHAR(20) | 否 | `pending` | 审核状态 | `pending`、`approved`、`rejected`、`canceled` |
| `display_name` | VARCHAR(50) | 否 |  | 教练展示名称 |  |
| `real_name` | VARCHAR(50) | 是 |  | 真实姓名 |  |
| `phone` | VARCHAR(30) | 是 |  | 联系电话 |  |
| `city` | VARCHAR(80) | 是 |  | 所在城市 |  |
| `specialties` | VARCHAR(255) | 是 |  | 擅长方向 | 逗号分隔文本 |
| `coaching_experience` | TEXT | 是 |  | 教学或训练经历 |  |
| `certification_title` | VARCHAR(120) | 是 |  | 资质名称 | 认证教练申请使用 |
| `certification_file_path` | TEXT | 是 |  | 教练资质证明文件路径或 URL | 认证教练申请必填 |
| `verification_video_path` | TEXT | 是 |  | 打球、教学或技术展示视频路径或 URL | 非职业教练申请必填 |
| `note` | TEXT | 是 |  | 申请补充说明 |  |
| `reviewer_user_id` | UUID | 是 |  | 审核管理员用户 | FK: `users.user_id` |
| `reviewed_at` | TIMESTAMPTZ | 是 |  | 审核时间 |  |
| `rejection_reason` | VARCHAR(500) | 是 |  | 拒绝原因 | 拒绝时必填 |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

约束与索引：

- `application_type IN ('certified', 'non_professional')`
- `status IN ('pending', 'approved', 'rejected', 'canceled')`
- `application_type = 'certified'` 时 `certification_file_path` 必填
- `application_type = 'non_professional'` 时 `verification_video_path` 必填
- `UNIQUE INDEX (applicant_user_id) WHERE status = 'pending'`
- `INDEX (status, created_at DESC)`
- `INDEX (application_type, status)`

### 1.2. `coach_profiles` 教练资料表

一条记录代表某个用户已经通过审核后获得的教练扩展身份。认证教练和非职业教练共享同一张表，通过 `coach_type` 区分。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `coach_profile_id` | UUID | 否 | 自动生成 | 教练资料主键 | 主键 |
| `user_id` | UUID | 否 |  | 对应普通用户账号 | FK: `users.user_id`，唯一 |
| `coach_type` | VARCHAR(30) | 否 |  | 教练类型 | `certified`、`non_professional` |
| `status` | VARCHAR(20) | 否 | `active` | 教练身份状态 | `active`、`suspended`、`revoked` |
| `display_name` | VARCHAR(50) | 否 |  | 教练展示名称 |  |
| `city` | VARCHAR(80) | 是 |  | 所在城市 |  |
| `specialties` | VARCHAR(255) | 是 |  | 擅长方向 | 逗号分隔文本 |
| `coaching_experience` | TEXT | 是 |  | 教学或训练经历 |  |
| `certification_title` | VARCHAR(120) | 是 |  | 资质名称 | 仅认证教练展示认证资质标识 |
| `certification_file_path` | TEXT | 是 |  | 资质证明文件路径或 URL | 后台审核资料 |
| `verification_video_path` | TEXT | 是 |  | 非职业教练展示视频路径或 URL | 后台审核资料 |
| `approved_application_id` | UUID | 是 |  | 最近通过的申请 | FK: `coach_applications.coach_application_id` |
| `approved_by_user_id` | UUID | 是 |  | 审核通过管理员 | FK: `users.user_id` |
| `approved_at` | TIMESTAMPTZ | 否 |  | 审核通过时间 |  |
| `suspended_at` | TIMESTAMPTZ | 是 |  | 暂停时间 |  |
| `revoked_at` | TIMESTAMPTZ | 是 |  | 撤销时间 |  |
| `status_reason` | VARCHAR(500) | 是 |  | 暂停、恢复或撤销说明 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

约束与索引：

- `UNIQUE (user_id)`
- `coach_type IN ('certified', 'non_professional')`
- `status IN ('active', 'suspended', 'revoked')`
- `INDEX (status, coach_type)`
- `INDEX (user_id, status)`

### 1.3. `admin_users` 后台管理员授权表

一条记录代表一个用户被授权为后台管理员。后台权限独立于普通用户资料，管理员接口必须先通过现有登录 token 识别用户，再检查 `admin_users.status = active`。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `admin_user_id` | UUID | 否 | 自动生成 | 后台授权记录主键 | 主键 |
| `user_id` | UUID | 否 |  | 被授权用户 | FK: `users.user_id`，唯一 |
| `role` | VARCHAR(30) | 否 | `operator` | 后台管理员角色 | `owner`、`admin`、`operator`、`viewer` |
| `status` | VARCHAR(20) | 否 | `active` | 后台授权状态 | `active`、`disabled` |
| `note` | VARCHAR(255) | 是 |  | 授权备注 |  |
| `created_by_user_id` | UUID | 是 |  | 授权创建人；首次初始化可为空 | FK: `users.user_id` |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `disabled_at` | TIMESTAMPTZ | 是 |  | 禁用时间 |  |

约束与索引：

- `PRIMARY KEY (admin_user_id)`
- `UNIQUE (user_id)`
- `role IN ('owner', 'admin', 'operator', 'viewer')`
- `status IN ('active', 'disabled')`
- `user_id REFERENCES users(user_id)`
- `created_by_user_id REFERENCES users(user_id)`
- `INDEX (status, role)`

说明：

- `admin_users` 只表达后台权限，不替代 `users` 用户身份。
- 用户端接口不得读取 `admin_users` 决定普通用户业务行为。
- 后台管理员首次初始化可通过运维脚本或数据库初始化数据写入，不能开放无鉴权创建管理员入口。

### 1.4. `admin_credentials` 后台登录凭据表

一条记录代表一个后台管理员的用户名密码凭据。该表只服务后台登录，不用于 App 用户端登录。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `admin_credential_id` | UUID | 否 | 自动生成 | 后台凭据主键 | 主键 |
| `user_id` | UUID | 否 |  | 对应内部用户 | FK: `users.user_id`，唯一 |
| `username` | VARCHAR(50) | 否 |  | 后台登录用户名 | 展示值 |
| `username_normalized` | VARCHAR(50) | 否 |  | 规范化用户名 | 唯一，大小写不敏感匹配 |
| `password_hash` | VARCHAR(255) | 否 |  | 密码哈希 | PBKDF2，不存明文密码 |
| `status` | VARCHAR(20) | 否 | `active` | 凭据状态 | `active`、`disabled` |
| `last_login_at` | TIMESTAMPTZ | 是 |  | 最近后台登录时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

约束与索引：

- `PRIMARY KEY (admin_credential_id)`
- `UNIQUE (user_id)`
- `UNIQUE INDEX (username_normalized)`
- `status IN ('active', 'disabled')`
- `user_id REFERENCES users(user_id)`
- `INDEX (user_id, status)`

说明：

- `password_hash` 保存 PBKDF2-SHA256 结果，测试账号初始密码也不应明文落库。
- 后台登录必须同时满足 `admin_credentials.status = active`、`admin_users.status = active` 和 `users.status = active`。

### 1.5. `auth_identities` 登录身份表

一条记录代表某个用户绑定的一种登录身份。一个用户可以绑定多个登录身份。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `identity_id` | UUID | 否 | 自动生成 | 登录身份主键 | 主键 |
| `user_id` | UUID | 否 |  | 所属内部用户 | FK: `users.user_id` |
| `provider` | VARCHAR(30) | 否 |  | 登录身份来源 | `phone`、`wechat`、`apple` |
| `provider_subject` | VARCHAR(255) | 否 |  | provider 原始身份标识 | 手机号、微信 openid、Apple subject 等 |
| `provider_subject_normalized` | VARCHAR(255) | 否 |  | 规范化后的身份标识 | 用于唯一匹配 |
| `is_verified` | BOOLEAN | 否 | `false` | 该身份是否已验证 | `true`、`false` |
| `verified_at` | TIMESTAMPTZ | 是 |  | 验证完成时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `provider IN ('phone', 'wechat', 'apple')`
- `user_id REFERENCES users(user_id)`
- `UNIQUE INDEX (provider, provider_subject_normalized) WHERE deleted_at IS NULL`
- `INDEX (user_id, provider)`

### 1.6. `auth_sessions` 会话/token 表

一条记录代表一个登录会话。当前使用服务端管理的 opaque token，客户端保存明文 token，数据库只保存 hash。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | UUID | 否 | 自动生成 | 会话主键 | 主键 |
| `user_id` | UUID | 否 |  | 会话所属用户 | FK: `users.user_id` |
| `access_token_hash` | CHAR(64) | 否 |  | access token 的 SHA-256 hash | 不存明文 token |
| `refresh_token_hash` | CHAR(64) | 否 |  | refresh token 的 SHA-256 hash | 不存明文 token |
| `device_name` | VARCHAR(120) | 是 |  | 登录设备名称 |  |
| `platform` | VARCHAR(50) | 是 |  | 登录平台 | iOS、Android、Web 等 |
| `ip_address` | VARCHAR(64) | 是 |  | 登录或刷新时的 IP |  |
| `user_agent` | VARCHAR(255) | 是 |  | 登录或刷新时的 User-Agent |  |
| `access_expires_at` | TIMESTAMPTZ | 否 |  | access token 过期时间 |  |
| `expires_at` | TIMESTAMPTZ | 否 |  | refresh/session 过期时间 |  |
| `last_seen_at` | TIMESTAMPTZ | 否 | 当前时间 | 最近使用时间 |  |
| `revoked_at` | TIMESTAMPTZ | 是 |  | 退出登录或服务端注销时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

约束与索引：

- `user_id REFERENCES users(user_id)`
- `UNIQUE INDEX access_token_hash`
- `UNIQUE INDEX refresh_token_hash`
- `INDEX (user_id, expires_at DESC) WHERE revoked_at IS NULL`

### 1.7. `auth_verification_codes` 验证码记录表

一条记录代表一次验证码请求。当前开发期验证码固定为 `000000`，不接真实短信；未来接短信服务时替换验证码发送和校验逻辑，不改变登录身份和会话模型。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `verification_code_id` | UUID | 否 | 自动生成 | 验证码记录主键 | 主键 |
| `provider` | VARCHAR(30) | 否 | `phone` | 验证渠道 | 当前仅 `phone` |
| `recipient` | VARCHAR(255) | 否 |  | 原始接收方 | 当前为手机号 |
| `recipient_normalized` | VARCHAR(255) | 否 |  | 规范化接收方 | 用于查询和限流 |
| `code_hash` | CHAR(64) | 否 |  | 验证码的 SHA-256 hash | 不存明文验证码 |
| `purpose` | VARCHAR(30) | 否 | `login` | 验证码用途 | `login`、`bind_identity` |
| `expires_at` | TIMESTAMPTZ | 否 |  | 验证码过期时间 |  |
| `consumed_at` | TIMESTAMPTZ | 是 |  | 使用时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

约束与索引：

- `provider IN ('phone')`
- `purpose IN ('login', 'bind_identity')`
- `INDEX (provider, recipient_normalized, created_at DESC)`
- `INDEX (expires_at)`

### 2. `lessons` 课程表

一条记录代表一节教练课。课程不直接拥有视频，而是通过 `tennis_activities.lesson_id` 组织教练和学生各自的活动记录。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `lesson_id` | UUID | 否 | 自动生成 | 课程主键 | 主键 |
| `coach_user_id` | UUID | 否 |  | 本节课教练 | FK: `users.user_id` |
| `title` | VARCHAR(120) | 是 |  | 课程标题 |  |
| `lesson_type` | VARCHAR(30) | 否 | `private` | 课程类型 | `private`、`group`、`camp`、`trial`、`other` |
| `status` | VARCHAR(30) | 否 | `draft` | 课程状态 | `draft`、`scheduled`、`completed`、`canceled` |
| `started_at` | TIMESTAMPTZ | 是 |  | 上课开始时间 |  |
| `ended_at` | TIMESTAMPTZ | 是 |  | 上课结束时间 |  |
| `location_name` | VARCHAR(120) | 是 |  | 场地名称 |  |
| `court_surface` | VARCHAR(30) | 是 |  | 场地类型 | `hard`、`clay`、`grass`、`carpet`、`unknown` |
| `training_content` | TEXT | 是 |  | 本节训练内容 |  |
| `coach_summary` | TEXT | 是 |  | 教练总结 |  |
| `homework` | TEXT | 是 |  | 全课通用作业 |  |
| `next_focus` | TEXT | 是 |  | 下节课重点 |  |
| `created_by_user_id` | UUID | 否 |  | 创建人 | FK: `users.user_id` |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (lesson_id)`
- `coach_user_id REFERENCES users(user_id)`
- `created_by_user_id REFERENCES users(user_id)`
- `ended_at >= started_at OR ended_at IS NULL OR started_at IS NULL`
- `INDEX (coach_user_id, started_at DESC)`
- `INDEX (status, started_at DESC)`

### 3. `lesson_students` 课程学生表

一条记录代表某个学生参与某节课程，并保存该学生在本节课内的独立反馈、评价和作业。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `lesson_student_id` | UUID | 否 | 自动生成 | 课程学生记录主键 | 主键 |
| `lesson_id` | UUID | 否 |  | 课程 ID | FK: `lessons.lesson_id` |
| `student_user_id` | UUID | 否 |  | 学生用户 ID | FK: `users.user_id` |
| `attendance_status` | VARCHAR(30) | 否 | `planned` | 出勤状态 | `planned`、`attended`、`absent`、`canceled` |
| `performance_summary` | TEXT | 是 |  | 表现总结 |  |
| `coach_feedback` | TEXT | 是 |  | 教练评价 |  |
| `homework` | TEXT | 是 |  | 学生个人作业 |  |
| `next_focus` | TEXT | 是 |  | 学生下节课重点 |  |
| `technical_issues` | TEXT | 是 |  | 技术问题摘要 |  |
| `created_by_user_id` | UUID | 否 |  | 创建人 | FK: `users.user_id` |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (lesson_student_id)`
- `UNIQUE (lesson_id, student_user_id) WHERE deleted_at IS NULL`
- `INDEX (lesson_id)`
- `INDEX (student_user_id, created_at DESC)`

### 4. `tennis_activities` 网球活动表

一条记录代表某个用户自己的网球活动记录。`TennisActivity` 必须且只能属于一个用户。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `tennis_activity_id` | UUID | 否 | 自动生成 | 活动主键 | 主键 |
| `owner_user_id` | UUID | 否 |  | 活动所有者 | FK: `users.user_id` |
| `lesson_id` | UUID | 是 |  | 所属课程；普通活动为空 | FK: `lessons.lesson_id` |
| `title` | VARCHAR(120) | 是 |  | 活动标题 |  |
| `activity_type` | VARCHAR(30) | 否 | `other` | 活动类型 | 见枚举 |
| `default_visibility` | VARCHAR(30) | 否 | `private` | 活动默认可见性 | 见枚举 |
| `started_at` | TIMESTAMPTZ | 是 |  | 活动开始时间 |  |
| `ended_at` | TIMESTAMPTZ | 是 |  | 活动结束时间 |  |
| `location_name` | VARCHAR(120) | 是 |  | 场地名称；兼容旧手填与自动生成的粗粒度显示 |  |
| `location_source` | VARCHAR(30) | 是 |  | 定位来源 | `device_gps`、`video_metadata`、`manual_legacy`、`unavailable` |
| `location_latitude` | DOUBLE PRECISION | 是 |  | 精确纬度 | 仅活动所有者和后台可见 |
| `location_longitude` | DOUBLE PRECISION | 是 |  | 精确经度 | 仅活动所有者和后台可见 |
| `location_accuracy_m` | DOUBLE PRECISION | 是 |  | 定位精度 | 米 |
| `location_captured_at` | TIMESTAMPTZ | 是 |  | 手机定位时间 | 仅活动所有者和后台可见 |
| `location_country_code` | VARCHAR(8) | 是 |  | 国家代码 |  |
| `location_region` | VARCHAR(80) | 是 |  | 省/州/地区 |  |
| `location_city` | VARCHAR(80) | 是 |  | 城市 |  |
| `location_district` | VARCHAR(80) | 是 |  | 区/县 |  |
| `location_address_label` | VARCHAR(255) | 是 |  | 精确地址展示 | 仅活动所有者和后台可见 |
| `location_coordinate_system` | VARCHAR(30) | 是 |  | 坐标系 | `wgs84`、`gcj02` |
| `court_surface` | VARCHAR(30) | 是 |  | 场地类型 | `hard`、`clay`、`grass`、`carpet`、`unknown` |
| `opponent_user_id` | UUID | 是 |  | 对手用户 | FK: `users.user_id` |
| `opponent_name` | VARCHAR(50) | 是 |  | 非注册对手显示名 |  |
| `note` | TEXT | 是 |  | 用户备注 |  |
| `analysis_summary_status` | VARCHAR(30) | 是 |  | 活动级分析汇总状态 | `pending`、`processing`、`completed`、`failed` |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (tennis_activity_id)`
- `owner_user_id REFERENCES users(user_id)`
- `lesson_id REFERENCES lessons(lesson_id)`
- `opponent_user_id REFERENCES users(user_id)`
- `INDEX (owner_user_id, created_at DESC)`
- `INDEX (lesson_id, created_at DESC)`
- `INDEX (activity_type, started_at DESC)`
- `INDEX (location_city, location_district, started_at DESC, tennis_activity_id DESC) WHERE deleted_at IS NULL`

定位口径：

- App 采集并保存的 Activity 经纬度使用 `wgs84`。
- App 前台运行时维护内存级位置缓存：启动和回到前台时刷新一次，前台每 3 分钟刷新一次；业务创建/发布流程优先使用最近一次缓存坐标。
- `device_gps` 表示手机系统定位得到的经纬度；`video_metadata` 表示上传或发布所选视频文件/相册资产自带的拍摄经纬度。当前不使用网络/IP 粗略定位兜底；无法取得手机或视频经纬度时使用 `unavailable`。
- 后端行政区解析使用 AreaCity 三级行政区边界数据、Shapely 和 STRtree，不在本阶段引入 PostGIS；默认读取 `backend/data/area_city_ok_geo.csv`，同时支持 GeoJSON/JSON 边界文件；API 启动时预热边界索引，正常解析请求不承担大文件冷加载成本。
- 边界数据坐标系由 `TENNIS_AREA_CITY_COORDINATE_SYSTEM` 配置，默认 `gcj02`；查询前后端负责把手机 `wgs84` 坐标转换到边界坐标系。
- 经纬度获取成功且边界数据可用时，后端返回精确命中或最近行政区近似结果；只有解析依赖、边界数据不可用或客户端请求超时时，仍保存经纬度，`location_city` / `location_district` 可为空。

### 5. `videos` 原始视频表

一条记录代表一个原始视频资产。视频可以属于某个 `TennisActivity`，但不直接属于 `Lesson`。当视频仅作为手机直传动态素材使用时，`tennis_activity_id = NULL`，并通过 `post_media.video_id` 被某条 `social_posts` 引用；这类视频不应出现在训练 activity 列表中。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `video_id` | UUID | 否 | 自动生成 | 视频主键 | 主键 |
| `tennis_activity_id` | UUID | 是 |  | 所属网球活动 | FK: `tennis_activities.tennis_activity_id` |
| `owner_user_id` | UUID | 否 |  | 视频所有者 | FK: `users.user_id` |
| `uploader_user_id` | UUID | 否 |  | 实际上传者 | FK: `users.user_id` |
| `filename` | VARCHAR(255) | 否 |  | 系统生成的唯一视频文件名 | 唯一 |
| `original_filename` | TEXT | 是 |  | 用户上传时的原始文件名 |  |
| `video_path` | TEXT | 否 |  | 原始视频文件路径 | 唯一 |
| `thumbnail_path` | TEXT | 是 |  | 封面图路径；上传完成后由后端生成，Tennis Activity 视频、手机直传 Post 视频和 Post 引用的视频片段共用该字段 |  |
| `mime_type` | VARCHAR(100) | 是 |  | 文件 MIME 类型 |  |
| `file_size_bytes` | BIGINT | 是 |  | 文件大小 | 字节 |
| `file_hash` | VARCHAR(128) | 是 |  | 文件哈希 |  |
| `video_duration_ms` | BIGINT | 是 |  | 视频总时长 | 毫秒 |
| `video_frame_count` | BIGINT | 是 |  | 视频总帧数 | 帧 |
| `video_fps` | REAL | 是 |  | 视频标称帧率 | fps |
| `video_width_px` | INTEGER | 是 |  | 视频宽度 | 像素 |
| `video_height_px` | INTEGER | 是 |  | 视频高度 | 像素 |
| `camera_view_angle` | VARCHAR(20) | 是 |  | 机位垂直视角 | `overhead`、`horizontal` |
| `camera_view_position` | VARCHAR(20) | 是 |  | 机位水平方位 | `side`、`rear`、`front`、`rear_side`、`front_side` |
| `frame_data_path` | TEXT | 是 |  | 逐帧 CV 数据文件路径 | 指向 `frame_data.jsonl` |
| `frame_data_version` | VARCHAR(30) | 是 |  | 逐帧数据结构版本 |  |
| `player_a_user_id` | UUID | 是 |  | A 球员对应注册用户 | FK: `users.user_id` |
| `player_b_user_id` | UUID | 是 |  | B 球员对应注册用户 | FK: `users.user_id` |
| `player_a_name` | VARCHAR(50) | 是 |  | A 球员在本次视频中的显示名称 |  |
| `player_b_name` | VARCHAR(50) | 是 |  | B 球员在本次视频中的显示名称 |  |
| `primary_player_slot` | CHAR(1) | 是 |  | 用户主要关注球员 | `A`、`B`、`NULL` |
| `visibility` | VARCHAR(30) | 否 | `inherit` | 视频可见性 | 见枚举 |
| `upload_status` | VARCHAR(30) | 否 | `pending` | 视频文件上传状态 | 见枚举 |
| `upload_error_message` | TEXT | 是 |  | 上传失败原因 |  |
| `uploaded_at` | TIMESTAMPTZ | 是 |  | 原始视频文件上传完成时间 |  |
| `analysis_status` | VARCHAR(30) | 否 | `uploaded` | 分析任务状态 | 见枚举 |
| `analysis_version` | VARCHAR(50) | 是 |  | 分析流程和算法版本 |  |
| `error_message` | TEXT | 是 |  | 分析失败原因 |  |
| `captured_at` | TIMESTAMPTZ | 是 |  | 视频实际拍摄时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 视频记录创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (video_id)`
- `UNIQUE (filename)`
- `UNIQUE (video_path)`
- `INDEX (tennis_activity_id, created_at DESC)`
- `INDEX (owner_user_id, created_at DESC)`
- `INDEX (uploader_user_id, created_at DESC)`
- `INDEX (analysis_status, created_at)`
- `INDEX (upload_status, created_at)`
- `INDEX (visibility)`
- `INDEX (camera_view_angle, camera_view_position)`

说明：

- `tennis_activity_id = NULL` 只表示视频不是某次 Tennis Activity 的组成部分，不表示视频没有所有者。
- 手机直传 Post 视频使用 `post_media.media_type = video` 引用独立视频；从 Tennis Activity 截取片段发布时使用 `post_media.media_type = video_clip` 引用原 activity 下的视频和片段时间范围。
- 已上传视频应有 `thumbnail_path`，客户端的首页、我的动态、Activity 列表和详情页均使用该字段作为视频缩略图来源。

### 6. `video_shares` 视频分享表

一条记录代表对某个视频的显式分享。课程默认关系可以参与权限判断，但不一定写入本表。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `video_share_id` | UUID | 否 | 自动生成 | 视频分享主键 | 主键 |
| `video_id` | UUID | 否 |  | 被分享视频 | FK: `videos.video_id` |
| `shared_by_user_id` | UUID | 否 |  | 分享发起人 | FK: `users.user_id` |
| `target_type` | VARCHAR(30) | 否 |  | 分享目标类型 | 见枚举 |
| `target_user_id` | UUID | 是 |  | 指定用户目标 | FK: `users.user_id` |
| `target_lesson_id` | UUID | 是 |  | 指定课程目标 | FK: `lessons.lesson_id` |
| `permission` | VARCHAR(30) | 否 | `view` | 分享权限 | 见枚举 |
| `status` | VARCHAR(20) | 否 | `active` | 分享状态 | 见枚举 |
| `expires_at` | TIMESTAMPTZ | 是 |  | 过期时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (video_share_id)`
- `target_type = 'user'` 时 `target_user_id` 必填
- `target_type IN ('lesson_coach', 'lesson_students', 'lesson_participants')` 时 `target_lesson_id` 必填
- `INDEX (video_id, status)`
- `INDEX (target_user_id, status)`
- `INDEX (target_lesson_id, status)`

### 7. `social_posts` 社交动态表

一条记录代表用户主动发布到社交区域的动态。动态可以引用活动，但删除动态不删除活动或视频。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `social_post_id` | UUID | 否 | 自动生成 | 动态主键 | 主键 |
| `author_user_id` | UUID | 否 |  | 发布者 | FK: `users.user_id` |
| `source_tennis_activity_id` | UUID | 是 |  | 来源活动 | FK: `tennis_activities.tennis_activity_id` |
| `title` | VARCHAR(120) | 是 |  | 标题 |  |
| `content` | TEXT | 是 |  | 正文 |  |
| `visibility` | VARCHAR(30) | 否 | `private` | 动态可见性 | 见枚举 |
| `status` | VARCHAR(30) | 否 | `draft` | 动态状态 | 见枚举 |
| `review_status` | VARCHAR(30) | 否 | `approved` | 审核状态 | `post_review_status` |
| `reviewed_at` | TIMESTAMPTZ | 是 |  | 审核时间 |  |
| `reviewer_user_id` | UUID | 是 |  | 审核人 | FK: `users.user_id` |
| `review_reason` | VARCHAR(500) | 是 |  | 审核原因或拒绝原因 |  |
| `location_scope` | VARCHAR(20) | 否 | `none` | 公开位置粒度 | `post_location_scope` |
| `location_region` | VARCHAR(80) | 是 |  | 粗粒度地区 | 不保存精确坐标 |
| `location_city` | VARCHAR(80) | 是 |  | 粗粒度城市 | 不保存精确坐标 |
| `published_at` | TIMESTAMPTZ | 是 |  | 发布时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (social_post_id)`
- `author_user_id REFERENCES users(user_id)`
- `source_tennis_activity_id REFERENCES tennis_activities(tennis_activity_id)`
- `reviewer_user_id REFERENCES users(user_id)`
- `location_scope = region` 时 `location_region` 必填
- `location_scope = city` 时 `location_city` 必填
- `INDEX (author_user_id, created_at DESC)`
- `INDEX (source_tennis_activity_id)`
- `INDEX (status, published_at DESC)`
- `INDEX (review_status, status, published_at DESC, social_post_id DESC) WHERE deleted_at IS NULL`
- `INDEX (location_city, location_region, published_at DESC, social_post_id DESC) WHERE deleted_at IS NULL`

### 8. `post_media` 动态媒体表

一条记录代表动态中引用的一项媒体或数据卡片。手机直传短视频使用 `media_type = video` 引用一条独立 `videos` 记录；引用 Tennis Activity 中的视频片段时使用 `media_type = video_clip`，只保存开始和结束时间，不复制原始视频。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `post_media_id` | UUID | 否 | 自动生成 | 动态媒体主键 | 主键 |
| `social_post_id` | UUID | 否 |  | 动态 ID | FK: `social_posts.social_post_id` |
| `media_type` | VARCHAR(30) | 否 |  | 媒体类型 | 见枚举 |
| `video_id` | UUID | 是 |  | 引用视频 | FK: `videos.video_id` |
| `image_path` | TEXT | 是 |  | 图片路径 |  |
| `data_card_type` | VARCHAR(50) | 是 |  | 数据卡片类型 |  |
| `data_payload_json` | JSON | 是 |  | 数据卡片内容 | JSON |
| `clip_start_ms` | BIGINT | 是 |  | 视频片段开始时间 | 毫秒 |
| `clip_end_ms` | BIGINT | 是 |  | 视频片段结束时间 | 毫秒 |
| `sort_order` | INTEGER | 否 | `0` | 排序 | 序号 |
| `caption` | VARCHAR(255) | 是 |  | 媒体说明 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `PRIMARY KEY (post_media_id)`
- `UNIQUE (social_post_id, sort_order) WHERE deleted_at IS NULL`
- `media_type = 'video'` 时只允许 `video_id` 非空
- `media_type = 'video_clip'` 时 `video_id`、`clip_start_ms`、`clip_end_ms` 必填，且 `clip_end_ms > clip_start_ms`
- `media_type = 'image'` 时只允许 `image_path` 非空
- `media_type = 'data_card'` 时只允许 `data_card_type`、`data_payload_json` 非空
- `INDEX (social_post_id, sort_order)`
- `video_id REFERENCES videos(video_id)`
- `INDEX (video_id)`

### 9. `social_post_stats`、`post_reactions`、`post_favorites`、`post_comments`、`post_shares`、`user_post_views` 与 `user_post_hides` 内容流行为表

`post_reactions`、`post_favorites`、`post_comments` 和 `post_shares` 保存 Post 互动事实，负责防重复、审计和通知来源。`social_post_stats` 保存 Post 基础互动统计缓存，作为接口展示和轻量排序输入，不替代事实表。`user_post_views` 保存某个用户是否已经看过某条 Post，是首页把已看内容后置的基础表；表结构预留浏览来源、首次/最近浏览时间、停留时长和浏览次数。`user_post_hides` 保存用户主动隐藏的 Post，隐藏后首页三个内容流默认排除。

| 表 | 关键字段 |
| --- | --- |
| `social_post_stats` | `social_post_id`、`like_count`、`comment_count`、`favorite_count`、`share_count`、`view_count`、`updated_at` |
| `post_reactions` | `reaction_id`、`social_post_id`、`user_id`、`reaction_type`、`status`、`source`、`reacted_at`、`canceled_at`、`created_at`、`updated_at` |
| `post_favorites` | `favorite_id`、`social_post_id`、`user_id`、`status`、`source`、`favorited_at`、`canceled_at`、`created_at`、`updated_at` |
| `post_comments` | `comment_id`、`social_post_id`、`author_user_id`、`parent_comment_id`、`root_comment_id`、`content`、`status`、`source`、`created_at`、`updated_at`、`deleted_at` |
| `post_shares` | `post_share_id`、`social_post_id`、`shared_by_user_id`、`share_target_type`、`target_user_id`、`conversation_id`、`message_id`、`channel`、`payload_json`、`created_at` |
| `user_post_views` | `user_post_view_id`、`user_id`、`social_post_id`、`first_viewed_at`、`last_viewed_at`、`first_view_source`、`last_view_source`、`view_count`、`total_dwell_time_ms`、`last_dwell_time_ms`、`created_at`、`updated_at` |
| `user_post_hides` | `user_post_hide_id`、`user_id`、`social_post_id`、`status`、`source`、`reason`、`hidden_at`、`canceled_at`、`created_at`、`updated_at` |

约束与索引：

- `social_post_stats.social_post_id` 是主键并引用 `social_posts.social_post_id`
- active 点赞 `(user_id, social_post_id, reaction_type)` 唯一，active 收藏 `(user_id, social_post_id)` 唯一
- 评论和回复使用同一张 `post_comments` 表；回复通过 `parent_comment_id` 和 `root_comment_id` 关联
- Post 分享写入 `post_shares`；分享到会话时可关联 `chat_conversations` 和生成的 `chat_messages`
- `user_post_views UNIQUE (user_id, social_post_id)`，保证重复批量上报不会生成重复浏览记录
- active 隐藏关系 `(user_id, social_post_id)` 唯一
- 所有 `user_id` 引用 `users.user_id`，所有 `social_post_id` 引用 `social_posts.social_post_id`
- `INDEX user_post_views(user_id, last_viewed_at DESC, social_post_id DESC)`
- `INDEX user_post_hides(user_id, hidden_at DESC)`

### 10. `user_follows`、`user_social_stats`、`user_blocks` 与 `user_privacy_settings` 社交关系表

`user_follows` 保存单向关注事实。好友/球友关系不单独落库，由两个方向均为 `status = active` 的关注关系派生。`user_social_stats` 是可选计数缓存，第一版接口允许实时聚合。`user_blocks` 保存主动拉黑关系，拉黑后禁止关注、私信和群聊邀请，并从 feed 中过滤双方内容。`user_privacy_settings` 保存用户级基础隐私控制。

| 表 | 关键字段 |
| --- | --- |
| `user_follows` | `follow_id`、`follower_user_id`、`following_user_id`、`status`、`source`、`followed_at`、`canceled_at`、`created_at`、`updated_at` |
| `user_social_stats` | `user_id`、`follower_count`、`following_count`、`friend_count`、`updated_at` |
| `user_blocks` | `user_block_id`、`blocker_user_id`、`blocked_user_id`、`reason`、`created_at`、`updated_at`、`deleted_at` |
| `user_privacy_settings` | `user_id`、`direct_message_policy`、`allow_message_requests`、`default_post_visibility`、`show_profile_to_strangers`、`created_at`、`updated_at` |

约束：

- `follower_user_id <> following_user_id`
- active 关注关系 `(follower_user_id, following_user_id)` 唯一
- active 拉黑关系 `(blocker_user_id, blocked_user_id)` 唯一
- 所有用户关系字段均引用 `users.user_id`

### 11. `chat_conversations`、`chat_conversation_members`、`chat_messages`、`chat_message_attachments` 与 `chat_message_requests` 消息表

`chat_conversations` 表达私信或群聊，`chat_conversation_members` 表达用户在会话中的成员状态、已读游标和未读数量。私信通过排序后的双方用户 ID 生成 `direct_pair_key`，保证一对用户只有一个有效私信会话。`chat_messages` 是通用消息信封，不直接拥有业务对象。`message_type` 表达消息展示类型，`target_object_type/object_id` 和 `context_object_type/context_id` 引用现有业务对象；文件和媒体细节放在 `chat_message_attachments`。`chat_message_requests` 保存非好友或不满足私信策略时的陌生人消息请求。

| 表 | 关键字段 |
| --- | --- |
| `chat_conversations` | `conversation_id`、`conversation_type`、`group_type`、`direct_pair_key`、`title`、`created_by_user_id`、`context_type`、`context_id`、`status`、`last_message_id`、`last_message_seq`、`last_message_preview`、`last_message_at` |
| `chat_conversation_members` | `conversation_member_id`、`conversation_id`、`user_id`、`member_role`、`status`、`joined_at`、`left_at`、`last_read_message_id`、`last_read_message_seq`、`last_read_at`、`unread_count`、`muted_until`、`pinned_at`、`archived_at` |
| `chat_messages` | `message_id`、`conversation_id`、`message_seq`、`sender_user_id`、`sender_type`、`message_type`、`text_content`、`payload_json`、`target_object_type`、`target_object_id`、`context_object_type`、`context_object_id`、`reply_to_message_id`、`client_message_id`、`status`、`sent_at` |
| `chat_message_attachments` | `attachment_id`、`message_id`、`attachment_type`、`media_path`、`thumbnail_path`、`mime_type`、`file_size_bytes`、`duration_ms`、`width_px`、`height_px`、`object_type`、`object_id`、`payload_json`、`sort_order` |
| `chat_message_requests` | `message_request_id`、`requester_user_id`、`recipient_user_id`、`conversation_id`、`status`、`request_message`、`source`、`requested_at`、`responded_at`、`created_at`、`updated_at` |

`reply_to_message_id` 可选引用同一会话中仍可用的消息；消息接口额外返回非持久化的 `reply_preview`，用于在原消息不在当前分页时安全展示引用。预览的 `state` 为 `available` 或 `unavailable`，不可用时不暴露删除、撤回或权限原因。Direct 文字消息撤回使用现有 `status = 'revoked'`，保留消息行、`message_seq`、`sent_at` 和已读/未读水位；用户侧序列化会清空撤回消息的内容、payload、业务对象引用、附件和 active reply preview，历史搜索仅返回 `status = 'sent'` 的文本。`client_message_id` 用于移动端超时重试幂等；消息已经落库后，即使接收方离线，也可通过成员 `unread_count` 和消息列表恢复。

陌生人消息请求在 `status = pending` 时 `(requester_user_id, recipient_user_id)` 唯一。接受请求后创建或复用双方 direct conversation，并把 `conversation_id` 写回请求记录。

### 12. `notification_events`、`user_notifications`、`user_inbox_counters`、`user_notification_preferences` 与 `content_reports` 通知和治理表

`notification_events` 保存一次业务事件，`user_notifications` 保存具体接收人的展示、已读和删除状态。通知对象通过多态对象字段引用 `social_posts`、`videos`、`tennis_activities`、`lessons` 等业务对象，不把业务逻辑写入通知表。

`user_notification_preferences` 保存未来系统 Push 的用户级投递偏好。六项布尔字段默认均为 `true`；没有偏好行的用户也按全开处理。该表不控制站内通知记录、未读计数、徽标、私信权限或消息请求权限。

| 表 | 关键字段 |
| --- | --- |
| `notification_events` | `notification_event_id`、`event_type`、`category`、`actor_user_id`、`object_type`、`object_id`、`context_type`、`context_id`、`title`、`body`、`deep_link`、`payload_json`、`dedup_key`、`aggregation_key`、`created_at` |
| `user_notifications` | `user_notification_id`、`notification_event_id`、`recipient_user_id`、`status`、`priority`、`delivered_at`、`seen_at`、`read_at`、`dismissed_at`、`created_at`、`updated_at`、`deleted_at` |
| `user_notification_preferences` | `user_id`、`direct_message_notifications`、`message_request_notifications`、`like_comment_notifications`、`follow_notifications`、`course_notifications`、`ai_analysis_notifications`、`created_at`、`updated_at` |
| `user_inbox_counters` | `user_id`、`unread_direct_message_count`、`unread_group_message_count`、`unread_notification_count`、`updated_at` |
| `content_reports` | `content_report_id`、`reporter_user_id`、`target_type`、`target_id`、`reason_type`、`reason_text`、`source`、`status`、`reviewer_user_id`、`reviewed_at`、`resolution_note`、`created_at`、`updated_at` |

同一个用户对同一个对象只能有一条 `pending` 或 `reviewing` 举报记录；处理完成后可再次提交新的举报事实。

### 13. `points` 每分表

一条记录代表视频中的一分。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `point_id` | UUID | 否 | 自动生成 | 每分主键 | 主键 |
| `video_id` | UUID | 否 |  | 所属视频 | FK: `videos.video_id` |
| `point_index` | INTEGER | 否 |  | 本次上传中的第几分，从 1 开始 | 序号 |
| `start_frame` | BIGINT | 否 |  | 这一分开始帧 | 帧，从 0 开始 |
| `end_frame` | BIGINT | 是 |  | 这一分结束帧 | 帧，从 0 开始 |
| `start_time_ms` | BIGINT | 否 |  | 这一分开始时间 | 毫秒 |
| `end_time_ms` | BIGINT | 是 |  | 这一分结束时间 | 毫秒 |
| `server_slot` | CHAR(1) | 是 |  | 发球方 | `A`、`B` |
| `winner_slot` | CHAR(1) | 是 |  | 得分方 | `A`、`B` |
| `terminal_shot_id` | UUID | 是 |  | 结束这一分的最后一拍 | FK: `shots.shot_id` |
| `set_index` | SMALLINT | 是 |  | 当前第几盘，从 1 开始 |  |
| `game_index_in_set` | SMALLINT | 是 |  | 当前盘中的第几局，从 1 开始 |  |
| `a_sets_before` | SMALLINT | 是 |  | 本分开始前 A 赢得的盘数 |  |
| `b_sets_before` | SMALLINT | 是 |  | 本分开始前 B 赢得的盘数 |  |
| `a_games_before` | SMALLINT | 是 |  | 本分开始前当前盘 A 赢得的局数 |  |
| `b_games_before` | SMALLINT | 是 |  | 本分开始前当前盘 B 赢得的局数 |  |
| `a_points_before` | SMALLINT | 是 |  | 本分开始前当前局 A 赢得的原始分数数量 | 不保存 15/30/40/AD 文本 |
| `b_points_before` | SMALLINT | 是 |  | 本分开始前当前局 B 赢得的原始分数数量 | 不保存 15/30/40/AD 文本 |
| `is_tiebreak` | BOOLEAN | 是 |  | 是否处于抢七 |  |
| `first_serve_in` | BOOLEAN | 是 |  | 一发是否为合法有效发球 |  |
| `second_serve_used` | BOOLEAN | 是 |  | 是否使用二发 |  |
| `second_serve_in` | BOOLEAN | 是 |  | 二发是否为合法有效发球 |  |
| `serve_let_count` | SMALLINT | 否 | `0` | 发球擦网重发次数 | 次 |
| `is_double_fault` | BOOLEAN | 是 |  | 是否双误 |  |
| `total_shot_count` | SMALLINT | 是 |  | 本分全部击球事件数量 | 次 |
| `in_play_shot_count` | SMALLINT | 是 |  | 最终有效回合中的击球数量 | 次 |
| `point_result` | VARCHAR(30) | 是 |  | 这一分的网球统计结果 | 见枚举 |
| `ending_reason` | VARCHAR(30) | 是 |  | 这一分具体如何结束 | 见枚举 |
| `confidence` | REAL | 是 |  | 这一分整体判断置信度 | 0～1 |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

计分约定：

- `a_points_before` 和 `b_points_before` 保存本局内真实发生的原始得分次数。
- 不保存 `15`、`30`、`40`、`AD` 文本。
- 不把多次平分压缩成固定值。

回合计数约定：

- `total_shot_count` 包括一发失误、发球擦网重发、二发、有效回合中的全部击球。
- `in_play_shot_count` 只包括最终有效发球及后续回合中的击球。
- `rally_shot_count` 为非落库派生字段，不包含发球。
- 有有效发球时：`rally_shot_count = in_play_shot_count - 1`。
- 发球直接结束的分，例如 Ace、发球直接得分或双误，`rally_shot_count = 0`。

约束与索引：

- `point_index >= 1`
- `start_frame >= 0`
- `end_frame >= start_frame`
- `start_time_ms >= 0`
- `end_time_ms >= start_time_ms`
- `server_slot IN ('A', 'B') OR server_slot IS NULL`
- `winner_slot IN ('A', 'B') OR winner_slot IS NULL`
- `point_result IN (...) OR point_result IS NULL`
- `ending_reason IN (...) OR ending_reason IS NULL`
- `set_index >= 1`
- `game_index_in_set >= 1`
- `a_sets_before >= 0`
- `b_sets_before >= 0`
- `a_games_before >= 0`
- `b_games_before >= 0`
- `a_points_before >= 0`
- `b_points_before >= 0`
- `serve_let_count >= 0`
- `total_shot_count >= 0`
- `in_play_shot_count >= 0`
- `total_shot_count >= in_play_shot_count`
- `confidence BETWEEN 0 AND 1`
- `PRIMARY KEY (point_id)`
- `UNIQUE (video_id, point_index)`
- `INDEX (video_id, start_time_ms)`
- `INDEX (video_id, winner_slot)`
- `INDEX (video_id, server_slot)`
- `INDEX (terminal_shot_id)`

发球摘要关系：

- `first_serve_in = true` 时，`second_serve_used = false`，`second_serve_in = NULL`，`is_double_fault = false`。
- `second_serve_used = false` 时，`second_serve_in = NULL`，`is_double_fault = false`。
- `is_double_fault = true` 时，`first_serve_in = false`，`second_serve_used = true`，`second_serve_in = false`，`point_result = 'double_fault'`。

### 10. `shots` 每拍表

一条记录代表一次球拍触球事件，以及本次触球后产生的球轨迹摘要。一发失误、发球擦网重发和二发分别作为独立 shot 保存。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `shot_id` | UUID | 否 | 自动生成 | 每拍主键 | 主键 |
| `point_id` | UUID | 否 |  | 所属分 | FK: `points.point_id` |
| `shot_index` | SMALLINT | 否 |  | 本分中的第几次击球，从 1 开始 | 序号 |
| `hitter_slot` | CHAR(1) | 是 |  | 击球者 | `A`、`B` |
| `shot_role` | VARCHAR(20) | 是 |  | 本拍在回合中的角色 | `serve`、`return`、`rally` |
| `serve_number` | SMALLINT | 是 |  | 一发为 1，二发为 2 | 非发球为 `NULL` |
| `contact_frame` | BIGINT | 否 |  | 击球发生的帧号 | 帧，从 0 开始 |
| `contact_time_ms` | BIGINT | 否 |  | 击球发生时间 | 毫秒 |
| `contact_projected_x_m` | DOUBLE PRECISION | 是 |  | 球触拍位置在场地平面上的投影 x | 米 |
| `contact_projected_y_m` | DOUBLE PRECISION | 是 |  | 球触拍位置在场地平面上的投影 y | 米 |
| `hitter_x_m` | DOUBLE PRECISION | 是 |  | 击球者脚下位置 x | 米 |
| `hitter_y_m` | DOUBLE PRECISION | 是 |  | 击球者脚下位置 y | 米 |
| `opponent_x_m` | DOUBLE PRECISION | 是 |  | 对手脚下位置 x | 米 |
| `opponent_y_m` | DOUBLE PRECISION | 是 |  | 对手脚下位置 y | 米 |
| `bounce_count_before_hit` | SMALLINT | 是 |  | 击球前球已经落地的次数 | 0 或 1 |
| `contact_confidence` | REAL | 是 |  | 击球事件和击球时刻判断置信度 | 0～1 |
| `stroke_type` | VARCHAR(30) | 是 |  | 击球技术类型 | 见枚举 |
| `stroke_side` | VARCHAR(20) | 是 |  | 正手或反手 | 见枚举 |
| `stroke_confidence` | REAL | 是 |  | 击球类型判断置信度 | 0～1 |
| `incoming_speed_mps` | DOUBLE PRECISION | 是 |  | 触球前二维轨迹平均球速 | 米/秒 |
| `outgoing_speed_mps` | DOUBLE PRECISION | 是 |  | 触球后二维轨迹平均球速 | 米/秒 |
| `outgoing_angle_deg` | DOUBLE PRECISION | 是 |  | 出球在场地平面上的方向角 | 度 |
| `first_bounce_frame` | BIGINT | 是 |  | 第一次落地帧 | 帧，从 0 开始 |
| `first_bounce_time_ms` | BIGINT | 是 |  | 第一次落地时间 | 毫秒 |
| `first_bounce_x_m` | DOUBLE PRECISION | 是 |  | 第一次落地点 x | 米 |
| `first_bounce_y_m` | DOUBLE PRECISION | 是 |  | 第一次落地点 y | 米 |
| `bounce_result` | VARCHAR(20) | 是 |  | 第一次落点是否有效 | `in`、`out`、`unknown` |
| `bounce_confidence` | REAL | 是 |  | 落点位置和有效性判断置信度 | 0～1 |
| `trajectory_end_type` | VARCHAR(30) | 是 |  | 本拍球轨迹如何结束 | 见枚举 |
| `shot_result` | VARCHAR(30) | 是 |  | 本拍产生的统计结果 | 见枚举 |
| `error_forcedness` | VARCHAR(20) | 是 |  | 受迫或非受迫失误 | 见枚举 |
| `error_type` | VARCHAR(20) | 是 |  | 具体失误形式 | 见枚举 |
| `is_point_ending` | BOOLEAN | 是 |  | 是否为结束这一分的最后一拍 |  |
| `point_winner_slot` | CHAR(1) | 是 |  | 如果结束该分，得分方 | `A`、`B` |
| `result_confidence` | REAL | 是 |  | 本拍结果判断置信度 | 0～1 |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |

速度和角度约定：

- `incoming_speed_mps` 是当前触球前一段连续有效二维球轨迹的平均速度。
- `outgoing_speed_mps` 是当前触球后，到第一次落地、对手触球或轨迹结束之间的连续有效二维球轨迹平均速度。
- 速度使用相邻轨迹点的累计路径长度除以时间，不使用起点和终点之间的直线距离代替。
- `outgoing_angle_deg` 中 `0°` 指向 `+x`，`90°` 指向 `+y`，`-90°` 指向 `-y`。
- `outgoing_angle_deg` 范围为 `-180 < value <= 180`。

落点有效性约定：

- 普通回合：`bounce_result` 表示是否落在有效单打场地内。
- 发球：`bounce_result` 表示是否落在正确发球区内。
- 发球落在单打场地内但没有落入正确发球区时，`bounce_result = out`。

约束与索引：

- `shot_index >= 1`
- `hitter_slot IN ('A', 'B') OR hitter_slot IS NULL`
- `shot_role IN ('serve', 'return', 'rally') OR shot_role IS NULL`
- `serve_number IN (1, 2) OR serve_number IS NULL`
- `contact_frame >= 0`
- `contact_time_ms >= 0`
- `bounce_count_before_hit >= 0 AND bounce_count_before_hit <= 1`
- `stroke_type IN (...) OR stroke_type IS NULL`
- `stroke_side IN (...) OR stroke_side IS NULL`
- `bounce_result IN ('in', 'out', 'unknown') OR bounce_result IS NULL`
- `trajectory_end_type IN (...) OR trajectory_end_type IS NULL`
- `shot_result IN (...) OR shot_result IS NULL`
- `error_forcedness IN ('forced', 'unforced', 'unknown') OR error_forcedness IS NULL`
- `error_type IN ('net', 'long', 'wide', 'unknown') OR error_type IS NULL`
- `incoming_speed_mps >= 0`
- `outgoing_speed_mps >= 0`
- `outgoing_angle_deg > -180 AND outgoing_angle_deg <= 180`
- `first_bounce_frame >= contact_frame`
- `first_bounce_time_ms >= contact_time_ms`
- `contact_confidence BETWEEN 0 AND 1`
- `stroke_confidence BETWEEN 0 AND 1`
- `bounce_confidence BETWEEN 0 AND 1`
- `result_confidence BETWEEN 0 AND 1`
- `point_winner_slot IN ('A', 'B') OR point_winner_slot IS NULL`
- `PRIMARY KEY (shot_id)`
- `UNIQUE (point_id, shot_index)`
- `INDEX (point_id, contact_time_ms)`
- `INDEX (hitter_slot)`
- `INDEX (stroke_type, stroke_side)`
- `INDEX (shot_result)`
- `INDEX (first_bounce_x_m, first_bounce_y_m) WHERE first_bounce_x_m IS NOT NULL AND first_bounce_y_m IS NOT NULL`

发球字段关系：

- `shot_role = 'serve'` 时，`serve_number` 必须为 `1` 或 `2`，且 `stroke_type = 'serve'`。
- `shot_role <> 'serve'` 时，`serve_number` 必须为 `NULL`。
- `stroke_type = 'serve'` 时，`shot_role = 'serve'`，且 `stroke_side = NULL`。

结果字段关系：

- `is_point_ending = false` 时，`point_winner_slot = NULL`。
- `is_point_ending = true` 时，`point_winner_slot` 必须为 `A` 或 `B`。
- `shot_result <> 'error'` 时，`error_forcedness` 和 `error_type` 通常为 `NULL`。
- `shot_result = 'serve_fault'` 时，`shot_role = 'serve'`，`serve_number` 必须为 `1` 或 `2`。
- `shot_result = 'let'` 时，`shot_role = 'serve'`，`is_point_ending = false`。

---

## 八、逐帧 CV 数据文件

逐帧数据不进入数据库，单独保存为文件：

```text
frame_data.jsonl
```

数据库通过 `videos.frame_data_path` 找到对应文件，`videos.frame_data_version` 标识逐帧数据结构版本。

逐帧文件负责保存：

- 每帧时间和帧号。
- 球的检测与跟踪结果。
- A、B 球员的位置。
- 场地识别结果。
- 单应矩阵。
- 各项 CV 置信度。

逐帧文件中如出现时间、坐标、速度、像素、置信度字段，必须遵守本字典的全局命名和单位规则。

---

## 九、非落库公共结构

### 1. 统计结果公共字段

以下字段用于统计结果载荷，均为 `非落库字段`。

| 字段 | 含义 | 单位/枚举 |
| --- | --- | --- |
| `video_id` | 视频 ID | UUID string |
| `player_slot` | 球员 A 或 B | `A`、`B` |
| `metric_code` | 本文件定义的指标字段名 | string |
| `metric_name` | 指标显示名称 | string |
| `metric_value` | 指标值 | 按 `metric_code` 单位 |
| `metric_unit` | 单位 | string |
| `sample_size` | 样本量 | count |
| `scope_type` | 统计范围 | `video`、`activity`、`lesson`、`set`、`game`、`point`、`history` |
| `scope_id` | 对应范围 ID | string/null |
| `dimension` | 指标维度 | `serve`、`return`、`rally`、`movement` 等 |
| `confidence` | 统计可信度 | 0～1 |
| `algorithm_version` | 算法版本 | string |
| `created_at` | 创建时间 | TIMESTAMPTZ/ISO 8601 |

### 2. 明细页派生字段

| 字段 | 来源 | 含义 |
| --- | --- | --- |
| `returner_slot` | 由 `server_slot` 推导 | 接发方 |
| `point_duration_ms` | `end_time_ms - start_time_ms` | 本分时长 |
| `is_key_point` | 规则或算法推断 | 是否关键分 |
| `previous_shot_id` | 同一分内 `shot_index` 推导 | 前一拍 ID |
| `depth_zone` | 落点/轨迹算法 | 击球深度，`shallow`、`middle`、`deep` |
| `shot_direction` | 线路算法 | 击球线路，`crosscourt`、`down_the_line`、`center` 等 |
| `rally_state` | 规则或算法推断 | `attack`、`neutral`、`defense`、`unknown` |
| `pressure_score` | 规则或算法计算 | 来球压力，0～100 |
| `shot_quality_score` | 规则或算法计算 | 击球质量，0～100 |
| `rally_shot_count` | `in_play_shot_count` 派生 | 发球之后的接发和相持击球数 |

---

## 十、统计指标字段字典

所有统计指标均为 `非落库字段`，除非同名字段已出现在四张核心表中。指标单位按字段后缀和全局单位规则确定。

### 1. 数据总览

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 视频总时长 | `video_duration_ms` | P0 |
| 有效运动时长 | `active_duration_ms` | P0 |
| 总分数 | `point_count` | P0 |
| 总击球数 | `shot_count` | P0 |
| 平均每分相持拍数 | `avg_rally_shot_count` | P0 |
| 最长相持拍数 | `max_rally_shot_count` | P0 |
| 平均每分时长 | `avg_point_duration_ms` | P0 |
| 获胜分数 | `point_won_count` | P0 |
| 失分数 | `point_lost_count` | P0 |
| 总得分率 | `point_win_rate` | P0 |
| 制胜分数 | `winner_count` | P0 |
| 受迫失误数 | `forced_error_count` | P1 |
| 非受迫失误数 | `unforced_error_count` | P1 |
| 主动得分占比 | `active_point_win_rate` | P1 |
| 对手失误得分占比 | `opponent_error_point_win_rate` | P1 |
| 最快发球速度 | `max_serve_speed_mps` | P0 |
| 最快击球速度 | `max_shot_speed_mps` | P0 |
| 总移动距离 | `total_move_distance_m` | P0 |
| 平均移动速度 | `avg_move_speed_mps` | P0 |
| 最大移动速度 | `max_move_speed_mps` | P0 |

### 2. 得分与失分

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 发球分数 | `serve_point_count` | P0 |
| 发球分获胜数 | `serve_point_won_count` | P0 |
| 发球分得分率 | `serve_point_win_rate` | P0 |
| 接发分数 | `return_point_count` | P0 |
| 接发分获胜数 | `return_point_won_count` | P0 |
| 接发分得分率 | `return_point_win_rate` | P0 |
| 短回合数量 | `short_rally_count` | P0 |
| 短回合得分率 | `short_rally_win_rate` | P0 |
| 中回合数量 | `medium_rally_count` | P0 |
| 中回合得分率 | `medium_rally_win_rate` | P0 |
| 长回合数量 | `long_rally_count` | P0 |
| 长回合得分率 | `long_rally_win_rate` | P0 |
| Ace 数量 | `ace_count` | P0 |
| 发球直接得分数 | `service_winner_count` | P0 |
| 双误数 | `double_fault_count` | P0 |
| 受迫类型未知的失误数 | `unknown_forcedness_error_count` | P1 |
| 下网失误数 | `net_error_count` | P0 |
| 出界过长数 | `long_error_count` | P0 |
| 出界过宽数 | `wide_error_count` | P0 |

回合长度划分：

- 短回合：`rally_shot_count` 为 1～4 拍。
- 中回合：`rally_shot_count` 为 5～8 拍。
- 长回合：`rally_shot_count` 为 9 拍及以上。

### 3. 发球分析

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 一发尝试次数 | `first_serve_attempt_count` | P0 |
| 一发成功次数 | `first_serve_in_count` | P0 |
| 一发成功率 | `first_serve_in_rate` | P0 |
| 一发失误次数 | `first_serve_fault_count` | P0 |
| 二发尝试次数 | `second_serve_attempt_count` | P0 |
| 二发成功次数 | `second_serve_in_count` | P0 |
| 二发成功率 | `second_serve_in_rate` | P0 |
| 双误率 | `double_fault_rate` | P0 |
| Ace 率 | `ace_rate` | P0 |
| 发球直接得分率 | `service_winner_rate` | P0 |
| 一发得分率 | `first_serve_point_win_rate` | P0 |
| 二发得分率 | `second_serve_point_win_rate` | P0 |
| 一发平均速度 | `avg_first_serve_speed_mps` | P0 |
| 二发平均速度 | `avg_second_serve_speed_mps` | P0 |
| 总体平均发球速度 | `avg_serve_speed_mps` | P0 |
| 发球速度标准差 | `serve_speed_std_mps` | P1 |
| 外角发球使用率 | `wide_serve_rate` | P0 |
| 外角发球成功率 | `wide_serve_in_rate` | P0 |
| 外角发球得分率 | `wide_serve_win_rate` | P0 |
| 外角发球平均速度 | `avg_wide_serve_speed_mps` | P0 |
| 追身发球使用率 | `body_serve_rate` | P0 |
| 追身发球成功率 | `body_serve_in_rate` | P0 |
| 追身发球得分率 | `body_serve_win_rate` | P0 |
| 追身发球平均速度 | `avg_body_serve_speed_mps` | P0 |
| 内角发球使用率 | `t_serve_rate` | P0 |
| 内角发球成功率 | `t_serve_in_rate` | P0 |
| 内角发球得分率 | `t_serve_win_rate` | P0 |
| 内角发球平均速度 | `avg_t_serve_speed_mps` | P0 |
| 发球后第一拍出现率 | `serve_plus_one_attempt_rate` | P1 |
| 发球后第一拍界内率 | `serve_plus_one_in_rate` | P1 |
| 发球后第一拍进攻率 | `serve_plus_one_attack_rate` | P1 |
| 发球后第一拍失误率 | `serve_plus_one_error_rate` | P1 |
| 发球后三拍内得分率 | `serve_first_three_shots_win_rate` | P1 |

发球方向指标应支持按 `serve_number` 和 `serve_court_side` 分组。

### 4. 接发分析

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 接发尝试次数 | `return_attempt_count` | P0 |
| 可触及发球次数 | `reachable_serve_count` | P0 |
| 接发成功次数 | `return_in_count` | P0 |
| 接发成功率 | `return_in_rate` | P0 |
| 接发直接失误数 | `return_error_count` | P0 |
| 接发直接失误率 | `return_error_rate` | P0 |
| 一发接发成功率 | `first_serve_return_in_rate` | P0 |
| 二发接发成功率 | `second_serve_return_in_rate` | P0 |
| 接发平均速度 | `avg_return_speed_mps` | P0 |
| 接发深球率 | `return_deep_rate` | P0 |
| 接发浅球率 | `return_shallow_rate` | P0 |
| 高质量接发比例 | `high_quality_return_rate` | P1 |
| 一般接发比例 | `normal_quality_return_rate` | P1 |
| 低质量接发比例 | `low_quality_return_rate` | P1 |
| 平均接发质量评分 | `avg_return_quality_score` | P1 |
| 接发后三拍内得分率 | `return_first_three_shots_win_rate` | P1 |
| 接发后对手直接进攻率 | `opponent_attack_after_return_rate` | P1 |

### 5. 击球与相持

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 总界内率 | `shot_in_rate` | P0 |
| 正手击球数 | `forehand_shot_count` | P0 |
| 正手使用率 | `forehand_shot_rate` | P0 |
| 正手界内率 | `forehand_in_rate` | P0 |
| 反手击球数 | `backhand_shot_count` | P0 |
| 反手使用率 | `backhand_shot_rate` | P0 |
| 反手界内率 | `backhand_in_rate` | P0 |
| 截击次数 | `volley_shot_count` | P0 |
| 截击界内率 | `volley_in_rate` | P0 |
| 平均连续有效击球数 | `avg_consecutive_in_shot_count` | P0 |
| 最大连续有效击球数 | `max_consecutive_in_shot_count` | P0 |
| 非受迫失误率 | `unforced_error_rate` | P1 |
| 正手非受迫失误率 | `forehand_unforced_error_rate` | P1 |
| 反手非受迫失误率 | `backhand_unforced_error_rate` | P1 |
| 正手制胜分数 | `forehand_winner_count` | P0 |
| 反手制胜分数 | `backhand_winner_count` | P0 |
| 正手非受迫失误数 | `forehand_unforced_error_count` | P1 |
| 反手非受迫失误数 | `backhand_unforced_error_count` | P1 |
| 正手受迫失误数 | `forehand_forced_error_count` | P1 |
| 反手受迫失误数 | `backhand_forced_error_count` | P1 |
| 正手平均速度 | `avg_forehand_speed_mps` | P0 |
| 反手平均速度 | `avg_backhand_speed_mps` | P0 |
| 所有击球平均速度 | `avg_shot_speed_mps` | P0 |
| 制胜分平均速度 | `avg_winner_speed_mps` | P0 |
| 失误球平均速度 | `avg_error_speed_mps` | P0 |
| 击球速度 90 分位数 | `shot_speed_p90_mps` | P1 |
| 击球速度标准差 | `shot_speed_std_mps` | P1 |
| 界内击球平均速度 | `avg_in_shot_speed_mps` | P0 |
| 深球率 | `deep_shot_rate` | P0 |
| 中区球比例 | `middle_depth_shot_rate` | P0 |
| 浅球率 | `shallow_shot_rate` | P0 |
| 正手深球率 | `forehand_deep_shot_rate` | P0 |
| 反手深球率 | `backhand_deep_shot_rate` | P0 |
| 深球后得分率 | `deep_shot_point_win_rate` | P1 |
| 浅球后失分率 | `shallow_shot_point_loss_rate` | P1 |
| 击球深度标准差 | `shot_depth_std_m` | P1 |
| 中路球比例 | `center_shot_rate` | P0 |
| 边线球比例 | `sideline_shot_rate` | P0 |
| 大角度球比例 | `wide_angle_shot_rate` | P1 |
| 斜线球比例 | `crosscourt_shot_rate` | P0 |
| 直线球比例 | `down_the_line_shot_rate` | P0 |
| 正手斜线比例 | `forehand_crosscourt_rate` | P0 |
| 正手直线比例 | `forehand_down_the_line_rate` | P0 |
| 反手斜线比例 | `backhand_crosscourt_rate` | P0 |
| 反手直线比例 | `backhand_down_the_line_rate` | P0 |
| 变线成功率 | `direction_change_success_rate` | P1 |
| 大角度球后得分率 | `wide_angle_shot_win_rate` | P1 |
| 平均击球质量 | `avg_shot_quality_score` | P1 |
| 发球质量 | `avg_serve_quality_score` | P1 |
| 接发质量 | `avg_return_quality_score` | P1 |
| 相持球质量 | `avg_rally_quality_score` | P1 |
| 进攻球质量 | `avg_attack_quality_score` | P1 |
| 防守球质量 | `avg_defense_quality_score` | P1 |

### 6. 进攻、防守与压力

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 平均来球压力 | `avg_pressure_score` | P1 |
| 高压力来球比例 | `high_pressure_shot_rate` | P1 |
| 中压力来球比例 | `medium_pressure_shot_rate` | P1 |
| 低压力来球比例 | `low_pressure_shot_rate` | P1 |
| 进攻击球比例 | `attack_shot_rate` | P1 |
| 均势击球比例 | `neutral_shot_rate` | P1 |
| 进攻成功率 | `attack_success_rate` | P1 |
| 进攻转化率 | `attack_conversion_rate` | P1 |
| 进攻失误率 | `attack_error_rate` | P1 |
| 浅球处理成功率 | `shallow_ball_attack_win_rate` | P1 |
| 终结机会转化率 | `finishing_opportunity_conversion_rate` | P2 |
| 取得主动后得分率 | `advantage_point_win_rate` | P1 |
| 首先取得主动比例 | `first_attack_rate` | P1 |
| 防守击球比例 | `defense_shot_rate` | P1 |
| 防守回球成功率 | `defense_return_in_rate` | P1 |
| 防守得分率 | `defense_point_win_rate` | P1 |
| 防守脱困率 | `defense_recovery_rate` | P1 |
| 防守转均势率 | `defense_to_neutral_rate` | P1 |
| 防守转进攻率 | `defense_to_attack_rate` | P2 |
| 跑动击球界内率 | `running_shot_in_rate` | P1 |
| 受迫失误率 | `forced_error_rate` | P1 |
| 主动权变化次数 | `advantage_change_count` | P2 |
| 平均主动权变化拍序 | `avg_advantage_change_shot_index` | P2 |
| 取得主动后保持率 | `advantage_retention_rate` | P2 |
| 丢失主动权比例 | `advantage_loss_rate` | P2 |

`pressure_score` 由来球速度、深度、宽度、球员移动距离和反应时间综合计算。

### 7. 移动与场地分布

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 单分平均移动距离 | `avg_move_distance_per_point_m` | P0 |
| 高强度移动次数 | `high_intensity_move_count` | P1 |
| 横向移动距离 | `lateral_move_distance_m` | P0 |
| 前后移动距离 | `longitudinal_move_distance_m` | P0 |
| 横向平均移动速度 | `avg_lateral_move_speed_mps` | P1 |
| 前后平均移动速度 | `avg_longitudinal_move_speed_mps` | P1 |
| 场地覆盖面积 | `court_coverage_area_m2` | P1 |
| 底线内击球比例 | `inside_baseline_shot_rate` | P0 |
| 底线后击球比例 | `behind_baseline_shot_rate` | P0 |
| 网前击球比例 | `net_position_shot_rate` | P0 |
| 被拉出边线击球次数 | `outside_sideline_shot_count` | P0 |
| 平均发球者脚下位置 X | `avg_serve_hitter_x_m` | P0 |
| 平均发球者脚下位置 Y | `avg_serve_hitter_y_m` | P0 |
| 平均接发站位 X | `avg_return_position_x_m` | P0 |
| 平均接发站位 Y | `avg_return_position_y_m` | P0 |
| 平均回位时间 | `avg_recovery_time_ms` | P1 |
| 平均回位距离 | `avg_recovery_distance_m` | P1 |
| 回位完成率 | `recovery_complete_rate` | P1 |
| 回位不足次数 | `incomplete_recovery_count` | P1 |
| 击球后停留次数 | `post_shot_idle_count` | P1 |
| 回位不足导致失分数 | `recovery_failure_point_loss_count` | P1 |
| 回位后位置平均误差 | `avg_recovery_position_error_m` | P1 |

### 8. 战术分析

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 短回合失误率 | `short_rally_error_rate` | P1 |
| 中回合失误率 | `medium_rally_error_rate` | P1 |
| 长回合失误率 | `long_rally_error_rate` | P1 |
| 短回合平均移动距离 | `avg_short_rally_move_distance_m` | P1 |
| 中回合平均移动距离 | `avg_medium_rally_move_distance_m` | P1 |
| 长回合平均移动距离 | `avg_long_rally_move_distance_m` | P1 |
| 长回合稳定性下降率 | `long_rally_stability_drop_rate` | P2 |
| 前三拍失分率 | `first_three_shots_loss_rate` | P1 |
| 打向对手正手次数 | `shot_to_opponent_forehand_count` | P1 |
| 打向对手正手得分率 | `shot_to_opponent_forehand_win_rate` | P1 |
| 打向对手反手次数 | `shot_to_opponent_backhand_count` | P1 |
| 打向对手反手得分率 | `shot_to_opponent_backhand_win_rate` | P1 |
| 对手正手失误率 | `opponent_forehand_error_rate` | P1 |
| 对手反手失误率 | `opponent_backhand_error_rate` | P1 |
| 攻击对手弱点比例 | `weakness_targeting_rate` | P2 |
| 战术调整次数 | `tactic_adjustment_count` | P2 |
| 变线次数 | `direction_change_count` | P1 |
| 正手变直线成功率 | `forehand_down_the_line_success_rate` | P1 |
| 反手变直线成功率 | `backhand_down_the_line_success_rate` | P1 |
| 变线制胜分数 | `direction_change_winner_count` | P1 |
| 变线失误数 | `direction_change_error_count` | P1 |
| 不合理变线次数 | `poor_direction_change_count` | P2 |
| 关键分数量 | `key_point_count` | P1 |
| 关键分得分率 | `key_point_win_rate` | P1 |
| 关键分非受迫失误率 | `key_point_unforced_error_rate` | P2 |

战术组合统一结构：

| 字段 | 含义 |
| --- | --- |
| `pattern_code` | 战术编码 |
| `pattern_attempt_count` | 使用次数 |
| `pattern_win_rate` | 得分率 |
| `pattern_error_rate` | 失误率 |
| `avg_pattern_rally_shot_count` | 平均相持拍数 |
| `pattern_confidence` | 识别可信度 |
| `evidence_point_ids` | 典型分 ID |

预设战术编码：

- `wide_serve_then_open_court`
- `target_backhand_repeatedly`
- `crosscourt_then_down_the_line`
- `deep_then_short`
- `center_then_open_angle`
- `deep_return_then_rally`

### 9. 能力画像

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 发球能力 | `serve_score` | P1 |
| 接发能力 | `return_score` | P1 |
| 相持稳定性 | `rally_stability_score` | P1 |
| 进攻与终结能力 | `attack_score` | P1 |
| 防守与脱困能力 | `defense_score` | P1 |
| 移动与覆盖能力 | `movement_score` | P1 |
| 战术执行能力 | `tactic_score` | P2 |
| 关键分能力 | `clutch_score` | P2 |
| 综合能力 | `overall_score` | P1 |
| 主要优势标签 | `strength_labels` | P1 |
| 主要短板标签 | `weakness_labels` | P1 |
| 球员风格标签 | `player_style_labels` | P2 |
| 主要训练方向 | `training_focus_labels` | P1 |

能力评分统一结构：

| 字段 | 含义 |
| --- | --- |
| `ability_code` | 能力编码 |
| `ability_score` | 能力评分 |
| `ability_change` | 与上次相比变化 |
| `sample_size` | 样本量 |
| `confidence` | 可信度 |
| `algorithm_version` | 评分版本 |
| `component_stats` | 子能力列表 |

子能力统一结构：

| 字段 | 含义 |
| --- | --- |
| `component_code` | 子能力编码 |
| `component_score` | 子能力评分 |
| `component_weight` | 权重 |
| `source_metric_codes` | 使用的原始指标 |

### 10. 历史趋势

趋势不为每个指标建立不同字段，统一使用原指标的 `metric_code`。

趋势记录结构：

| 字段 | 含义 |
| --- | --- |
| `metric_code` | 指标字段名 |
| `recorded_at` | 记录时间 |
| `metric_value` | 当前值 |
| `sample_size` | 样本量 |
| `confidence` | 可信度 |
| `video_id` | 对应视频 |

历史对比字段：

| 数据 | 字段名 | 阶段 |
| --- | --- | --- |
| 当前值 | `current_value` | P0 |
| 上一次值 | `previous_value` | P0 |
| 最近五次平均值 | `avg_recent_five_value` | P0 |
| 最近一个月平均值 | `avg_monthly_value` | P0 |
| 个人最佳值 | `personal_best_value` | P0 |
| 个人最差值 | `personal_worst_value` | P0 |
| 历史平均值 | `avg_historical_value` | P0 |
| 历史标准差 | `historical_std_value` | P1 |
| 与上次变化值 | `previous_change_value` | P0 |
| 与上次变化率 | `previous_change_rate` | P0 |
| 长期进步率 | `improvement_rate` | P1 |
| 进步速度 | `improvement_speed` | P2 |

主要展示趋势：

- 一发成功率
- 发球速度
- 正手界内率
- 反手界内率
- 深球率
- 非受迫失误率
- 平均相持拍数
- 移动距离和速度
- 所有能力评分

### 11. 问题诊断与训练建议

| 字段 | 含义 |
| --- | --- |
| `insight_id` | 诊断 ID |
| `insight_type` | `strength`、`weakness`、`trend`、`warning`、`recommendation` |
| `dimension` | 发球、接发、相持等 |
| `severity` | 重要程度 |
| `title` | 标题 |
| `description` | 诊断描述 |
| `possible_reason` | 可能原因 |
| `recommendation` | 改进建议 |
| `training_drill` | 推荐训练方法 |
| `target_metric_code` | 后续观察指标 |
| `target_metric_value` | 建议目标值 |
| `evidence_metric_codes` | 数据证据 |
| `evidence_shot_ids` | 相关击球 |
| `evidence_point_ids` | 相关分 |
| `clip_start_ms` | 视频开始时间 |
| `clip_end_ms` | 视频结束时间 |
| `confidence` | 可信度 |
| `algorithm_version` | 算法版本 |

阶段：

- 规则式诊断：P1
- 个性化 AI 诊断：P2

### 12. 可视化点与视频片段

可视化点字段：

| 字段 | 含义 |
| --- | --- |
| `court_x_m` | 场地坐标 X，单位米 |
| `court_y_m` | 场地坐标 Y，单位米 |
| `timestamp_ms` | 视频时间 |
| `shot_id` | 击球 ID |
| `point_id` | 分 ID |
| `player_slot` | 球员 |
| `visualization_type` | `landing`、`movement`、`hit_position` 等 |
| `value` | 热力或权重值 |

视频片段字段：

| 数据 | 字段名 |
| --- | --- |
| 视频片段 ID | `clip_id` |
| 片段类型 | `clip_type` |
| 开始时间 | `clip_start_ms` |
| 结束时间 | `clip_end_ms` |
| 关联分 | `point_id` |
| 关联击球 | `shot_ids` |
| 标签 | `clip_labels` |
| 评分 | `clip_score` |

---

## 十一、跨字段一致性规则

### 1. 分与拍的引用关系

- `videos.video_id` 是原始视频资产和视频分析结果的唯一 ID。
- `points.video_id` 必须指向 `videos.video_id`。
- `shots.point_id` 必须指向 `points.point_id`。
- `points.terminal_shot_id` 指向结束该分的 `shots.shot_id`。
- 应用层必须保证 `terminal_shot_id` 指向的 shot 属于当前 point。

### 2. 发球成功、Ace、发球直接得分

- `first_serve_in` 和 `second_serve_in` 表示发球是否落入正确发球区并成为合法发球。
- Ace 和发球直接得分也算发球成功，不要求后续出现接发或相持。
- 一发成功时，不应再出现二发。
- 双误必须由第二发 `serve_fault` 结束该分。

### 3. 分结果和拍结果

- `points.point_result` 保存每分层面的统计结果。
- `points.ending_reason` 保存每分层面的粗粒度结束原因。
- `shots.shot_result` 保存每拍层面的统计结果。
- `shots.error_type` 保存具体失误形式，尤其是 `long` 和 `wide`。
- `points.ending_reason = out` 时，如需区分过长或过宽，应读取终结拍 `shots.error_type`。

### 4. 典型结果组合

正常相持继续：

```text
shot_result = continue
error_forcedness = NULL
error_type = NULL
is_point_ending = false
point_winner_slot = NULL
```

正手非受迫下网：

```text
stroke_side = forehand
shot_result = error
error_forcedness = unforced
error_type = net
is_point_ending = true
```

发球擦网重发：

```text
shot_role = serve
shot_result = let
is_point_ending = false
```

一发失误：

```text
shot_role = serve
serve_number = 1
shot_result = serve_fault
is_point_ending = false
```

双误的第二发：

```text
shot_role = serve
serve_number = 2
shot_result = serve_fault
is_point_ending = true
point_result = double_fault
```

### 5. 非落库字段派生约定

| 字段 | 派生规则 |
| --- | --- |
| `returner_slot` | `server_slot = A` 时为 `B`，`server_slot = B` 时为 `A` |
| `point_duration_ms` | `end_time_ms - start_time_ms` |
| `previous_shot_id` | 同一 `point_id` 内 `shot_index - 1` 对应的 `shot_id` |
| `rally_shot_count` | 有有效发球时为 `in_play_shot_count - 1`，发球直接结束时为 `0` |
| `point_count` | 当前统计范围内 `points` 数量 |
| `shot_count` | 当前统计范围内 `shots` 数量 |
| `winner_count` | `point_result = winner` 或按终结拍 `shot_result = winner` 统计，具体口径需在接口实现中固定 |
| `long_error_count` | 终结拍 `error_type = long` |
| `wide_error_count` | 终结拍 `error_type = wide` |

---

## 十二、开发阶段

| 阶段 | 含义 |
| --- | --- |
| P0 | 基础数据直接统计，第一版完成 |
| P1 | 需要规则推断，第一版后期完成 |
| P2 | 复杂战术、长期模型或群体模型 |

P0 范围：

- 数据总览
- 得分与失分
- 发球基础数据
- 接发基础数据
- 正反手、速度、深度和线路
- 移动轨迹与热力图
- 每分、每拍和视频明细
- 基础历史趋势

P1 范围：

- 受迫和非受迫失误
- 来球压力
- 击球质量
- 接发质量
- 进攻、防守和主动权
- 回位分析
- 发球后第一拍
- 能力评分
- 问题诊断和训练建议

P2 范围：

- 复杂战术组合
- 对手弱点识别
- 球员风格
- 关键分能力
- 长期进步模型
- 同水平用户百分位
- 个性化训练计划

所有 P1、P2 数据现在先保留字段和接口位置，不能从整体数据设计中删除。

---

## 十三、后续新增字段检查清单

新增或修改任何字段前，必须确认：

1. 字段名是否符合 `snake_case` 和后缀单位规则。
2. 字段属于落库字段、逐帧文件字段、算法结果字段、接口聚合字段还是前端展示字段。
3. 是否已有同义字段，是否会造成跨端重复命名。
4. 数据类型、单位、空值含义、默认值是否明确。
5. 是否需要新增枚举值，枚举值是否已写入本文件。
6. 是否需要新增数据库约束、索引、外键或迁移。
7. 是否需要新增 API schema、前端类型、App 模型和测试用例。
8. 如果是统计指标，是否明确 `metric_code`、`metric_unit`、`sample_size`、`scope_type`、`confidence` 和 `algorithm_version`。
9. 如果是 P1/P2 算法字段，是否明确输入来源、计算口径、算法版本和可回溯证据。
