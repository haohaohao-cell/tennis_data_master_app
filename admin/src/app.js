import { AdminApiClient, loadSettings, saveSettings } from "./api.js";
import { cloneMockItems } from "./mockData.js";

const activityTypes = [
  "casual_hit",
  "match",
  "serve_training",
  "forehand_training",
  "backhand_training",
  "multi_ball_drill",
  "stroke_recording",
  "post_match_review",
  "lesson_practice",
  "coach_demo",
  "other",
];
const activityVisibility = ["private", "friends", "specified_users", "lesson_coach", "lesson_participants", "public"];
const videoVisibility = ["inherit", ...activityVisibility];
const postVisibility = ["private", "friends", "followers", "specified_users", "public"];
const analysisStatuses = ["uploaded", "queued", "processing", "completed", "failed", "canceled"];
const analysisSummaryStatuses = ["pending", "processing", "completed", "failed"];
const userStatuses = ["active", "disabled", "deleted"];
const coachStatuses = ["pending", "active", "disabled", "rejected"];
const coachApplicationStatuses = ["pending", "approved", "rejected", "canceled"];
const postStatuses = ["draft", "published", "hidden", "deleted"];

const resources = [
  {
    id: "users",
    title: "用户管理",
    navLabel: "用户",
    endpoint: "/admin/users",
    idLabel: "user_id",
    idField: "user_id",
    newIdPrefix: "user",
    getId: (item) => item.user_id,
    listKeys: ["users"],
    mediaFields: ["avatar_path"],
    searchFields: ["user_id", "nickname", "phone", "email", "status", "coach_status"],
    filter: { label: "用户状态", field: "status", param: "status", options: userStatuses },
    columns: [
      { label: "昵称", value: (item) => item.nickname },
      { label: "手机号", value: (item) => item.phone },
      { label: "状态", value: (item) => badge(item.status) },
      { label: "后台", value: (item) => (item.admin_role ? badge(item.admin_role) : "-") },
      { label: "教练", value: (item) => (item.is_coach ? badge(item.coach_status || "pending") : "-") },
      { label: "创建时间", value: (item) => formatDate(item.created_at) },
    ],
    detailFields: ["user_id", "nickname", "avatar_path", "phone", "email", "status", "profile_completed", "playing_hand", "is_coach", "coach_status", "coach_verified_at", "admin_role", "admin_status", "created_at", "updated_at", "deleted_at"],
    formFields: [
      { name: "nickname", label: "昵称", required: true },
      { name: "phone", label: "手机号" },
      { name: "email", label: "邮箱" },
      { name: "avatar_path", label: "头像路径" },
      { name: "status", label: "状态", type: "select", options: userStatuses, defaultValue: "active", required: true },
      { name: "playing_hand", label: "持拍手", type: "select", options: ["right", "left", "unknown"], defaultValue: "right", required: true },
      { name: "profile_completed", label: "资料已完善", type: "checkbox", defaultValue: false },
      { name: "is_coach", label: "教练身份", type: "checkbox", defaultValue: false },
      { name: "coach_status", label: "教练状态", type: "select", options: coachStatuses, nullable: true },
      { name: "coach_verified_at", label: "教练认证时间" },
    ],
    mockDefaults: { status: "active", profile_completed: false, playing_hand: "right", is_coach: false },
    quickActions: (item) => [
      item.status === "disabled"
        ? { label: "启用", patch: { status: "active" }, tone: "primary" }
        : { label: "禁用", patch: { status: "disabled" }, tone: "warning", disabled: item.status === "deleted" },
      { label: "软删除", patch: { status: "deleted" }, tone: "danger", disabled: item.status === "deleted" },
    ],
  },
  {
    id: "coach_applications",
    title: "教练申请审核",
    navLabel: "教练申请",
    endpoint: "/admin/coach-applications",
    idLabel: "coach_application_id",
    idField: "coach_application_id",
    newIdPrefix: "coach-application",
    allowCreate: false,
    allowEdit: false,
    allowDelete: false,
    getId: (item) => item.coach_application_id,
    listKeys: ["coach_applications"],
    mediaFields: ["certification_file_path", "verification_video_path"],
    searchFields: ["coach_application_id", "applicant_user_id", "applicant_nickname", "display_name", "real_name", "city", "specialties", "status"],
    filter: { label: "审核状态", field: "status", param: "status", options: coachApplicationStatuses },
    columns: [
      { label: "申请人", value: (item) => item.display_name || item.applicant_nickname },
      { label: "类型", value: (item) => badge(item.application_type) },
      { label: "状态", value: (item) => badge(item.status) },
      { label: "当前教练", value: (item) => (item.current_coach_status ? badge(item.current_coach_status) : "-") },
      { label: "城市", value: (item) => item.city || "-" },
      { label: "提交时间", value: (item) => formatDate(item.created_at) },
    ],
    detailFields: [
      "coach_application_id",
      "applicant_user_id",
      "applicant_nickname",
      "applicant_phone",
      "application_type",
      "status",
      "display_name",
      "real_name",
      "phone",
      "city",
      "specialties",
      "coaching_experience",
      "certification_title",
      "certification_file_path",
      "verification_video_path",
      "note",
      "reviewer_user_id",
      "reviewed_at",
      "rejection_reason",
      "current_coach_type",
      "current_coach_status",
      "created_at",
      "updated_at",
    ],
    formFields: [],
    mockDefaults: { status: "pending", application_type: "non_professional" },
    quickActions: (item) => {
      const actions = [];
      if (item.status === "pending") {
        actions.push({
          label: "通过",
          tone: "primary",
          customEndpoint: (record) => `/admin/coach-applications/${encodeURIComponent(record.coach_application_id)}/approve`,
          mockPatch: {
            status: "approved",
            current_coach_type: item.application_type,
            current_coach_status: "active",
            reviewed_at: new Date().toISOString(),
          },
        });
        actions.push({
          label: "拒绝",
          tone: "danger",
          customEndpoint: (record) => `/admin/coach-applications/${encodeURIComponent(record.coach_application_id)}/reject`,
          prompt: "请输入拒绝原因",
          payloadKey: "rejection_reason",
          mockPatch: { status: "rejected", reviewed_at: new Date().toISOString() },
        });
      }
      if (item.current_coach_status === "active") {
        actions.push({
          label: "暂停",
          tone: "warning",
          customEndpoint: (record) => `/admin/coaches/${encodeURIComponent(record.applicant_user_id)}/suspend`,
          prompt: "请输入暂停原因",
          payloadKey: "reason",
          mockPatch: { current_coach_status: "suspended" },
        });
        actions.push({
          label: "撤销",
          tone: "danger",
          customEndpoint: (record) => `/admin/coaches/${encodeURIComponent(record.applicant_user_id)}/revoke`,
          prompt: "请输入撤销原因",
          payloadKey: "reason",
          mockPatch: { current_coach_status: "revoked" },
        });
      }
      if (item.current_coach_status === "suspended") {
        actions.push({
          label: "恢复",
          tone: "primary",
          customEndpoint: (record) => `/admin/coaches/${encodeURIComponent(record.applicant_user_id)}/restore`,
          prompt: "请输入恢复说明",
          payloadKey: "reason",
          mockPatch: { current_coach_status: "active" },
        });
        actions.push({
          label: "撤销",
          tone: "danger",
          customEndpoint: (record) => `/admin/coaches/${encodeURIComponent(record.applicant_user_id)}/revoke`,
          prompt: "请输入撤销原因",
          payloadKey: "reason",
          mockPatch: { current_coach_status: "revoked" },
        });
      }
      return actions;
    },
  },
  {
    id: "tennis_activities",
    title: "tennis_activity 管理",
    navLabel: "活动",
    endpoint: "/admin/tennis-activities",
    idLabel: "tennis_activity_id",
    idField: "tennis_activity_id",
    newIdPrefix: "activity",
    getId: (item) => item.tennis_activity_id,
    listKeys: ["tennis_activities", "activities"],
    searchFields: ["tennis_activity_id", "owner_user_id", "title", "activity_type", "default_visibility", "analysis_summary_status", "location_name"],
    filter: { label: "分析状态", field: "analysis_summary_status", param: "analysis_summary_status", options: analysisSummaryStatuses },
    columns: [
      { label: "标题", value: (item) => item.title || "未命名活动" },
      { label: "类型", value: (item) => item.activity_type },
      { label: "所有者", value: (item) => shortId(item.owner_user_id) },
      { label: "可见性", value: (item) => badge(item.default_visibility) },
      { label: "汇总", value: (item) => badge(item.analysis_summary_status || "pending") },
      { label: "开始时间", value: (item) => formatDate(item.started_at) },
      { label: "场地", value: (item) => item.location_name || "-" },
    ],
    detailFields: ["tennis_activity_id", "owner_user_id", "lesson_id", "title", "activity_type", "default_visibility", "started_at", "ended_at", "location_name", "court_surface", "opponent_user_id", "opponent_name", "note", "analysis_summary_status", "created_at", "updated_at", "deleted_at"],
    formFields: [
      { name: "owner_user_id", label: "所有者 user_id", required: true },
      { name: "title", label: "标题" },
      { name: "activity_type", label: "活动类型", type: "select", options: activityTypes, defaultValue: "other", required: true },
      { name: "default_visibility", label: "默认可见性", type: "select", options: activityVisibility, defaultValue: "private", required: true },
      { name: "analysis_summary_status", label: "分析汇总状态", type: "select", options: analysisSummaryStatuses, nullable: true },
      { name: "lesson_id", label: "课程 ID" },
      { name: "started_at", label: "开始时间" },
      { name: "ended_at", label: "结束时间" },
      { name: "location_name", label: "场地名称" },
      { name: "court_surface", label: "场地类型", type: "select", options: ["hard", "clay", "grass", "carpet", "unknown"], nullable: true },
      { name: "opponent_user_id", label: "对手 user_id" },
      { name: "opponent_name", label: "对手姓名" },
      { name: "note", label: "备注", type: "textarea" },
    ],
    mockDefaults: { activity_type: "other", default_visibility: "private", analysis_summary_status: null },
    quickActions: (item) => [
      { label: "设公开", patch: { default_visibility: "public" }, tone: "primary", disabled: item.default_visibility === "public" },
      { label: "设私密", patch: { default_visibility: "private" }, tone: "warning", disabled: item.default_visibility === "private" },
      { label: "重跑汇总", patch: { analysis_summary_status: "pending" }, tone: "secondary", disabled: item.analysis_summary_status === "processing" },
    ],
  },
  {
    id: "videos",
    title: "视频管理",
    navLabel: "视频",
    endpoint: "/admin/videos",
    idLabel: "video_id",
    idField: "video_id",
    newIdPrefix: "video",
    getId: (item) => item.video_id,
    listKeys: ["videos"],
    mediaFields: ["thumbnail_path", "video_path"],
    searchFields: ["video_id", "filename", "original_filename", "owner_user_id", "uploader_user_id", "analysis_status", "visibility"],
    filter: { label: "分析状态", field: "analysis_status", param: "analysis_status", options: analysisStatuses },
    columns: [
      { label: "文件名", value: (item) => item.filename },
      { label: "分析", value: (item) => badge(item.analysis_status) },
      { label: "可见性", value: (item) => badge(item.visibility) },
      { label: "所有者", value: (item) => shortId(item.owner_user_id) },
      { label: "时长", value: (item) => formatDuration(item.video_duration_ms) },
      { label: "大小", value: (item) => formatBytes(item.file_size_bytes) },
      { label: "创建时间", value: (item) => formatDate(item.created_at) },
    ],
    detailFields: ["video_id", "tennis_activity_id", "owner_user_id", "uploader_user_id", "filename", "original_filename", "video_path", "thumbnail_path", "mime_type", "file_size_bytes", "file_hash", "video_duration_ms", "video_frame_count", "video_fps", "video_width_px", "video_height_px", "camera_view_angle", "camera_view_position", "frame_data_path", "frame_data_version", "player_a_user_id", "player_b_user_id", "player_a_name", "player_b_name", "primary_player_slot", "visibility", "analysis_status", "analysis_version", "error_message", "captured_at", "created_at", "updated_at", "deleted_at"],
    formFields: [
      { name: "owner_user_id", label: "所有者 user_id", required: true },
      { name: "uploader_user_id", label: "上传者 user_id", required: true },
      { name: "tennis_activity_id", label: "活动 ID" },
      { name: "filename", label: "文件名", required: true },
      { name: "video_path", label: "视频路径", required: true },
      { name: "original_filename", label: "原始文件名" },
      { name: "thumbnail_path", label: "封面路径" },
      { name: "mime_type", label: "MIME 类型" },
      { name: "file_size_bytes", label: "文件大小 bytes", type: "number" },
      { name: "video_duration_ms", label: "时长 ms", type: "number" },
      { name: "video_frame_count", label: "总帧数", type: "number" },
      { name: "video_fps", label: "FPS", type: "number" },
      { name: "video_width_px", label: "宽度 px", type: "number" },
      { name: "video_height_px", label: "高度 px", type: "number" },
      { name: "visibility", label: "可见性", type: "select", options: videoVisibility, defaultValue: "inherit", required: true },
      { name: "analysis_status", label: "分析状态", type: "select", options: analysisStatuses, defaultValue: "uploaded", required: true },
      { name: "analysis_version", label: "分析版本" },
      { name: "error_message", label: "错误信息", type: "textarea" },
      { name: "captured_at", label: "拍摄时间" },
    ],
    mockDefaults: { visibility: "inherit", analysis_status: "uploaded" },
    quickActions: (item) => [
      { label: "重新排队", patch: { analysis_status: "queued" }, tone: "primary", disabled: !["uploaded", "failed", "canceled"].includes(item.analysis_status) },
      { label: "取消分析", patch: { analysis_status: "canceled" }, tone: "warning", disabled: !["queued", "processing"].includes(item.analysis_status) },
      { label: "设公开", patch: { visibility: "public" }, tone: "secondary", disabled: item.visibility === "public" },
      { label: "设私密", patch: { visibility: "private" }, tone: "secondary", disabled: item.visibility === "private" },
    ],
  },
  {
    id: "posts",
    title: "Post 管理",
    navLabel: "Post",
    endpoint: "/admin/posts",
    idLabel: "social_post_id",
    idField: "social_post_id",
    newIdPrefix: "post",
    getId: (item) => item.social_post_id,
    listKeys: ["posts", "social_posts"],
    searchFields: ["social_post_id", "author_user_id", "source_tennis_activity_id", "title", "content", "status", "visibility"],
    filter: { label: "动态状态", field: "status", param: "status", options: postStatuses },
    columns: [
      { label: "标题", value: (item) => item.title || "无标题" },
      { label: "状态", value: (item) => badge(item.status) },
      { label: "可见性", value: (item) => badge(item.visibility) },
      { label: "作者", value: (item) => shortId(item.author_user_id) },
      { label: "发布时间", value: (item) => formatDate(item.published_at) },
      { label: "创建时间", value: (item) => formatDate(item.created_at) },
    ],
    detailFields: ["social_post_id", "author_user_id", "source_tennis_activity_id", "title", "content", "visibility", "status", "published_at", "created_at", "updated_at", "deleted_at"],
    formFields: [
      { name: "author_user_id", label: "作者 user_id", required: true },
      { name: "source_tennis_activity_id", label: "来源活动 ID" },
      { name: "title", label: "标题" },
      { name: "content", label: "正文", type: "textarea" },
      { name: "visibility", label: "可见性", type: "select", options: postVisibility, defaultValue: "private", required: true },
      { name: "status", label: "状态", type: "select", options: postStatuses, defaultValue: "draft", required: true },
      { name: "published_at", label: "发布时间" },
    ],
    mockDefaults: { visibility: "private", status: "draft" },
    quickActions: (item) => [
      { label: "发布", patch: { status: "published" }, tone: "primary", disabled: item.status === "published" || item.status === "deleted" },
      { label: "隐藏", patch: { status: "hidden" }, tone: "warning", disabled: item.status !== "published" },
      { label: "恢复草稿", patch: { status: "draft" }, tone: "secondary", disabled: item.status !== "deleted" },
      { label: "软删除", patch: { status: "deleted" }, tone: "danger", disabled: item.status === "deleted" },
    ],
  },
];

