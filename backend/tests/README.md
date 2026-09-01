# Backend Tests

The backend runtime is PostgreSQL-only. Smoke and API scripts that exercise
runtime behavior should use `TENNIS_DATABASE_URL` (or `TENNIS_POSTGRES_DSN`)
and an initialized PostgreSQL schema. The retained Stage regression scripts
that run a temporary SQLite fixture explicitly call
`initialize_sqlite_database()`; that process-local test mode never changes
the runtime default.

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
