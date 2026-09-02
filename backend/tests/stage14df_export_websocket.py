"""Isolated Stage 14D-F checks; uses a temporary SQLite database when API tests are added."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.messages.realtime import RealtimeRegistry


class FakeSocket:
    def __init__(self):
        self.closed = []

    async def close(self, **kwargs):
        self.closed.append(kwargs)


async def _registry_checks():
    registry = RealtimeRegistry()
    a1, a2, b1 = FakeSocket(), FakeSocket(), FakeSocket()
    await registry.register("user-a", "device-a1", a1)
    await registry.register("user-a", "device-a2", a2)
    await registry.register("user-b", "device-b1", b1)
    registry.disconnect_user("user-a")
    await asyncio.sleep(0.01)
    assert registry.active_connection_count() == 1
    assert len(a1.closed) == len(a2.closed) == 1
    assert not b1.closed
    registry.disconnect_user("user-a")
    await asyncio.sleep(0.01)
    assert registry.active_connection_count() == 1


def test_user_level_cleanup_isolated_and_idempotent():
    asyncio.run(_registry_checks())


if __name__ == "__main__":
    test_user_level_cleanup_isolated_and_idempotent()
    print("stage14df_export_websocket: PASS")