const state = {
  settings: loadSettings(),
  resourceId: "users",
  page: 1,
  pageSize: 10,
  search: "",
  filterValue: "all",
  total: 0,
  items: [],
  usingMock: false,
  mockStore: Object.fromEntries(resources.map((resource) => [resource.id, cloneMockItems(resource.id)])),
  formMode: "create",
  formItemId: null,
  mediaSources: {},
};

const elements = {
  resourceNav: document.querySelector("#resourceNav"),
  pageTitle: document.querySelector("#pageTitle"),
  connectionForm: document.querySelector("#connectionForm"),
  apiBaseUrl: document.querySelector("#apiBaseUrl"),
  adminUsername: document.querySelector("#adminUsername"),
  adminPassword: document.querySelector("#adminPassword"),
  adminToken: document.querySelector("#adminToken"),
  adminLoginButton: document.querySelector("#adminLoginButton"),
  mockFallback: document.querySelector("#mockFallback"),
  statusStrip: document.querySelector("#statusStrip"),
  searchInput: document.querySelector("#searchInput"),
  primaryFilterLabel: document.querySelector("#primaryFilterLabel"),
  primaryFilter: document.querySelector("#primaryFilter"),
  pageSizeSelect: document.querySelector("#pageSizeSelect"),
  createButton: document.querySelector("#createButton"),
  refreshButton: document.querySelector("#refreshButton"),
  summaryGrid: document.querySelector("#summaryGrid"),
  tableHead: document.querySelector("#tableHead"),
  tableBody: document.querySelector("#tableBody"),
  previousPage: document.querySelector("#previousPage"),
  nextPage: document.querySelector("#nextPage"),
  pageIndicator: document.querySelector("#pageIndicator"),
  detailDrawer: document.querySelector("#detailDrawer"),
  closeDrawer: document.querySelector("#closeDrawer"),
  drawerKicker: document.querySelector("#drawerKicker"),
  drawerTitle: document.querySelector("#drawerTitle"),
  drawerActions: document.querySelector("#drawerActions"),
  mediaPreviewList: document.querySelector("#mediaPreviewList"),
  detailList: document.querySelector("#detailList"),
  jsonBlock: document.querySelector("#jsonBlock"),
  mediaLightbox: document.querySelector("#mediaLightbox"),
  mediaLightboxImage: document.querySelector("#mediaLightboxImage"),
  mediaLightboxTitle: document.querySelector("#mediaLightboxTitle"),
  closeMediaLightbox: document.querySelector("#closeMediaLightbox"),
  formModal: document.querySelector("#formModal"),
  formKicker: document.querySelector("#formKicker"),
  formTitle: document.querySelector("#formTitle"),
  recordForm: document.querySelector("#recordForm"),
  formFields: document.querySelector("#formFields"),
  closeForm: document.querySelector("#closeForm"),
  cancelForm: document.querySelector("#cancelForm"),
  toast: document.querySelector("#toast"),
};

