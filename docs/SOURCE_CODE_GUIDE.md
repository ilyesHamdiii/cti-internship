# Source Code Guide

This guide explains the repository as it exists in this project snapshot. It is intended for a supervisor, reviewer, or maintainer who needs to understand where the code lives, what each layer does, and how the CTI-to-detection workflow is implemented.

## 1. Project overview

This repository implements an AI-assisted CTI detection-engineering platform for a local SOC workflow.

The platform:

- ingests MISP events through the MISP API
- normalizes event data into a local PostgreSQL model
- extracts behavior candidates from the CTI
- validates ATT&CK mappings against a local ATT&CK reference set
- checks telemetry visibility and catalog coverage
- decides whether a new detection should be generated or whether the event is already covered
- uses AI to propose a Sigma rule
- validates the rule with Sigma schema checks and pySigma compilation to Splunk SPL
- applies a bounded repair loop if validation fails
- queues the result for human analyst review
- publishes a validated detection catalog entry after approval

The platform is intentionally review-gated: AI proposes; deterministic services validate; a human approves or rejects.

## 2. Architecture overview

The project has three main operational layers:

1. Frontend UI
   - Next.js application served through nginx
   - displays dashboards, workflows, proposals, reviews, detections, MISP queues, and AI reasoning sessions

2. Backend API and graph engine
   - FastAPI API with JWT-based auth
   - SQLAlchemy models against PostgreSQL
   - LangGraph workflow orchestrates the detection lifecycle
   - Celery workers execute background graph runs and MISP polling

3. Supporting services
   - Redis for Celery broker/backend
   - PostgreSQL for all durable app state
   - MISP official Docker deployment as CTI source
   - AI provider abstraction for DeepSeek fixture or live mode

## 3. Repository tree

```text
.
├── .env.example
├── .github/
│   └── workflows/
├── backend/
│   ├── alembic/
│   ├── app/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── alembic.ini
├── docker/
│   └── nginx.conf
├── docs/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── Dockerfile
│   ├── next.config.mjs
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── scripts/
│   ├── backend/
│   └── ci/
├── tests/
│   ├── e2e/
│   └── integration/
├── docker-compose.yml
├── Makefile
├── README.md
├── sonar-project.properties
├── artifacts/
└── visual_audit_mockup1_20260806-150059/
```

## 4. Backend modules and responsibilities

### backend/app/main.py
- What it does: creates the FastAPI application, sets CORS, starts baseline seeding, includes routers.
- Why it exists: central application factory and entry point.
- Calls: `app.api.auth`, `app.api.routes`, `seed_baseline`.
- Calls it: `uvicorn app.main:app`.
- Inputs/outputs: HTTP app instance; startup seeding of baseline data.

### backend/app/core/config.py
- What it does: defines environment-driven `Settings` using `pydantic-settings`.
- Why it exists: centralizes config for database URL, Redis, JWT secret, AI provider, MISP API, Sigma target, and workflow thresholds.
- Calls: none directly. Used by all services and workers.
- Inputs/outputs: environment variables prefixed with `CTI_`.

### backend/app/core/security.py
- What it does: JWT creation and validation, password hashing and verification.
- Why it exists: authenticates app users and authorizes protected API routes.
- Calls: `passlib` and `python-jose` helpers.
- Inputs/outputs: token payloads, hashed passwords, password verification results.

### backend/app/db/session.py
- What it does: builds the SQLAlchemy session factory.
- Why it exists: shared database access for FastAPI dependency injection and background tasks.
- Calls: `create_engine` and `sessionmaker`.
- Inputs/outputs: `Session` instances bound to the configured database URL.

### backend/app/db/base.py
- What it does: defines the SQLAlchemy declarative base.
- Why it exists: common parent for all ORM models.
- Calls: none.
- Inputs/outputs: metadata registry for Alembic and model creation.

### backend/app/api/auth.py
- What it does: exposes `/auth/login`, `/auth/refresh`, and `/auth/me`.
- Why it exists: user access and token acquisition.
- Calls: `current_user`, `refresh_user`, `create_token`, `verify_password`.
- Inputs/outputs: email/password -> JWT pair, user identity response.

