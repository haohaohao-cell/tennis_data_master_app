from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "api" / "messages.ts").read_text(encoding="utf-8")
chat = (ROOT / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

assert "createMessageVideoUploadIntent" in api
assert "sendVideoMessage" in api
assert "uploadMessageMediaFile" in api
assert "completeMessageMediaUpload" in api
assert "cancelMessageMediaUpload" in api
assert "uploadMessageMediaFile(accessToken, attempt.mediaId" in chat
assert "uploadMessageImageFile(accessToken, intent.media.media_id, { name: video" not in chat
assert "mediaTypes: [\"videos\"]" in chat
assert "VideoMessageContent" in chat
assert "聊天视频首帧" in chat
assert "saveLocalMessageMediaAttempt" in chat
assert "listLocalMessageMediaAttempts" in chat
assert "cancelVideoUpload" in chat
assert "clientUploadId: pending.client_upload_id" in chat
assert "clientMessageId: pending.client_message_id" in chat
assert "app/api/uploads.ts" not in api + chat
print("Message video static test passed.")