const resourceById = new Map(resources.map((resource) => [resource.id, resource]));
let searchTimer = 0;

function currentResource() {
  return resourceById.get(state.resourceId) || resources[0];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function html(value) {
  return { __html: value };
}

function renderCellValue(value) {
  if (value && typeof value === "object" && "__html" in value) {
    return value.__html;
  }
  return escapeHtml(value ?? "-");
}

function shortId(value) {
  if (!value) {
    return "-";
  }
  const text = String(value);
  return text.length > 14 ? `${text.slice(0, 8)}...${text.slice(-4)}` : text;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value);
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDuration(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const totalSeconds = Math.round(Number(value) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function normalizeMediaSource(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }
  if (text.startsWith("data:") || text.startsWith("http://") || text.startsWith("https://") || text.startsWith("blob:")) {
    return text;
  }
  if (text.startsWith("file://")) {
    return text;
  }
  if (text.startsWith("/")) {
    try {
      const apiUrl = new URL(state.settings.apiBaseUrl);
      return `${apiUrl.origin}${text}`;
    } catch {
      return text;
    }
  }
  return text;
}

function isImageValue(field, value) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) {
    return false;
  }
  if (text.startsWith("data:image/")) {
    return true;
  }
  if (["thumbnail_path", "image_path", "avatar_path", "certification_file_path"].includes(field)) {
    return true;
  }
  return /\.(png|jpe?g|webp|gif|bmp|heic|heif)(\?.*)?$/.test(text);
}

