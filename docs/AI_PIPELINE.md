# AI / LangGraph pipeline

This project uses AI as an assistive detection-engineering component, not as the final authority for security decisions.

## 1. Why AI is used

The platform needs to convert raw CTI into detection logic in a reviewable, explainable path. AI is used to:

- extract independent suspicious behaviors from MISP event content
- propose ATT&CK mappings
- propose Sigma rule logic grounded in the event evidence
- repair invalid or weak Sigma candidates under bounded rules

AI is useful here because it can transform unstructured CTI into structured rule proposals, but the repository explicitly keeps deterministic verification in front of publication.

## 2. What AI is responsible for

The AI component is responsible for:

- behavior extraction from normalized CTI
- ATT&CK mapping proposals
- Sigma candidate generation
- Sigma repair under validation failures
- structured justification with confidence metadata

The AI does not decide whether the final detection is approved, deployed, or published. That remains a human review action.

## 3. What is deterministic

The following parts are deterministic and authoritative:

- ATT&CK validation against the local seeded techniques
- coverage analysis against `detection_catalog`
- duplicate detection using behavior and query fingerprints
- telemetry visibility checks
- policy routing
- Sigma schema validation
- pySigma compilation to Splunk backend
- quality scoring
- analyst review workflow
- deployment artifact publication

This is a key design principle: AI proposes, deterministic logic verifies, analysts decide.

## 4. AI provider abstraction

The provider interface is defined in `backend/app/services/ai.py` and implemented by `DeterministicFixtureProvider` and a DeepSeek-backed client abstraction.

The project supports:

- fixture mode: deterministic outputs for repeatable demos and CI
- live mode: DeepSeek-backed generation when `CTI_DEEPSEEK_API_KEY` is present and `CTI_AI_FIXTURE_MODE=false`

The provider interface exposes:

- `analyze_cti()`
- `generate_sigma()`
- `repair_sigma()`

The key idea is that the graph works against a common provider interface, not against a hard-coded vendor implementation.

## 5. DeepSeek integration

The live provider class is configured by environment variables:

- `CTI_DEEPSEEK_API_KEY`
- `CTI_DEEPSEEK_MODEL`
- `CTI_DEEPSEEK_BASE_URL`

The system tracks:

- request payload and response payload
- tokens used
- estimated cost
- latency
- confidence
- structured justification

These values are persisted in the database as `ai_interactions` and AI reasoning session records.

## 6. LangGraph state and routing

The actual workflow is defined in `backend/app/graph/runner.py`.

The state is a dictionary passed through the graph; it includes identifiers such as:

- `workflow_id`
- `graph_run_id`
- `reasoning_session_id`
- `cti_event_id`
- `proposal_id`
- `resume_from_node`
- `analyst_comment`

The graph executes named nodes including:

- `consume_cti`
- `extract_behaviors`
- `verify_attack_mapping`
- `coverage_analysis`
- `visibility_analysis`
- `policy_decision`
- `generate_candidate`
- `validate_candidate`
- `repair_candidate`
- `queue_review`
- `approved`
- `deployment`
- terminal states such as `terminal_covered`, `terminal_visibility_gap`, `terminal_insufficient_evidence`, `terminal_failed`, `terminal_rejected`

## 7. Graph transitions

Important transitions are:

```text
START -> entry -> consume_cti -> extract_behaviors
extract_behaviors -> verify_attack_mapping -> coverage_analysis -> visibility_analysis -> policy_decision
policy_decision -> generate_candidate (if allowed)
generate_candidate -> validate_candidate
validate_candidate -> queue_review (if valid)
validate_candidate -> repair_candidate (if repairable invalid)
validate_candidate -> terminal_failed (if unrepairable invalid)
repair_candidate -> validate_candidate or terminal_failed
queue_review -> approved / next behavior / terminal states
approved -> deployment or repair_candidate or terminal_rejected
```

The route selection is not left to the AI. It is determined by deterministic checks, confidence thresholds, trust thresholds, and analyst actions.

## 8. AI session memory and repair loop

The project maintains a bounded reasoning loop:

- `AiReasoningSession` stores current reasoning context
- `AiReasoningRevision` stores revision history
- `AiWatcherResult` captures watcher status
- `AiConfidenceEvent` tracks confidence over time

The repair loop is bounded by:

- `CTI_MAX_REPAIR_ATTEMPTS`
- `CTI_REASONING_MAX_REVISIONS`
- `CTI_REASONING_MIN_IMPROVEMENT_DELTA`

This prevents unbounded AI iteration and keeps the workflow reproducible.

## 9. Structured outputs

The AI outputs are validated with Pydantic models in `backend/app/schemas/ai.py`.

The schema includes:

- `BehaviorCandidate`
- `CtiAnalysisResponse`
- `SigmaCandidate`
- `SigmaGenerationResponse`
- `SigmaRepairResponse`

This ensures that AI content is structured and machine-checkable rather than freeform text.

## 10. Sigma generation and validation

The AI generates a structured Sigma candidate, then the system validates it using:

- required fields
- ATT&CK tags
- valid Sigma logsource and detection shape
- `SigmaCollection.from_yaml()`
- compiler output through the Splunk backend
- duplicate and coverage checks

If it fails, the repair loop can revise the candidate by interpreting validation failures and adjusting the Sigma rule.

## 11. Confidence and reliability

The reasoning engine records:

- AI confidence
- watcher pass/failed/warning results
- aggregated confidence score
- trust score
- recommendation (`approve`, `approve_with_warning`, `needs_review`, `request_changes`, `reject`)

This is not presented as autonomous trust. It is evidence for the eventual human decision-maker.

## 12. Human review

The platform explicitly requires review before publication to the detection catalog.

Supported analyst actions:

- `approve`
- `request_changes`
- `reject`

These actions route through the graph’s `approved` node and can trigger a new repair cycle or deployment artifact creation.

## 13. Fixture/demo mode

The project includes a deterministic fixture AI provider that intentionally produces rule candidates for demo and CI conditions.

This is controlled by:

- `CTI_AI_FIXTURE_MODE=true` in `.env.example`

The fixture provider makes the platform reproducible and safe for demonstrations, but it is not a production-grade AI engine.

## 14. Important implementation note

The project uses the phrase “AI-assisted” in its actual design. The graph stores outputs, evidence, and state, but the final decision authority is intentionally kept human-controlled and deterministic.
