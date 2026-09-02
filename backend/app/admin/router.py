from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.admin.dependencies import AdminActor, require_admin_actor
from backend.app.admin.schemas import (
    AdminDeleteResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPostCreate,
    AdminPostListResponse,
    AdminPostRecord,
    AdminPostUpdate,
    AdminTennisActivityCreate,
    AdminTennisActivityListResponse,
    AdminTennisActivityRecord,
    AdminTennisActivityUpdate,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserRecord,
    AdminUserUpdate,
    AdminVideoCreate,
    AdminVideoListResponse,
    AdminVideoRecord,
    AdminVideoUpdate,
    AdminMessageMetrics,
    AdminAiAssistResponse,
)
from backend.app.admin import service
from backend.app.coach import service as coach_service
from backend.app.coach.schemas import (
    AdminCoachApplicationListResponse,
    AdminCoachApplicationRecord,
    AdminCoachReviewPayload,
    AdminCoachStatusPayload,
    CoachProfileRecord,
)
from backend.app.reports import service as reports_service
from backend.app.reports.schemas import MessageReportListResponse, MessageReportResponse, MessageReportUpdate


router = APIRouter(prefix="/admin", tags=["admin"])


Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(max_length=120)]
StatusFilter = Annotated[str | None, Query(alias="status")]
AdminDependency = Annotated[AdminActor, Depends(require_admin_actor)]


def _user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:255] if user_agent else None


@router.post("/auth/login", response_model=AdminLoginResponse)
def login_admin(payload: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    token_issue = service.login_admin_with_password(
        username=payload.username,
        password=payload.password,
        device=payload.device,
        ip_address=request.client.host if request.client else None,
        user_agent=_user_agent(request),
    )
    return AdminLoginResponse(
        access_token=token_issue.token_issue.access_token,
        refresh_token=token_issue.token_issue.refresh_token,
        access_expires_at=token_issue.token_issue.access_expires_at,
        refresh_expires_at=token_issue.token_issue.refresh_expires_at,
        user=token_issue.token_issue.user,
        admin_role=token_issue.admin_role,
    )


@router.get("/message-reports", response_model=MessageReportListResponse)
def list_message_reports(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    status_filter: StatusFilter = None,
) -> MessageReportListResponse:
    return reports_service.list_message_reports(page, page_size, status_filter)


@router.get("/message-metrics", response_model=AdminMessageMetrics)
def get_message_metrics(
    _: AdminDependency,
    since: Annotated[str, Query(max_length=40)],
    until: Annotated[str, Query(max_length=40)],
) -> AdminMessageMetrics:
    if since >= until:
        raise HTTPException(status_code=400, detail={"code": "METRICS_TIME_RANGE_INVALID", "message": "since must be earlier than until."})
    return service.message_metrics(since, until)


@router.post("/ai-assist/status", response_model=AdminAiAssistResponse)
def get_ai_assist_status(_: AdminDependency) -> AdminAiAssistResponse:
    return service.ai_assist_unavailable()


@router.patch("/message-reports/{report_id}", response_model=MessageReportResponse)
def update_message_report(report_id: str, payload: MessageReportUpdate, actor: AdminDependency) -> MessageReportResponse:
    return reports_service.update_message_report(report_id, actor.user.user_id, payload)
@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    q: Search = None,
    status_filter: StatusFilter = None,
    is_coach: bool | None = None,
    coach_status: str | None = None,
) -> AdminUserListResponse:
    result = service.list_users(
        page=page,
        page_size=page_size,
        q=q,
        status_filter=status_filter,
        is_coach=is_coach,
        coach_status=coach_status,
    )
    return AdminUserListResponse(**result.__dict__)


@router.post("/users", response_model=AdminUserRecord, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    _: AdminDependency,
) -> AdminUserRecord:
    return service.create_user(payload)