function isVideoValue(field, value) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) {
    return false;
  }
  if (text.startsWith("data:video/")) {
    return true;
  }
  if (["video_path", "verification_video_path"].includes(field)) {
    return true;
  }
  return /\.(mp4|mov|m4v|webm|ogg)(\?.*)?$/.test(text);
}

function mediaTitle(field) {
  const titleMap = {
    avatar_path: "头像",
    certification_file_path: "资质证明图片",
    image_path: "图片",
    thumbnail_path: "视频封面",
    verification_video_path: "展示视频",
    video_path: "视频",
  };
  return titleMap[field] || field;
}

function mediaSourceLabel(source) {
  if (!source) {
    return "未上传";
  }
  if (source.startsWith("data:image/")) {
    return "已上传图片数据";
  }
  if (source.startsWith("data:video/")) {
    return "已上传视频数据";
  }
  return source.length > 120 ? `${source.slice(0, 80)}...${source.slice(-24)}` : source;
}

function stashMediaSource(source) {
  const key = `media-${Object.keys(state.mediaSources).length + 1}`;
  state.mediaSources[key] = source;
  return key;
}

function collectMediaPreviews(resource, item) {
  const fields = Array.from(
    new Set([
      ...(resource.mediaFields || []),
      "avatar_path",
      "certification_file_path",
      "verification_video_path",
      "thumbnail_path",
      "image_path",
      "video_path",
    ]),
  );

  return fields
    .map((field) => {
      const value = item[field];
      if (!value) {
        return null;
      }
      const source = normalizeMediaSource(value);
      if (isImageValue(field, value)) {
        return { field, source, title: mediaTitle(field), type: "image" };
      }
      if (isVideoValue(field, value)) {
        return { field, source, title: mediaTitle(field), type: "video" };
      }
      return null;
    })
    .filter(Boolean);
}

