# Detection engineering workflow

This repository implements a practical CTI-to-detection pipeline that follows the operational pattern below:

MISP CTI -> normalization -> behavior extraction -> ATT&CK mapping -> telemetry/coverage -> policy -> AI Sigma generation -> validation -> pySigma -> Splunk SPL -> analyst review -> approved catalog

## 1. Inputs and sources

The CTI source is MISP. The project reads events through the MISP API and normalizes them into local `cti_events` and `normalized_event` content.

The normalization step extracts:

- original MISP event ID
- title
- publication status
- tags
- attributes
- evidence text

This normalized form is then used by the graph.

## 2. Behavior extraction

The first AI step is behavior extraction. The AI tries to isolate independently detectable suspicious actions from the CTI narrative and raw attributes.

The output is a `BehaviorCandidate` object, which includes:

- summary
- behavior type
- action/target/execution mechanism
- ATT&CK proposals
- telemetry requirements
- evidence references
- observables
- confidence
- uncertainties

These behaviors are stored as `behaviors` rows with a fingerprint and evidence references.

## 3. ATT&CK verification

The system verifies whether the proposed ATT&CK mappings are valid and consistent with the evidence.

The `AttackVerificationService` checks:

- whether the technique exists in the local ATT&CK reference table
- whether it is revoked or deprecated
- whether tactic alignment matches
- whether confidence is above threshold
- whether evidence references are present and consistent
- whether the behavior platform is compatible with the technique platform

If the mapping fails validation, the workflow does not proceed blindly; the behavior is rejected or routed for repair.

## 4. Telemetry and coverage

The platform performs deterministic checks before any Sigma generation is considered.

### Telemetry visibility

`TelemetryService` compares required telemetry sources and fields against the known telemetry inventory. Results are stored in `visibility_results`.

### Coverage analysis

`CoverageService` compares behavior fingerprints and logic similarity against the active `detection_catalog` entries. This is used to decide whether the behavior is already covered or only partially covered.

### Policy decision

`decide_policy()` routes behavior by policy:

- `already_covered`
- `visibility_gap`
- `insufficient_evidence`
- `generate_candidate`

This is the crucial gate that prevents unneeded or unsupported detections.

## 5. Sigma generation

When policy allows generation, the AI proposes a Sigma candidate based on:

- behavior summary
- evidence refs
- ATT&CK mapping
- telemetry constraints
- false positive notes
- quality heuristics

The generated output is structured as `SigmaCandidate` and stored as a proposal revision.

## 6. Sigma validation

The `SigmaValidationService` performs:

- schema validation using Pydantic models
- required detection field checks
- ATT&CK tag presence checks
- field inventory checks
- compile attempt with `pysigma-backend-splunk`
- quality score calculation

The compile result is the concrete Splunk query. The platform records this in `validation_results` and stores the compiled output in JSONB.

## 7. Duplicate detection

The duplicate logic compares for:

- exact fingerprint matches
- canonical similarity
- compiled query similarity
- overlap thresholds

This is implemented in `DuplicateDetectionService` and supports the review guardrail: do not generate redundant detections when a near-duplicate already exists.

## 8. Repair loop

If validation fails but is considered repairable, the graph calls `repair_candidate`.

The repair loop is bounded and records:

- attempted revisions
- change summary
- validation failures addressed
- unresolved issues
- confidence delta before and after
- route selected

This makes repair traceable and limits runaway or brittle AI changes.

## 9. Analyst review lifecycle

The proposal is queued for review only after it passes the deterministic gates.

A review action can be:

- approve
- request_changes
- reject

This stage is not AI-driven. The analyst is the final decision-maker.

## 10. Deployment and catalog publication

On approval, the deployment service creates a file artifact and publishes an entry to `detection_catalog`.

The published detection includes:

- `name`
- `detection_type`
- `source`
- `content`
- `normalized_logic`
- `behavior_fingerprint`
- `status`

The catalog entry also links ATT&CK mapping records and stores the compiled query.

## 11. Real design constraints

This project is deliberately conservative.

Important constraints in the implementation:

- AI is not the final author of detections
- validation is deterministic
- review is mandatory
- repair attempts are finite
- publication requires a successful validated proposal
- run state, nodes, revisions, and actions are audited in the database

## 12. Example supported flow

A typical supported path in this repository is:

1. MISP event imported and normalized
2. Graph extracts PowerShell or scheduled-task behavior
3. ATT&CK mapping is verified against the local dataset
4. coverage and telemetry checks run
5. policy decides whether to generate a candidate
6. Sigma candidate is generated and compiled to Splunk query
7. validation score and duplicate checks occur
8. proposal is queued for review
9. analyst approves, requests changes, or rejects
10. approved detection is stored in the catalog

This matches the repository’s actual implementation boundaries and is the most accurate positioning for the internship project handoff.
