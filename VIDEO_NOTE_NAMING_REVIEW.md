# Video Note Naming Review

> 复查对象：`tennis_data_master_app` 当前 `main` 分支（HEAD `6b6538d`，工作区干净）。
> 复查目标：评估 Codex 将 `VideoNoteProject / Note / notes` 重命名为 `VideoNote / NoteAnnotation / noteAnnotations` 这一轮工作的完整性、准确性与一致性。
> 本文档仅做检查，不修改任何代码、配置、数据、测试或文档。

---

## 1. 总体结论

**本次重命名复查的最关键结论：本仓库当前 `main` 分支并不存在 `VideoNoteProject / Note / notes` 这套领域，也未引入 `VideoNote / NoteAnnotation / noteAnnotations` 这套新领域。**

具体证据：

- 在仓库内对源码、配置、Schema、文档、测试进行大小写不敏感的全文搜索后：
  - `VideoNoteProject` —— **0 处命中**
  - `VideoNote` / `videoNote` / `video_note` —— **0 处命中**
  - `NoteAnnotation` / `noteAnnotation` / `note_annotation` —— **0 处命中**
  - `PlaybackPlan` —— **0 处命中**
  - `VideoCanvas` —— **0 处命中**
- 数据库（`docs/data/tennis_global_data_dictionary.md`、`docs/data/网球数据库设计.md`、`backend/db/`）列出的表只有：
  `users`、`coach_applications`、`coach_profiles`、`admin_users`、`admin_credentials`、`auth_identities`、`auth_sessions`、`auth_verification_codes`、`lessons`、`lesson_students`、`tennis_activities`、`videos`、`video_shares`、`social_posts`、`social_post_stats`、`post_reactions`、`post_favorites`、`post_comments`、`post_shares`、`post_media`、`user_follows`、`user_social_stats`、`user_blocks`、`user_privacy_settings`、`user_post_views`、`user_post_hides`、`chat_conversations`、`chat_conversation_members`、`chat_messages`、`chat_message_attachments`、`chat_message_requests`、`notification_events`、`user_notifications`、`user_inbox_counters`、`content_reports`、`points`、`shots`。
  **没有任何与“视频笔记 / 视频批注”对应的表。**
- 后端代码模块（`backend/app/`）仅有：`admin / auth / coach / core / locations / messages / posts / privacy / profile / reports / social / uploads / users`。**没有 playback / editor / canvas / annotation 模块。**
- 移动端代码（`app/app`、`app/api`、`app/components`）只有上传视频、动态、聊天、消息、个人页、训练页等页面。**没有任何 VideoNote / NoteAnnotation 的页面、组件、Hook、API 或 TypeScript 类型。**
- `docs/PRODUCT_FEATURE_SPEC.md` 第 19 行明确写明“视频批注”目前仍属于“演示或占位的移动端范围”，即：**该功能尚未在代码中实现**。
- `git log` 全量搜索也没有出现 `VideoNote`、`NoteAnnotation`、`rename`、重命名、`note→annotation` 等提交记录；当前 `main` 仅有最近 30+ 条业务功能提交。

因此：

> **Codex 这一轮重命名无法在本仓库验证为“已完成”。要么该轮重命名根本没有落到本仓库，要么它被 revert，要么它在另一个未合并的分支或另一个仓库上执行。**

风险判断：

- **无破坏风险**：因为根本不存在被误改的代码路径。
- **有沟通风险**：如果用户认为 Codex 已经完成了本次重命名，但实际上没有，那么后续所有基于 `VideoNote` / `NoteAnnotation` 的设计、API、持久化、UI 都还没有动工；任何“复用了重命名结果”的下游工作需要重新对齐。

---

## 2. 遗漏的旧命名

| 项目 | 位置 | 当前名称 | 建议名称 | 原因 |
| --- | --- | --- | --- | --- |
| 无 | 无 | 无 | 无 | 仓库中未发现任何 `VideoNoteProject` / `Note` / `notes` 的“视频笔记 / 视频批注”相关用法，因此**不存在尚未替换的旧命名**。 |