function renderMediaPreviews(resource, item) {
  const previews = collectMediaPreviews(resource, item);
  if (!previews.length) {
    elements.mediaPreviewList.innerHTML = `
      <section class="media-preview-empty">
        未发现可预览的图片或视频材料。请检查 certification_file_path、verification_video_path 或 video_path 是否有值。
      </section>
    `;
    elements.mediaPreviewList.hidden = false;
    return;
  }

  elements.mediaPreviewList.hidden = false;
  elements.mediaPreviewList.innerHTML = previews
    .map((preview) => {
      const source = escapeHtml(preview.source);
      const mediaKey = escapeHtml(stashMediaSource(preview.source));
      const field = escapeHtml(preview.field);
      const title = escapeHtml(preview.title);
      if (preview.type === "image") {
        const sourceLabel = escapeHtml(mediaSourceLabel(preview.source));
        return `
          <section class="media-preview-card">
            <div class="media-preview-header">
              <strong>${title}</strong>
              <button type="button" data-action="preview-media" data-media-key="${mediaKey}" data-title="${title}">预览图片</button>
            </div>
            <img alt="${title}" class="media-preview-image" data-action="preview-media" data-media-key="${mediaKey}" data-title="${title}" src="${source}" />
            <p class="media-preview-path">${field}: ${sourceLabel}</p>
          </section>
        `;
      }
      const sourceLabel = escapeHtml(mediaSourceLabel(preview.source));
      return `
        <section class="media-preview-card">
          <div class="media-preview-header">
            <strong>${title}</strong>
            <a href="${source}" target="_blank" rel="noreferrer">打开视频</a>
          </div>
          <video class="media-preview-video" controls preload="metadata" src="${source}"></video>
          <p class="media-preview-path">${field}: ${sourceLabel}</p>
        </section>
      `;
    })
    .join("");
}

function renderDetailValue(field, value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (isImageValue(field, value) || isVideoValue(field, value)) {
    const source = normalizeMediaSource(value);
    if (isImageValue(field, value)) {
      const mediaKey = escapeHtml(stashMediaSource(source));
      const title = escapeHtml(mediaTitle(field));
      return `
        <div class="detail-media-inline">
          <img alt="${title}" class="detail-inline-image" data-action="preview-media" data-media-key="${mediaKey}" data-title="${title}" src="${escapeHtml(source)}" />
          <div class="detail-media-meta">
            <span class="detail-uploaded-badge">已上传图片</span>
            <button class="detail-media-link" type="button" data-action="preview-media" data-media-key="${mediaKey}" data-title="${title}">预览图片</button>
          </div>
        </div>
      `;
    }
    return `
      <div class="detail-media-inline">
        <video class="detail-inline-video" controls preload="metadata" src="${escapeHtml(source)}"></video>
        <div class="detail-media-meta">
          <span class="detail-uploaded-badge">已上传视频</span>
          <a class="detail-media-link" href="${escapeHtml(source)}" target="_blank" rel="noreferrer">打开视频</a>
        </div>
      </div>
    `;
  }

  if (field.endsWith("_at")) {
    return escapeHtml(formatDate(value));
  }

  return escapeHtml(value);
}

function orderedDetailFields(resource, item) {
  const fields = [...resource.detailFields];
  const mediaFields = fields.filter((field) => isImageValue(field, item[field]) || isVideoValue(field, item[field]));
  const nonMediaFields = fields.filter((field) => !mediaFields.includes(field));
  return [...mediaFields, ...nonMediaFields];
}

function badge(value) {
  const text = value || "unknown";
  const variantMap = {
    active: "good",
    completed: "good",
    published: "good",
    public: "good",
    owner: "good",
    admin: "good",
    approved: "good",
    certified: "good",
    pending: "info",
    processing: "info",
    queued: "info",
    non_professional: "info",
    uploaded: "neutral",
    draft: "neutral",
    private: "neutral",
    inherit: "neutral",
    operator: "neutral",
    viewer: "neutral",
    disabled: "warning",
    suspended: "warning",
    hidden: "warning",
    failed: "danger",
    deleted: "danger",
    canceled: "danger",
    rejected: "danger",
    revoked: "danger",
  };
  const variant = variantMap[text] || "neutral";
  return html(`<span class="badge badge-${variant}">${escapeHtml(text)}</span>`);
}

function setStatus(message, type = "info") {
  elements.statusStrip.className = `status-strip status-${type}`;
  elements.statusStrip.textContent = message;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("toast-visible");
  window.setTimeout(() => elements.toast.classList.remove("toast-visible"), 2600);
}

function renderNav() {
  elements.resourceNav.innerHTML = resources
    .map((resource) => {
      const active = resource.id === state.resourceId ? "active" : "";
      return `<button class="${active}" type="button" data-resource-id="${resource.id}">${resource.navLabel}</button>`;
    })
    .join("");
}

function renderFilter() {
  const resource = currentResource();
  elements.primaryFilterLabel.textContent = resource.filter.label;
  elements.primaryFilter.innerHTML = ["all", ...resource.filter.options]
    .map((value) => `<option value="${value}">${value === "all" ? "全部" : value}</option>`)
    .join("");
  elements.primaryFilter.value = state.filterValue;
}

function itemMatchesSearch(resource, item, search) {
  if (!search) {
    return true;
  }
  const normalizedSearch = search.trim().toLowerCase();
  return resource.searchFields.some((field) => String(item[field] ?? "").toLowerCase().includes(normalizedSearch));
}

function localList(resource) {
  const source = state.mockStore[resource.id] || [];
  const filtered = source.filter((item) => {
    const matchesSearch = itemMatchesSearch(resource, item, state.search);
    const matchesFilter = state.filterValue === "all" || item[resource.filter.field] === state.filterValue;
    return matchesSearch && matchesFilter;
  });
  const start = (state.page - 1) * state.pageSize;
  return { items: filtered.slice(start, start + state.pageSize), total: filtered.length };
}

function buildListParams(resource) {
  return {
    page: state.page,
    page_size: state.pageSize,
    q: state.search,
    [resource.filter.param]: state.filterValue,
  };
}