### backend/app/api/deps.py
- What it does: validates bearer tokens and enforces role checks.
- Why it exists: protects routes requiring admin or analyst permissions.
- Calls: `decode_token`, `get_db`, `User` records.
- Inputs/outputs: parsed token -> user object or 401/403 rejection.

### backend/app/api/routes.py
- What it does: main REST API for dashboards, CTI events, MISP, graph runs, AI sessions, proposals, detections, telemetry, deployment artifacts, and settings.
- Why it exists: central operational interface for the platform.
- Calls: graph runner, MISP services, reasoner, Sigma validation, deployment services, DB queries.
- Inputs/outputs: designed around database entities and review actions.

### backend/app/models/models.py
- What it does: defines the PostgreSQL schema for CTI events, workflows, graph runs, behaviors, ATT&CK mappings, proposals, validations, deployment artifacts, and telemetry sources.
- Why it exists: durable state model for the detection lifecycle.
- Calls: none; it is the ORM layer.
- Inputs/outputs: database rows and JSONB payloads.

### backend/app/models/enums.py
- What it does: defines lifecycle status enums for CTI, workflow, graph nodes, review states, coverage, visibility, and detection type.
- Why it exists: consistent status semantics across API and graph logic.
- Calls: none.
- Inputs/outputs: enum values used in DB and route logic.

### backend/app/services/
This folder contains the deterministic and provider services that are called by the graph and API.

- `misp.py`: MISP API access, normalization, ingestion, polling, and schedule control
- `attack.py`: ATT&CK verification against the local reference dataset
- `coverage.py`: detection coverage checks against the catalog
- `telemetry.py`: telemetry availability checks for required fields/sources
- `policy.py`: routing policy decisions (`already_covered`, `visibility_gap`, etc.)
- `sigma.py`: Sigma schema validation and pySigma compilation to Splunk
- `reasoning.py`: AI watcher engine, confidence scoring, trust scoring, and session memory summarization
- `deployment.py`: writes Sigma YAML artifacts and publishes approved detections to `detection_catalog`
- `duplicates.py`: duplicate detection by fingerprint and compiled query similarity
- `fingerprinting.py`: behavior fingerprint generation for coverage and duplicates
- `bootstrap.py`: seeds the admin account and ATT&CK/telemetry catalog baseline
- `ai.py`: provider abstraction and DeepSeek implementation

## 5. Frontend modules and responsibilities

The frontend lives under `frontend/app` and `frontend/components`.

### App structure
- `app/page.tsx`: entry page
- `app/login/page.tsx`: login form
- `app/dashboard/`: dashboard and summary views
- `app/detections/`: detection catalog screens
- `app/graph/`: workflow graph and execution views
- `app/ai/`: reasoning dashboard and AI workflow page
- `app/ai-workflow/`: workflow visualizations
- `app/proposals/`: proposal and review workspace
- `app/reviews/`: review workspace and actions
- `app/health/`: system health and service checks
- `app/threats/`: MISP event queue and ingestion controls
- `app/settings/`: settings and configuration views
- `app/telemetry/`: telemetry sources
- `app/attack/`: ATT&CK coverage views
- `app/runs/`: graph-run timelines

### frontend/lib/api.ts
- What it does: wraps HTTP calls to `/api/v1` and reads the JWT from `localStorage`.
- Why it exists: frontend API access with bearer-token auth.
- Calls: fetch API for GET/POST/PATCH operations
- Inputs/outputs: JSON payloads or download blobs.

### UI behavior
The frontend is mainly a monitoring and analyst review UI. It does not implement security decisions itself: it reads the backend state and allows approval, request-changes, and rejection actions.

## 6. Database and migrations

### Database engine
- PostgreSQL is the authoritative store.
- The backend config uses `CTI_DATABASE_URL` and defaults to `postgresql+psycopg://cti:cti@postgres:5432/cti` in compose.

### Migrations
- Alembic migration files are in `backend/alembic/versions`.
- The base migration is `0001_initial.py`, which creates the schema using `Base.metadata.create_all`.
- Later migrations add AI reasoning and policy metadata and compliance/audit fields.

### Important database objects
The major tables include:

