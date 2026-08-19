# UI 命名注册表

这份文档只给“用户能明显感知的一大块”命名：页面、子页面、页面模式、主板块、抽屉、弹窗、底部弹层、详情区、列表区，以及少量重要复用组件。

普通按钮、图标、输入框、分割线、纯装饰元素不单独命名。

## 命名规则

统一格式：

```text
<端>.<业务域>.<对象>
```

示例：

```text
app.profile.profile_menu_drawer
app.create_menu_sheet.lesson_entry
app.post_detail.comments_panel
```

约定：

1. `端` 先用 `app`、`admin`、`web` 这样的前缀。
2. `业务域` 尽量稳定，优先按页面或业务场景分组。
3. `对象` 用小写英文和下划线，保持可读、稳定，不跟文案走。
4. 同类重复实例可追加 `#<key>`，例如 `app.home.feed_card#post_123`。
5. 加载、空、错误、未登录等可见状态也算对象，建议命名为 `*_state`。

## 类型词表

下面这些类型词主要是为了让命名更统一，不要求一次性用全。

| 类型 | 含义 |
| --- | --- |
| `screen` | 独立页面 |
| `tab` | 底部或顶部切换项 |
| `tab_entry` | 特别突出的导航入口 |
| `tab_panel` | 某个 Tab 对应的内容区 |
| `section` | 页面中的主分区 |
| `panel` | 独立面板块 |
| `card` | 卡片式内容块 |
| `list` | 列表区 |
| `list_item` | 列表项 |
| `sheet` | 底部弹层 |
| `drawer` | 抽屉 |
| `modal` | 覆盖式弹窗 |
| `dialog` | 确认框 / 原生提示框 |
| `form` | 表单区 |
| `stage` | 主展示区 / 舞台区 |
| `state` | 加载、空、错误、未登录等状态块 |
| `mode` | 页面模式 |
| `subview` | 同一页面里的二级视图 |
| `notice` | 提示型可见信息块 |
| `component` | 重要复用组件 |

## 当前范围

当前先整理移动端 App 第一版。后续 Admin / Web 可以沿用同一规则补表。

## App 壳层与主导航

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.main_tabs` | 底部导航 | shell | 首页、训练、创建、消息、我的的主壳层 |
| `app.main_tabs.home` | 首页入口 | tab | 底部导航首页 |
| `app.main_tabs.training` | 训练入口 | tab | 底部导航训练 |
| `app.main_tabs.create_entry` | 创建入口 | tab_entry | 底部中间的创建入口 |
| `app.main_tabs.messages` | 消息入口 | tab | 底部导航消息 |
| `app.main_tabs.profile` | 我的入口 | tab | 底部导航我的 |

## 首页

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.home` | 首页 | screen | 信息流主页面 |
| `app.home.feed_switcher` | 信息流切换区 | section | 推荐 / 关注 / 附近 |
| `app.home.feed_list` | 动态流 | list | 首页主内容列表 |
| `app.home.feed_card` | 动态卡片 | component | 信息流中的单条内容卡 |
| `app.home.nearby_filter_panel` | 附近筛选区 | panel | 附近信息流的城市 / 区域条件区 |
| `app.home.loading_state` | 首页加载状态 | state | 首页首次加载或刷新中 |
| `app.home.error_state` | 首页错误状态 | state | 首页内容加载失败时的可见状态 |

## 训练页

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.training` | 训练页 | screen | 训练总览与最近活动 |
| `app.training.weekly_overview_card` | 本周概览卡 | card | 本周数据和简要趋势 |
| `app.training.record_section` | 记录区 | section | 记录练习 / 比赛 / 课程的入口区 |
| `app.training.recent_activity_list` | 最近活动列表 | list | 最近活动的列表区 |
| `app.training.loading_state` | 训练页加载状态 | state | 训练页数据加载中 |

## 创建入口

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.create_menu_sheet` | 创建菜单 | sheet | 点击中间创建入口后弹出的底部弹层 |
| `app.create_menu_sheet.root_step` | 创建首层 | subview | “发布动态 / 创建网球日记”这一层 |
| `app.create_menu_sheet.journal_step` | 创建日记二层 | subview | 选择练习 / 比赛 / 课程这一层 |
| `app.create_menu_sheet.publish_post_entry` | 发布动态入口 | menu_item | 发布动态这一项 |
| `app.create_menu_sheet.create_journal_entry` | 创建网球日记入口 | menu_item | 进入网球日记类型选择这一项 |
| `app.create_menu_sheet.practice_entry` | 练习记录入口 | menu_item | 选择“记录练习” |
| `app.create_menu_sheet.match_entry` | 比赛记录入口 | menu_item | 选择“记录比赛” |
| `app.create_menu_sheet.lesson_entry` | 课程记录入口 | menu_item | 选择“记录课程” |

