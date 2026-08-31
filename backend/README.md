# Backend API

This backend provides the API surface for the tennis data master app.

## Development

Use the project Conda environment before running backend commands:

```bash
conda activate tennis
```

The backend requires PostgreSQL. Set `TENNIS_DATABASE_URL` (or the compatibility
alias `TENNIS_POSTGRES_DSN`) before starting the API; there is no SQLite runtime
fallback. Run `python scripts/init_postgres_db.py` once to create both the
backend schema and the CV `cv_analysis` schema.

Start the local API server:

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

The authentication module currently supports development phone login with a fixed verification code:

```text
000000
```

The account model is structured for production expansion: users are internal app accounts, identities store login providers, and sessions store server-managed tokens.

## Admin API

The admin API is part of this same backend service and is mounted under:

```text
/api/v1/admin
```

Admin endpoints use the existing Bearer access token for authentication, then check the `admin_users` table for an active authorization row. User-facing routes and admin routes must remain separate in router prefix, permission checks, and service entry points.

Admin Web can sign in through:

```text
POST /api/v1/admin/auth/login
```

Local development can create or reset the test admin account with:

```bash
python scripts/seed_test_admin.py --username li --password 0000
```

The test password is stored as a PBKDF2 hash in `admin_credentials`; the backend does not expose an unauthenticated endpoint for creating admin permissions.
