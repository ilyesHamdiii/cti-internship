# Running the project

This guide is written for a developer or reviewer who is seeing the project for the first time. It uses the repository as it exists in this snapshot and documents only commands and services that are actually configured.

## A. Prerequisites

### Required tools

- Git
- Docker
- Docker Compose
- Python 3.11 for backend tooling and CI parity
- Node.js 20 for frontend tooling and CI parity

### Operating system assumptions

This project is prepared for Linux-based container execution and is configured to run locally with Docker Desktop or a compatible Docker engine on Windows/macOS/Linux.

The repository is not written around a specific non-container execution model; the supported workflow is Docker Compose for application services.

### Versions enforced by the repository

- Backend Python: `>=3.11` in `backend/pyproject.toml`
- Frontend Node: CI uses `node-version: "20"` in `.github/workflows/*.yml`
- Backend Docker image: `python:3.11-slim`
- Frontend Docker image: `node:20-alpine`
- PostgreSQL: `postgres:16-alpine`
- Redis: `redis:7-alpine`
- MISP stack: official MISP Docker images with MariaDB and Valkey

## B. Clone and setup

```bash
git clone <repository-url>
cd <repository-name>
cp .env.example .env
```

Then edit `.env` with the values for your local environment.

## C. Environment variables

The repository uses the `.env.example` file as the source of environment variables. The stack also writes a CI `.env` file through `scripts/ci/write-ci-env.sh`.

### Core application variables

| Variable | Purpose | Required | Example value | Secret |
|---|---|---:|---|---|
| `CTI_ENVIRONMENT` | Runtime environment label | Yes | `local` | No |
| `CTI_DATABASE_URL` | PostgreSQL DSN for the backend | Yes | `postgresql+psycopg://cti:cti@postgres:5432/cti` | No |
| `CTI_REDIS_URL` | Redis URL for Celery broker and backend | Yes | `redis://redis:6379/0` | No |
| `CTI_JWT_SECRET` | JWT signing key for access/refresh tokens | Yes | `replace-with-a-long-random-secret` | Yes |
| `CTI_SEEDED_ADMIN_EMAIL` | Local seeded admin email | Yes | `admin@example.com` | No |
| `CTI_SEEDED_ADMIN_PASSWORD` | Local seeded admin password | Yes | `ChangeMe123!` | Yes |
| `CTI_AI_FIXTURE_MODE` | Enables deterministic fixture provider instead of live DeepSeek calls | Yes | `true` | No |
| `CTI_DEEPSEEK_API_KEY` | Live DeepSeek API key | No unless live AI is used | `DEEPSEEK_API_KEY=<your-key>` | Yes |
| `CTI_DEEPSEEK_MODEL` | DeepSeek model name | No | `deepseek-chat` | No |
| `CTI_MISP_URL` | Base URL for MISP API within Docker | Yes for MISP integration | `https://misp` | No |
| `CTI_MISP_API_KEY` | MISP authentication key | Yes for MISP integration | `MISP_AUTH_KEY=<your-misp-key>` | Yes |
| `CTI_MISP_VERIFY_TLS` | TLS verification for MISP | Yes for MISP integration | `false` | No |
| `CTI_MISP_POLL_INTERVAL_SECONDS` | Celery beat polling interval | Yes | `300` | No |
| `CTI_SIGMA_TARGET` | Target backend for Sigma compilation | Yes | `splunk` | No |
| `CTI_MAX_REPAIR_ATTEMPTS` | Maximum repair iterations | Yes | `3` | No |
| `CTI_REASONING_MAX_REVISIONS` | Maximum AI reasoning revisions | Yes | `3` | No |
| `CTI_REASONING_MIN_IMPROVEMENT_DELTA` | Minimum reasoning improvement required | Yes | `0.03` | No |
| `CTI_REASONING_CONFIDENCE_TARGET` | Confidence target used by reasoning logic | Yes | `0.82` | No |
| `CTI_REASONING_TRUST_TARGET` | Trust target used by reasoning logic | Yes | `0.88` | No |
| `CTI_QUALITY_THRESHOLD` | Minimum validation quality threshold | Yes | `75` | No |

### MISP variables