@router.get("/users/{user_id}", response_model=AdminUserRecord)
def get_user(user_id: str, _: AdminDependency) -> AdminUserRecord:
    return service.get_user(user_id)


@router.patch("/users/{user_id}", response_model=AdminUserRecord)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    actor: AdminDependency,
) -> AdminUserRecord:
    return service.update_user(user_id, payload, actor.user.user_id)


@router.delete("/users/{user_id}", response_model=AdminDeleteResponse)
def delete_user(user_id: str, actor: AdminDependency) -> AdminDeleteResponse:
    service.delete_user(user_id, actor.user.user_id)
    return AdminDeleteResponse(success=True, id=user_id)


@router.get("/coach-applications", response_model=AdminCoachApplicationListResponse)
def list_coach_applications(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    q: Search = None,
    status_filter: StatusFilter = None,
    application_type: str | None = None,
) -> AdminCoachApplicationListResponse:
    result = coach_service.list_admin_coach_applications(
        page=page,
        page_size=page_size,
        q=q,
        status_filter=status_filter,
        application_type=application_type,
    )
    return AdminCoachApplicationListResponse(**result.__dict__)


@router.get("/coach-applications/{coach_application_id}", response_model=AdminCoachApplicationRecord)
def get_coach_application(
    coach_application_id: str,
    _: AdminDependency,
) -> AdminCoachApplicationRecord:
    return coach_service.get_admin_coach_application(coach_application_id)


@router.post("/coach-applications/{coach_application_id}/approve", response_model=AdminCoachApplicationRecord)
def approve_coach_application(
    coach_application_id: str,
    actor: AdminDependency,
) -> AdminCoachApplicationRecord:
    return coach_service.approve_coach_application(coach_application_id, actor.user.user_id)


@router.post("/coach-applications/{coach_application_id}/reject", response_model=AdminCoachApplicationRecord)
def reject_coach_application(
    coach_application_id: str,
    payload: AdminCoachReviewPayload,
    actor: AdminDependency,
) -> AdminCoachApplicationRecord:
    return coach_service.reject_coach_application(coach_application_id, actor.user.user_id, payload)


@router.post("/coaches/{user_id}/suspend", response_model=CoachProfileRecord)
def suspend_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
    _: AdminDependency,
) -> CoachProfileRecord:
    return coach_service.suspend_coach(user_id, payload)


@router.post("/coaches/{user_id}/restore", response_model=CoachProfileRecord)
def restore_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
    _: AdminDependency,
) -> CoachProfileRecord:
    return coach_service.restore_coach(user_id, payload)


@router.post("/coaches/{user_id}/revoke", response_model=CoachProfileRecord)
def revoke_coach(
    user_id: str,
    payload: AdminCoachStatusPayload,
    _: AdminDependency,
) -> CoachProfileRecord:
    return coach_service.revoke_coach(user_id, payload)


@router.get("/tennis-activities", response_model=AdminTennisActivityListResponse)
def list_activities(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    q: Search = None,
    activity_type: str | None = None,
    default_visibility: str | None = None,
    analysis_summary_status: str | None = None,
    owner_user_id: str | None = None,
    include_deleted: bool = False,
) -> AdminTennisActivityListResponse:
    result = service.list_activities(
        page=page,
        page_size=page_size,
        q=q,
        activity_type=activity_type,
        default_visibility=default_visibility,
        analysis_summary_status=analysis_summary_status,
        owner_user_id=owner_user_id,
        include_deleted=include_deleted,
    )
    return AdminTennisActivityListResponse(**result.__dict__)


