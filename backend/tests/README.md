# Backend Tests

The backend runtime and database test authority are PostgreSQL-only. Smoke and
API scripts that exercise database behavior must use `TENNIS_DATABASE_URL` (or
`TENNIS_POSTGRES_DSN`) and an initialized, isolated PostgreSQL schema. Retained
tests that allocate a legacy local fixture are historical compatibility
evidence, not current runtime regression gates.

The following scripts are historical performance baselines:

- `message_outbox_performance.py`
- `message_performance_baseline.py`
- `message_query_benchmark.py`

Do not treat those baselines as current PostgreSQL evidence until they use
isolated PostgreSQL fixtures. Use `message_outbox_postgres_final.py` for the
current outbox gate.

For repeatable API tests, use a dedicated PostgreSQL database or schema per
run and reset it before execution. The test scripts intentionally keep their
original entry-point style so they can be migrated incrementally without
changing application code.
