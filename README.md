# CTI Detection Engineering Platform

This repository contains an AI-assisted CTI detection engineering platform for a local SOC workflow. The project ingests MISP CTI, normalizes it, extracts behaviors, verifies ATT&CK mappings, checks telemetry and coverage, generates Sigma candidates with bounded AI support, validates them with deterministic services, and requires human analyst approval before a detection is cataloged.

## Supervisor handoff package

The repository now includes:

- [docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.md](docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.md)
- [docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.pdf](docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.pdf)
- [docs/SOURCE_CODE_GUIDE.md](docs/SOURCE_CODE_GUIDE.md)
- [docs/RUNNING_THE_PROJECT.md](docs/RUNNING_THE_PROJECT.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/DATABASE.md](docs/DATABASE.md)
- [docs/AI_PIPELINE.md](docs/AI_PIPELINE.md)
- [docs/DETECTION_ENGINEERING.md](docs/DETECTION_ENGINEERING.md)
- [docs/DEVSECOPS_PIPELINE.md](docs/DEVSECOPS_PIPELINE.md)
- [docs/MISP_INTEGRATION.md](docs/MISP_INTEGRATION.md)
- [docs/SECURITY_AND_LIMITATIONS.md](docs/SECURITY_AND_LIMITATIONS.md)

## What this demonstrates

- Real MISP API ingestion and normalization
- LangGraph workflow orchestration with persisted execution state
- Deterministic ATT&CK verification, telemetry checks, coverage analysis, duplicate detection, and policy gating
- AI provider abstraction with fixture mode for demos and CI
- pySigma compilation to Splunk SPL
- Human review workflow before catalog publication

## Local start

1. Copy the sample environment file:

```bash
cp .env.example .env
```

2. Adjust secrets and local values in `.env`.
3. Start the base stack:

```bash
docker compose up --build
```

4. If MISP is required, start the MISP profile:

```bash
docker compose --profile misp up -d --build
```

The main frontend is exposed at:

```text
http://localhost:8080
```

## Default local login

The backend seeds a local admin account from environment variables:

- `CTI_SEEDED_ADMIN_EMAIL`
- `CTI_SEEDED_ADMIN_PASSWORD`

The auth endpoint is:

```text
POST /api/v1/auth/login
```

## Exact project commands

Run the backend script tests:

```bash
cd backend && pytest ../scripts/backend -q
```

Run the migration inside the app container:

```bash
docker compose exec backend sh -lc "PYTHONPATH=/app alembic upgrade head"
```

Run the standard compose stack:

```bash
docker compose up --build
```

Run the MISP-enabled stack:

```bash
docker compose --profile misp up -d --build
```

## Project status

This is a working local engineering prototype with documented deterministic controls and review gates. It is not a production-hardened enterprise SOC platform. See [docs/SECURITY_AND_LIMITATIONS.md](docs/SECURITY_AND_LIMITATIONS.md) for the current limitations and hardening requirements.

## Documentation index

For the complete handoff, start here:

- [docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.md](docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.md)
- [docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.pdf](docs/AI-Assisted_CTI_Detection_Platform_Technical_Documentation.pdf)
- [docs/RUNNING_THE_PROJECT.md](docs/RUNNING_THE_PROJECT.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/DATABASE.md](docs/DATABASE.md)
- [docs/AI_PIPELINE.md](docs/AI_PIPELINE.md)
- [docs/DETECTION_ENGINEERING.md](docs/DETECTION_ENGINEERING.md)
- [docs/DEVSECOPS_PIPELINE.md](docs/DEVSECOPS_PIPELINE.md)