@router.post(
    "/tennis-activities",
    response_model=AdminTennisActivityRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_activity(
    payload: AdminTennisActivityCreate,
    _: AdminDependency,
) -> AdminTennisActivityRecord:
    return service.create_activity(payload)


@router.get("/tennis-activities/{tennis_activity_id}", response_model=AdminTennisActivityRecord)
def get_activity(
    tennis_activity_id: str,
    _: AdminDependency,
) -> AdminTennisActivityRecord:
    return service.get_activity(tennis_activity_id)


@router.patch("/tennis-activities/{tennis_activity_id}", response_model=AdminTennisActivityRecord)
def update_activity(
    tennis_activity_id: str,
    payload: AdminTennisActivityUpdate,
    _: AdminDependency,
) -> AdminTennisActivityRecord:
    return service.update_activity(tennis_activity_id, payload)


@router.delete("/tennis-activities/{tennis_activity_id}", response_model=AdminDeleteResponse)
def delete_activity(
    tennis_activity_id: str,
    _: AdminDependency,
) -> AdminDeleteResponse:
    service.delete_activity(tennis_activity_id)
    return AdminDeleteResponse(success=True, id=tennis_activity_id)


@router.get("/videos", response_model=AdminVideoListResponse)
def list_videos(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    q: Search = None,
    analysis_status: str | None = None,
    visibility: str | None = None,
    owner_user_id: str | None = None,
    include_deleted: bool = False,
) -> AdminVideoListResponse:
    result = service.list_videos(
        page=page,
        page_size=page_size,
        q=q,
        analysis_status=analysis_status,
        visibility=visibility,
        owner_user_id=owner_user_id,
        include_deleted=include_deleted,
    )
    return AdminVideoListResponse(**result.__dict__)


@router.post("/videos", response_model=AdminVideoRecord, status_code=status.HTTP_201_CREATED)
def create_video(
    payload: AdminVideoCreate,
    _: AdminDependency,
) -> AdminVideoRecord:
    return service.create_video(payload)


@router.get("/videos/{video_id}", response_model=AdminVideoRecord)
def get_video(video_id: str, _: AdminDependency) -> AdminVideoRecord:
    return service.get_video(video_id)


@router.patch("/videos/{video_id}", response_model=AdminVideoRecord)
def update_video(
    video_id: str,
    payload: AdminVideoUpdate,
    _: AdminDependency,
) -> AdminVideoRecord:
    return service.update_video(video_id, payload)


@router.delete("/videos/{video_id}", response_model=AdminDeleteResponse)
def delete_video(video_id: str, _: AdminDependency) -> AdminDeleteResponse:
    service.delete_video(video_id)
    return AdminDeleteResponse(success=True, id=video_id)


@router.get("/posts", response_model=AdminPostListResponse)
def list_posts(
    _: AdminDependency,
    page: Page = 1,
    page_size: PageSize = 20,
    q: Search = None,
    status_filter: StatusFilter = None,
    visibility: str | None = None,
    author_user_id: str | None = None,
) -> AdminPostListResponse:
    result = service.list_posts(
        page=page,
        page_size=page_size,
        q=q,
        status_filter=status_filter,
        visibility=visibility,
        author_user_id=author_user_id,
    )
    return AdminPostListResponse(**result.__dict__)


@router.post("/posts", response_model=AdminPostRecord, status_code=status.HTTP_201_CREATED)
def create_post(payload: AdminPostCreate, _: AdminDependency) -> AdminPostRecord:
    return service.create_post(payload)


@router.get("/posts/{social_post_id}", response_model=AdminPostRecord)
def get_post(social_post_id: str, _: AdminDependency) -> AdminPostRecord:
    return service.get_post(social_post_id)


@router.patch("/posts/{social_post_id}", response_model=AdminPostRecord)
def update_post(
    social_post_id: str,
    payload: AdminPostUpdate,
    _: AdminDependency,
) -> AdminPostRecord:
    return service.update_post(social_post_id, payload)


@router.delete("/posts/{social_post_id}", response_model=AdminDeleteResponse)
def delete_post(social_post_id: str, _: AdminDependency) -> AdminDeleteResponse:
    service.delete_post(social_post_id)
    return AdminDeleteResponse(success=True, id=social_post_id)
