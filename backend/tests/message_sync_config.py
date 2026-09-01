"""Configuration-only safety checks for Stage 11B cursor signing."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.config import DEVELOPMENT_MESSAGE_PUSH_TOKEN_KEY, DEVELOPMENT_MESSAGE_SYNC_CURSOR_SECRET, Settings


def main() -> None:
    assert Settings(environment="development", message_sync_cursor_secret=None).resolved_message_sync_cursor_secret() == (
        DEVELOPMENT_MESSAGE_SYNC_CURSOR_SECRET
    )
    try:
        Settings(environment="production", message_sync_cursor_secret=None).resolved_message_sync_cursor_secret()
    except RuntimeError as error:
        assert "TENNIS_MESSAGE_SYNC_CURSOR_SECRET" in str(error)
    else:
        raise AssertionError("Production must reject an implicit sync cursor secret")
    assert Settings(environment="production", message_sync_cursor_secret="test-secret").resolved_message_sync_cursor_secret() == "test-secret"
    production = Settings(environment="production", message_sync_cursor_secret="test-secret", message_push_token_key="production-key", export_storage_provider="external_contract", export_storage_bucket="exports", instance_id="test-instance")
    object.__setattr__(production, "cors_origins", ["https://app.example.test"])
    production.validate_runtime_configuration()
    unsafe_push = Settings(environment="production", message_sync_cursor_secret="test-secret", message_push_token_key=DEVELOPMENT_MESSAGE_PUSH_TOKEN_KEY, export_storage_provider="external_contract", export_storage_bucket="exports", instance_id="test-instance")
    object.__setattr__(unsafe_push, "cors_origins", ["https://app.example.test"])
    try:
        unsafe_push.validate_runtime_configuration()
    except RuntimeError as error:
        assert "MESSAGE_PUSH_TOKEN_KEY" in str(error)
    else:
        raise AssertionError("Production must reject the development Push token key")
    unsafe_cors = Settings(environment="production", message_sync_cursor_secret="test-secret", message_push_token_key="production-key", export_storage_provider="external_contract", export_storage_bucket="exports", instance_id="test-instance")
    object.__setattr__(unsafe_cors, "cors_origins", ["*"])
    try:
        unsafe_cors.validate_runtime_configuration()
    except RuntimeError as error:
        assert "TENNIS_CORS_ORIGINS" in str(error)
    else:
        raise AssertionError("Production must reject wildcard CORS")
    unsafe_export = Settings(environment="production", message_sync_cursor_secret="test-secret", message_push_token_key="production-key", instance_id="test-instance")
    object.__setattr__(unsafe_export, "cors_origins", ["https://app.example.test"])
    try:
        unsafe_export.validate_runtime_configuration()
    except RuntimeError as error:
        assert "EXPORT_STORAGE_PROVIDER" in str(error)
    else:
        raise AssertionError("Production must reject test export storage")
    print("Message sync cursor-secret configuration test passed.")


if __name__ == "__main__":
    main()
