# AI Reasoning Architecture

This platform uses AI as a bounded drafting and repair component inside a deterministic detection-engineering workflow. MISP ingestion, ATT&CK verification, coverage analysis, telemetry analysis, policy routing, pySigma validation, duplicate detection, review, deployment, and catalog publication remain authoritative controls.

For full node-and-arrow Mermaid diagrams, see `docs/AI_WORKFLOW_DIAGRAM.md`.

## Workflow

The LangGraph workflow is:

1. `consume_cti`
2. `extract_behaviors`
3. `verify_attack_mapping`
4. `coverage_analysis`
5. `visibility_analysis`
6. `policy_decision`
7. `generate_candidate`
8. `validate_candidate`
9. `repair_candidate`
10. `queue_review`
11. `approved`
12. `deployment`

Terminal routes exist for already covered behavior, visibility gaps, insufficient evidence, failure, rejection, and behavior advancement.

## Bounded Revision Loop

The AI loop is:

1. Extract behavior.
2. Generate Sigma.
3. Evaluate with watchers.
4. Validate with pySigma and duplicate detection.
5. Calculate proposal confidence.
6. Calculate deterministic trust.
7. If satisfied, queue for human review.
8. If not satisfied and repairable, repair and re-evaluate.

Loop controls are environment-backed:

- `CTI_REASONING_MAX_REVISIONS`
- `CTI_REASONING_MIN_IMPROVEMENT_DELTA`
- `CTI_REASONING_CONFIDENCE_TARGET`
- `CTI_MAX_REPAIR_ATTEMPTS`

The graph stops on validation success, repair limit, no meaningful improvement, terminal policy route, failure, or analyst intervention.

## Persisted State

The platform persists structured AI operational state only:

- `ai_reasoning_sessions`
- `ai_reasoning_revisions`
- `ai_watcher_results`
- `ai_confidence_events`
- `cti_consumption_records`

Stored session memory includes behavior IDs, accepted ATT&CK IDs, repair history, validation history, watcher failures, confidence progression, policy decisions, duplicate statuses, current revision, and termination reason.

The platform does not persist hidden chain-of-thought. AI decisions are represented as structured justification, watcher outcomes, confidence factors, trust factors, validation errors, and revision summaries.

## Watchers

Watchers report `PASS`, `WARNING`, or `FAIL`.

Implemented watcher categories:

- schema
- evidence
- ATT&CK
- Sigma
- confidence
- duplicate
- telemetry
- hallucination
- safety

Watchers do not approve detections. They provide evidence to the confidence and trust engines.

## Confidence

Proposal confidence is calculated from:

- AI confidence
- pySigma validation status
- watcher results
- telemetry visibility
- coverage state
- duplicate status
- repair count

Confidence is recorded as a timeline in `ai_confidence_events`.

## Trust

Trust is separate from confidence. It is weighted toward deterministic verification. A high AI confidence score cannot approve an invalid Sigma candidate.

Recommendations:

- `approve`
- `approve_with_warning`
- `needs_review`
- `request_changes`
- `reject`

Human review remains required before deployment.

## CTI Consumption

MISP ingestion now records consumption state through the MISP API path:

- trigger source
- strategy
- consumed timestamp
- CTI event ID
- workflow ID
- status: pending, consumed, skipped, failed, duplicate

The AI Dashboard exposes last poll, last successful poll, next scheduled poll, interval, scheduler status, worker status, and queue counts.

## UI

Implemented pages:

- `/ai`: AI Dashboard with current session, watcher counts, revision timeline, confidence/trust, session memory, and MISP consumption.
- `/ai-workflow`: Visual workflow architecture with purpose, input, output, executor type, execution time, node status, confidence, and watcher counts.
- `/graph`: LangGraph execution audit trail.
- `/health`: System health, including MISP configured/reachable/authenticated/polling states.

## Limitations

The reasoning engine is structured and bounded, but it is not autonomous deployment. It requires deterministic validation and analyst approval. Scheduler and worker status currently use broker reachability as an operational proxy, not a full Celery event monitor.
