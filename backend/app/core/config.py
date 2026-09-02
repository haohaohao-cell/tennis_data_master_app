from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
NETWORK_CONFIG_PATH = ROOT_DIR / "config" / "network.json"


def _load_network_config() -> dict:
    if not NETWORK_CONFIG_PATH.is_file():
        raise RuntimeError(
            "Network configuration file not found: "
            f"{NETWORK_CONFIG_PATH}\n\n"
            "Copy config/network.example.json to config/network.json "
            "and configure the network settings for this machine."
        )
    try:
        with NETWORK_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid network configuration JSON: {NETWORK_CONFIG_PATH}: {error}") from error
    if not isinstance(config, dict):
        raise RuntimeError(f"Network configuration must be a JSON object: {NETWORK_CONFIG_PATH}")
    return config


NETWORK_CONFIG = _load_network_config()


def _network_section(name: str) -> dict:
    value = NETWORK_CONFIG.get(name)
    if not isinstance(value, dict):
        raise RuntimeError(f"network.json is missing required section: {name}")
    return value


BACKEND_NETWORK_CONFIG = _network_section("backend")
PUBLIC_NETWORK_CONFIG = _network_section("public")


def _network_value(section: dict, name: str) -> object:
    if name not in section:
        raise RuntimeError(f"network.json is missing required field: {name}")
    return section[name]


def _network_int(name: str) -> int:
    value = _network_value(BACKEND_NETWORK_CONFIG, name)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"network.json backend.{name} must be an integer") from error
    if name == "port" and not 1 <= parsed <= 65535:
        raise RuntimeError("network.json backend.port must be an integer between 1 and 65535")
    return parsed


def _network_str(name: str) -> str:
    value = _network_value(BACKEND_NETWORK_CONFIG, name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"network.json backend.{name} must be a non-empty string")
    return value.strip()


def _public_api_base_url() -> str:
    value = _network_value(PUBLIC_NETWORK_CONFIG, "apiBaseUrl")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("network.json public.apiBaseUrl must be a non-empty URL")
    return value.strip().rstrip("/")


def _network_cors_origins() -> list[str] | None:
    value = BACKEND_NETWORK_CONFIG.get("corsOrigins")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(origin, str) for origin in value):
        raise RuntimeError("network.json backend.corsOrigins must be an array of strings")
    return [origin.strip() for origin in value if origin.strip()]


