# Deployment Guide

1. Copy `.env.example` to `.env`.
2. Set `CTI_JWT_SECRET`.
3. Keep `CTI_AI_FIXTURE_MODE=true` for deterministic local demos or set a DeepSeek key for live provider use.
4. Start the platform:

```bash
docker compose up --build
```

Enable the official MISP profile when local MISP is required:

```bash
docker compose --profile misp up -d --build
```

The local ingress is `http://localhost:8080`.
The local MISP web interface is `https://localhost:8443`.

For MISP login, auth key setup, test event creation, scheduler verification,
and API-only E2E validation, see `docs/MISP_INTEGRATION.md`.
