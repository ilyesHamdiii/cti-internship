# Security and production limitations

This section documents the project honestly. It describes the current state of the platform as a local, review-gated engineering prototype rather than a production-hardened SOC platform.

## 1. Known limitations and production hardening requirements

### 1.1 Local demo and development defaults

The project includes local defaults in `.env.example` such as:

- `CTI_AI_FIXTURE_MODE=true`
- default admin-like credentials
- local self-signed MISP TLS behavior
- local Redis and PostgreSQL service names

These are appropriate for local development and demo use, but they are not a production security model.

### 1.2 CORS is permissive

In `backend/app/main.py`, the app configures CORS with:

```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

This is acceptable for local testing but not for a hardened production deployment.

### 1.3 JWT and secrets are environment-managed

The project expects secure configuration for:

- `CTI_JWT_SECRET`
- `CTI_SEEDED_ADMIN_PASSWORD`
- `CTI_MISP_API_KEY`
- `CTI_DEEPSEEK_API_KEY`

These should be managed through a secret store or secure environment management outside of a repository checkout.

### 1.4 Frontend token storage uses localStorage

The frontend reads tokens from `window.localStorage` in `frontend/lib/api.ts`.

This is convenient for demos, but it is not a modern production-grade token storage approach for high-assurance applications. Browser storage is not sufficient for strong session protection in a hardened production environment.

### 1.5 No production identity provider or MFA layer

The platform implements a simple local JWT flow and seeded admin account. It does not implement:

- enterprise SSO
- OIDC/OAuth provider integration
- MFA enforcement
- role separation beyond the local enum model
- password rotation policies

This is a development-oriented implementation.

### 1.6 External deployment and webhook secrets are required

The deploy workflow includes environment-based deployment hooks:

- `DEVELOPMENT_DEPLOY_WEBHOOK`
- `STAGING_DEPLOY_WEBHOOK`
- `PRODUCTION_DEPLOY_WEBHOOK`

These are not configured in the repository and are intentionally external to the codebase.

### 1.7 Security scanning is configured, but not necessarily enforced externally

The project includes workflows for:

- Bandit
- pip-audit
- detect-secrets
- Semgrep
- Checkov
- Trivy
- Snyk (optional when the token is configured)
- SonarQube (optional when the secrets are configured)

These are good engineering controls, but they are only effective when the organization configures and enforces the necessary secrets and policies.

### 1.8 MISP integration is local-demo capable, not hardened enterprise MISP

The compose file includes official MISP Docker images and a dedicated `misp_internal` network. This is useful for local development and controlled validation, but it is not a production MISP deployment architecture.

### 1.9 AI provider integration is constrained by external service availability

The system supports both:

- fixture mode
- live DeepSeek API

However, in a real environment, the AI service can fail or be unavailable. The project tracks that through the AI interaction records, but the platform still depends on the external provider for live reasoning.

### 1.10 Alerting, monitoring, and resilience are minimal

The repository contains health endpoints and runtime checks, but it does not include a full production observability stack such as:

- centralized log aggregation
- distributed tracing
- alerting pipelines
- production SLO tracking
- full platform uptime monitoring

### 1.11 Partial or seeded ATT&CK data

The local system seeds ATT&CK techniques from a small fixture dataset. This is suitable for local validation and demos, but it is not a full ATT&CK knowledge base replacement for production-grade coverage mapping.

### 1.12 Review workflow is local and human-controlled, not enterprise governance

The application requires analyst approval and stores review actions, but it does not implement:

- explicit four-eyes approval separation
- audit sign-off policies
- delegated reviewer hierarchy
- policy-based enforcement for production releases

## 2. Security posture summary

The project is best described as a functional security engineering prototype with sound local controls, deterministic validation, and developer-oriented DevSecOps automation. It is not yet a production-grade SOC platform.

## 3. Recommended next hardening steps

- replace wildcard CORS with explicit origins
- move JWT secret storage to a secret manager
- replace localStorage token storage with a more secure session strategy
- integrate an enterprise identity provider and MFA
- configure real deployment secrets and protected GitHub environments
- add production observability, alerting, and centralized logs
- extend the ATT&CK dataset and telemetry inventories
- formalize production policy gates and access review workflows

The goal is not to hide these limitations, but to make them explicit for a responsible internship handoff.