| Variable | Purpose | Required | Example value | Secret |
|---|---|---:|---|---|
| `MISP_BASE_URL` | Browser-facing MISP base URL | Yes only for MISP profile | `https://localhost:8443` | No |
| `MISP_CORE_HTTP_PORT` | MISP HTTP port | No | `8081` | No |
| `MISP_CORE_HTTPS_PORT` | MISP HTTPS port | No | `8443` | No |
| `MISP_ADMIN_EMAIL` | MISP admin account | Yes for MISP profile | `admin@admin.test` | No |
| `MISP_ADMIN_PASSWORD` | MISP admin password | Yes for MISP profile | `ChangeMeMisp123!` | Yes |
| `MISP_ADMIN_KEY` | MISP API key for admin user | Yes for integration | `MISP_AUTH_KEY=<your-misp-key>` | Yes |
| `MISP_ADMIN_ORG` | MISP org | Yes for MISP profile | `CTI Local` | No |
| `MISP_EMAIL` | MISP contact email | Yes for MISP profile | `misp@localhost` | No |
| `MISP_CONTACT` | MISP contact field | Yes for MISP profile | `misp@localhost` | No |
| `MISP_GPG_PASSPHRASE` | GPG passphrase for MISP | No | `replace-with-local-passphrase` | Yes |
| `MISP_MYSQL_USER` | MariaDB user | Yes for MISP profile | `misp` | No |
| `MISP_MYSQL_PASSWORD` | MariaDB password | Yes for MISP profile | `example` | Yes |
| `MISP_MYSQL_ROOT_PASSWORD` | MariaDB root password | Yes for MISP profile | `password` | Yes |
| `MISP_MYSQL_DATABASE` | MISP DB name | Yes for MISP profile | `misp` | No |
| `MISP_REDIS_PASSWORD` | Valkey password | Yes for MISP profile | `redispassword` | Yes |

> Never commit or expose real values. Use placeholders or local-only development secrets.

## D. Build and start

### Standard local stack

```bash
docker compose up --build
```

This starts:

- PostgreSQL
- Redis
- backend
- worker
- scheduler
- frontend
- nginx

The UI is served through nginx at:

```text
http://localhost:8080
```

### MISP-enabled stack

```bash
docker compose --profile misp up -d --build
```

This starts the official MISP deployment, plus the platform services required to talk to it.

The MISP web UI is available at:

```text
https://localhost:8443
```

## E. Database initialization

The backend service starts with an Alembic migration on boot:

```yaml
command:
  - sh
  - -c
  - PYTHONPATH=/app alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If you need to run migrations manually, use the same working directory and Python path:

```bash
docker compose exec backend sh -lc "PYTHONPATH=/app alembic upgrade head"
```

The repository also has a migration baseline script in CI and Docker validation workflows, which uses:

```bash
docker compose run --rm -e PYTHONPATH=/app backend bash -lc "alembic upgrade 0001_initial && alembic stamp head"
```

This is the migration pattern used by the project’s own GitHub Actions.

## F. Service verification

### Backend API

Check the health endpoint:

```bash
curl http://localhost:8080/api/v1/health
```

Expected response shape:

```json
{
  "status": "healthy",
  "checked_at": "...",
  "components": {
    "database": "healthy"
  }
}
```

### Frontend

Open the app in a browser:

```text
http://localhost:8080
```

The frontend is reverse-proxied by nginx and the backend is reachable at `/api/v1` through the same origin.

### PostgreSQL

```bash
docker compose exec postgres pg_isready -U cti -d cti
```

Expected: a successful readiness response.

### Redis

```bash
docker compose exec redis redis-cli ping
```

Expected:

```text
PONG
```

### MISP

With the `misp` profile enabled:

```text
https://localhost:8443
```

The repo also checks MISP health from inside the container with:

```bash
docker compose exec misp curl -ks https://localhost/users/heartbeat
```

### Celery

Check worker status:

```bash
docker compose exec worker celery -A app.workers.celery_app.celery_app inspect active
```

Check scheduler health:

```bash
docker compose logs scheduler
```

### Nginx

The reverse proxy is configured in `docker/nginx.conf` and exposed on port `8080`.

```bash
docker compose logs nginx
```

## G. Login and authentication

The backend seeds a local admin user from environment variables during startup.

Use the values from your `.env` file:

```text
CTI_SEEDED_ADMIN_EMAIL
CTI_SEEDED_ADMIN_PASSWORD
```

The API route is:

```text
POST /api/v1/auth/login
```

Example request:

```json
{
  "email": "admin@example.com",
  "password": "ChangeMe123!"
}
```

The frontend login form defaults to `admin@example.com` with a password field that is populated with `admin123`, but the authoritative local-user creation logic in the backend uses the seeded values from `.env`. For local developer setups, use the `.env` values rather than the hardcoded demo credentials in the UI.

## H. Running the workflow

Below is the supported workflow path in the current implementation.

1. Start services

```bash
docker compose --profile misp up -d --build
```

2. Open the platform

```text
http://localhost:8080
```

3. Ingest a MISP event

- open the MISP UI at `https://localhost:8443`
- create or import a CTI event
- use the platform MISP inbox or direct API ingestion route

4. Process CTI

Use the platform UI or API to trigger the graph execution.

5. Run workflow

```bash
docker compose exec -T backend python -m app.scripts.bootstrap_demo
```

or trigger the API route:

