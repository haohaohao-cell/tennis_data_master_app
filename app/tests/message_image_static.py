from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "api" / "messages.ts").read_text(encoding="utf-8")
client = (ROOT / "api" / "client.ts").read_text(encoding="utf-8")
chat = (ROOT / "app" / "chat" / "[id].tsx").read_text(encoding="utf-8")

assert "/api/v1/messages/media/upload-intents" in api
assert "/messages/media/" in api
assert "sendImageMessage" in api
assert "uploadMessageMediaFile" in api
assert "message_type: \"image\"" in api
assert "expo-image-picker" in chat
assert "ImageMessageContent" in chat
assert "thumbnail_url" in chat
assert "图片不可用" in chat
assert "imageAttemptRef" in chat
assert "clientUploadId: attempt.clientUploadId" in chat
assert "attempt.clientMessageId" in chat
assert "app/api/uploads.ts" not in api + chat
assert "/posts/upload-intents" not in api + chat
assert "/tennis-activities/upload-intents" not in api + chat
assert "apiUpload" in client
assert "uploadMessageImageFile(accessToken, intent.media.media_id" in chat
print("Message image static test passed.")
