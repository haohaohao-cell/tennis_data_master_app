from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.auth_api_smoke import asgi_request


async def login_phone(app, phone: str) -> tuple[str, str]:
    response = await asgi_request(
        app,
        "POST",
        "/api/v1/auth/phone-login",
        {"phone": phone, "code": "000000"},
    )
    assert response.status == 200, response
    return response.json_body["access_token"], response.json_body["user"]["user_id"]


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = os.path.join(temp_dir, "coach_api_smoke.sqlite3")

        from backend.app.admin.service import ensure_test_admin_account
        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        user_token, user_id = await login_phone(app, "13700000001")
        user_headers = {"authorization": f"Bearer {user_token}"}

        initial_identity = await asgi_request(
            app,
            "GET",
            "/api/v1/users/me/coach-identity",
            headers=user_headers,
        )
        assert initial_identity.status == 200, initial_identity
        assert initial_identity.json_body["status"] == "normal_user"

        non_professional_application = await asgi_request(
            app,
            "POST",
            "/api/v1/users/me/coach-applications",
            {
                "application_type": "non_professional",
                "display_name": "Baseline Helper",
                "city": "Shanghai",
                "specialties": "底线稳定性, 入门陪练",
                "coaching_experience": "长期参加业余训练营，常帮助新手修正击球节奏。",
                "verification_video_path": "/storage/coach-applications/nonpro-demo.mp4",
            },
            headers=user_headers,
        )
        assert non_professional_application.status == 200, non_professional_application
        application_id = non_professional_application.json_body["application"]["coach_application_id"]
        assert non_professional_application.json_body["identity"]["status"] == "pending_review"

        duplicate_application = await asgi_request(
            app,
            "POST",
            "/api/v1/users/me/coach-applications",
            {
                "application_type": "non_professional",
                "display_name": "Duplicate",
                "verification_video_path": "/storage/coach-applications/duplicate.mp4",
            },
            headers=user_headers,
        )
        assert duplicate_application.status == 409, duplicate_application
        assert duplicate_application.json_body["detail"]["code"] == "COACH_APPLICATION_PENDING_EXISTS"

        admin_user_id = ensure_test_admin_account("coach-admin", "0000")
        admin_login = await asgi_request(
            app,
            "POST",
            "/api/v1/admin/auth/login",
            {"username": "coach-admin", "password": "0000"},
        )
        assert admin_login.status == 200, admin_login
        admin_headers = {"authorization": f"Bearer {admin_login.json_body['access_token']}"}

        applications = await asgi_request(
            app,
            "GET",
            "/api/v1/admin/coach-applications",
            headers=admin_headers,
        )
        assert applications.status == 200, applications
        assert applications.json_body["total"] == 1
        assert applications.json_body["items"][0]["applicant_user_id"] == user_id

        approved = await asgi_request(
            app,
            "POST",
            f"/api/v1/admin/coach-applications/{application_id}/approve",
            headers=admin_headers,
        )
        assert approved.status == 200, approved
        assert approved.json_body["status"] == "approved"
        assert approved.json_body["reviewer_user_id"] == admin_user_id

        approved_identity = await asgi_request(
            app,
            "GET",
            "/api/v1/users/me/coach-identity",
            headers=user_headers,
        )
        assert approved_identity.status == 200, approved_identity
        assert approved_identity.json_body["status"] == "non_professional_coach"
        assert approved_identity.json_body["capabilities"]["video_review"] is True
        assert approved_identity.json_body["capabilities"]["course_management"] is False

        suspended = await asgi_request(
            app,
            "POST",
            f"/api/v1/admin/coaches/{user_id}/suspend",
            {"reason": "资料复核中"},
            headers=admin_headers,
        )
        assert suspended.status == 200, suspended
        assert suspended.json_body["status"] == "suspended"

        suspended_identity = await asgi_request(
            app,
            "GET",
            "/api/v1/users/me/coach-identity",
            headers=user_headers,
        )
        assert suspended_identity.status == 200, suspended_identity
        assert suspended_identity.json_body["status"] == "coach_suspended"
        assert suspended_identity.json_body["capabilities"]["video_review"] is False

        restored = await asgi_request(
            app,
            "POST",
            f"/api/v1/admin/coaches/{user_id}/restore",
            {"reason": "复核通过"},
            headers=admin_headers,
        )
        assert restored.status == 200, restored
        assert restored.json_body["status"] == "active"

        revoked = await asgi_request(
            app,
            "POST",
            f"/api/v1/admin/coaches/{user_id}/revoke",
            {"reason": "用户主动取消教练身份"},
            headers=admin_headers,
        )
        assert revoked.status == 200, revoked
        assert revoked.json_body["status"] == "revoked"

        rejected_token, _ = await login_phone(app, "13700000002")
        rejected_headers = {"authorization": f"Bearer {rejected_token}"}
        certified_application = await asgi_request(
            app,
            "POST",
            "/api/v1/users/me/coach-applications",
            {
                "application_type": "certified",
                "display_name": "Certified Candidate",
                "real_name": "Li Coach",
                "certification_title": "ITF Level 1",
                "certification_file_path": "/storage/coach-applications/itf-level-1.pdf",
            },
            headers=rejected_headers,
        )
        assert certified_application.status == 200, certified_application
        certified_application_id = certified_application.json_body["application"]["coach_application_id"]

        rejected = await asgi_request(
            app,
            "POST",
            f"/api/v1/admin/coach-applications/{certified_application_id}/reject",
            {"rejection_reason": "资质证明信息不完整"},
            headers=admin_headers,
        )
        assert rejected.status == 200, rejected
        assert rejected.json_body["status"] == "rejected"

        rejected_identity = await asgi_request(
            app,
            "GET",
            "/api/v1/users/me/coach-identity",
            headers=rejected_headers,
        )
        assert rejected_identity.status == 200, rejected_identity
        assert rejected_identity.json_body["status"] == "review_rejected"
        assert rejected_identity.json_body["rejection_reason"] == "资质证明信息不完整"

        resubmitted = await asgi_request(
            app,
            "POST",
            "/api/v1/users/me/coach-applications",
            {
                "application_type": "certified",
                "display_name": "Certified Candidate",
                "real_name": "Li Coach",
                "certification_title": "ITF Level 1",
                "certification_file_path": "/storage/coach-applications/itf-level-1-new.pdf",
            },
            headers=rejected_headers,
        )
        assert resubmitted.status == 200, resubmitted
        assert resubmitted.json_body["identity"]["status"] == "pending_review"

        print("Coach API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())

