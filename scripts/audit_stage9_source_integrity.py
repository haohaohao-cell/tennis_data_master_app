"""Read-only audit of the SQLite migration source; never opens it for writes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def file_fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {"exists": True, "sha256": digest.hexdigest(), "size_bytes": stat.st_size, "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=root / "backend/db/tennis_data_master.sqlite3")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--expected-sha256",
        help="Approved SHA-256 for this migration source. Without it, the audit reports structure and fingerprint but does not claim approval.",
    )
    args = parser.parse_args()
    db = args.db.resolve()
    report_path = args.report or root / "backend/db" / f"stage9-source-integrity-review-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    files = {name: file_fingerprint(path) for name, path in (("main", db), ("wal", Path(f"{db}-wal")), ("shm", Path(f"{db}-shm")))}
    table_counts: dict[str, int] = {}
    if db.exists():
        with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
            for table in ("chat_messages", "chat_message_media", "chat_message_attachments", "outbox_events", "user_inbox_counters"):
                table_counts[table] = int(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0])
                if table_counts[table]:
                    table_counts[f"{table}.rows"] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            table_counts["tables"] = int(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0])
    current_sha256 = files["main"].get("sha256")
    expected_sha256 = args.expected_sha256.lower() if args.expected_sha256 else None
    if expected_sha256 and (len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256)):
        raise SystemExit("--expected-sha256 must be a 64-character lowercase or uppercase hexadecimal digest")
    integrity_status = (
        "verified" if expected_sha256 and current_sha256 == expected_sha256
        else "fingerprint_mismatch" if expected_sha256
        else "fingerprint_recorded_unverified"
    )
    report = {
        "stage": "stage9-r-source-integrity-review",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(db),
        "files": files,
        "table_counts": table_counts,
        "expected_sha256": expected_sha256,
        "fingerprint_status": integrity_status,
        "migration_source_allowed": integrity_status == "verified",
        "manual_confirmation_required": integrity_status != "verified",
        "main_file_modified_by_this_audit": False,
        "sidecar_state_change_explained": False,
        "notes": [
            "The audit records the source fingerprint and verifies it only when an approved expected digest is supplied.",
            "Read-only SQLite access can materialize WAL/SHM sidecars; their presence is reported and no sidecar cleanup was performed.",
            "No repair, VACUUM, checkpoint, import, delete, or overwrite was performed by this audit.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Source integrity report written: {report_path}")


if __name__ == "__main__":
    main()
