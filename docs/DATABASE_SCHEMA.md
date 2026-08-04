# Database Schema Contract

PostgreSQL is the authoritative business-state store. Redis is used only for background execution coordination.

## Lifecycle Enums

`cti_event_status`: `pending`, `running`, `waiting_repair`, `ready_review`, `approved`, `rejected`, `failed`, `covered`, `visibility_gap`, `insufficient_evidence`

`workflow_status`: `pending`, `running`, `waiting_review`, `approved`, `deployed`, `rejected`, `failed`, `completed`

`graph_run_status`: `pending`, `running`, `succeeded`, `failed`, `cancelled`

`node_status`: `pending`, `running`, `succeeded`, `failed`, `skipped`

`proposal_status`: `ready_review`, `approved`, `changes_requested`, `rejected`, `superseded`, `deployed`

`review_action`: `approve`, `request_changes`, `reject`

`coverage_status`: `covered`, `partial`, `not_covered`

`visibility_status`: `visible`, `partial`, `gap`

## Tables

The implementation must create the tables defined in `docs/ARCHITECTURE.md`:

- `cti_events`
- `workflows`
- `graph_runs`
- `graph_node_runs`
- `ai_interactions`
- `behaviors`
- `attack_mappings`
- `attack_techniques`
- `detection_catalog`
- `detection_attack_mappings`
- `detection_telemetry_requirements`
- `telemetry_sources`
- `coverage_results`
- `visibility_results`
- `proposals`
- `proposal_revisions`
- `validation_results`
- `review_actions`
- `deployment_artifacts`
- `users`
- `settings`
- `misp_poll_state`
- `system_health_checks`

## Constraints

- `cti_events.misp_event_id` is unique.
- `workflows.cti_event_id` is unique.
- `proposals.behavior_id` is unique for active proposal ownership.
- `proposal_revisions(proposal_id, revision_number)` is unique.
- `proposal_revisions` are immutable after insert.
- `review_actions` are append-only.
- All proposal revisions reference `proposal_id`, `behavior_id`, `workflow_id`, and `graph_run_id`.
- One proposal references exactly one behavior.
- One behavior references exactly one CTI event and workflow.

## JSON Fields

JSONB fields store structured data only. AI reasoning fields must contain structured justification:

- `decision_factors`
- `evidence_refs`
- `attack_rationale`
- `coverage_rationale`
- `telemetry_rationale`
- `confidence`
- `uncertainties`
- `change_summary`

Chain-of-thought must not be requested or stored.
