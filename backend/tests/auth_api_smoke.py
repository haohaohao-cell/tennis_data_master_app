from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class AsgiResponse:
    status: int
    headers: dict[str, str]
    json_body: dict[str, Any]


async def asgi_request(
    app: Callable[..., Awaitable[None]],
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> AsgiResponse:
    body_bytes = b"" if body is None else json.dumps(body).encode("utf-8")
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    if body is not None:
        raw_headers.append((b"content-type", b"application/json"))
        raw_headers.append((b"content-length", str(len(body_bytes)).encode("latin-1")))

    parsed_path = urlsplit(path)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": parsed_path.path,
        "raw_path": parsed_path.path.encode("ascii"),
        "query_string": parsed_path.query.encode("ascii"),
        "headers": raw_headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    received = False
    response_status = 500
    response_headers: dict[str, str] = {}
    response_body = bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal response_status, response_headers
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in message.get("headers", [])
            }
        if message["type"] == "http.response.body":
            response_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    payload = json.loads(response_body.decode("utf-8")) if response_body else {}
    return AsgiResponse(status=response_status, headers=response_headers, json_body=payload)


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = os.path.join(temp_dir, "auth_api_smoke.sqlite3")

        from backend.app.core.database import initialize_database
        from backend.app.main import app

        initialize_database()

        send_code = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/verification-codes",
            {"phone": "138 0000 0000"},
        )
        assert send_code.status == 200, send_code
        assert send_code.json_body["success"] is True
        assert send_code.json_body["dev_code"] == "000000"

        invalid_login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "138 0000 0000", "code": "123456"},
        )
        assert invalid_login.status == 400, invalid_login
        assert invalid_login.json_body["detail"]["code"] == "INVALID_VERIFICATION_CODE"

        first_login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {
                "phone": "138 0000 0000",
                "code": "000000",
                "device": {"device_name": "API smoke", "platform": "test"},
            },
        )
        assert first_login.status == 200, first_login
        user_id = first_login.json_body["user"]["user_id"]
        assert first_login.json_body["user"]["phone"] == "13800000000"
        assert first_login.json_body["user"]["profile_completed"] is False

        second_login = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/phone-login",
            {"phone": "13800000000", "code": "000000"},
        )
        assert second_login.status == 200, second_login
        assert second_login.json_body["user"]["user_id"] == user_id

        access_token = first_login.json_body["access_token"]
        me = await asgi_request(
            app,
            "GET",
            "/api/v1/auth/me",
            headers={"authorization": f"Bearer {access_token}"},
        )
        assert me.status == 200, me
        assert me.json_body["user"]["user_id"] == user_id

        profile_update = await asgi_request(
            app,
            "PATCH",
            "/api/v1/users/me",
            {
                "nickname": "Court Builder",
                "playing_hand": "left",
            },
            headers={"authorization": f"Bearer {access_token}"},
        )
        assert profile_update.status == 200, profile_update
        assert profile_update.json_body["user"]["user_id"] == user_id
        assert profile_update.json_body["user"]["nickname"] == "Court Builder"
        assert profile_update.json_body["user"]["playing_hand"] == "left"
        assert profile_update.json_body["user"]["profile_completed"] is True

        refresh = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/refresh",
            {"refresh_token": first_login.json_body["refresh_token"]},
        )
        assert refresh.status == 200, refresh
        assert refresh.json_body["user"]["user_id"] == user_id
        assert refresh.json_body["access_token"] != access_token

        logout = await asgi_request(
            app,
            "POST",
            "/api/v1/auth/logout",
            headers={"authorization": f"Bearer {refresh.json_body['access_token']}"},
        )
        assert logout.status == 200, logout
        assert logout.json_body["success"] is True

        revoked_me = await asgi_request(
            app,
            "GET",
            "/api/v1/auth/me",
            headers={"authorization": f"Bearer {refresh.json_body['access_token']}"},
        )
        assert revoked_me.status == 401, revoked_me
        assert revoked_me.json_body["detail"]["code"] == "INVALID_ACCESS_TOKEN"

        print("Auth API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
