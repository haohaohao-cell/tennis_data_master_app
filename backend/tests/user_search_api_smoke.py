from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "user_search_api_smoke.sqlite3")

        from backend.app.core.database import initialize_database, transaction
        from backend.app.main import app

        initialize_database()

        alice_token, alice_id = await login_phone(app, "13700000001")
        bob_token, bob_id = await login_phone(app, "13700000002")
        private_token, private_id = await login_phone(app, "13700000003")
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        private_headers = {"authorization": f"Bearer {private_token}"}

        with transaction() as connection:
            connection.execute("UPDATE users SET nickname = 'Alice Baseline' WHERE user_id = ?;", (alice_id,))
            connection.execute("UPDATE users SET nickname = 'Bob Serve Partner' WHERE user_id = ?;", (bob_id,))
            connection.execute("UPDATE users SET nickname = 'Private Court' WHERE user_id = ?;", (private_id,))
            connection.execute(
                """
                INSERT INTO user_privacy_settings (user_id, show_profile_to_strangers)
                VALUES (?, 0);
                """,
                (private_id,),
            )

        anonymous = await asgi_request(app, "GET", "/api/v1/users/search?q=Bob")
        assert anonymous.status == 401, anonymous

        too_short = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=B",
            headers=alice_headers,
        )
        assert too_short.status == 400, too_short
        assert too_short.json_body["detail"]["code"] == "USER_SEARCH_QUERY_TOO_SHORT"

        nickname_search = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=Serve",
            headers=alice_headers,
        )
        assert nickname_search.status == 200, nickname_search
        assert nickname_search.json_body["items"][0]["user"]["user_id"] == bob_id
        assert nickname_search.json_body["items"][0]["match_type"] == "nickname"
        assert nickname_search.json_body["items"][0]["relationship"]["is_friend"] is False
        assert "phone" not in nickname_search.json_body["items"][0]["user"]
        assert "email" not in nickname_search.json_body["items"][0]["user"]

        id_search = await asgi_request(
            app,
            "GET",
            f"/api/v1/users/search?q={bob_id[:8]}",
            headers=alice_headers,
        )
        assert id_search.status == 200, id_search
        assert any(item["user"]["user_id"] == bob_id and item["match_type"] == "user_id" for item in id_search.json_body["items"])

        follow_bob = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{bob_id}",
            {"source": "friend_search"},
            headers=alice_headers,
        )
        assert follow_bob.status == 201, follow_bob

        followed_search = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=Serve",
            headers=alice_headers,
        )
        assert followed_search.status == 200, followed_search
        assert followed_search.json_body["items"][0]["relationship"]["is_following"] is True
        assert followed_search.json_body["items"][0]["relationship"]["is_friend"] is False

        follow_alice = await asgi_request(
            app,
            "POST",
            f"/api/v1/social/follows/{alice_id}",
            {"source": "friend_search"},
            headers=bob_headers,
        )
        assert follow_alice.status == 201, follow_alice

        friend_search = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=Serve",
            headers=alice_headers,
        )
        assert friend_search.status == 200, friend_search
        assert friend_search.json_body["items"][0]["relationship"]["is_friend"] is True

        private_hidden = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=Private",
            headers=alice_headers,
        )
        assert private_hidden.status == 200, private_hidden
        assert private_hidden.json_body["items"] == []

        private_self = await asgi_request(
            app,
            "GET",
            "/api/v1/users/search?q=Private",
            headers=private_headers,
        )
        assert private_self.status == 200, private_self
        assert private_self.json_body["items"][0]["is_self"] is True

        print("User search API smoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