> 注：仓库内仍存在若干 `note` 字段字符串，例如 `coach_applications.note`（申请补充说明）、`admin_credentials.note`（授权备注）、`tennis_activities.note`（用户备注）、`content_reports.resolution_note`（处置备注）。这些字段表达的是“自由文本备注”，与“视频笔记 / 视频批注”是完全不同的概念，**不应被改名为 `noteAnnotation`**。详见第 3 节。

---

## 3. 可能的误改

由于本仓库目前并不存在 `VideoNote / NoteAnnotation` 领域，**不可能出现“把 `Note` 改成 `NoteAnnotation`”这种误改**。

但仍需明确指出：**未来引入这套领域时，绝对不应该把下列自由文本字段一起改成 `noteAnnotation`**，否则会出现领域语义错误：

| 文件 / 表 | 当前字段 | 当前含义 | 如果误改成 `noteAnnotation` 会变成什么 |
| --- | --- | --- | --- |
| `backend/app/uploads/schemas.py:145, 181, 212` | `UploadIntentCreate.note`、`TennisActivityCreate.note`、`TennisActivityRecord.note` | 网球活动的自由文本备注 | “活动内的一条视频批注”——语义错误 |
| `docs/data/tennis_global_data_dictionary.md:312` | `coach_applications.note` | 教练认证申请的补充说明 | “教练认证申请内的一条视频批注”——语义错误 |
| `docs/data/tennis_global_data_dictionary.md:373` | `admin_credentials.note` | 管理员授权备注 | “管理员授权记录内的一条视频批注”——语义错误 |
| `docs/data/tennis_global_data_dictionary.md:590` | `docs/data/网球数据库设计.md:269` | `tennis_activities.note` | 用户对活动的备注 | “活动内的一条视频批注”——语义错误 |
| `docs/data/tennis_global_data_dictionary.md:847` | `content_reports.resolution_note` | 内容审核处置备注 | “举报处理内的一条视频批注”——语义错误 |
| `app/app/upload-video.tsx:184, 443, 797, 801, 805` | `note` 状态 + `note` 输入框 + payload 字段 | 上传视频时输入的“备注” | 错误地暗示这是“视频批注”——会和 `noteAnnotation` 命名空间冲突 |
| `admin/src/mockData.js:76, 101, 126`、`admin/src/app.js:110, 204, 218` | `note` 字段与表单 | 教练申请 / 活动 / 备注 UI | 同上 |

> 这些位置应当**保持现状**（`note` / `备注`），未来引入 `NoteAnnotation` 时建议单独建表，并使用独立字段名（例如 `video_note_annotations` 表、`video_id` 外键、`note_annotation_id` 主键、`start_time_ms` / `elements` 等），不要复用现有 `note` 字段。

---

## 4. 领域语义或逻辑不一致

因为 `VideoNote / NoteAnnotation` 领域在仓库中**根本不存在**，无法定位到具体的代码逻辑出现“名字改了但语义还是旧的”这种问题。

但通过阅读现有代码可以确认一个事实：

- 当前仓库的视频相关领域只有一条：
  ```text
  tennis_activities  ──┐
                       ├── videos[]（视频资产）
  social_posts ─────► post_media[].video_id ──► videos（社交动态引用）
  ```
  其中视频层没有任何“视频笔记”或“视频批注”层级。`videos` 表只保存原始视频元信息，没有 `note_annotations` / `elements` 之类的子结构。

- `docs/PRODUCT_FEATURE_SPEC.md` 描述的“视频批注”是面向未来的功能，目前**连一个最小的数据模型都没有**：
  - 没有 `video_note_annotations` 表；
  - 没有 `note_annotation_id` / `start_time_ms` / `end_time_ms` 等列；
  - 没有前端页面 / 组件 / Hook；
  - 没有 `PlaybackPlan`、`VideoCanvas`、`Editor`、`Timeline` 等模块；
  - 没有针对该领域的 mock 数据 / demo 数据；
  - 没有针对该领域的 backend 测试 / app 测试 / cv 测试。

> 因此本节判定：**不存在代码层面的“名字与语义不一致”问题**。