## 发布动态

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.create_post` | 发布动态页 | screen | Post 发布流程 |
| `app.create_post.content_section` | 内容区 | section | 标题、正文等内容输入区 |
| `app.create_post.visibility_section` | 可见范围区 | section | 公开 / 仅自己 |
| `app.create_post.location_section` | 发布位置区 | section | 发布时的位置展示与刷新 |
| `app.create_post.video_section` | 短视频区 | section | 选择视频、上传进度、视频状态 |
| `app.create_post.draft_panel` | 草稿提示区 | panel | Post 草稿已创建时的提示块 |
| `app.create_post.action_bar` | 发布操作区 | section | 底部发布 / 取消草稿操作区 |
| `app.create_post.loading_state` | 发布页加载状态 | state | 登录态确认中 |
| `app.create_post.guest_state` | 发布页未登录状态 | state | 未登录提示与登录入口 |

## 创建网球日记

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.create_activity` | 创建网球日记页 | screen | 创建活动记录的主页面 |
| `app.create_activity.context_panel` | 日记说明区 | panel | 顶部的当前记录说明 |
| `app.create_activity.training_type_section` | 练习类型区 | section | 仅练习模式下的类型选择 |
| `app.create_activity.lesson_picker_section` | 课程选择区 | section | 课程模式下的课程绑定入口 |
| `app.create_activity.activity_info_section` | 活动信息区 | section | 标题、时间、地点、对手、备注 |
| `app.create_activity.surface_section` | 场地类型区 | section | 硬地 / 红土 / 草地 / 地毯 |
| `app.create_activity.visibility_section` | 可见范围区 | section | 记录可见范围 |
| `app.create_activity.video_queue_section` | 相册视频区 | section | 相册选择的视频列表、进度和状态 |
| `app.create_activity.upload_status_panel` | 视频上传状态区 | panel | 视频上传阶段、失败提示和重试状态 |
| `app.create_activity.upload_draft_panel` | 视频上传草稿区 | panel | 服务端 Activity 草稿已创建时的状态提示 |
| `app.create_activity.lesson_picker_modal` | 课程选择弹窗 | modal | 绑定课程时弹出的课程列表 |
| `app.create_activity.save_bar` | 保存操作区 | section | 底部保存记录操作 |
| `app.create_activity.loading_state` | 创建活动加载状态 | state | 登录态确认中 |
| `app.create_activity.guest_state` | 创建活动未登录状态 | state | 未登录提示与登录入口 |

## 上传视频

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.upload_video` | 上传视频页 | screen | 一次上传多个视频到 Activity |
| `app.upload_video.mode_section` | 上传模式区 | section | 个人 / 教练示范 / 课程练习等模式 |
| `app.upload_video.lesson_picker_modal` | 课程选择弹窗 | modal | 课程练习或关联课程时弹出 |
| `app.upload_video.video_queue_section` | 视频队列区 | section | 选中的视频列表、进度和状态 |
| `app.upload_video.location_section` | 位置区 | section | 位置刷新与粗粒度地点展示 |
| `app.upload_video.intent_panel` | 上传草稿区 | panel | 服务端 Activity 草稿已创建时的提示块 |
| `app.upload_video.action_bar` | 上传操作区 | section | 上传、取消草稿、重试等操作区 |
| `app.upload_video.loading_state` | 上传页加载状态 | state | 登录态确认中 |
| `app.upload_video.guest_state` | 上传页未登录状态 | state | 未登录提示与登录入口 |

## 消息页

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.messages` | 消息页 | screen | 消息中心主页面 |
| `app.messages.view_switcher` | 消息视图切换区 | section | 通知 / 聊天 / 请求 |
| `app.messages.notification_list` | 通知列表 | list | 系统通知与互动通知 |
| `app.messages.conversation_list` | 会话列表 | list | 私信和群聊会话 |
| `app.messages.request_list` | 请求列表 | list | 消息请求列表 |
| `app.messages.loading_state` | 消息页加载状态 | state | 登录态确认或消息加载中 |
| `app.messages.error_state` | 消息页错误状态 | state | 某一类消息加载失败 |

