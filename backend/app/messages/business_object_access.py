"""Read-only permission adapters for message-referenced domain objects.

Message rows retain only object type and ID. This module resolves those IDs
against current domain permissions and only returns data safe for a card.
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Literal


ObjectAccess = Literal["allowed", "denied", "not_found"]
ObjectState = Literal["active", "archived", "deleted", "unavailable"]


@dataclass(frozen=True)
class BusinessObjectAccessResult:
    object_type: str
    object_id: str
    access: ObjectAccess
    state: ObjectState
    can_preview: bool
    can_open: bool
    can_forward: bool
    safe_summary: str | None = None
    title: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


def _unavailable(object_type: str, object_id: str, *, access: ObjectAccess, state: ObjectState) -> BusinessObjectAccessResult:
    return BusinessObjectAccessResult(object_type, object_id, access, state, False, False, False)


def _lesson_role(connection: sqlite3.Connection, lesson_id: str | None, viewer_user_id: str) -> str | None:
    if not lesson_id:
        return None
    row = connection.execute(
        """
        SELECT CASE WHEN lessons.coach_user_id = ? THEN 'coach'
                    WHEN lesson_students.student_user_id IS NOT NULL THEN 'student'
                    ELSE NULL END AS viewer_role
        FROM lessons
        LEFT JOIN lesson_students ON lesson_students.lesson_id = lessons.lesson_id
          AND lesson_students.student_user_id = ? AND lesson_students.deleted_at IS NULL
        WHERE lessons.lesson_id = ? AND lessons.deleted_at IS NULL LIMIT 1;
        """,
        (viewer_user_id, viewer_user_id, lesson_id),
    ).fetchone()
    return row["viewer_role"] if row is not None else None


def _can_view_activity(connection: sqlite3.Connection, activity: sqlite3.Row, viewer_user_id: str) -> bool:
    if activity["owner_user_id"] == viewer_user_id or activity["default_visibility"] == "public":
        return True
    role = _lesson_role(connection, activity["lesson_id"], viewer_user_id)
    visibility = activity["default_visibility"]
    if (role == "coach" and visibility in {"lesson_coach", "lesson_participants"}) or (role == "student" and visibility == "lesson_participants"):
        return True
    # Keep the existing Activity-detail rule: a viewer who can see one of its
    # videos can open the containing Activity, even when its own default is
    # more restrictive.
    videos = connection.execute(
        "SELECT * FROM videos WHERE tennis_activity_id = ? AND deleted_at IS NULL;",
        (activity["tennis_activity_id"],),
    ).fetchall()
    return any(_can_view_video(connection, video, activity, viewer_user_id) for video in videos)


def _effective_video_visibility(activity: sqlite3.Row | None, video: sqlite3.Row) -> str:
    return activity["default_visibility"] if video["visibility"] == "inherit" and activity is not None else video["visibility"]


def _can_view_video(connection: sqlite3.Connection, video: sqlite3.Row, activity: sqlite3.Row | None, viewer_user_id: str) -> bool:
    if video["owner_user_id"] == viewer_user_id or (activity is not None and activity["owner_user_id"] == viewer_user_id):
        return True
    visibility = _effective_video_visibility(activity, video)
    if visibility == "public":
        return True
    role = _lesson_role(connection, activity["lesson_id"] if activity is not None else None, viewer_user_id)
    return (role == "coach" and visibility in {"lesson_coach", "lesson_participants"}) or (role == "student" and visibility == "lesson_participants")


def _resolve_activity(connection: sqlite3.Connection, object_id: str, viewer_user_id: str) -> BusinessObjectAccessResult:
    row = connection.execute("SELECT * FROM tennis_activities WHERE tennis_activity_id = ? LIMIT 1;", (object_id,)).fetchone()
    if row is None:
        return _unavailable("tennis_activity", object_id, access="not_found", state="unavailable")
    if row["deleted_at"] is not None:
        return _unavailable("tennis_activity", object_id, access="denied", state="deleted")
    if not _can_view_activity(connection, row, viewer_user_id):
        return _unavailable("tennis_activity", object_id, access="denied", state="unavailable")
    return BusinessObjectAccessResult("tennis_activity", object_id, "allowed", "active", True, True, True, (row["activity_type"] or "other")[:50], (row["title"] or "网球活动")[:120], {"activity_type": row["activity_type"], "visibility": row["default_visibility"]})


def _resolve_lesson(connection: sqlite3.Connection, object_id: str, viewer_user_id: str) -> BusinessObjectAccessResult:
    row = connection.execute("SELECT * FROM lessons WHERE lesson_id = ? LIMIT 1;", (object_id,)).fetchone()
    if row is None:
        return _unavailable("lesson", object_id, access="not_found", state="unavailable")
    if row["deleted_at"] is not None:
        return _unavailable("lesson", object_id, access="denied", state="deleted")
    if _lesson_role(connection, object_id, viewer_user_id) is None:
        return _unavailable("lesson", object_id, access="denied", state="unavailable")
    archived = row["status"] in {"completed", "canceled"}
    return BusinessObjectAccessResult("lesson", object_id, "allowed", "archived" if archived else "active", True, True, True, (row["lesson_type"] or "other")[:50], (row["title"] or "网球课程")[:120], {"lesson_type": row["lesson_type"], "status": row["status"]})


def _resolve_video(connection: sqlite3.Connection, object_id: str, viewer_user_id: str) -> BusinessObjectAccessResult:
    row = connection.execute("SELECT * FROM videos WHERE video_id = ? LIMIT 1;", (object_id,)).fetchone()
    if row is None:
        return _unavailable("video", object_id, access="not_found", state="unavailable")
    if row["deleted_at"] is not None:
        return _unavailable("video", object_id, access="denied", state="deleted")
    activity = connection.execute("SELECT * FROM tennis_activities WHERE tennis_activity_id = ? LIMIT 1;", (row["tennis_activity_id"],)).fetchone() if row["tennis_activity_id"] else None
    if activity is not None and activity["deleted_at"] is not None:
        activity = None
    if not _can_view_video(connection, row, activity, viewer_user_id):
        return _unavailable("video", object_id, access="denied", state="unavailable")
    if row["upload_status"] != "uploaded":
        return _unavailable("video", object_id, access="allowed", state="unavailable")
    return BusinessObjectAccessResult("video", object_id, "allowed", "active", True, True, True, "视频已就绪", "训练视频", {"analysis_status": row["analysis_status"], "visibility": _effective_video_visibility(activity, row)})


def resolve_business_object_access(connection: sqlite3.Connection, object_type: str, object_id: str, viewer_user_id: str | None) -> BusinessObjectAccessResult:
    """Resolve a message object with current access and forwarding eligibility."""
    if object_type not in {"tennis_activity", "lesson", "video", "analysis"}:
        return _unavailable(object_type, object_id, access="not_found", state="unavailable")
    if not viewer_user_id:
        return _unavailable(object_type, object_id, access="denied", state="unavailable")
    if object_type == "tennis_activity":
        return _resolve_activity(connection, object_id, viewer_user_id)
    if object_type == "lesson":
        return _resolve_lesson(connection, object_id, viewer_user_id)
    if object_type == "video":
        return _resolve_video(connection, object_id, viewer_user_id)
    # Analysis has no independent table or detail endpoint. Its status belongs
    # to Activity/Video records, so granting arbitrary analysis IDs is unsafe.
    return _unavailable("analysis", object_id, access="not_found", state="unavailable")
