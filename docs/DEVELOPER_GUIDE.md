# Developer Guide

Backend commands:

```bash
cd backend
alembic upgrade head
pytest ../tests/backend
ruff check app ../tests/backend
mypy app
```

Frontend commands:

```bash
cd frontend
npm install
npm run build
```

The single workflow entrypoint is `app.graph.runner.DetectionEngineeringGraph`.
