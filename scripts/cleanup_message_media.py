"""Scan or explicitly clean the isolated message-media storage root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.messages.media_cleanup import cleanup_message_media


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean message-image media files; defaults to dry-run.")
    parser.add_argument("--execute", action="store_true", help="Delete only reported safe candidates.")
    parser.add_argument("--grace-hours", type=int, default=24)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = cleanup_message_media(dry_run=not args.execute, grace_hours=args.grace_hours)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