---

## 5. 前后端 / API / 数据结构一致性

### 5.1 现状

- 后端 `backend/app/uploads/schemas.py`、`shared/api-schema/activity-detail.md`、`shared/api-schema/uploads.md` 等都只定义了 `TennisActivity*`、`VideoRecord`、`UploadIntent*`、`VideoUploadIntent*`、`Lesson*`、`ActivityDetail*` 等结构，**完全没有 `VideoNote` / `NoteAnnotation`**。
- 前端 `app/api/uploads.ts`、`app/api/activityDetail.ts`、`app/api/posts.ts`、`app/api/coach.ts` 等也只引用 `ActivityType`、`ActivityVisibility`、`TennisActivityRecord`、`VideoRecord`、`LessonOption`，**完全没有 `VideoNote` / `NoteAnnotation`**。
- `docs/data/tennis_global_data_dictionary.md` 列出的字段、枚举、表、索引中**没有**任何 `VideoNote`、`NoteAnnotation`、`noteAnnotations` 字段或表。
- `shared/api-schema/` 目录下的所有 `.md` 文档（activity-detail、admin、auth、locations、posts、profile-content、social-messages、uploads、users）**都没有** `VideoNote` / `NoteAnnotation` 相关条目。

### 5.2 一致性结论

| 端 | 是否包含 `VideoNote` | 是否包含 `NoteAnnotation` | 是否包含 `noteAnnotations` |
| --- | --- | --- | --- |
| 移动端 App（`app/`） | 否 | 否 | 否 |
| 后端 FastAPI（`backend/`） | 否 | 否 | 否 |
| 数据库 / 全局数据字典（`docs/data/`） | 否 | 否 | 否 |
| 共享 API Schema（`shared/api-schema/`） | 否 | 否 | 否 |
| Admin Web（`admin/`） | 否 | 否 | 否 |
| Web 仪表盘（`web/`） | 否（未读取，但目录结构中无相关模块） | 否 | 否 |
| CV 流水线（`cv/`） | 否 | 否 | 否 |
| 文档（`docs/PRODUCT_FEATURE_SPEC.md`、`docs/ui/UI_NAMING_REGISTRY.md`、`docs/messages/`） | 否（仅中文文案层面提到“视频批注”作为未来功能） | 否 | 否 |

> 结论：**没有任何不一致需要修复**——因为新命名根本没有落地。

---

## 6. 核心模块检查结果

用户特别提到的核心模块在仓库中的现状：

| 模块 | 仓库中是否存在 | 状态 |
| --- | --- | --- |
| Playback Engine（视频播放引擎） | 不存在独立模块 | 只有 `expo-image` / `expo-av` 风格的简单视频缩略图与上传，无自定义播放引擎 |
| PlaybackPlan | 不存在 | 0 处命中 |
| Seek / Active Annotation 逻辑 | 不存在 | 0 处命中 |
| Timeline（时间线） | 不存在 | 仅有 `app.message_timeline`（消息列表时间线，与视频批注无关） |
| Editor（视频批注编辑器） | 不存在 | 0 处命中 |
| VideoCanvas | 不存在 | 0 处命中 |
| Element 渲染（批注元素的渲染） | 不存在 | 0 处命中；CV 侧 `cv/visualization/overlays.py` 是比赛轨迹叠加，与视频批注无关 |
| Audio / Recording | 不存在 | 0 处命中 |
| Demo / Mock 数据 | 不存在 | `admin/src/mockData.js`、`app/data/mockData.ts` 都没有视频批注示例 |
| Tests（视频批注相关） | 不存在 | `backend/tests/` 与 `app/tests/` 中所有 `message_*` 测试均与消息模块相关，无视频批注测试 |
| README / 注释（视频批注相关） | 不存在 | 仅 `docs/PRODUCT_FEATURE_SPEC.md` 在中文层面试描述了“视频批注”作为未来功能 |

---

## 7. 建议修改清单

### 7.1 必须修改

**无。**

仓库当前不存在需要被纠正的 `VideoNote / NoteAnnotation` 命名问题，也没有可识别的“误改”。