## 我的页

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.profile` | 我的页 | screen | 个人中心主页面 |
| `app.profile.player_mode` | 球员模式 | mode | 我的页默认模式 |
| `app.profile.coach_workspace` | 教练工作台 | mode | 教练身份下的工作区 |
| `app.profile.player_header` | 个人资料头部 | section | 头像、昵称、资料状态、教练入口 |
| `app.profile.player_stats` | 数据统计区 | section | 动态、比赛、训练、课程统计 |
| `app.profile.social_stats` | 社交统计区 | section | 获赞、互关、关注、粉丝统计，互关/关注/粉丝可点击 |
| `app.profile.content_tabs` | 内容分类区 | section | 动态、比赛、训练、课程、收藏、赞过、数据 |
| `app.profile.content_area` | 内容展示区 | section | 各 Tab 的内容结果区 |
| `app.profile.profile_menu_drawer` | 功能菜单抽屉 | drawer | 右上角三横线打开的抽屉 |
| `app.profile.profile_menu_drawer.account_profile_entry` | 账号资料入口 | menu_item | 进入资料编辑页 |
| `app.profile.profile_menu_drawer.coach_identity_entry` | 教练身份入口 | menu_item | 进入教练申请或状态页 |
| `app.profile.profile_menu_drawer.settings_entry` | 设置入口 | menu_item | 进入设置页 |
| `app.profile.guest_state` | 我的页未登录状态 | state | 未登录时的入口页 |
| `app.profile.loading_state` | 我的页加载状态 | state | 登录态确认中 |

## 账号资料

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.profile.edit` | 账号资料页 | screen | 头像、昵称、持拍手编辑页 |
| `app.profile.edit.avatar_section` | 头像区 | section | 头像选择与预览 |
| `app.profile.edit.basic_info_form` | 基本资料表单 | form | 昵称和持拍手 |
| `app.profile.edit.save_bar` | 保存操作区 | section | 保存资料按钮区 |
| `app.profile.edit.loading_state` | 资料页加载状态 | state | 登录态确认中 |
| `app.profile.edit.guest_state` | 资料页未登录状态 | state | 未登录提示与登录入口 |

## 教练身份

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.profile.coach_apply` | 教练身份页 | screen | 教练申请和身份状态页 |
| `app.profile.coach_apply.identity_summary` | 身份摘要区 | panel | 当前教练身份状态 |
| `app.profile.coach_apply.application_form` | 申请表单 | form | 展示名称、电话、城市等 |
| `app.profile.coach_apply.qualification_section` | 资质说明区 | section | 认证类型与资质信息 |
| `app.profile.coach_apply.evidence_section` | 证明材料区 | section | 证书或示范视频等材料 |
| `app.profile.coach_apply.submit_bar` | 提交操作区 | section | 提交申请按钮区 |
| `app.profile.coach_apply.loading_state` | 教练页加载状态 | state | 身份同步中 |
| `app.profile.coach_apply.guest_state` | 教练页未登录状态 | state | 未登录提示与登录入口 |

## 设置

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.profile.settings` | 设置页 | screen | 账户与登录状态设置页 |
| `app.profile.settings.account_section` | 账户区 | section | 账号资料入口 |
| `app.profile.settings.login_status_section` | 登录状态区 | section | 退出登录入口 |
| `app.profile.settings.logout_confirm_dialog` | 退出登录确认框 | dialog | 原生确认弹窗 |
| `app.profile.settings.loading_state` | 设置页加载状态 | state | 登录态确认中 |
| `app.profile.settings.guest_state` | 设置页未登录状态 | state | 未登录提示与登录入口 |

## 登录

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.login` | 登录页 | screen | 手机号验证码登录页 |
| `app.login.header` | 登录头部 | section | 标题、说明、品牌标识 |
| `app.login.form` | 登录表单 | form | 手机号和验证码输入区 |
| `app.login.agreement_section` | 协议区 | section | 用户协议与隐私政策勾选 |
| `app.login.action_area` | 登录操作区 | section | 登录、获取验证码、微信登录 |
| `app.login.wechat_login_notice` | 微信登录提示 | notice | 点击微信登录时的不可用提示 |

## 活动详情

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.activity_detail` | 活动详情页 | screen | Tennis Activity 详情页 |
| `app.activity_detail.tab_bar` | 详情分栏区 | section | 概览、视频、数据、建议 |
| `app.activity_detail.overview_tab` | 概览区 | tab_panel | 活动基础信息与摘要 |
| `app.activity_detail.videos_tab` | 视频区 | tab_panel | 关联视频和播放区 |
| `app.activity_detail.data_tab` | 数据区 | tab_panel | 统计数据和分析结果 |
| `app.activity_detail.advice_tab` | 建议区 | tab_panel | 训练建议和复盘建议 |
| `app.activity_detail.video_list` | 视频列表 | list | 关联视频列表 |
| `app.activity_detail.loading_state` | 活动详情加载状态 | state | 详情加载中 |
| `app.activity_detail.empty_state` | 活动详情空状态 | state | 没有数据或无权限时的提示 |

