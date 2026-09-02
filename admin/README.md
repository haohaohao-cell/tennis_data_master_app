# Tennis Admin Web

独立后台管理 Web 前端，用于运营和管理员查看、筛选、处理平台核心业务数据。admin 不包含独立后端，所有真实数据和管理操作都通过现有 backend 管理员接口完成。

## 当前范围

- 用户管理：查看用户、按状态筛选、启用/禁用/软删除用户。
- tennis_activity 管理：查看活动、按活动分析汇总状态筛选、调整默认可见性、触发活动汇总重跑。
- 视频管理：查看视频、按分析状态筛选、重新排队/取消分析、调整视频可见性。
- Post 管理：查看社交动态、按动态状态筛选、发布/隐藏/恢复草稿/软删除动态。

## 运行

首次使用时，在项目根目录执行：

```powershell
Copy-Item config/network.example.json config/network.json
```

Admin 启动服务器会自动读取该文件中的 `admin.host`、`admin.port` 和
`public.apiBaseUrl`，并将公共 API 地址注入页面；不需要额外生成配置。

```bash
npm run dev
```

默认地址：`http://localhost:5175`

静态检查：

```bash
npm run build
```

## 连接 backend

页面右上角可以配置 API Base URL 和管理员 Bearer token。默认值由
`config/network.json` 的 `public.apiBaseUrl` 自动派生（模板对应）：

```text
http://localhost:8000/api/v1
```

当前前端使用的管理员接口为：

```text
POST  /api/v1/admin/auth/login
GET   /api/v1/admin/users
POST  /api/v1/admin/users
PATCH /api/v1/admin/users/{user_id}
DELETE /api/v1/admin/users/{user_id}
GET   /api/v1/admin/coach-applications
GET   /api/v1/admin/coach-applications/{coach_application_id}
POST  /api/v1/admin/coach-applications/{coach_application_id}/approve
POST  /api/v1/admin/coach-applications/{coach_application_id}/reject
POST  /api/v1/admin/coaches/{user_id}/suspend
POST  /api/v1/admin/coaches/{user_id}/restore
POST  /api/v1/admin/coaches/{user_id}/revoke
GET   /api/v1/admin/tennis-activities
POST  /api/v1/admin/tennis-activities
PATCH /api/v1/admin/tennis-activities/{tennis_activity_id}
DELETE /api/v1/admin/tennis-activities/{tennis_activity_id}
GET   /api/v1/admin/videos
POST  /api/v1/admin/videos
PATCH /api/v1/admin/videos/{video_id}
DELETE /api/v1/admin/videos/{video_id}
GET   /api/v1/admin/posts
POST  /api/v1/admin/posts
PATCH /api/v1/admin/posts/{social_post_id}
DELETE /api/v1/admin/posts/{social_post_id}
```

列表接口建议支持通用参数：`page`、`page_size`、`q`，以及各模块自己的状态筛选参数，例如 `status`、`analysis_status`、`analysis_summary_status`。

接口不可用时，可以启用“自动演示数据”，用于先确认后台管理信息架构和操作流。接入真实管理员接口后，可以关闭该开关验证真实数据。

本地测试管理员账号可以用脚本创建：

```bash
python scripts/seed_test_admin.py --username li --password 0000
```

测试账号 `li / 0000` 只用于本地开发。密码会以 PBKDF2 hash 写入 `admin_credentials`，不会明文存库。后台前端不会提供无鉴权创建管理员入口。