- `users`
- `cti_events`
- `workflows`
- `graph_runs`
- `graph_node_runs`
- `ai_interactions`
- `ai_reasoning_sessions`
- `ai_reasoning_revisions`
- `ai_watcher_results`
- `ai_confidence_events`
- `behaviors`
- `attack_techniques`
- `attack_mappings`
- `coverage_results`
- `visibility_results`
- `policy_decisions`
- `proposals`
- `proposal_revisions`
- `validation_results`
- `review_actions`
- `detection_catalog`
- `telemetry_sources`
- `deployment_artifacts`
- `settings`

These tables are not just metadata; they track the full lifecycle through ingestion, graph execution, review, approval, and deployment artifact generation.

## 7. AI/LangGraph components

### backend/app/graph/runner.py
- What it does: defines the actual LangGraph state machine.
- Why it exists: the platform’s decision engine for CTI consumption through validation/review/deployment.
- Calls: AI provider, ATT&CK verification, coverage, visibility, duplicate, policy, Sigma validation, deployment.
- Inputs: `workflow_id`, optional resume nodes, proposal id, analyst comment.
- Outputs: graph run object and workflow state updates.

### Key graph flow
The graph executes in this logical order:

`consume_cti -> extract_behaviors -> verify_attack_mapping -> coverage_analysis -> visibility_analysis -> policy_decision -> generate_candidate -> validate_candidate -> repair_candidate -> queue_review -> approved -> deployment`

There are terminal states for covered, visibility gap, insufficient evidence, failed, and rejected outcomes.

### State and auditing
The graph persists:

- `GraphRun`
- `GraphNodeRun`
- `AiInteraction`
- `AiReasoningSession`
- `AiReasoningRevision`
- `AiWatcherResult`
- `AiConfidenceEvent`

This is important because the platform treats AI as a traceable reasoning component rather than an autonomous decision-maker.

## 8. MISP integration

### backend/app/services/misp.py
- What it does: wraps the MISP API, fetches events, normalizes them, records ingest state, and polls for new events.
- Why it exists: keeps CTI acquisition external to the platform data store.
- Calls: PyMISP client; `MispIngestionService`; Celery task scheduler.
- Inputs: MISP API key, URL, TLS mode, event metadata.
- Outputs: normalized CTI payloads and ingested event/workflow records.

### MISP data flow
- MISP event is fetched from MISP API
- MISP event is normalized into local `cti_events` and a `workflow`
- the workflow triggers a graph run
- behavior extraction and detection generation follow

The project includes a profile `misp` in `docker-compose.yml` for the official MISP Docker stack.

## 9. ATT&CK / telemetry / policy services

### backend/app/services/attack.py
- Verifies ATT&CK IDs and tactics against the local mapped dataset.
- Prevents invalid or stale mappings before generation proceeds.

### backend/app/services/telemetry.py
- Checks whether the required telemetry fields and sources exist in the telemetry inventory.
- Determines `visible`, `partial`, or `gap` visibility statuses.

### backend/app/services/policy.py
- Uses evidence-sufficiency, confidence, coverage status, and telemetry status to decide whether the workflow should generate a detection or stop.

These are deterministic guardrails; they are not optional AI judgments.

## 10. Sigma and pySigma pipeline

### backend/app/services/sigma.py
- What it does: validates Sigma schema, required fields, ATT&CK tags, and compiles to Splunk backend via `pysigma-backend-splunk`.
- Why it exists: makes Sigma generation deterministic and machine-checkable before proposal review.
- Calls: `sigma.collection.SigmaCollection`, `SigmaCandidate`, and the Splunk backend module.
- Inputs: Sigma candidate JSON
- Outputs: validation result, warnings, generated Splunk query, quality score

### Operation model
- AI generates candidate Sigma
- deterministic validation checks structure and required fields
- the query is compiled to Splunk SPL
- duplicate detection and coverage checks happen before approval
- a human analyst reviews the generated rule and approves or changes it

## 11. Celery/Redis

### backend/app/workers/celery_app.py
- What it does: creates the Celery app and configures broker/backend from Redis.
- Why it exists: schedule and execute asynchronous tasks.
- Calls: included task module `app.workers.tasks`.
- Inputs: Redis URL from settings.
- Outputs: task dispatch for graph and polling work.