## 动态详情

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.post_detail` | 动态详情页 | screen | 单条动态详情页 |
| `app.post_detail.media_stage` | 主展示区 | stage | 视频 / 封面主展示区 |
| `app.post_detail.action_bar` | 互动操作区 | section | 点赞、收藏、评论等互动区 |
| `app.post_detail.comments_panel` | 评论面板 | panel | 底部评论弹层 |
| `app.post_detail.comment_composer` | 评论输入区 | section | 评论输入与发送区 |
| `app.post_detail.loading_state` | 动态详情加载状态 | state | 详情加载中 |

## 用户主页

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.user_profile` | 发布者主页 | screen | 用户公开主页 |
| `app.user_profile.header` | 主页头部 | section | 头像、昵称、关系状态 |
| `app.user_profile.social_stats` | 社交统计区 | section | 粉丝、互关、动态等 |
| `app.user_profile.relationship_actions` | 关系操作区 | section | 关注、私信、消息请求等 |
| `app.user_profile.loading_state` | 用户主页加载状态 | state | 用户资料加载中 |

## 学员档案

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.student_profile` | 学员档案页 | screen | 教练视角的学员资料页 |
| `app.student_profile.identity_card` | 学员身份卡 | card | 学员身份、等级、最近上课信息 |
| `app.student_profile.record_section` | 记录区 | section | 训练 / 比赛 / 视频记录概览 |
| `app.student_profile.coach_review_card` | 教练评价卡 | card | 阶段反馈与教练评语 |

## 私信

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.chat` | 聊天页 | screen | 单个会话详情页 |
| `app.chat.header` | 会话头部 | section | 头像、会话名、返回区 |
| `app.chat.message_timeline` | 消息时间线 | list | 历史消息与滚动加载 |
| `app.chat.composer` | 输入区 | section | 文本输入与发送区 |
| `app.chat.loading_state` | 聊天加载状态 | state | 会话加载中 |

## 球友搜索

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.friend_search` | 球友搜索页 | screen | 搜索昵称或球友 ID |
| `app.friend_search.search_bar` | 搜索栏 | section | 输入框与清空区 |
| `app.friend_search.state_panel` | 状态区 | state | 未登录、搜索中、空结果、错误 |
| `app.friend_search.result_list` | 搜索结果列表 | list | 球友结果列表 |
| `app.friend_search.result_item` | 搜索结果项 | list_item | 单条用户结果 |

## 关注 / 粉丝列表

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `app.friend_list` | 关注/粉丝列表页 | screen | 互关、关注、粉丝用户列表 |
| `app.friend_list.user_list` | 用户列表 | list | 对应类型的用户列表 |
| `app.friend_list.user_item` | 用户列表项 | list_item | 单条用户，含头像、昵称与关系操作 |

## 重要复用组件

这些组件不是每个都必须在日常沟通里单独点名，但当它们跨页面反复出现时，可以作为稳定对象引用。

| ID | 中文名 | 类型 | 说明 |
| --- | --- | --- | --- |
| `components.top_bar` | 顶部栏 | component | 页面通用顶栏 |
| `components.scroll_page` | 滚动页面容器 | component | 通用滚动页面壳 |
| `components.segmented_control` | 分段切换器 | component | 选项切换控件 |
| `components.card` | 内容卡片 | component | 通用卡片容器 |
| `components.row_button` | 行入口 | component | 通用列表入口行 |
| `components.avatar` | 头像 | component | 头像展示组件 |
| `components.metric_card` | 指标卡 | component | 单项指标展示 |
| `components.pill` | 状态标签 | component | 小状态胶囊标签 |
| `components.section_header` | 分区标题 | component | 区块标题行 |
| `components.icon_badge` | 图标徽章 | component | 带底色的图标块 |

## 后续补充方式

如果后面新增页面或板块，就按同样规则继续往下加：

1. 先定页面名。
2. 再定主板块名。
3. 最后只给少数真正重要的复用组件命名。
