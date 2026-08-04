# Demo Guide

1. Start the stack with Docker Compose.
2. Apply migrations if this is a fresh database:

```bash
docker compose run --rm -e PYTHONPATH=/app backend alembic upgrade head
```

3. Run the idempotent local demo bootstrap:

```bash
make demo
```

4. Log in as:

- Email: `admin@example.com`
- Password: `admin123`

5. Open Threat Queue, Automation Runs, Live AI Graph, Review Queue, ATT&CK Coverage, Detection Catalog, System Health, and Settings.
6. Request Changes to create a new immutable proposal revision.
7. Approve the current revision.
8. Confirm a deployment artifact appears with checksum metadata.

The local demo uses a MISP-shaped PowerShell encoded-command event and deterministic AI fixtures. It still exercises PostgreSQL, Redis, Celery, the backend graph runner, deterministic ATT&CK/coverage/telemetry checks, Sigma validation, and the review lifecycle.