### 7.2 建议修改

1. **确认 Codex 的重命名到底落在了哪里**（推荐）
   - 询问 / 核查 Codex 当时执行该重命名的目标分支或工作目录。
   - 如果它在另一条 feature 分支上，确认该分支是否需要 rebase / cherry-pick 到 `main`。
   - 如果它已经被丢弃，需要重新规划落地方案（因为当前 `main` 上根本没有 `VideoNote / NoteAnnotation` 这一层）。
   - 文件：无（这是流程层动作，不修改任何代码）。

2. **明确领域边界，避免未来混淆**（推荐）
   - 在 `docs/data/tennis_global_data_dictionary.md` 或 `docs/PRODUCT_FEATURE_SPEC.md` 中显式声明：
     - `VideoNote` 尚未在本仓库中实现；
     - 现有 `note` / `备注` 字段（`coach_applications.note`、`admin_credentials.note`、`tennis_activities.note`、`content_reports.resolution_note`）属于“自由文本备注”，与未来的 `NoteAnnotation`（视频批注）是不同概念；
     - 未来 `NoteAnnotation` 应作为 `VideoNote`（或 `videos`）的子资源，**不要复用现有 `note` 字段命名空间**。

### 7.3 可保持现状

- 现有 `note` / `备注` 字段：保持现状，不要改名。
- 现有 `VideoRecord`、`TennisActivityRecord` 等 schema：保持现状。
- 现有 UI 命名注册表（`docs/ui/UI_NAMING_REGISTRY.md`）：保持现状；如果未来引入视频批注 UI，再单独追加条目（例如 `app.video_player.annotation_panel`、`app.video_player.timeline_track` 等）。

---

## 8. 复查方式与方法（留痕）

为避免误判，本次复查使用了以下方法：

1. **大小写不敏感的字符串搜索**：
   - `VideoNoteProject` / `VideoNote` / `NoteAnnotation` / `noteAnnotation` / `videoNote` / `video_note` / `note_annotation` / `PlaybackPlan` / `VideoCanvas` 全部 0 命中。
   - 工具：`grep -rin`，覆盖 `*.ts / *.tsx / *.js / *.jsx / *.py / *.md / *.json / *.sql`，排除 `node_modules / .git / .expo / .vscode / __pycache__`。
2. **目录结构核对**：
   - 后端 `backend/app/` 13 个子模块没有 `playback / annotation / editor / canvas`。
   - 移动端 `app/app/` 页面只有 `(tabs)/`、`activity/`、`chat/`、`friends/`、`messages/`、`post/`、`profile/`、`student/`、`user/`，没有任何视频笔记 / 视频批注页面。
3. **数据库字典核对**：
   - `docs/data/tennis_global_data_dictionary.md` 与 `docs/data/网球数据库设计.md` 列出的全部表中没有 `video_notes` / `note_annotations` / `video_note_annotations` / 类似命名的表。
4. **产品文档核对**：
   - `docs/PRODUCT_FEATURE_SPEC.md` 明确把“视频批注”列为尚未实现的“演示或占位”功能。
5. **Git 历史核对**：
   - `git log --all` 全量搜索，没有出现 `VideoNote`、`NoteAnnotation`、`rename`、`重命名`、`note→annotation` 等提交记录。
   - `git status` / `git stash list` / `git worktree list` 显示当前工作区干净、无未提交修改、无 stash、无并行 worktree。

---

## 9. 一句话结论

> **Codex 这一轮 `VideoNoteProject → VideoNote` / `Note → NoteAnnotation` 的重命名没有体现在当前 `main` 分支上——既看不到旧命名残留，也看不到新命名落地。当前仓库的视频领域只有 `tennis_activities → videos`，没有任何视频笔记 / 视频批注层。**
>
> 后续如果要真正引入这套领域，应按 `VideoNote / NoteAnnotation / noteAnnotations` 在数据库、Schema、API、移动端组件里**从零实现**，并明确与现有自由文本 `note` 字段做命名空间隔离，不要把它们混淆。