### backend/app/workers/tasks.py
- `run_graph`: executes a graph run for a workflow.
- `poll_misp`: fetches new MISP events on a schedule.

Redis is used as both:

- Celery broker
- Celery result backend

## 12. Authentication

Authentication is implemented with JWT and bearer tokens.

- `backend/app/api/auth.py` issues access and refresh tokens.
- `backend/app/api/deps.py` validates them and enforces role checks.
- User roles are defined in `backend/app/models/enums.py` as `Admin` and `Analyst`.
- `seed_baseline` creates a seeded admin user from `CTI_SEEDED_ADMIN_EMAIL` and `CTI_SEEDED_ADMIN_PASSWORD`.

The API routes use `require_role(UserRole.admin, UserRole.analyst)` to protect most operational endpoints.

## 13. API structure

The public API is prefixed as `/api/v1` and grouped by responsibility.

Key areas:

- Auth: `/auth/login`, `/auth/refresh`, `/auth/me`
- Health: `/health`
- Dashboard: `/dashboard/summary`, `/dashboard/recent-decisions`
- CTI: `/cti-events`, `/misp/events`, `/misp/events/{id}/ingest`
- Graph: `/graph-runs`, `/graph-runs/{id}/timeline`, `/ai/workflow`
- AI: `/ai/dashboard`, `/ai/sessions`, `/ai/consumption`
- Proposals: `/proposals`, `/proposals/{id}/approve`, `/request-changes`, `/reject`
- Detections: `/detections`, `/detections/{id}`
- Attack/coverage: `/attack/coverage`, `/attack/techniques/{id}`
- Telemetry and settings: `/telemetry-sources`, `/settings`

The backend uses FastAPI OpenAPI automatically, which is exposed by default through the FastAPI docs routes.

## 14. Testing

The repository includes:

- backend Python tests under `scripts/backend/`
- runtime integration tests under `tests/integration/`
- Playwright E2E tests under `tests/e2e/`
- CI workflows under `.github/workflows/`

Important checks include:

- Python compile all
- Ruff lint and format checks
- mypy
- script-based backend tests
- frontend lint and TypeScript check
- frontend build
- Docker Compose validation
- MISP-enabled integration tests
- OWASP ZAP DAST baseline

## 15. Docker

Docker is the supported local execution model.

### Containers in docker-compose.yml
- `postgres`: PostgreSQL 16
- `redis`: Redis 7
- `backend`: FastAPI service with Alembic migration on startup
- `worker`: Celery worker
- `scheduler`: Celery Beat scheduler
- `frontend`: Next.js app
- `nginx`: reverse proxy on `:8080`
- `misp`, `misp-db`, `misp-valkey`, `misp-modules`, `misp-mail`: optional MISP stack behind the `misp` profile

### Runtime assumptions
- backend and worker connect to PostgreSQL and Redis over the `platform_internal` network
- MISP uses a separate `misp_internal` network
- frontend is exposed via nginx at `http://localhost:8080`

## 16. CI/CD

The GitHub workflows implement a practical engineering pipeline:

- `pr-quality.yml`: backend and frontend quality gates
- `security.yml`: dependency, code, secret, container, and IaC scans
- `docker-validation.yml`: build and health validation for compose stack
- `integration-e2e.yml`: full stack with MISP and runtime tests
- `deploy.yml`: GHCR image publish plus deploy hooks for dev/staging/production environments

Production deploy hooks require secrets and are not executed automatically unless configured.

## 17. Important configuration files

- `.env.example`: authoritative template for runtime environment values
- `docker-compose.yml`: local stack and MISP profile configuration
- `backend/pyproject.toml`: backend dependencies, pytest config, Ruff config, mypy config
- `frontend/package.json`: frontend scripts and dependencies
- `Makefile`: local validation commands
- `sonar-project.properties`: SonarQube project configuration
- `docker/nginx.conf`: nginx reverse proxy rules

## 18. Summary

This repository is best understood as a bounded AI-assisted SOC workflow with deterministic safety controls. The AI component proposes, but the deterministic backend tests, validates, scores, and enforces the route. Human analyst approval remains the final control point before a detection enters the catalog.
