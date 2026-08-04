# LangGraph Contract

There is exactly one authoritative graph.

## Nodes

`consume_cti -> extract_behaviors -> verify_attack_mapping -> coverage_analysis -> visibility_analysis -> policy_decision -> generate_candidate -> validate_candidate -> repair_candidate -> queue_review -> approved -> deployment`

## State

Every graph execution persists:

- `workflow_id`
- `graph_run_id`
- `cti_event_id`
- `proposal_id`
- `behavior_id`
- `revision_number`
- `current_node`
- `previous_node`
- node inputs and outputs
- retry count
- timing
- token usage
- estimated cost
- terminal status
- failure reason

## Routing

- Covered behaviors terminate without proposals.
- Visibility gaps terminate without proposals.
- Insufficient evidence terminates without proposals.
- Candidate-required behaviors route to `generate_candidate`.
- Invalid repairable candidates route to `repair_candidate`.
- Valid candidates route to `queue_review`.
- Request Changes resumes at `repair_candidate`.
- Approval resumes at `approved` and then `deployment`.
- Rejection is routed through the graph into terminal rejected state.

## AI Calls

AI Call 1 occurs in `extract_behaviors`.

AI Call 2 occurs only in `generate_candidate`.

AI Call 3+ occurs only in `repair_candidate`.

All AI responses are schema-validated JSON. Invalid or malformed responses are rejected and retried according to node policy.
