from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or reset a local development admin account."
    )
    parser.add_argument("--username", default="li", help="Admin username.")
    parser.add_argument("--password", required=True, help="Initial admin password.")
    parser.add_argument(
        "--role",
        default="owner",
        choices=("owner", "admin", "operator", "viewer"),
        help="Admin role.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from backend.app.admin.service import ensure_test_admin_account
    from backend.app.core.database import initialize_database

    initialize_database()
    user_id = ensure_test_admin_account(args.username, args.password, args.role)
    print(f"Test admin account is ready: username={args.username} user_id={user_id}")


if __name__ == "__main__":
    main()