```text
POST /api/v1/cti-events/{event_id}/run-workflow
```

6. Observe LangGraph workflow

Open the AI workflow or graph run view in the UI.

The backend exposes:

```text
GET /api/v1/ai/workflow
GET /api/v1/graph-runs
GET /api/v1/graph-runs/{run_id}/timeline
```

7. Review ATT&CK mapping

The platform stores verified ATT&CK mappings in the `attack_mappings` and `attack_techniques` tables. Review them through the UI or API endpoints.

8. Review telemetry/coverage

The workflow produces `coverage_results` and `visibility_results`; the UI and API allow inspection of those results.

9. Generate detection

The backend generates a Sigma candidate only after the policy decision says `generate_candidate`.

10. Validate Sigma

The validation layer uses Pydantic and `SigmaValidationService` to confirm required fields and compile with the Splunk backend.

11. Compile to Splunk SPL

This is done inside `backend/app/services/sigma.py` using the `pysigma-backend-splunk` compiler.

12. Review proposal

The proposal workspace exposes:

```text
GET /api/v1/proposals/{proposal_id}/workspace
GET /api/v1/proposals/{proposal_id}/revisions
```

13. Approve/reject/request changes

Use the review endpoints:

```text
POST /api/v1/proposals/{proposal_id}/approve
POST /api/v1/proposals/{proposal_id}/request-changes
POST /api/v1/proposals/{proposal_id}/reject
```

14. View approved detection

Approved detections are stored in the detection catalog and exposed by:

```text
GET /api/v1/detections
GET /api/v1/detections/{detection_id}
```

## I. Testing

### Backend unit/script tests

The repository’s CI uses:

```bash
cd backend && pytest ../scripts/backend
```

The local Makefile contains:

```bash
make backend-test
```

but the actual script test directory in this repository is `scripts/backend`, and that is the path used by CI.

### Backend lint and types

```bash
cd backend && ruff check app ../scripts/backend && mypy app
```

### Frontend lint

```bash
cd frontend && npm run lint
```

### Frontend type check

```bash
cd frontend && npx tsc --noEmit
```

### Frontend build

```bash
cd frontend && npm run build
```

### Playwright E2E

```bash
npx playwright test tests/e2e --config=tests/e2e/playwright.config.ts
```

### DAST / ZAP

```bash
bash scripts/ci/run-zap-baseline.sh
```

### Docker validation

```bash
docker compose config
docker compose build
docker compose up -d postgres redis
docker compose up -d backend worker scheduler frontend nginx
```

## J. Troubleshooting

### Containers do not start

Check logs:

```bash
docker compose logs --no-color --tail=200 backend
```

Common causes:

- missing `.env`
- invalid DB/Redis connection strings
- MISP profile not enabled when MISP is required
- port conflicts on `8080`, `8443`, or `5432`

### Migrations fail

Run:

```bash
docker compose exec backend sh -lc "PYTHONPATH=/app alembic upgrade head"
```

If the migration script cannot find Alembic config or app package, ensure the working directory is `/app` and `PYTHONPATH=/app` is set.

### Database connection issue

Verify PostgreSQL is ready:

```bash
docker compose exec postgres pg_isready -U cti -d cti
```

Check the DSN in `.env` and verify it matches the compose service name `postgres`.

### Redis issue

```bash
docker compose exec redis redis-cli ping
```

If Redis is not reachable, confirm the container is healthy and the backend `CTI_REDIS_URL` matches the service name `redis`.

### MISP connectivity

- verify `CTI_MISP_URL` is set to `https://misp`
- verify `CTI_MISP_API_KEY` matches a valid MISP admin key
- verify `CTI_MISP_VERIFY_TLS=false` for local self-signed certs
- check `docker compose --profile misp ps`

### Missing environment variables

The application reads env vars via `pydantic-settings` with `CTI_` prefix. If the required variables are missing, the backend will use defaults but many integrations will be broken or not configured.

### AI provider unavailable

If `CTI_AI_FIXTURE_MODE=false` and `CTI_DEEPSEEK_API_KEY` is empty, the system will not have a live AI provider. This is expected. The project explicitly supports a fixture mode and the default `.env.example` uses `true`.

### Frontend/backend connection fails

Check that nginx is running at `:8080` and that backend health is available at `/api/v1/health`.

### Port conflicts

Common ports in this project:

- `8080` for nginx frontend proxy
- `8443` for MISP HTTPS
- `5432` for PostgreSQL (internal Docker service only)
- `6379` for Redis (internal Docker service only)

Use `docker compose ps` and `docker ps` to confirm which services own these ports.

## Final note

This repository is designed for local Dockerized development and CI validation. It is not a fully production-hardened deployment stack; it is a functional CTI detection engineering prototype with deterministic validation and human review controls.
