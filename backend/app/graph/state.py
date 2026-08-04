from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    workflow_id: str
    graph_run_id: str
    cti_event_id: str
    proposal_id: str
    behavior_id: str
    revision_number: int
    resume_from_node: str
    current_node: str
    previous_node: str
    normalized_cti: dict[str, Any]
    behavior_ids: list[str]
    candidate: dict[str, Any]
    validation: dict[str, Any]
    analyst_action: str
    analyst_comment: str
    terminal_status: str
    failure_reason: str
