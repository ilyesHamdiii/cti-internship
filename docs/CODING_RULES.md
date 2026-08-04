# Coding Rules

- Do not create manual CTI upload paths.
- Do not create alternate workflow orchestration outside the single graph.
- Do not use Celery chains as orchestration.
- Do not let AI become authoritative for deterministic checks.
- Do not store or request chain-of-thought.
- Store structured justification only.
- Keep proposal revisions immutable.
- Use repositories and services for database access.
- Use strict Pydantic v2 schemas at boundaries.
- Use SQLAlchemy 2 for persistence.
- Never log secrets.
- Never expose provider keys to the frontend.
- Every frontend page must use backend APIs.
- Test deterministic services without DeepSeek.
- Use provider fixtures for automated AI tests.
