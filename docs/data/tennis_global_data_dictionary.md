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
2. 第一版落库字段以 `users`、`uploads`、`points`、`shots` 四张表为准。
3. Web 看板指标、趋势、诊断、视频片段、可视化点和明细页计算字段，除非出现在四张核心表中，否则均为 `非落库字段`。
4. `非落库字段` 可以由数据库字段、`frame_data.jsonl`、算法结果或接口聚合计算得到，不要求第一版新增数据库列。
5. `NULL` 表示未采集、未标注、不适用或历史数据缺失；`unknown` 表示已完成分析但无法可靠分类。
6. 布尔字段中，`NULL`、`false`、`true` 含义必须严格区分。`NULL` 不是 `false`。
7. 比例统一保存为 `0～1`，评分统一保存为 `0～100`，置信度统一保存为 `0～1`。

---

## 二、数据分层

| 数据层 | 是否持久化 | 主要载体 | 说明 |
| --- | --- | --- | --- |
| 用户与上传任务 | 落库 | `users`、`uploads` | 用户、视频文件、分析任务、机位和球员槽位 |
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

### 1. 用户与上传枚举

| 枚举字段 | 可选值 | 说明 |
| --- | --- | --- |
| `status` | `active`、`disabled`、`deleted` | 用户状态 |
| `playing_hand` | `right`、`left`、`unknown` | 用户主要持拍手 |
| `activity_type` | `match`、`training`、`drill` | 视频活动类型 |
| `analysis_status` | `uploaded`、`processing`、`completed`、`failed` | 分析任务状态 |
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
| `scope_type` | `upload`、`set`、`game`、`point`、`history` | 统计范围 |
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
| `avatar_path` | TEXT | 是 |  | 头像文件路径 |  |
| `phone` | VARCHAR(30) | 是 |  | 手机号 | 非空时唯一 |
| `email` | VARCHAR(255) | 是 |  | 邮箱 | 非空时唯一，大小写不敏感 |
| `status` | VARCHAR(20) | 否 | `active` | 用户状态 | `active`、`disabled`、`deleted` |
| `playing_hand` | VARCHAR(10) | 否 | `right` | 用户主要持拍手 | `right`、`left`、`unknown` |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

约束与索引：

- `status IN ('active', 'disabled', 'deleted')`
- `playing_hand IN ('right', 'left', 'unknown')`
- `PRIMARY KEY (user_id)`
- `UNIQUE INDEX lower(email) WHERE email IS NOT NULL AND deleted_at IS NULL`
- `UNIQUE INDEX phone WHERE phone IS NOT NULL AND deleted_at IS NULL`

### 2. `uploads` 上传记录表

一条记录代表一次视频上传和一次分析任务。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `upload_id` | UUID | 否 | 自动生成 | 上传记录主键 | 主键 |
| `owner_user_id` | UUID | 否 |  | 上传者 | FK: `users.user_id` |
| `filename` | VARCHAR(255) | 否 |  | 系统生成的唯一视频文件名 | 唯一 |
| `original_filename` | TEXT | 是 |  | 用户上传时的原始文件名 |  |
| `activity_type` | VARCHAR(20) | 否 |  | 视频活动类型 | `match`、`training`、`drill` |
| `video_path` | TEXT | 否 |  | 原始视频文件路径 | 唯一 |
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
| `analysis_status` | VARCHAR(30) | 否 | `uploaded` | 分析任务状态 | `uploaded`、`processing`、`completed`、`failed` |
| `analysis_version` | VARCHAR(50) | 是 |  | 分析流程和算法版本 |  |
| `error_message` | TEXT | 是 |  | 分析失败原因 |  |
| `captured_at` | TIMESTAMPTZ | 是 |  | 视频实际拍摄时间 |  |
| `created_at` | TIMESTAMPTZ | 否 | 当前时间 | 上传记录创建时间 |  |
| `updated_at` | TIMESTAMPTZ | 否 | 当前时间 | 更新时间 |  |
| `deleted_at` | TIMESTAMPTZ | 是 |  | 软删除时间 |  |

`filename` 推荐生成规则：

```text
{user_id}_{timestamp_ms}_{upload_id}.{extension}
```

约束与索引：

- `activity_type IN ('match', 'training', 'drill')`
- `analysis_status IN ('uploaded', 'processing', 'completed', 'failed')`
- `primary_player_slot IN ('A', 'B') OR primary_player_slot IS NULL`
- `camera_view_angle IN ('overhead', 'horizontal') OR camera_view_angle IS NULL`
- `camera_view_position IN ('side', 'rear', 'front', 'rear_side', 'front_side') OR camera_view_position IS NULL`
- `video_duration_ms >= 0`
- `video_frame_count >= 0`
- `video_fps > 0`
- `video_width_px > 0`
- `video_height_px > 0`
- `player_a_user_id <> player_b_user_id`
- `PRIMARY KEY (upload_id)`
- `UNIQUE (filename)`
- `UNIQUE (video_path)`
- `INDEX (owner_user_id, created_at DESC)`
- `INDEX (analysis_status, created_at)`
- `INDEX (camera_view_angle, camera_view_position)`
- `INDEX (player_a_user_id, created_at DESC)`
- `INDEX (player_b_user_id, created_at DESC)`

### 3. `points` 每分表

一条记录代表视频中的一分。

| 字段 | 类型 | 是否为空 | 默认值 | 含义 | 单位/枚举/引用 |
| --- | --- | --- | --- | --- | --- |
| `point_id` | UUID | 否 | 自动生成 | 每分主键 | 主键 |
| `upload_id` | UUID | 否 |  | 所属上传记录 | FK: `uploads.upload_id` |
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
- `UNIQUE (upload_id, point_index)`
- `INDEX (upload_id, start_time_ms)`
- `INDEX (upload_id, winner_slot)`
- `INDEX (upload_id, server_slot)`
- `INDEX (terminal_shot_id)`

发球摘要关系：

- `first_serve_in = true` 时，`second_serve_used = false`，`second_serve_in = NULL`，`is_double_fault = false`。
- `second_serve_used = false` 时，`second_serve_in = NULL`，`is_double_fault = false`。
- `is_double_fault = true` 时，`first_serve_in = false`，`second_serve_used = true`，`second_serve_in = false`，`point_result = 'double_fault'`。

### 4. `shots` 每拍表

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

数据库通过 `uploads.frame_data_path` 找到对应文件，`uploads.frame_data_version` 标识逐帧数据结构版本。

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
| `upload_id` | 上传任务 ID | UUID string |
| `player_slot` | 球员 A 或 B | `A`、`B` |
| `metric_code` | 本文件定义的指标字段名 | string |
| `metric_name` | 指标显示名称 | string |
| `metric_value` | 指标值 | 按 `metric_code` 单位 |
| `metric_unit` | 单位 | string |
| `sample_size` | 样本量 | count |
| `scope_type` | 统计范围 | `upload`、`set`、`game`、`point`、`history` |
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
| `upload_id` | 对应上传 |

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

- `uploads.upload_id` 是一次上传和分析任务的唯一 ID。
- `points.upload_id` 必须指向 `uploads.upload_id`。
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
