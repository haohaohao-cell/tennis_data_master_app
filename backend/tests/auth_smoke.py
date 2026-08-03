from __future__ import annotations

import os
import tempfile

from fastapi import HTTPException


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = os.path.join(temp_dir, "auth_smoke.sqlite3")

        from backend.app.auth.service import (
            authenticate_access_token,
            login_with_phone_code,
            logout_session,
            refresh_tokens,
            send_phone_verification_code,
        )
        from backend.app.core.database import initialize_database

        initialize_database()

        phone = "138 0000 0000"
        send_phone_verification_code(phone)

        first_login = login_with_phone_code(phone, "000000", None, "127.0.0.1", "auth-smoke")
        first_session = authenticate_access_token(first_login.access_token)

        second_login = login_with_phone_code("13800000000", "000000", None, None, None)
        assert first_login.user.user_id == second_login.user.user_id

        refreshed = refresh_tokens(first_login.refresh_token, None, None, None)
        refreshed_session = authenticate_access_token(refreshed.access_token)
        assert refreshed.user.user_id == first_login.user.user_id

        logout_session(refreshed_session.session_id)
        try:
            authenticate_access_token(refreshed.access_token)
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("Logout should revoke the active session.")

        assert first_session.user.user_id == first_login.user.user_id
        print("Auth smoke test passed.")


if __name__ == "__main__":
    main()
