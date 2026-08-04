# Official MISP Docker Integration

This project uses the official `MISP/misp-docker` images for local MISP:

- `ghcr.io/misp/misp-docker/misp-core`
- `ghcr.io/misp/misp-docker/misp-modules`
- `mariadb:10.11`
- `valkey/valkey:7.2`
- `ghcr.io/egos-tech/smtp`

MISP services run on the dedicated `misp_internal` Docker network. Platform
`backend`, `worker`, and `scheduler` are attached to that network only so they
can call the MISP API by service hostname.

## Start MISP

```bash
docker compose --profile misp up -d --build
```

MISP startup can take several minutes on the first run because the database and
application configuration are initialized.

Check status:

```bash
docker compose --profile misp ps
```

The MISP web interface is exposed at:

```text
https://localhost:8443
```

The container uses a local/self-signed certificate. Your browser may require you
to accept the local certificate warning.

## Initial Login

Local credentials are controlled by `.env`:

```text
MISP_ADMIN_EMAIL=admin@admin.test
MISP_ADMIN_PASSWORD=admin
```

Open `https://localhost:8443` and log in with those values.

## Create An Authentication Key

The local Compose file can seed an admin key through:

```text
MISP_ADMIN_KEY=UPyXcj1Qk7mbviwxdUIGTmqv7PcNr9UokEtVU2SJ
```

To create or rotate a key from the MISP UI:

1. Log in to `https://localhost:8443`.
2. Open the user menu.
3. Go to `Auth keys`.
4. Create a new authentication key for the admin user.
5. Copy the key value immediately.

Put that key in the platform `.env`:

```text
CTI_MISP_URL=https://misp
CTI_MISP_API_KEY=<copied-misp-auth-key>
CTI_MISP_VERIFY_TLS=false
```

`https://misp` is the Docker service hostname used by backend, worker, and
scheduler from inside Docker. Use `https://localhost:8443` only from the host
browser or host-side scripts.

Restart platform services after changing `.env`:

```bash
docker compose --profile misp up -d --force-recreate backend worker scheduler nginx
```

## Create A Test Event In MISP

1. Log in to MISP.
2. Open `Event Actions`.
3. Choose `Add Event`.
4. Use an event title such as `CTI Platform E2E PowerShell Test`.
5. Set distribution, threat level, and analysis values appropriate for local
   testing.
6. Add at least one attribute, for example:
   - Type: `text`
   - Category: `External analysis`
   - Value: `PowerShell downloads and executes remote content with encoded command arguments.`
7. Add an optional network indicator such as `ip-dst=203.0.113.44`.
8. Save the event.

Publishing is not required for the local poller; the poller searches events via
the authenticated MISP API.

## Verify Scheduler Ingestion

The scheduler enqueues `app.workers.tasks.poll_misp` every
`CTI_MISP_POLL_INTERVAL_SECONDS`.

The Threat Queue also provides a UI control for scheduling MISP ingestion:

```text
http://localhost:8080/threats
```

Open `Scheduled MISP Ingestion`, choose a mode, and click `Save Schedule`.

Supported modes:

- `Disabled`: Celery Beat wakes up, but the poll task skips ingestion.
- `Default interval`: use `CTI_MISP_POLL_INTERVAL_SECONDS`.
- `Hourly`: poll once per hour.
- `Daily at time`: poll every day at the selected local time.
- `Weekly at time`: poll every selected weekday at the selected local time.
- `Specific date/time`: poll once at the selected date and time, then disable the schedule.

The button calls the backend schedule API:

```text
GET  /api/v1/misp/ingestion-schedule
POST /api/v1/misp/ingestion-schedule
```

The schedule is stored in the `settings` table under:

```text
misp_ingestion_schedule
```

Celery Beat and the worker must still be running. The UI schedule controls when
the existing poll task is allowed to ingest; it does not replace the scheduler
container.

To trigger polling immediately:

```bash
docker compose exec -T worker celery -A app.workers.celery_app.celery_app call app.workers.tasks.poll_misp
```

Then open the platform:

```text
http://localhost:8080/threats
```

Confirm the event appears in the MISP Inbox section. Use these controls when
you want to exercise the path manually instead of waiting for the scheduler:

1. Select the MISP event.
2. Click `Ingest Selected`.
3. Confirm it appears in `Ingested CTI Events`.
4. Click `Run Detection Workflow`.
5. Open `Live AI Graph` and confirm a graph run exists.
6. Open `Review Workspace` and inspect the generated Sigma YAML and compiled
   query.
7. Approve the proposal and confirm a generated entry appears in `Detection
   Catalog`.

You can also run the API-only end-to-end helper:

```bash
docker compose exec -T backend python -m app.scripts.misp_e2e
```

This helper creates a real MISP event through `/events/add`, calls the existing
MISP poller, and verifies that a CTI event, workflow, and graph run exist. It
does not insert CTI directly into PostgreSQL.

## System Health

The System Health page reports `misp_api` with these statuses:

- `not_configured`: missing `CTI_MISP_URL` or `CTI_MISP_API_KEY`
- `unreachable`: MISP cannot be reached or returns an unexpected server error
- `authentication_failed`: MISP is reachable but the API key is rejected
- `authenticated`: API authentication works, but no polling state exists yet
- `healthy`: MISP is reachable, authenticated, and a poll state has been persisted

The details include:

- `configured`
- `reachable`
- `authenticated`
- `polling_successful`
- `url`
- `verify_tls`
- `last_poll_at`
- `last_event_id`
