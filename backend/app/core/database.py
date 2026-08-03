from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from collections.abc import Iterator

from .config import settings


AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS auth_identities (
    identity_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL
        CHECK (provider IN ('phone', 'wechat', 'apple')),
    provider_subject TEXT NOT NULL CHECK (length(provider_subject) <= 255),
    provider_subject_normalized TEXT NOT NULL CHECK (length(provider_subject_normalized) <= 255),
    is_verified INTEGER NOT NULL DEFAULT 0 CHECK (is_verified IN (0, 1)),
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    access_token_hash TEXT NOT NULL CHECK (length(access_token_hash) = 64),
    refresh_token_hash TEXT NOT NULL CHECK (length(refresh_token_hash) = 64),
    device_name TEXT CHECK (device_name IS NULL OR length(device_name) <= 120),
    platform TEXT CHECK (platform IS NULL OR length(platform) <= 50),
    ip_address TEXT CHECK (ip_address IS NULL OR length(ip_address) <= 64),
    user_agent TEXT CHECK (user_agent IS NULL OR length(user_agent) <= 255),
    access_expires_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_verification_codes (
    verification_code_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'phone'
        CHECK (provider IN ('phone')),
    recipient TEXT NOT NULL CHECK (length(recipient) <= 255),
    recipient_normalized TEXT NOT NULL CHECK (length(recipient_normalized) <= 255),
    code_hash TEXT NOT NULL CHECK (length(code_hash) = 64),
    purpose TEXT NOT NULL DEFAULT 'login'
        CHECK (purpose IN ('login', 'bind_identity')),
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_identities_provider_subject_active
    ON auth_identities(provider, provider_subject_normalized)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_auth_identities_user_provider
    ON auth_identities(user_id, provider);

CREATE INDEX IF NOT EXISTS idx_auth_identities_provider_created
    ON auth_identities(provider, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_access_token_hash
    ON auth_sessions(access_token_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_sessions_refresh_token_hash
    ON auth_sessions(refresh_token_hash);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active
    ON auth_sessions(user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires
    ON auth_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_auth_verification_codes_recipient_created
    ON auth_verification_codes(provider, recipient_normalized, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_auth_verification_codes_expires
    ON auth_verification_codes(expires_at);

CREATE TRIGGER IF NOT EXISTS trg_auth_identities_set_updated_at
AFTER UPDATE ON auth_identities
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_identities
    SET updated_at = CURRENT_TIMESTAMP
    WHERE identity_id = OLD.identity_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_auth_sessions_set_updated_at
AFTER UPDATE ON auth_sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_sessions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE session_id = OLD.session_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_auth_verification_codes_set_updated_at
AFTER UPDATE ON auth_verification_codes
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE auth_verification_codes
    SET updated_at = CURRENT_TIMESTAMP
    WHERE verification_code_id = OLD.verification_code_id;
END;
"""


ADMIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS admin_users (
    admin_user_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    note TEXT CHECK (note IS NULL OR length(note) <= 255),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disabled_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS admin_credentials (
    admin_credential_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL CHECK (length(username) <= 50),
    username_normalized TEXT NOT NULL CHECK (length(username_normalized) <= 50),
    password_hash TEXT NOT NULL CHECK (length(password_hash) <= 255),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_admin_users_status_role
    ON admin_users(status, role);

CREATE INDEX IF NOT EXISTS idx_admin_users_created_by
    ON admin_users(created_by_user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_credentials_username
    ON admin_credentials(username_normalized);

CREATE INDEX IF NOT EXISTS idx_admin_credentials_user_status
    ON admin_credentials(user_id, status);

CREATE TRIGGER IF NOT EXISTS trg_admin_users_set_updated_at
AFTER UPDATE ON admin_users
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE admin_users
    SET updated_at = CURRENT_TIMESTAMP
    WHERE admin_user_id = OLD.admin_user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_admin_credentials_set_updated_at
AFTER UPDATE ON admin_credentials
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE admin_credentials
    SET updated_at = CURRENT_TIMESTAMP
    WHERE admin_credential_id = OLD.admin_credential_id;
END;
"""


COACH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS coach_applications (
    coach_application_id TEXT PRIMARY KEY,
    applicant_user_id TEXT NOT NULL,
    application_type TEXT NOT NULL
        CHECK (application_type IN ('certified', 'non_professional')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'canceled')),
    display_name TEXT NOT NULL CHECK (length(display_name) <= 50),
    real_name TEXT CHECK (real_name IS NULL OR length(real_name) <= 50),
    phone TEXT CHECK (phone IS NULL OR length(phone) <= 30),
    city TEXT CHECK (city IS NULL OR length(city) <= 80),
    specialties TEXT CHECK (specialties IS NULL OR length(specialties) <= 255),
    coaching_experience TEXT,
    certification_title TEXT CHECK (certification_title IS NULL OR length(certification_title) <= 120),
    certification_file_path TEXT,
    verification_video_path TEXT,
    note TEXT,
    reviewer_user_id TEXT,
    reviewed_at TEXT,
    rejection_reason TEXT CHECK (rejection_reason IS NULL OR length(rejection_reason) <= 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (application_type <> 'certified' OR certification_file_path IS NOT NULL),
    CHECK (application_type <> 'non_professional' OR verification_video_path IS NOT NULL),
    FOREIGN KEY (applicant_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS coach_profiles (
    coach_profile_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    coach_type TEXT NOT NULL
        CHECK (coach_type IN ('certified', 'non_professional')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    display_name TEXT NOT NULL CHECK (length(display_name) <= 50),
    city TEXT CHECK (city IS NULL OR length(city) <= 80),
    specialties TEXT CHECK (specialties IS NULL OR length(specialties) <= 255),
    coaching_experience TEXT,
    certification_title TEXT CHECK (certification_title IS NULL OR length(certification_title) <= 120),
    certification_file_path TEXT,
    verification_video_path TEXT,
    approved_application_id TEXT,
    approved_by_user_id TEXT,
    approved_at TEXT NOT NULL,
    suspended_at TEXT,
    revoked_at TEXT,
    status_reason TEXT CHECK (status_reason IS NULL OR length(status_reason) <= 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (approved_application_id) REFERENCES coach_applications(coach_application_id),
    FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coach_applications_user_pending
    ON coach_applications(applicant_user_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_coach_applications_status_created
    ON coach_applications(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coach_applications_type_status
    ON coach_applications(application_type, status);

CREATE INDEX IF NOT EXISTS idx_coach_profiles_status_type
    ON coach_profiles(status, coach_type);

CREATE INDEX IF NOT EXISTS idx_coach_profiles_user_status
    ON coach_profiles(user_id, status);

CREATE TRIGGER IF NOT EXISTS trg_coach_applications_set_updated_at
AFTER UPDATE ON coach_applications
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE coach_applications
    SET updated_at = CURRENT_TIMESTAMP
    WHERE coach_application_id = OLD.coach_application_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_coach_profiles_set_updated_at
AFTER UPDATE ON coach_profiles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE coach_profiles
    SET updated_at = CURRENT_TIMESTAMP
    WHERE coach_profile_id = OLD.coach_profile_id;
END;
"""

SQLITE_CONNECT_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = 5000
STALE_TENNIS_ACTIVITIES_BACKUP_TABLE = "tennis_activities_old_location_source"

TENNIS_ACTIVITIES_SCHEMA_SQL = """
CREATE TABLE tennis_activities (
    tennis_activity_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    lesson_id TEXT,
    title TEXT CHECK (title IS NULL OR length(title) <= 120),
    activity_type TEXT NOT NULL DEFAULT 'other'
        CHECK (activity_type IN (
            'casual_hit',
            'match',
            'serve_training',
            'forehand_training',
            'backhand_training',
            'multi_ball_drill',
            'stroke_recording',
            'post_match_review',
            'lesson_practice',
            'coach_demo',
            'other'
        )),
    default_visibility TEXT NOT NULL DEFAULT 'private'
        CHECK (default_visibility IN (
            'private',
            'friends',
            'specified_users',
            'lesson_coach',
            'lesson_participants',
            'public'
        )),
    started_at TEXT,
    ended_at TEXT,
    location_name TEXT CHECK (location_name IS NULL OR length(location_name) <= 120),
    location_source TEXT CHECK (
        location_source IN ('device_gps', 'video_metadata', 'manual_legacy', 'unavailable')
        OR location_source IS NULL
    ),
    location_latitude REAL CHECK (
        location_latitude IS NULL
        OR (location_latitude >= -90 AND location_latitude <= 90)
    ),
    location_longitude REAL CHECK (
        location_longitude IS NULL
        OR (location_longitude >= -180 AND location_longitude <= 180)
    ),
    location_accuracy_m REAL CHECK (location_accuracy_m IS NULL OR location_accuracy_m >= 0),
    location_captured_at TEXT,
    location_country_code TEXT CHECK (location_country_code IS NULL OR length(location_country_code) <= 8),
    location_region TEXT CHECK (location_region IS NULL OR length(location_region) <= 80),
    location_city TEXT CHECK (location_city IS NULL OR length(location_city) <= 80),
    location_district TEXT CHECK (location_district IS NULL OR length(location_district) <= 80),
    location_address_label TEXT CHECK (location_address_label IS NULL OR length(location_address_label) <= 255),
    location_coordinate_system TEXT CHECK (
        location_coordinate_system IN ('wgs84', 'gcj02')
        OR location_coordinate_system IS NULL
    ),
    court_surface TEXT CHECK (
        court_surface IN ('hard', 'clay', 'grass', 'carpet', 'unknown')
        OR court_surface IS NULL
    ),
    opponent_user_id TEXT,
    opponent_name TEXT CHECK (opponent_name IS NULL OR length(opponent_name) <= 50),
    note TEXT,
    analysis_summary_status TEXT CHECK (
        analysis_summary_status IN ('pending', 'processing', 'completed', 'failed')
        OR analysis_summary_status IS NULL
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at),
    CHECK (opponent_user_id IS NULL OR opponent_user_id <> owner_user_id),
    FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id),
    FOREIGN KEY (opponent_user_id) REFERENCES users(user_id)
);
"""

TENNIS_ACTIVITIES_SUPPORT_SQL = """
CREATE INDEX IF NOT EXISTS idx_activities_owner_created
    ON tennis_activities(owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_lesson_created
    ON tennis_activities(lesson_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_type_started
    ON tennis_activities(activity_type, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_activities_location_city_started
    ON tennis_activities(location_city, location_district, started_at DESC, tennis_activity_id DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_activities_visibility
    ON tennis_activities(default_visibility);

CREATE TRIGGER IF NOT EXISTS trg_tennis_activities_set_updated_at
AFTER UPDATE ON tennis_activities
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE tennis_activities
    SET updated_at = CURRENT_TIMESTAMP
    WHERE tennis_activity_id = OLD.tennis_activity_id;
END;
"""


def _connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        settings.database_path,
        timeout=SQLITE_CONNECT_TIMEOUT_SECONDS,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS};")
    connection.execute("PRAGMA synchronous = NORMAL;")
    return connection


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(*, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    return any(row["name"] == column_name for row in rows)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1;
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_sql(connection: sqlite3.Connection, table_name: str) -> str | None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?;
        """,
        (table_name,),
    ).fetchone()
    return row["sql"] if row else None


def _repair_stale_tennis_activity_fk_references(connection: sqlite3.Connection) -> None:
    stale_table = STALE_TENNIS_ACTIVITIES_BACKUP_TABLE
    rows = connection.execute(
        """
        SELECT 1
        FROM sqlite_schema
        WHERE sql LIKE ?
          AND name <> ?
          AND tbl_name <> ?
        LIMIT 1;
        """,
        (f"%{stale_table}%", stale_table, stale_table),
    ).fetchone()
    if rows is None:
        return

    schema_version = connection.execute("PRAGMA schema_version;").fetchone()[0]
    connection.execute("PRAGMA writable_schema = ON;")
    try:
        # A previous SQLite table rebuild renamed child foreign keys to this
        # temporary table. Patch only the schema text so existing rows stay put.
        connection.execute(
            """
            UPDATE sqlite_schema
            SET sql = replace(replace(sql, ?, 'tennis_activities'), ?, 'tennis_activities')
            WHERE sql LIKE ?
              AND name <> ?
              AND tbl_name <> ?;
            """,
            (
                f'"{stale_table}"',
                stale_table,
                f"%{stale_table}%",
                stale_table,
                stale_table,
            ),
        )
        connection.execute(f"PRAGMA schema_version = {int(schema_version) + 1};")
    finally:
        connection.execute("PRAGMA writable_schema = OFF;")


def _run_tennis_activities_location_source_constraint_migration(connection: sqlite3.Connection) -> None:
    table_sql = _table_sql(connection, "tennis_activities")
    if table_sql is None:
        return
    if "video_metadata" in table_sql and "network_estimate" not in table_sql:
        return

    columns = [row["name"] for row in connection.execute("PRAGMA table_info(tennis_activities);").fetchall()]
    column_list = ", ".join(columns)
    location_columns_to_clear = {
        "location_latitude",
        "location_longitude",
        "location_accuracy_m",
        "location_captured_at",
        "location_country_code",
        "location_region",
        "location_city",
        "location_district",
        "location_address_label",
        "location_coordinate_system",
    }
    select_expressions = []
    for column in columns:
        if column == "location_source":
            select_expressions.append(
                "CASE WHEN location_source = 'network_estimate' THEN 'unavailable' ELSE location_source END AS location_source"
            )
        elif column in location_columns_to_clear:
            select_expressions.append(
                f"CASE WHEN location_source = 'network_estimate' THEN NULL ELSE {column} END AS {column}"
            )
        else:
            select_expressions.append(column)
    select_list = ", ".join(select_expressions)
    backup_table = STALE_TENNIS_ACTIVITIES_BACKUP_TABLE
    legacy_alter_table = connection.execute("PRAGMA legacy_alter_table;").fetchone()[0]
    connection.execute("PRAGMA legacy_alter_table = ON;")
    try:
        connection.execute(f"DROP TABLE IF EXISTS {backup_table};")
        connection.execute(f"ALTER TABLE tennis_activities RENAME TO {backup_table};")
        connection.execute(TENNIS_ACTIVITIES_SCHEMA_SQL)
        connection.execute(
            f"""
            INSERT INTO tennis_activities ({column_list})
            SELECT {select_list}
            FROM {backup_table};
            """
        )
        connection.execute(f"DROP TABLE {backup_table};")
        connection.executescript(TENNIS_ACTIVITIES_SUPPORT_SQL)
    finally:
        connection.execute(f"PRAGMA legacy_alter_table = {int(legacy_alter_table)};")


def _run_users_migrations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "users"):
        return

    if not _column_exists(connection, "users", "profile_completed"):
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN profile_completed INTEGER NOT NULL DEFAULT 0
                CHECK (profile_completed IN (0, 1));
            """
        )
    if not _column_exists(connection, "users", "is_coach"):
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN is_coach INTEGER NOT NULL DEFAULT 0
                CHECK (is_coach IN (0, 1));
            """
        )
    if not _column_exists(connection, "users", "coach_status"):
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN coach_status TEXT CHECK (
                coach_status IN ('pending', 'active', 'disabled', 'rejected')
                OR coach_status IS NULL
            );
            """
        )
    if not _column_exists(connection, "users", "coach_verified_at"):
        connection.execute("ALTER TABLE users ADD COLUMN coach_verified_at TEXT;")


def _run_video_upload_migrations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "videos"):
        return

    if not _column_exists(connection, "videos", "upload_status"):
        connection.execute(
            """
            ALTER TABLE videos
            ADD COLUMN upload_status TEXT NOT NULL DEFAULT 'uploaded'
                CHECK (upload_status IN ('pending', 'uploading', 'uploaded', 'failed', 'canceled'));
            """
        )
    if not _column_exists(connection, "videos", "upload_error_message"):
        connection.execute("ALTER TABLE videos ADD COLUMN upload_error_message TEXT;")
    if not _column_exists(connection, "videos", "uploaded_at"):
        connection.execute("ALTER TABLE videos ADD COLUMN uploaded_at TEXT;")
    if not _column_exists(connection, "videos", "thumbnail_path"):
        connection.execute("ALTER TABLE videos ADD COLUMN thumbnail_path TEXT;")

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_videos_upload_status
            ON videos(upload_status, created_at);
        """
    )


def _run_activity_location_migrations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "tennis_activities"):
        return

    columns = (
        (
            "location_source",
            """
            ALTER TABLE tennis_activities
            ADD COLUMN location_source TEXT CHECK (
                location_source IN ('device_gps', 'video_metadata', 'manual_legacy', 'unavailable')
                OR location_source IS NULL
            );
            """,
        ),
        (
            "location_latitude",
            """
            ALTER TABLE tennis_activities
            ADD COLUMN location_latitude REAL CHECK (
                location_latitude IS NULL
                OR (location_latitude >= -90 AND location_latitude <= 90)
            );
            """,
        ),
        (
            "location_longitude",
            """
            ALTER TABLE tennis_activities
            ADD COLUMN location_longitude REAL CHECK (
                location_longitude IS NULL
                OR (location_longitude >= -180 AND location_longitude <= 180)
            );
            """,
        ),
        (
            "location_accuracy_m",
            """
            ALTER TABLE tennis_activities
            ADD COLUMN location_accuracy_m REAL CHECK (
                location_accuracy_m IS NULL OR location_accuracy_m >= 0
            );
            """,
        ),
        ("location_captured_at", "ALTER TABLE tennis_activities ADD COLUMN location_captured_at TEXT;"),
        (
            "location_country_code",
            "ALTER TABLE tennis_activities ADD COLUMN location_country_code TEXT CHECK (location_country_code IS NULL OR length(location_country_code) <= 8);",
        ),
        (
            "location_region",
            "ALTER TABLE tennis_activities ADD COLUMN location_region TEXT CHECK (location_region IS NULL OR length(location_region) <= 80);",
        ),
        (
            "location_city",
            "ALTER TABLE tennis_activities ADD COLUMN location_city TEXT CHECK (location_city IS NULL OR length(location_city) <= 80);",
        ),
        (
            "location_district",
            "ALTER TABLE tennis_activities ADD COLUMN location_district TEXT CHECK (location_district IS NULL OR length(location_district) <= 80);",
        ),
        (
            "location_address_label",
            "ALTER TABLE tennis_activities ADD COLUMN location_address_label TEXT CHECK (location_address_label IS NULL OR length(location_address_label) <= 255);",
        ),
        (
            "location_coordinate_system",
            """
            ALTER TABLE tennis_activities
            ADD COLUMN location_coordinate_system TEXT CHECK (
                location_coordinate_system IN ('wgs84', 'gcj02')
                OR location_coordinate_system IS NULL
            );
            """,
        ),
    )
    for column_name, statement in columns:
        if not _column_exists(connection, "tennis_activities", column_name):
            connection.execute(statement)

    _run_tennis_activities_location_source_constraint_migration(connection)

    connection.execute(
        """
        UPDATE tennis_activities
        SET location_source = CASE
                WHEN location_name IS NOT NULL THEN 'manual_legacy'
                ELSE 'unavailable'
            END
        WHERE location_source IS NULL;
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_activities_location_city_started
            ON tennis_activities(location_city, location_district, started_at DESC, tennis_activity_id DESC)
            WHERE deleted_at IS NULL;
        """
    )


def _run_post_feed_migrations(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "social_posts"):
        return

    columns = (
        (
            "review_status",
            """
            ALTER TABLE social_posts
            ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'
                CHECK (review_status IN ('pending', 'approved', 'rejected'));
            """,
        ),
        ("reviewed_at", "ALTER TABLE social_posts ADD COLUMN reviewed_at TEXT;"),
        ("reviewer_user_id", "ALTER TABLE social_posts ADD COLUMN reviewer_user_id TEXT;"),
        (
            "review_reason",
            "ALTER TABLE social_posts ADD COLUMN review_reason TEXT CHECK (review_reason IS NULL OR length(review_reason) <= 500);",
        ),
        (
            "location_scope",
            """
            ALTER TABLE social_posts
            ADD COLUMN location_scope TEXT NOT NULL DEFAULT 'none'
                CHECK (location_scope IN ('none', 'region', 'city'));
            """,
        ),
        (
            "location_region",
            "ALTER TABLE social_posts ADD COLUMN location_region TEXT CHECK (location_region IS NULL OR length(location_region) <= 80);",
        ),
        (
            "location_city",
            "ALTER TABLE social_posts ADD COLUMN location_city TEXT CHECK (location_city IS NULL OR length(location_city) <= 80);",
        ),
    )
    for column_name, statement in columns:
        if not _column_exists(connection, "social_posts", column_name):
            connection.execute(statement)

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS social_post_stats (
            social_post_id TEXT PRIMARY KEY,
            like_count INTEGER NOT NULL DEFAULT 0 CHECK (like_count >= 0),
            comment_count INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
            favorite_count INTEGER NOT NULL DEFAULT 0 CHECK (favorite_count >= 0),
            share_count INTEGER NOT NULL DEFAULT 0 CHECK (share_count >= 0),
            view_count INTEGER NOT NULL DEFAULT 0 CHECK (view_count >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_post_views (
            user_post_view_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            social_post_id TEXT NOT NULL,
            first_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            first_view_source TEXT CHECK (first_view_source IS NULL OR length(first_view_source) <= 50),
            last_view_source TEXT CHECK (last_view_source IS NULL OR length(last_view_source) <= 50),
            view_count INTEGER NOT NULL DEFAULT 1 CHECK (view_count >= 1),
            total_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (total_dwell_time_ms >= 0),
            last_dwell_time_ms INTEGER NOT NULL DEFAULT 0 CHECK (last_dwell_time_ms >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, social_post_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_post_hides (
            user_post_hide_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            social_post_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'canceled')),
            source TEXT CHECK (source IS NULL OR length(source) <= 50),
            reason TEXT CHECK (reason IS NULL OR length(reason) <= 255),
            hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            canceled_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (status = 'active' OR canceled_at IS NOT NULL),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (social_post_id) REFERENCES social_posts(social_post_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_social_posts_feed_published
            ON social_posts(review_status, status, published_at DESC, social_post_id DESC)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_social_posts_location_published
            ON social_posts(location_city, location_region, published_at DESC, social_post_id DESC)
            WHERE deleted_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_social_post_stats_updated
            ON social_post_stats(updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_user_post_views_user_last_viewed
            ON user_post_views(user_id, last_viewed_at DESC, social_post_id DESC);

        CREATE INDEX IF NOT EXISTS idx_user_post_views_post
            ON user_post_views(social_post_id, last_viewed_at DESC);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_post_hides_active_pair
            ON user_post_hides(user_id, social_post_id)
            WHERE status = 'active';

        CREATE INDEX IF NOT EXISTS idx_user_post_hides_user_hidden
            ON user_post_hides(user_id, hidden_at DESC);

        INSERT OR IGNORE INTO social_post_stats (social_post_id)
        SELECT social_post_id
        FROM social_posts;

        CREATE TRIGGER IF NOT EXISTS trg_social_post_stats_set_updated_at
        AFTER UPDATE ON social_post_stats
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE social_post_stats
            SET updated_at = CURRENT_TIMESTAMP
            WHERE social_post_id = OLD.social_post_id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_user_post_views_set_updated_at
        AFTER UPDATE ON user_post_views
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE user_post_views
            SET updated_at = CURRENT_TIMESTAMP
            WHERE user_post_view_id = OLD.user_post_view_id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_user_post_hides_set_updated_at
        AFTER UPDATE ON user_post_hides
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE user_post_hides
            SET updated_at = CURRENT_TIMESTAMP
            WHERE user_post_hide_id = OLD.user_post_hide_id;
        END;
        """
    )


def initialize_database() -> None:
    schema_sql = settings.schema_path.read_text(encoding="utf-8")
    social_message_schema_path = settings.schema_path.parent / "social_message_schema.sql"
    social_message_schema_sql = social_message_schema_path.read_text(encoding="utf-8")
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA foreign_keys = OFF;")
        if _table_exists(connection, "users"):
            _run_users_migrations(connection)
            _run_video_upload_migrations(connection)
            _run_activity_location_migrations(connection)
            _run_post_feed_migrations(connection)
            connection.executescript(AUTH_SCHEMA_SQL)
        else:
            connection.executescript(schema_sql)
            _run_users_migrations(connection)
            _run_video_upload_migrations(connection)
            _run_activity_location_migrations(connection)
            _run_post_feed_migrations(connection)
        _repair_stale_tennis_activity_fk_references(connection)
        connection.executescript(social_message_schema_sql)
        connection.executescript(ADMIN_SCHEMA_SQL)
        connection.executescript(COACH_SCHEMA_SQL)
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON;")

        foreign_key_issues = list(connection.execute("PRAGMA foreign_key_check;"))
        if foreign_key_issues:
            raise RuntimeError(f"Foreign key check failed: {foreign_key_issues}")
