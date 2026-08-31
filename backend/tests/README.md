# Backend Tests

The backend runtime is PostgreSQL-only. These smoke and API scripts must be
run with `TENNIS_DATABASE_URL` (or `TENNIS_POSTGRES_DSN`) configured and an
initialized PostgreSQL schema. `TENNIS_DB_PATH` is retained only by the
legacy SQLite migration tools and is ignored by the application.

The scripts that still describe themselves as SQLite-only are historical
performance baselines, not runtime regression gates:

- `message_outbox_performance.py`
- `message_performance_baseline.py`
- `message_query_benchmark.py`

Do not run those baselines against the PostgreSQL application until they are
ported to PostgreSQL fixtures. Use `message_outbox_postgres_final.py` for the
current PostgreSQL outbox gate.

For repeatable API tests, use a dedicated PostgreSQL database or schema per
run and reset it before execution. The test scripts intentionally keep their
original entry-point style so they can be migrated incrementally without
changing application code.
