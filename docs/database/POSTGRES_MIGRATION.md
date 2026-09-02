# PostgreSQL Database Policy

PostgreSQL is the only database used by the project. Backend APIs, background
tasks, CV persistence, supported database tests, and local development use
PostgreSQL. The application has no embedded-file database fallback.

## Setup

Activate the project environment, install dependencies, configure the DSN, and
initialize both application schemas:

```powershell
conda activate tennis
pip install -r backend/requirements.txt
$env:TENNIS_DATABASE_HOST = "localhost"
$env:TENNIS_DATABASE_PORT = "5432"
$env:TENNIS_DATABASE_NAME = "tennis_data_master"
$env:TENNIS_DATABASE_URL = "postgresql://postgres@localhost:5432/tennis_data_master"
# Use your local PostgreSQL user/password as appropriate; do not commit the DSN.
python scripts/inspect_postgres_environment.py
python scripts/init_postgres_db.py
```

The backend uses the `public` schema and CV persistence uses the independent
`cv_analysis` schema. The generated definitions are checked in at
`backend/db/postgres_schema.sql` and `cv/db/postgres_schema.sql`.

## Runtime Rules

- `TENNIS_DATABASE_URL` is the canonical connection setting;
  `TENNIS_POSTGRES_DSN` remains a compatibility alias.
- A missing or invalid DSN must stop startup instead of creating a local
  database file.
- Schema changes must be additive, executable, repeatable, and reflected in the
  global data dictionary and every affected consumer.
- Tests that touch database behavior must use a dedicated database or an
  explicitly named isolated schema.
- PostgreSQL transaction, constraint, index, locking, and query behavior is the
  authority for correctness and performance evidence.

## Historical Data Import

The one-time, read-only historical import and validation procedure is
centralized in the repository-root `POSTGRES_MIGRATION_GUIDE.md`. Do not copy
its commands into other documents. Application runtime code must not open a
legacy database file.

## Validation And Reports

Run `scripts/inspect_postgres_environment.py` before initialization or schema
changes to confirm the intended host, port, database, user, active schema, and
permissions. Migration validation and query-performance reports are local
environment evidence; keep them out of version control and never include
passwords, complete DSNs, tokens, storage keys, or user content.

Database migration does not copy media files. Video originals, thumbnails,
message media, and CV output require separate backup and lifecycle management.
