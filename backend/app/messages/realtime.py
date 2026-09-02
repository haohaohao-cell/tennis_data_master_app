"""Single-instance WebSocket wake-up transport for recipient sync events.

WebSocket is deliberately only a best-effort signal.  Clients fetch the
authoritative event stream through the Stage 11B REST sync endpoint after each
wake-up, so an unavailable or duplicate socket notification cannot change
message state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import socket
from typing import Any, Protocol

from fastapi import WebSocket

from backend.app.core.database import get_connection
from backend.app.core.config import settings
from backend.app.core.time import utc_now_iso


PROTOCOL_VERSION = 1
MAX_PENDING_ENVELOPES = 64
HEARTBEAT_TIMEOUT_SECONDS = 45
AUTHENTICATION_TIMEOUT_SECONDS = 10


@dataclass(eq=False)
class RealtimeConnection:
    user_id: str
    device_id: str
    socket: WebSocket
    queue: asyncio.Queue[dict[str, object]]


@dataclass(frozen=True)
class FanoutEnvelope:
    """Broker-safe contract: remote consumers re-read the authoritative sync event."""

    event_id: str
    recipient_user_id: str
    origin_instance_id: str
    emitted_at: str


class WakeupDispatcher(Protocol):
    """Optional post-commit fan-out boundary; implementations must never raise into writes."""

    def dispatch(self, envelope: FanoutEnvelope) -> None: ...


class ProcessLocalWakeupDispatcher:
    """Contract-only default. No broker or network transport is performed."""

    def dispatch(self, envelope: FanoutEnvelope) -> None:
        del envelope


def _instance_id() -> str:
    configured = (settings.instance_id or "").strip()
    if configured:
        return configured
    return f"local-{socket.gethostname()}-{os.getpid()}"


class RealtimeRegistry:
    """Bounded, process-local connection registry for the Stage 11D baseline."""

    def __init__(self, dispatcher: WakeupDispatcher | None = None, instance_id: str | None = None) -> None:
        self._by_user: dict[str, set[RealtimeConnection]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.instance_id = instance_id or _instance_id()
        self._dispatcher = dispatcher or ProcessLocalWakeupDispatcher()

    async def register(self, user_id: str, device_id: str, socket: WebSocket) -> RealtimeConnection:
        self._loop = asyncio.get_running_loop()
        connection = RealtimeConnection(
            user_id=user_id,
            device_id=device_id,
            socket=socket,
            queue=asyncio.Queue(maxsize=MAX_PENDING_ENVELOPES),
        )
        self._by_user.setdefault(user_id, set()).add(connection)
        return connection

    def unregister(self, connection: RealtimeConnection) -> None:
        connections = self._by_user.get(connection.user_id)
        if connections is None:
            return
        connections.discard(connection)
        if not connections:
            self._by_user.pop(connection.user_id, None)

    def active_connection_count(self) -> int:
        return sum(len(connections) for connections in self._by_user.values())

    def fanout_contract(self, event_id: str, user_id: str, emitted_at: str) -> FanoutEnvelope:
        return FanoutEnvelope(event_id, user_id, self.instance_id, emitted_at)

    def disconnect_device(self, user_id: str, device_id: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._disconnect_device_on_loop, user_id, device_id)

    def disconnect_user(self, user_id: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._disconnect_user_on_loop, user_id)

    def _disconnect_user_on_loop(self, user_id: str) -> None:
        for connection in tuple(self._by_user.get(user_id, ())):
            self.unregister(connection)
            asyncio.create_task(self._safe_close(connection.socket))

    @staticmethod
    async def _safe_close(socket: WebSocket) -> None:
        try:
            await socket.close(code=4403, reason="user data governance")
        except Exception:
            pass

    def _disconnect_device_on_loop(self, user_id: str, device_id: str) -> None:
        for connection in tuple(self._by_user.get(user_id, ())):
            if connection.device_id == device_id:
                self.unregister(connection)
                asyncio.create_task(connection.socket.close(code=4403, reason="messaging device revoked"))

    def publish_from_sync_event(self, event_id: str) -> None:
        """Schedule post-commit recipient wake-ups from an HTTP worker thread."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT recipient_user_id, event_id, event_type, conversation_id, message_seq, persisted_at
                FROM user_sync_events
                WHERE event_id = ?
                  AND event_type IN ('message.created', 'message.recalled', 'message.edited', 'message.reaction_changed', 'message.forwarded', 'conversation.read', 'conversation.members_changed');
                """,
                (event_id,),
            ).fetchall()
        loop = self._loop
        for row in rows:
            envelope: dict[str, object] = {
                "type": "sync.wake",
                "protocol_version": PROTOCOL_VERSION,
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "sync_required": True,
                "conversation_id": row["conversation_id"],
                "message_seq": row["message_seq"],
                "emitted_at": row["persisted_at"] or utc_now_iso(),
            }
            recipient_user_id = row["recipient_user_id"]
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self._enqueue_user, recipient_user_id, envelope)
            # This call happens after the database transaction and never
            # changes sync correctness: remote instances re-read by event_id.
            try:
                self._dispatcher.dispatch(
                    self.fanout_contract(row["event_id"], recipient_user_id, envelope["emitted_at"])
                )
            except Exception:
                # Broker adapters are intentionally best effort. REST sync is
                # the recovery path and failed dispatch must not affect writes.
                pass

    def _enqueue_user(self, user_id: str, envelope: dict[str, object]) -> None:
        for connection in tuple(self._by_user.get(user_id, ())):
            try:
                connection.queue.put_nowait(envelope)
            except asyncio.QueueFull:
                # Slow receivers must reconnect and use REST sync; retaining an
                # unbounded in-memory backlog would make one client a process risk.
                self.unregister(connection)
                asyncio.create_task(connection.socket.close(code=1013, reason="realtime backpressure"))

    async def shutdown(self) -> None:
        connections = [connection for group in self._by_user.values() for connection in group]
        self._by_user.clear()
        for connection in connections:
            try:
                await connection.socket.close(code=1001, reason="server shutdown")
            except Exception:
                pass


registry = RealtimeRegistry()


async def relay_connection(connection: RealtimeConnection) -> None:
    """Relay queue envelopes and client heartbeats until timeout or disconnect."""
    while True:
        receive_task = asyncio.create_task(connection.socket.receive_json())
        queue_task = asyncio.create_task(connection.queue.get())
        done, pending = await asyncio.wait(
            {receive_task, queue_task},
            timeout=HEARTBEAT_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if not done:
            await connection.socket.close(code=1001, reason="heartbeat timeout")
            return
        task = done.pop()
        value: Any = task.result()
        if task is queue_task:
            try:
                await connection.socket.send_json(value)
            except Exception:
                return
            continue
        if not isinstance(value, dict):
            await connection.socket.close(code=1003, reason="invalid realtime frame")
            return
        if value.get("type") == "ping":
            await connection.socket.send_json({"type": "pong", "emitted_at": utc_now_iso()})
            continue
        await connection.socket.close(code=1003, reason="unsupported realtime frame")
        return


def active_device_is_valid(user_id: str, device_id: str) -> bool:
    """Check device ownership without retaining a database connection for a socket."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1 FROM messaging_devices
            WHERE user_id = ? AND device_id = ? AND revoked_at IS NULL
            LIMIT 1;
            """,
            (user_id, device_id),
        ).fetchone()
    return row is not None
