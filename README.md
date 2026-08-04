# CTI Detection Engineering Platform

A production-style demonstration platform that turns MISP CTI into reviewed Sigma detections.

The system is intentionally review-gated. AI or deterministic fixture output can draft and repair Sigma candidates, but pySigma validation, duplicate analysis, policy decisions, and analyst approval control what reaches the Detection Catalog.

## What This Demonstrates

- Real MISP API ingestion, not direct database insertion.
- LangGraph workflow orchestration with persisted node audit records.
- Deterministic coverage, telemetry, ATT&CK, duplicate, and policy gates.
- AI provider abstraction with honest fixture mode for repeatable demos.
- pySigma compilation to Splunk SPL.
- Analyst review, request changes, approval, deployment artifact, and catalog publication lifecycle.

## Local Start

1. Copy `.env.example` to `.env`.
2. Adjust secrets.
3. Run database migrations.
4. Start the stack:

```bash
docker compose up --build
```

The platform UI is available at `http://localhost:8080`.

## Default Local Login

The backend seeds a local admin from environment variables:

- `CTI_SEEDED_ADMIN_EMAIL`
- `CTI_SEEDED_ADMIN_PASSWORD`

Change these before using non-local environments.

## Testing

```bash
make backend-test
make backend-lint
make compose-config
```

## Local Demo Data

After the stack is running and migrations have been applied:

```bash
make demo
```

This seeds baseline reference data and creates repeatable demonstration state. For MISP-backed tests, use the scenario helpers documented in `docs/MISP_INTEGRATION.md`.

## Official Local MISP

Start the platform with the official MISP Docker deployment:

```bash
docker compose --profile misp up -d --build
```

MISP is available at `https://localhost:8443`. See `docs/MISP_INTEGRATION.md`
for login, API key setup, event creation, scheduler polling, and API-only E2E
verification.

## Architecture

See `docs/ARCHITECTURE.md`.

The bounded AI reasoning loop, watchers, confidence scoring, trust scoring, session memory, and visual AI workflow pages are documented in `docs/AI_REASONING_ARCHITECTURE.md`.

For node-and-arrow diagrams of how the AI consumes CTI, reasons, checks itself with watchers, repairs failed candidates, and waits for analyst approval, see `docs/AI_WORKFLOW_DIAGRAM.md`.

## Demo Readiness And Limitations

See `docs/FINAL_QUALITY_AUDIT.md` for the current quality scorecard, known limitations, and production-readiness assessment.

For the complete repository-derived engineering reference intended to support an academic internship report, see `docs/COMPLETE_TECHNICAL_ENGINEERING_REPORT.md`.

For the DevSecOps pipeline, GitHub Actions quality gates, security scans, integration/E2E strategy, and Dev -> Staging -> Production workflow, see `docs/DEVSECOPS_PIPELINE.md`.

## CI validation