async function loadResource() {
  const resource = currentResource();
  const client = new AdminApiClient(state.settings);
  elements.pageTitle.textContent = resource.title;
  elements.createButton.hidden = resource.allowCreate === false;
  renderNav();
  renderFilter();
  closeDrawer();
  setStatus(`正在加载 ${resource.title}...`);

  try {
    const result = await client.list(resource, buildListParams(resource));
    state.items = result.items;
    state.total = result.total;
    state.usingMock = false;
    setStatus(`已连接 backend 管理接口：${resource.endpoint}`, "success");
  } catch (error) {
    if (state.settings.mockFallback) {
      const result = localList(resource);
      state.items = result.items;
      state.total = result.total;
      state.usingMock = true;
      setStatus(`当前显示演示数据；接口 ${resource.endpoint} 暂不可用：${error.message}`, "warning");
    } else {
      state.items = [];
      state.total = 0;
      state.usingMock = false;
      setStatus(`加载失败：${error.message}。请确认 backend、管理员 token 和 admin_users 授权。`, "error");
    }
  }

  renderSummary();
  renderTable();
  renderPagination();
}

function renderSummary() {
  const resource = currentResource();
  const allLoaded = state.usingMock ? state.mockStore[resource.id] : state.items;
  const counts = new Map();
  allLoaded.forEach((item) => {
    const key = item[resource.filter.field] || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  const cards = [
    { label: "当前结果", value: state.total },
    { label: "本页记录", value: state.items.length },
    ...Array.from(counts.entries()).slice(0, 4).map(([label, value]) => ({ label, value })),
  ];
  elements.summaryGrid.innerHTML = cards
    .map((card) => `<div class="summary-card"><span>${escapeHtml(card.label)}</span><strong>${card.value}</strong></div>`)
    .join("");
}

function renderTable() {
  const resource = currentResource();
  const columnHead = resource.columns.map((column) => `<th>${column.label}</th>`).join("");
  elements.tableHead.innerHTML = `<tr><th>${resource.idLabel}</th>${columnHead}<th>操作</th></tr>`;

  if (!state.items.length) {
    elements.tableBody.innerHTML = `<tr><td class="empty-cell" colspan="${resource.columns.length + 2}">暂无符合条件的记录</td></tr>`;
    return;
  }

  elements.tableBody.innerHTML = state.items
    .map((item) => {
      const id = resource.getId(item);
      const cells = resource.columns.map((column) => `<td>${renderCellValue(column.value(item))}</td>`).join("");
      return `
        <tr>
          <td class="mono">${escapeHtml(shortId(id))}</td>
          ${cells}
          <td class="actions-cell">
            <button type="button" data-action="detail" data-id="${escapeHtml(id)}">详情</button>
            ${resource.allowEdit === false ? "" : `<button type="button" data-action="edit" data-id="${escapeHtml(id)}">编辑</button>`}
            ${resource.quickActions(item)
              .slice(0, 1)
              .map((action, index) => quickActionButton(action, id, index))
              .join("")}
            ${resource.allowDelete === false ? "" : `<button class="button-danger" type="button" data-action="delete" data-id="${escapeHtml(id)}">删除</button>`}
          </td>
        </tr>
      `;
    })
    .join("");
}

function quickActionButton(action, id, index) {
  const disabled = action.disabled ? "disabled" : "";
  return `<button class="button-${action.tone || "secondary"}" type="button" data-action="quick-patch" data-id="${escapeHtml(id)}" data-action-index="${index}" ${disabled}>${escapeHtml(action.label)}</button>`;
}

function renderPagination() {
  const maxPage = Math.max(1, Math.ceil(state.total / state.pageSize));
  elements.pageIndicator.textContent = `第 ${state.page} / ${maxPage} 页`;
  elements.previousPage.disabled = state.page <= 1;
  elements.nextPage.disabled = state.page >= maxPage;
}

function openDrawer(item) {
  const resource = currentResource();
  const id = resource.getId(item);
  state.mediaSources = {};
  elements.drawerKicker.textContent = resource.title;
  elements.drawerTitle.textContent = shortId(id);
  elements.drawerActions.innerHTML = `
    ${resource.allowEdit === false ? "" : `<button type="button" data-action="edit" data-id="${escapeHtml(id)}">编辑</button>`}
    ${resource.quickActions(item).map((action, index) => quickActionButton(action, id, index)).join("")}
    ${resource.allowDelete === false ? "" : `<button class="button-danger" type="button" data-action="delete" data-id="${escapeHtml(id)}">删除</button>`}
  `;
  renderMediaPreviews(resource, item);
  elements.detailList.innerHTML = orderedDetailFields(resource, item)
    .map((field) => {
      const value = item[field];
      return `<dt>${escapeHtml(field)}</dt><dd>${renderDetailValue(field, value)}</dd>`;
    })
    .join("");
  elements.jsonBlock.textContent = JSON.stringify(item, null, 2);
  elements.detailDrawer.classList.add("drawer-open");
  elements.detailDrawer.setAttribute("aria-hidden", "false");
}

async function openDetailById(id) {
  const resource = currentResource();
  const item = getItemById(id);
  if (!item) {
    return;
  }

  if (state.usingMock) {
    openDrawer(item);
    return;
  }

  try {
    const client = new AdminApiClient(state.settings);
    const detail = await client.get(resource, id);
    const index = state.items.findIndex((candidate) => resource.getId(candidate) === id);
    if (index >= 0) {
      state.items[index] = { ...state.items[index], ...detail };
    }
    openDrawer({ ...item, ...detail });
  } catch (error) {
    showToast(`详情加载失败，显示列表数据：${error.message}`);
    openDrawer(item);
  }
}

function closeDrawer() {
  elements.detailDrawer.classList.remove("drawer-open");
  elements.detailDrawer.setAttribute("aria-hidden", "true");
  elements.mediaPreviewList.innerHTML = "";
  elements.mediaPreviewList.hidden = true;
}

function openMediaLightbox(mediaKey, title = "图片预览") {
  const source = state.mediaSources[mediaKey];
  if (!source) {
    showToast("未找到可预览的图片");
    return;
  }
  elements.mediaLightboxImage.src = source;
  elements.mediaLightboxTitle.textContent = title || "图片预览";
  elements.mediaLightbox.classList.add("lightbox-open");
  elements.mediaLightbox.setAttribute("aria-hidden", "false");
}

function closeMediaLightbox() {
  elements.mediaLightbox.classList.remove("lightbox-open");
  elements.mediaLightbox.setAttribute("aria-hidden", "true");
  elements.mediaLightboxImage.removeAttribute("src");
}

function openForm(mode, item = null) {
  const resource = currentResource();
  state.formMode = mode;
  state.formItemId = item ? resource.getId(item) : null;
  elements.formKicker.textContent = resource.title;
  elements.formTitle.textContent = mode === "create" ? "新建记录" : "编辑记录";
  elements.formFields.innerHTML = resource.formFields.map((field) => renderFormField(field, item)).join("");
  elements.formModal.classList.add("modal-open");
  elements.formModal.setAttribute("aria-hidden", "false");
}

function closeForm() {
  elements.formModal.classList.remove("modal-open");
  elements.formModal.setAttribute("aria-hidden", "true");
  state.formItemId = null;
}

function fieldValue(field, item) {
  if (item && item[field.name] !== undefined && item[field.name] !== null) {
    return item[field.name];
  }
  return field.defaultValue ?? "";
}

function renderFormField(field, item) {
  const value = fieldValue(field, item);
  const required = field.required ? "required" : "";
  const common = `name="${field.name}" id="field_${field.name}" ${required}`;
  if (field.type === "checkbox") {
    const checked = value ? "checked" : "";
    return `<label class="checkbox-field"><input type="checkbox" ${common} ${checked} /><span>${escapeHtml(field.label)}</span></label>`;
  }
  if (field.type === "select") {
    const emptyOption = field.nullable ? `<option value="">未设置</option>` : "";
    const options = field.options.map((option) => {
      const selected = option === value ? "selected" : "";
      return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option)}</option>`;
    });
    return `<label><span>${escapeHtml(field.label)}</span><select ${common}>${emptyOption}${options.join("")}</select></label>`;
  }
  if (field.type === "textarea") {
    return `<label class="wide-field"><span>${escapeHtml(field.label)}</span><textarea ${common} rows="${field.rows || 4}">${escapeHtml(value)}</textarea></label>`;
  }
  if (field.type === "number") {
    return `<label><span>${escapeHtml(field.label)}</span><input type="number" step="any" value="${escapeHtml(value)}" ${common} /></label>`;
  }
  return `<label><span>${escapeHtml(field.label)}</span><input type="text" value="${escapeHtml(value)}" ${common} /></label>`;
}

function serializeForm(resource) {
  const formData = new FormData(elements.recordForm);
  const payload = {};
  for (const field of resource.formFields) {
    if (field.type === "checkbox") {
      payload[field.name] = formData.has(field.name);
      continue;
    }

    const rawValue = String(formData.get(field.name) ?? "").trim();
    if (!rawValue) {
      if (field.required) {
        throw new Error(`${field.label} 是必填项`);
      }
      payload[field.name] = null;
      continue;
    }

    payload[field.name] = field.type === "number" ? Number(rawValue) : rawValue;
  }
  return payload;
}

function getItemById(id) {
  const resource = currentResource();
  return state.items.find((item) => resource.getId(item) === id) || state.mockStore[resource.id].find((item) => resource.getId(item) === id);
}

function createMockItem(resource, payload) {
  const now = new Date().toISOString();
  const item = {
    ...resource.mockDefaults,
    ...payload,
    [resource.idField]: `${resource.newIdPrefix}-${Date.now()}`,
    created_at: now,
    updated_at: now,
    deleted_at: null,
  };
  if (resource.id === "posts" && item.status === "published" && !item.published_at) {
    item.published_at = now;
  }
  state.mockStore[resource.id].unshift(item);
  return item;
}

function updateMockItem(resource, id, patch) {
  const item = state.mockStore[resource.id].find((candidate) => resource.getId(candidate) === id);
  if (!item) {
    return null;
  }
  Object.assign(item, patch, { updated_at: new Date().toISOString() });
  if (resource.id === "posts" && patch.status === "published" && !item.published_at) {
    item.published_at = new Date().toISOString();
  }
  if (patch.status === "deleted") {
    item.deleted_at = new Date().toISOString();
  }
  return item;
}

function deleteMockItem(resource, id) {
  const patch =
    resource.id === "users"
      ? { status: "deleted", deleted_at: new Date().toISOString() }
      : resource.id === "posts"
        ? { status: "deleted", deleted_at: new Date().toISOString() }
        : { deleted_at: new Date().toISOString() };
  return updateMockItem(resource, id, patch);
}

async function submitForm(event) {
  event.preventDefault();
  const resource = currentResource();
  let payload;
  try {
    payload = serializeForm(resource);
  } catch (error) {
    showToast(error.message);
    return;
  }

  try {
    if (state.usingMock) {
      if (state.formMode === "create") {
        createMockItem(resource, payload);
      } else {
        updateMockItem(resource, state.formItemId, payload);
      }
      showToast("演示数据已保存");
    } else {
      const client = new AdminApiClient(state.settings);
      if (state.formMode === "create") {
        await client.create(resource, payload);
      } else {
        const item = getItemById(state.formItemId);
        await client.patch(resource, item, payload);
      }
      showToast("已保存到 backend");
    }
    closeForm();
    await loadResource();
  } catch (error) {
    showToast(`保存失败：${error.message}`);
  }
}

async function patchItem(id, actionIndex) {
  const resource = currentResource();
  const item = getItemById(id);
  if (!item) {
    return;
  }
  const action = resource.quickActions(item)[Number(actionIndex)];
  if (!action || action.disabled) {
    return;
  }

  const payload = {};
  if (action.prompt) {
    const input = window.prompt(action.prompt);
    if (input === null) {
      return;
    }
    const value = input.trim();
    if (!value) {
      showToast("需要填写操作原因");
      return;
    }
    payload[action.payloadKey || "reason"] = value;
  }

  try {
    if (state.usingMock) {
      const patch = { ...(action.patch || action.mockPatch || {}) };
      if (action.payloadKey && payload[action.payloadKey]) {
        patch[action.payloadKey] = payload[action.payloadKey];
      }
      updateMockItem(resource, id, patch);
      showToast("演示数据已更新");
    } else if (action.customEndpoint) {
      const client = new AdminApiClient(state.settings);
      await client.postEndpoint(action.customEndpoint(item), payload);
      showToast("已提交到 backend");
    } else {
      const client = new AdminApiClient(state.settings);
      await client.patch(resource, item, action.patch);
      showToast("已提交到 backend");
    }
    await loadResource();
  } catch (error) {
    showToast(`操作失败：${error.message}`);
  }
}

async function deleteItem(id) {
  const resource = currentResource();
  const item = getItemById(id);
  if (!item || !window.confirm(`确认删除 ${resource.idLabel}: ${id} ?`)) {
    return;
  }

  try {
    if (state.usingMock) {
      deleteMockItem(resource, id);
      showToast("演示数据已软删除");
    } else {
      const client = new AdminApiClient(state.settings);
      await client.delete(resource, item);
      showToast("已提交删除");
    }
    await loadResource();
  } catch (error) {
    showToast(`删除失败：${error.message}`);
  }
}

async function loginAdmin() {
  const username = elements.adminUsername.value.trim();
  const password = elements.adminPassword.value;
  if (!username || !password) {
    showToast("请输入管理员用户名和密码");
    return;
  }

  try {
    state.settings = {
      apiBaseUrl: elements.apiBaseUrl.value.trim(),
      adminToken: state.settings.adminToken,
      mockFallback: elements.mockFallback.checked,
    };
    const client = new AdminApiClient(state.settings);
    const result = await client.login(username, password);
    state.settings.adminToken = result.access_token;
    elements.adminToken.value = result.access_token;
    elements.adminPassword.value = "";
    saveSettings(state.settings);
    showToast(`管理员 ${result.user?.nickname || username} 登录成功`);
    await loadResource();
  } catch (error) {
    showToast(`管理员登录失败：${error.message}`);
  }
}

function handleRecordAction(event) {
  const target = event.target.closest("[data-action]");
  if (!target) {
    return;
  }
  const id = target.dataset.id;
  if (target.dataset.action === "preview-media") {
    openMediaLightbox(target.dataset.mediaKey, target.dataset.title);
    return;
  }
  if (target.dataset.action === "detail") {
    openDetailById(id);
  }
  if (target.dataset.action === "edit") {
    const item = getItemById(id);
    if (item) {
      openForm("edit", item);
    }
  }
  if (target.dataset.action === "quick-patch") {
    patchItem(id, target.dataset.actionIndex);
  }
  if (target.dataset.action === "delete") {
    deleteItem(id);
  }
}

function bindEvents() {
  elements.resourceNav.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-resource-id]");
    if (!button) {
      return;
    }
    state.resourceId = button.dataset.resourceId;
    state.page = 1;
    state.filterValue = "all";
    loadResource();
  });

  elements.connectionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    state.settings = {
      apiBaseUrl: elements.apiBaseUrl.value.trim(),
      adminToken: elements.adminToken.value.trim(),
      mockFallback: elements.mockFallback.checked,
    };
    saveSettings(state.settings);
    showToast("连接设置已保存");
    loadResource();
  });

  elements.searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = elements.searchInput.value.trim();
      state.page = 1;
      loadResource();
    }, 220);
  });

  elements.primaryFilter.addEventListener("change", () => {
    state.filterValue = elements.primaryFilter.value;
    state.page = 1;
    loadResource();
  });

  elements.pageSizeSelect.addEventListener("change", () => {
    state.pageSize = Number(elements.pageSizeSelect.value);
    state.page = 1;
    loadResource();
  });

  elements.adminLoginButton.addEventListener("click", loginAdmin);
  elements.createButton.addEventListener("click", () => openForm("create"));
  elements.refreshButton.addEventListener("click", () => loadResource());
  elements.previousPage.addEventListener("click", () => {
    state.page = Math.max(1, state.page - 1);
    loadResource();
  });
  elements.nextPage.addEventListener("click", () => {
    state.page += 1;
    loadResource();
  });

  elements.tableBody.addEventListener("click", handleRecordAction);
  elements.drawerActions.addEventListener("click", handleRecordAction);
  elements.detailDrawer.addEventListener("click", handleRecordAction);
  elements.closeDrawer.addEventListener("click", closeDrawer);
  elements.closeMediaLightbox.addEventListener("click", closeMediaLightbox);
  elements.mediaLightbox.addEventListener("click", (event) => {
    if (event.target === elements.mediaLightbox) {
      closeMediaLightbox();
    }
  });
  elements.closeForm.addEventListener("click", closeForm);
  elements.cancelForm.addEventListener("click", closeForm);
  elements.formModal.addEventListener("click", (event) => {
    if (event.target === elements.formModal) {
      closeForm();
    }
  });
  elements.recordForm.addEventListener("submit", submitForm);
}

function init() {
  elements.apiBaseUrl.value = state.settings.apiBaseUrl;
  elements.adminToken.value = state.settings.adminToken;
  elements.mockFallback.checked = state.settings.mockFallback;
  elements.pageSizeSelect.value = String(state.pageSize);
  bindEvents();
  loadResource();
}

init();
