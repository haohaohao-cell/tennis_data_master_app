# Message Video Operations

消息视频写入 `TENNIS_MESSAGE_MEDIA_STORAGE_DIR` 下的 `videos/{media_id}/original.<ext>`，首帧写入同一媒体目录的 `thumbnail.jpg`。这些路径是测试存储实现，API 只返回鉴权 content URL，不返回 storage key。

允许的 MIME：`video/mp4`、`video/quicktime`、`video/webm`、`video/x-matroska`、`video/3gpp`。服务端使用 `ffprobe` 检查真实视频流、容器、codec、宽高、时长和字节数；上传过程流式计算 SHA-256。`ffmpeg` 负责首帧 JPEG，缩略图失败不会删除已验证原视频。

状态包括 `created`、`uploading`、`uploaded`、`attached`、`failed`、`expired`、`deleted`。只有已上传且未绑定的媒体可在消息事务中绑定；成员、消息状态、过期、撤回和删除都会在读取时重新检查。取消、过期、失败和孤儿文件由 `scripts/cleanup_message_media.py` 扫描，执行模式显式开启并可重试。

本地依赖：Windows PATH 中需有 `ffprobe.exe` 和 `ffmpeg.exe`，或设置 `TENNIS_FFPROBE_PATH`、`TENNIS_FFMPEG_PATH`。可调配置包括 `TENNIS_MAX_MESSAGE_VIDEO_SIZE_BYTES`、`TENNIS_MAX_MESSAGE_VIDEO_DURATION_MS`、`TENNIS_MAX_MESSAGE_VIDEO_PIXELS`、`TENNIS_MESSAGE_MEDIA_TTL_HOURS`。本地文件性能只能作为测试基线，不能外推对象存储生产容量。