def _parse_cors_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return ["*"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Tennis Data Master API"
    api_prefix: str = "/api/v1"
    environment: str = os.getenv("TENNIS_API_ENV", "development")
    backend_host: str = _network_str("host")
    backend_port: int = _network_int("port")
    public_api_base_url: str = _public_api_base_url()
    database_path: Path = Path(
        os.getenv(
            "TENNIS_DB_PATH",
            str(ROOT_DIR / "backend" / "db" / "tennis_data_master.sqlite3"),
        )
    )
    schema_path: Path = ROOT_DIR / "backend" / "db" / "schema.sql"
    cors_origins: list[str] = None  # type: ignore[assignment]
    dev_sms_code: str = os.getenv("TENNIS_DEV_SMS_CODE", "000000")
    verification_code_ttl_minutes: int = int(os.getenv("TENNIS_CODE_TTL_MINUTES", "10"))
    access_token_ttl_minutes: int = int(os.getenv("TENNIS_ACCESS_TOKEN_TTL_MINUTES", "60"))
    refresh_token_ttl_days: int = int(os.getenv("TENNIS_REFRESH_TOKEN_TTL_DAYS", "30"))
    video_storage_dir: Path = Path(
        os.getenv(
            "TENNIS_VIDEO_STORAGE_DIR",
            str(ROOT_DIR / "backend" / "storage" / "videos"),
        )
    )
    public_video_path_prefix: str = os.getenv("TENNIS_VIDEO_PUBLIC_PATH_PREFIX", "/storage/videos")
    avatar_storage_dir: Path = Path(
        os.getenv(
            "TENNIS_AVATAR_STORAGE_DIR",
            str(ROOT_DIR / "backend" / "storage" / "avatars"),
        )
    )
    public_avatar_path_prefix: str = os.getenv("TENNIS_AVATAR_PUBLIC_PATH_PREFIX", "/storage/avatars")
    message_media_storage_dir: Path = Path(
        os.getenv(
            "TENNIS_MESSAGE_MEDIA_STORAGE_DIR",
            str(ROOT_DIR / "backend" / "storage" / "message_media"),
        )
    )
    # PostgreSQL is the only runtime database. SQLite is intentionally limited
    # to the explicit legacy migration utilities under scripts/.
    database_url: str | None = os.getenv("TENNIS_DATABASE_URL") or os.getenv("TENNIS_POSTGRES_DSN")
    database_pool_min_size: int = int(os.getenv("TENNIS_DATABASE_POOL_MIN_SIZE", "1"))
    database_pool_max_size: int = int(os.getenv("TENNIS_DATABASE_POOL_MAX_SIZE", "10"))
    database_connect_timeout_seconds: float = float(os.getenv("TENNIS_DATABASE_CONNECT_TIMEOUT_SECONDS", "5"))
    database_transaction_timeout_seconds: int = int(os.getenv("TENNIS_DATABASE_TRANSACTION_TIMEOUT_SECONDS", "30000"))
    max_message_image_size_bytes: int = int(
        os.getenv("TENNIS_MAX_MESSAGE_IMAGE_SIZE_BYTES", str(15 * 1024 * 1024))
    )
    max_message_image_pixels: int = int(
        os.getenv("TENNIS_MAX_MESSAGE_IMAGE_PIXELS", str(40_000_000))
    )
    max_message_video_size_bytes: int = int(
        os.getenv("TENNIS_MAX_MESSAGE_VIDEO_SIZE_BYTES", str(200 * 1024 * 1024))
    )
    max_message_video_pixels: int = int(os.getenv("TENNIS_MAX_MESSAGE_VIDEO_PIXELS", str(40_000_000)))
    max_message_video_duration_ms: int = int(os.getenv("TENNIS_MAX_MESSAGE_VIDEO_DURATION_MS", str(5 * 60 * 1000)))
    ffprobe_path: str | None = os.getenv("TENNIS_FFPROBE_PATH")
    ffmpeg_path: str | None = os.getenv("TENNIS_FFMPEG_PATH")
    video_probe_timeout_seconds: int = int(os.getenv("TENNIS_VIDEO_PROBE_TIMEOUT_SECONDS", "30"))
    message_media_ttl_hours: int = int(os.getenv("TENNIS_MESSAGE_MEDIA_TTL_HOURS", "24"))
    max_upload_avatar_size_bytes: int = int(
        os.getenv("TENNIS_MAX_UPLOAD_AVATAR_SIZE_BYTES", str(5 * 1024 * 1024))
    )
    max_upload_video_size_bytes: int = int(
        os.getenv("TENNIS_MAX_UPLOAD_VIDEO_SIZE_BYTES", str(2 * 1024 * 1024 * 1024))
    )
    max_post_video_duration_ms: int = int(
        os.getenv("TENNIS_MAX_POST_VIDEO_DURATION_MS", str(10 * 60 * 1000))
    )
    area_city_boundary_path: Path = Path(
        os.getenv(
            "TENNIS_AREA_CITY_BOUNDARY_PATH",
            str(ROOT_DIR / "backend" / "data" / "area_city_ok_geo.csv"),
        )
    )
    area_city_boundary_coordinate_system: str = os.getenv("TENNIS_AREA_CITY_COORDINATE_SYSTEM", "gcj02")

    def __post_init__(self) -> None:
        configured_cors = os.getenv("TENNIS_CORS_ORIGINS")
        if configured_cors is not None:
            cors_origins = _parse_cors_origins(configured_cors)
        else:
            network_origins = _network_cors_origins()
            cors_origins = network_origins if network_origins is not None else ["*"]
        object.__setattr__(
            self,
            "cors_origins",
            cors_origins,
        )

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"dev", "development", "local"}

    @property
    def uses_postgres(self) -> bool:
        # Keep one database contract across every backend module. A missing
        # DSN is reported by the PostgreSQL adapter instead of silently
        # creating a local SQLite file.
        return True


settings = Settings()
