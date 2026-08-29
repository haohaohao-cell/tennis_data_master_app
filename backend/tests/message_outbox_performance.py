"""SQLite-only local latency baseline on an isolated temporary database.

The script records measurements for diagnosis only; it intentionally has no
machine-dependent latency assertion and is not a CI performance gate.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.tests.activity_detail_api_smoke import login_phone
from backend.tests.auth_api_smoke import asgi_request


def percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "p99_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))], 3),
        "max_ms": round(max(ordered), 3),
    }


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ.pop("TENNIS_DATABASE_URL", None)
        os.environ.pop("TENNIS_POSTGRES_DSN", None)
        os.environ["TENNIS_DB_PATH"] = str(Path(temp_dir) / "stage9-performance.sqlite3")
        from backend.app.core.database import initialize_database
        from backend.app.main import app
        from backend.app.messages import outbox

        initialize_database()
        (alice_token, alice_id), (bob_token, bob_id) = [
            await login_phone(app, phone) for phone in ("13990000011", "13990000012")
        ]
        alice_headers = {"authorization": f"Bearer {alice_token}"}
        bob_headers = {"authorization": f"Bearer {bob_token}"}
        for target_id, headers in ((bob_id, alice_headers), (alice_id, bob_headers)):
            response = await asgi_request(app, "POST", f"/api/v1/social/follows/{target_id}", {"source": "stage9-performance"}, headers=headers)
            assert response.status == 201, response
        response = await asgi_request(app, "POST", "/api/v1/messages/direct-conversations", {"target_user_id": bob_id}, headers=alice_headers)
        assert response.status == 201, response
        conversation_id = response.json_body["conversation"]["conversation_id"]

        timings: dict[str, list[float]] = {"message_plus_outbox_write": [], "event_read": [], "event_lease": [], "client_recovery": []}
        for index in range(20):
            client_id = f"stage9-performance-{index}"
            started = time.perf_counter()
            response = await asgi_request(app, "POST", f"/api/v1/messages/conversations/{conversation_id}/messages", {"message_type": "text", "text_content": f"perf {index}", "client_message_id": client_id}, headers=alice_headers)
            timings["message_plus_outbox_write"].append((time.perf_counter() - started) * 1000)
            assert response.status == 201, response
            event_id = response.json_body["event_id"]

            started = time.perf_counter()
            events = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/events?limit=100", headers=bob_headers)
            timings["event_read"].append((time.perf_counter() - started) * 1000)
            assert events.status == 200, events

            started = time.perf_counter()
            leased = outbox.lease_events(f"stage9-performance-{index}", limit=1)
            timings["event_lease"].append((time.perf_counter() - started) * 1000)
            assert len(leased) == 1 and leased[0].event_id == event_id
            assert outbox.acknowledge_event(event_id, f"stage9-performance-{index}") is True

            started = time.perf_counter()
            recovered = await asgi_request(app, "GET", f"/api/v1/messages/conversations/{conversation_id}/messages/by-client-id/{client_id}", headers=alice_headers)
            timings["client_recovery"].append((time.perf_counter() - started) * 1000)
            assert recovered.status == 200 and recovered.json_body["found"] is True, recovered

        report = {
            "report_type": "local_message_outbox_performance_baseline",
            "run_at_utc": datetime.now(timezone.utc).isoformat(),
            "database_type": "SQLite",
            "isolated_temporary_database": True,
            "samples_per_operation": 20,
            "operations": {name: percentiles(values) for name, values in timings.items()},
            "errors": 0,
            "timeouts": 0,
            "production_capacity_claim": False,
            "ci_latency_gate": False,
        }
        report_path = os.getenv("TENNIS_PERFORMANCE_REPORT")
        if report_path:
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("SQLite message-outbox performance baseline collected.")


if __name__ == "__main__":
    asyncio.run(main())
