"""Temporary-SQLite WebSocket transport regression for the Stage 11D baseline."""

from __future__ import annotations

from pathlib import Path
import asyncio
import os
import sys
import tempfile
from typing import cast
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))


def _login(client: TestClient, phone: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/phone-login", json={"phone": phone, "code": "000000"})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]["user_id"]


def _scoped_dsn(source: str, schema: str) -> str:
    parts = urlsplit(source)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "options"]
    query.append(("options", f"-c search_path={schema},pg_catalog"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(f"{quote(key)}={quote(value)}" for key, value in query), parts.fragment))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_device(client: TestClient, token: str, device_id: str) -> None:
    response = client.post(
        "/api/v1/messages/devices",
        headers=_headers(token),
        json={"device_id": device_id, "platform": "unknown"},
    )
    assert response.status_code == 200, response.text


def _authenticate(socket, token: str, device_id: str) -> None:
    socket.send_json({"type": "authenticate", "access_token": token, "device_id": device_id})
    ready = socket.receive_json()
    assert ready["type"] == "ready" and ready["protocol_version"] == 1


def _expect_rejected(client: TestClient, frame: dict[str, str], code: int) -> None:
    try:
        with client.websocket_connect("/api/v1/messages/realtime") as socket:
            socket.send_json(frame)
            socket.receive_json()
    except WebSocketDisconnect as error:
        assert error.code == code
        return
    raise AssertionError("WebSocket authentication unexpectedly succeeded")


class _SlowSocket:
    def __init__(self) -> None:
        self.close_codes: list[int] = []
        self.sent: list[dict[str, object]] = []

    async def close(self, code: int, reason: str) -> None:
        del reason
        self.close_codes.append(code)

    async def receive_json(self):
        await asyncio.sleep(10)

    async def send_json(self, value: dict[str, object]) -> None:
        self.sent.append(value)


async def _verify_registry_limits() -> None:
    from backend.app.messages import realtime

    registry = realtime.RealtimeRegistry()
    slow_socket = _SlowSocket()
    connection = await registry.register("slow-user", "slow-device", cast(object, slow_socket))
    for _ in range(realtime.MAX_PENDING_ENVELOPES):
        connection.queue.put_nowait({"type": "sync.wake"})
    registry._enqueue_user("slow-user", {"type": "sync.wake"})
    await asyncio.sleep(0)
    assert slow_socket.close_codes == [1013]

    timeout_socket = _SlowSocket()
    timeout_connection = await registry.register("timeout-user", "timeout-device", cast(object, timeout_socket))
    original_timeout = realtime.HEARTBEAT_TIMEOUT_SECONDS
    realtime.HEARTBEAT_TIMEOUT_SECONDS = 0.001
    try:
        await realtime.relay_connection(timeout_connection)
    finally:
        realtime.HEARTBEAT_TIMEOUT_SECONDS = original_timeout
    assert timeout_socket.close_codes == [1001]


