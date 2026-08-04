# SOC User Guide

## Threat Queue

Use `Threat Queue` to work from the real MISP API path:

1. Confirm the event appears in `MISP Inbox`.
2. Select the event and click `Ingest Selected`, or use `Ingest All New`.
3. Confirm the event appears in `Ingested CTI Events`.
4. Click `Run Detection Workflow` to execute the authoritative graph.
5. Use `Reprocess` only when you intentionally want another graph run for the
   same CTI event.

The page shows MISP ingestion state, CTI status, workflow status, proposal
state, graph status, ATT&CK techniques, and the current graph run id.

## Live AI Graph

Use `Live AI Graph` to inspect a graph run node by node. Resume runs mark
earlier context as inherited/skipped instead of pretending every prior node ran
again.

## Review Workspace

Analysts use `Review Workspace` to inspect validated proposals. The available
actions are:

- `Approve`: resumes the graph through deployment, creates a deployment
  artifact, and publishes a generated detection catalog entry.
- `Request Changes`: records analyst feedback, resumes the graph through the
  repair node, and creates an immutable new proposal revision.
- `Reject`: records the decision and marks the proposal/workflow as rejected.

The workspace shows the current Sigma YAML, compiled query, validation results,
ATT&CK mapping, coverage/visibility checks, graph history, review actions, and
deployment artifacts.

## Detection Catalog

Use `Detection Catalog` to verify approved generated detections. Generated
entries include Sigma content, compiled query, ATT&CK mappings, quality score,
proposal id, revision number, workflow id, and deployment artifact id.

## System Health

Use `System Health` to verify MISP status. The MISP check distinguishes
`not_configured`, `unreachable`, `authentication_failed`, `authenticated`, and
`healthy`, and exposes configured/reachable/authenticated/polling booleans.
