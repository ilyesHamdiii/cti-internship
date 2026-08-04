# API Contract

Base path: `/api/v1`

All endpoints return bounded responses with pagination where collections are exposed.

## Authentication

- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`

Roles: `Admin`, `Analyst`.

## Dashboard

- `GET /dashboard/summary`
- `GET /dashboard/recent-decisions`

## CTI

- `GET /cti-events`
- `GET /cti-events/{id}`
- `POST /cti-events/{id}/run-workflow`
- `POST /cti-events/{id}/reprocess`

No manual CTI upload endpoint is allowed.

## MISP

- `GET /misp/events`
- `GET /misp/events/{misp_event_id}`
- `POST /misp/events/{misp_event_id}/ingest`
- `POST /misp/events/ingest-all-new`

MISP endpoints call the configured MISP API. They do not create CTI records by
direct PostgreSQL insertion.

## Graph Runs

- `GET /graph-runs`
- `GET /graph-runs/{id}`
- `GET /graph-runs/{id}/timeline`
- `GET /graph-runs/{id}/events`

## Proposals

- `GET /proposals`
- `GET /proposals/{id}`
- `GET /proposals/{id}/revisions`
- `GET /proposal-revisions/{id}/validation`
- `POST /proposals/{id}/approve`
- `POST /proposals/{id}/request-changes`
- `POST /proposals/{id}/reject`

## Deterministic Data

- `GET /detections`
- `GET /detections/{id}`
- `POST /detections/import`
- `GET /attack/coverage`
- `GET /attack/techniques/{id}`
- `GET /telemetry-sources`
- `POST /telemetry-sources`
- `PATCH /telemetry-sources/{id}`

## Operations

- `GET /automation-runs`
- `GET /system-health`
- `GET /settings`
- `PATCH /settings/{key}`
- `GET /deployment-artifacts/{id}`

## Error Format

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```