def main() -> None:
    schema, source = os.environ.get("STAGE11D_SCHEMA"), os.environ.get("TENNIS_DATABASE_URL")
    temporary_directory = tempfile.TemporaryDirectory(prefix="stage11d-") if not schema else None
    try:
        from backend.app.core import config

        if schema:
            if not source:
                raise SystemExit("TENNIS_DATABASE_URL is required with STAGE11D_SCHEMA")
            object.__setattr__(config.settings, "database_url", _scoped_dsn(source, schema))
        else:
            assert temporary_directory is not None
            object.__setattr__(config.settings, "database_url", None)
            object.__setattr__(config.settings, "database_path", Path(temporary_directory.name) / "fixture.sqlite3")
        from backend.app.main import app
        from backend.app.messages import realtime

        with TestClient(app) as client:
            alice_token, alice_id = _login(client, "13981100001")
            bob_token, bob_id = _login(client, "13981100002")
            carol_token, carol_id = _login(client, "13981100003")
            alice_device, bob_device, bob_second, carol_device = (
                "stage11d-alice-device",
                "stage11d-bob-device",
                "stage11d-bob-second",
                "stage11d-carol-device",
            )
            for token, device_id in (
                (alice_token, alice_device),
                (bob_token, bob_device),
                (bob_token, bob_second),
                (carol_token, carol_device),
            ):
                _register_device(client, token, device_id)

            group_response = client.post(
                "/api/v1/messages/groups",
                headers=_headers(alice_token),
                json={"title": "Stage 11D", "group_type": "custom", "member_user_ids": [bob_id]},
            )
            assert group_response.status_code == 201, group_response.text
            conversation_id = group_response.json()["conversation"]["conversation_id"]
            from backend.app.core.database import transaction
            from backend.app.messages import service

            with transaction(immediate=True) as connection:
                direct_conversation_id = service.ensure_direct_conversation_in_transaction(
                    connection,
                    alice_id,
                    bob_id,
                    require_direct_permission=False,
                )

            _expect_rejected(client, {"type": "authenticate", "device_id": alice_device}, 4401)
            _expect_rejected(client, {"type": "authenticate", "access_token": "invalid", "device_id": alice_device}, 4401)
            _expect_rejected(client, {"type": "authenticate", "access_token": bob_token, "device_id": alice_device}, 4403)

            with (
                client.websocket_connect("/api/v1/messages/realtime") as bob_socket,
                client.websocket_connect("/api/v1/messages/realtime") as bob_second_socket,
                client.websocket_connect("/api/v1/messages/realtime") as carol_socket,
            ):
                _authenticate(bob_socket, bob_token, bob_device)
                _authenticate(bob_second_socket, bob_token, bob_second)
                _authenticate(carol_socket, carol_token, carol_device)
                assert realtime.registry.active_connection_count() == 3
                carol_connections = realtime.registry._by_user[carol_id]
                assert all(connection.queue.empty() for connection in carol_connections)

                message = client.post(
                    f"/api/v1/messages/conversations/{conversation_id}/messages",
                    headers=_headers(alice_token),
                    json={"message_type": "text", "text_content": "private", "client_message_id": "stage11d-message"},
                )
                assert message.status_code == 201, message.text
                event_id = message.json()["event_id"]
                first, second = bob_socket.receive_json(), bob_second_socket.receive_json()
                assert {first["event_id"], second["event_id"]} == {event_id}
                assert all(item["event_type"] == "message.created" for item in (first, second))
                assert "private" not in str(first) and "private" not in str(second)
                assert all(connection.queue.empty() for connection in carol_connections)

                bob_socket.send_json({"type": "ping"})
                assert bob_socket.receive_json()["type"] == "pong"

                direct_message = client.post(
                    f"/api/v1/messages/conversations/{direct_conversation_id}/messages",
                    headers=_headers(alice_token),
                    json={"message_type": "text", "text_content": "recall", "client_message_id": "stage11d-recall"},
                )
                assert direct_message.status_code == 201, direct_message.text
                assert bob_socket.receive_json()["event_type"] == "message.created"
                recall = client.post(
                    f"/api/v1/messages/conversations/{direct_conversation_id}/messages/{direct_message.json()['message']['message_id']}/recall",
                    headers=_headers(alice_token),
                )
                assert recall.status_code == 200, recall.text
                assert bob_socket.receive_json()["event_type"] == "message.recalled"

                read = client.post(
                    f"/api/v1/messages/conversations/{conversation_id}/read",
                    headers=_headers(bob_token),
                    json={"through_message_seq": 1},
                )
                assert read.status_code == 200, read.text
                assert bob_socket.receive_json()["event_type"] == "conversation.read"

                # The REST sync log is still the recovery authority after wakes.
                sync = client.get(
                    f"/api/v1/messages/sync?device_id={bob_device}&limit=20",
                    headers=_headers(bob_token),
                )
                assert sync.status_code == 200 and {item["event_id"] for item in sync.json()["items"]} >= {event_id}

                # Explicit transaction rollback produces neither event row nor wake-up queue entry.
                original_append = service.sync_service.append_conversation_event
                service.sync_service.append_conversation_event = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rollback"))
                try:
                    failed = client.post(
                        f"/api/v1/messages/conversations/{conversation_id}/messages",
                        headers=_headers(alice_token),
                        json={"message_type": "text", "text_content": "rolled back", "client_message_id": "stage11d-rollback"},
                    )
                finally:
                    service.sync_service.append_conversation_event = original_append
                assert failed.status_code == 500
                assert all(connection.queue.empty() for connection in realtime.registry._by_user[bob_id])

                revoke = client.delete(f"/api/v1/messages/devices/{bob_second}", headers=_headers(bob_token))
                assert revoke.status_code == 200, revoke.text
            assert realtime.registry.active_connection_count() == 0
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()
    asyncio.run(_verify_registry_limits())
    print("Stage 11D WebSocket realtime test passed.")


if __name__ == "__main__":
    main()
