from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.graph.runner import DetectionEngineeringGraph
from app.models.enums import (
    CtiEventStatus,
    GraphRunStatus,
    ProposalStatus,
    ReviewActionType,
    UserRole,
)
from app.models.models import (
    AiConfidenceEvent,
    AiInteraction,
    AiReasoningRevision,
    AiReasoningSession,
    AiWatcherResult,
    AttackMapping,
    AttackTechnique,
    Behavior,
    CoverageResult,
    CtiEvent,
    DeploymentArtifact,
    DetectionAttackMapping,
    DetectionCatalog,
    GraphNodeRun,
    GraphRun,
    PolicyDecision,
    Proposal,
    ProposalRevision,
    ReviewAction,
    Setting,
    SystemHealthCheck,
    TelemetrySource,
    User,
    ValidationResult,
    VisibilityResult,
    Workflow,
)
from app.schemas.api import (
    DashboardSummary,
    ListResponse,
    MispIngestionScheduleUpdate,
    RequestChangesRequest,
    ReviewRequest,
    SettingUpdate,
    TelemetrySourceCreate,
)
from app.schemas.common import HealthResponse
from app.services.misp import MispApiService, MispConnectivityService, MispIngestionScheduleService
from app.services.reasoning import ConsumptionStatusService
from app.services.sigma import SigmaValidationService
from app.workers.tasks import run_graph

router = APIRouter()


AI_WORKFLOW_NODES = [
    {
        "node": "consume_cti",
        "purpose": "Load normalized MISP CTI and mark the event running",
        "input": "cti_event_id",
        "output": "normalized_cti",
        "executor": "deterministic",
    },
    {
        "node": "extract_behaviors",
        "purpose": "Extract behavior candidates and evidence references",
        "input": "normalized_cti",
        "output": "behaviors",
        "executor": "ai",
    },
    {
        "node": "verify_attack_mapping",
        "purpose": "Verify proposed ATT&CK techniques against local ATT&CK data",
        "input": "behavior candidates",
        "output": "verified mappings",
        "executor": "deterministic",
    },
    {
        "node": "coverage_analysis",
        "purpose": "Determine whether matching detections already exist",
        "input": "behavior fingerprint",
        "output": "coverage result",
        "executor": "deterministic",
    },
    {
        "node": "visibility_analysis",
        "purpose": "Check telemetry availability for the behavior",
        "input": "required telemetry",
        "output": "visibility result",
        "executor": "deterministic",
    },
    {
        "node": "policy_decision",
        "purpose": "Route covered, visibility gap, insufficient evidence, or generation",
        "input": "confidence, coverage, visibility, ATT&CK verification",
        "output": "policy decision",
        "executor": "deterministic",
    },
    {
        "node": "generate_candidate",
        "purpose": "Generate a Sigma candidate from verified behavior context",
        "input": "behavior and verified mappings",
        "output": "sigma candidate",
        "executor": "ai",
    },
    {
        "node": "validate_candidate",
        "purpose": "Run pySigma validation",
        "input": "sigma candidate",
        "output": "validation result",
        "executor": "deterministic_validator",
    },
    {
        "node": "validate_candidate",
        "stage": "watcher_evaluation",
        "purpose": "Aggregate schema, Sigma, confidence, duplicate, telemetry, hallucination, and safety watchers",
        "input": "candidate and validation result",
        "output": "watcher aggregation and route cause",
        "executor": "deterministic_watcher",
    },
    {
        "node": "validate_candidate",
        "stage": "confidence_calculation",
        "purpose": "Calculate proposal confidence from AI, validation, watchers, telemetry, coverage, duplicate, and repair penalty",
        "input": "watchers and validation",
        "output": "confidence score",
        "executor": "scoring_gate",
    },
    {
        "node": "validate_candidate",
        "stage": "trust_calculation",
        "purpose": "Calculate deterministic trust and recommendation",
        "input": "validation, watchers, confidence",
        "output": "trust score and recommendation",
        "executor": "scoring_gate",
    },
    {
        "node": "validate_candidate",
        "stage": "satisfaction_decision",
        "purpose": "Route to review, repair, visibility gap, insufficient evidence, duplicate terminal, or rejection",
        "input": "mandatory gates, confidence threshold, trust threshold",
        "output": "selected route",
        "executor": "policy_gate",
    },
    {
        "node": "repair_candidate",
        "stage": "revision_loop",
        "purpose": "Repair invalid or low-quality candidates with bounded session memory",
        "input": "candidate, validation errors, watcher failures, repair history",
        "output": "revised sigma candidate",
        "executor": "ai",
    },
    {
        "node": "queue_review",
        "purpose": "Persist validated proposal and revision for analyst review",
        "input": "validated candidate",
        "output": "proposal revision",
        "executor": "deterministic",
    },
    {
        "node": "approved",
        "purpose": "Resume after human analyst approval, rejection, or requested changes",
        "input": "review action",
        "output": "analyst route",
        "executor": "human",
    },
    {
        "node": "deployment",
        "purpose": "Create deployment artifact and publish detection catalog entry",
        "input": "approved proposal revision",
        "output": "artifact and detection",
        "executor": "deterministic",
    },
    {
        "node": "terminal_insufficient_evidence",
        "purpose": "Terminal state for unsupported evidence or insufficient mapping",
        "input": "watcher or policy failure",
        "output": "insufficient evidence status",
        "executor": "terminal",
    },
    {
        "node": "terminal_visibility_gap",
        "purpose": "Terminal state for missing telemetry",
        "input": "telemetry watcher or visibility gate",
        "output": "visibility gap status",
        "executor": "terminal",
    },
    {
        "node": "terminal_covered",
        "purpose": "Terminal state for existing coverage or exact duplicate",
        "input": "coverage or duplicate gate",
        "output": "covered status",
        "executor": "terminal",
    },
    {
        "node": "terminal_rejected",
        "purpose": "Terminal state for safety failure or analyst rejection",
        "input": "safety watcher or analyst rejection",
        "output": "rejected status",
        "executor": "terminal",
    },
]


def page(db: Session, model: Any, limit: int, offset: int) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(model)) or 0
    rows = db.scalars(select(model).limit(limit).offset(offset)).all()
    return ListResponse(
        items=[to_dict(row) for row in rows], total=total, limit=limit, offset=offset
    )


def to_dict(row: Any) -> dict[str, Any]:
    return {
        column.key: serialize_value(getattr(row, column.key))
        for column in row.__mapper__.column_attrs
    }


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): serialize_value(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [serialize_value(nested) for nested in value]
    return value


def collapse_duplicate_proposals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(proposal_group_key(item), []).append(item)

    collapsed: list[dict[str, Any]] = []
    for group in grouped.values():
        ranked = sorted(group, key=proposal_rank)
        representative = dict(ranked[0])
        representative["duplicate_count"] = len(group)
        representative["duplicate_proposal_ids"] = [item["id"] for item in group]
        representative["duplicate_statuses"] = sorted(
            {str(item.get("status") or "unknown") for item in group}
        )
        representative["duplicate_behavior_summaries"] = sorted(
            {str(item.get("behavior_summary") or "") for item in group}
        )
        collapsed.append(representative)
    return sorted(collapsed, key=proposal_rank)


def proposal_group_key(item: dict[str, Any]) -> str:
    summary = str(item.get("behavior_summary") or item.get("id") or "").strip().lower()
    techniques = ",".join(sorted(str(value) for value in item.get("attack_techniques") or []))
    return f"{summary}|{techniques}"


def proposal_rank(item: dict[str, Any]) -> tuple[int, str]:
    status_rank = {
        "ready_review": 0,
        "changes_requested": 1,
        "approved": 2,
        "deployed": 3,
        "rejected": 4,
    }
    status = str(item.get("status") or "")
    return (status_rank.get(status, 99), str(item.get("updated_at") or ""))


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(select(1))
    return HealthResponse(
        status="healthy", checked_at=datetime.now(UTC), components={"database": "healthy"}
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> DashboardSummary:
    pending = (
        db.scalar(
            select(func.count())
            .select_from(CtiEvent)
            .where(CtiEvent.status == CtiEventStatus.pending)
        )
        or 0
    )
    running = (
        db.scalar(
            select(func.count())
            .select_from(GraphRun)
            .where(GraphRun.status == GraphRunStatus.running)
        )
        or 0
    )
    queued = (
        db.scalar(
            select(func.count())
            .select_from(Proposal)
            .where(Proposal.status == ProposalStatus.ready_review)
        )
        or 0
    )
    avg_conf = db.scalar(select(func.avg(Proposal.confidence))) or 0
    avg_cost = db.scalar(select(func.avg(ProposalRevision.estimated_cost))) or 0
    avg_runtime = db.scalar(select(func.avg(GraphRun.duration_ms))) or 0
    coverage_total = db.scalar(select(func.count()).select_from(CoverageResult)) or 0
    covered = (
        db.scalar(
            select(func.count())
            .select_from(CoverageResult)
            .where(CoverageResult.coverage_status == "covered")
        )
        or 0
    )
    visibility_total = db.scalar(select(func.count()).select_from(VisibilityResult)) or 0
    visible = (
        db.scalar(
            select(func.count())
            .select_from(VisibilityResult)
            .where(VisibilityResult.visibility_status == "visible")
        )
        or 0
    )
    return DashboardSummary(
        pending_cti=pending,
        running_graphs=running,
        queued_reviews=queued,
        coverage_percent=(covered / coverage_total * 100) if coverage_total else 0.0,
        visibility_percent=(visible / visibility_total * 100) if visibility_total else 0.0,
        average_confidence=float(avg_conf),
        average_cost=float(avg_cost),
        average_runtime_ms=float(avg_runtime),
        generated_at=datetime.now(UTC),
    )


@router.get("/dashboard/recent-decisions")
def recent_decisions(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> ListResponse:
    return page(db, CtiEvent, 10, 0)


@router.get("/dashboard/active-workflows", response_model=ListResponse)
def active_workflows(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> ListResponse:
    rows = db.scalars(select(Workflow).order_by(Workflow.updated_at.desc()).limit(10)).all()
    return ListResponse(items=[to_dict(row) for row in rows], total=len(rows), limit=10, offset=0)


@router.get("/cti-events", response_model=ListResponse)
def cti_events(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(CtiEvent)) or 0
    rows = db.scalars(
        select(CtiEvent).order_by(CtiEvent.received_at.desc()).limit(limit).offset(offset)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = to_dict(row)
        behaviors = db.scalars(select(Behavior).where(Behavior.cti_event_id == row.id)).all()
        item["behavior_count"] = len(behaviors)
        item["ioc_count"] = (
            len(row.normalized_event.get("attributes", []))
            if isinstance(row.normalized_event, dict)
            else 0
        )
        item["confidence"] = max((behavior.confidence for behavior in behaviors), default=0.0)
        item["severity"] = (
            "high"
            if item["confidence"] >= 0.75
            else "medium"
            if item["confidence"] >= 0.45
            else "low"
        )
        workflow = db.scalar(select(Workflow).where(Workflow.cti_event_id == row.id))
        item["workflow_status"] = workflow.status if workflow else None
        current_run = (
            db.scalars(
                select(GraphRun)
                .where(GraphRun.workflow_id == workflow.id)
                .order_by(GraphRun.created_at.desc())
            ).first()
            if workflow
            else None
        )
        item["current_graph_run_id"] = current_run.id if current_run else None
        item["graph_status"] = current_run.status if current_run else None
        item["elapsed_ms"] = current_run.duration_ms if current_run else None
        behavior_ids = [behavior.id for behavior in behaviors]
        mappings = (
            db.scalars(
                select(AttackMapping).where(
                    AttackMapping.behavior_id.in_(behavior_ids), AttackMapping.verified.is_(True)
                )
            ).all()
            if behavior_ids
            else []
        )
        item["attack_techniques"] = sorted({mapping.technique_id for mapping in mappings})
        proposals_for_event = (
            db.scalars(select(Proposal).where(Proposal.workflow_id == workflow.id)).all()
            if workflow
            else []
        )
        item["proposal_state"] = proposals_for_event[0].status if proposals_for_event else None
        item["proposal_id"] = proposals_for_event[0].id if proposals_for_event else None
        decisions = (
            db.scalars(
                select(PolicyDecision)
                .where(PolicyDecision.workflow_id == workflow.id)
                .order_by(PolicyDecision.created_at.desc())
            ).all()
            if workflow
            else []
        )
        item["policy_outcomes"] = [decision.decision for decision in decisions]
        item["final_policy_outcome"] = decisions[0].decision if decisions else None
        item["terminal_reason"] = workflow.terminal_reason if workflow else None
        items.append(item)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/cti-events/{event_id}")
def cti_event(
    event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    event = db.get(CtiEvent, event_id)
    if event is None:
        raise HTTPException(404, "CTI event not found")
    return to_dict(event)


@router.post("/cti-events/{event_id}/run-workflow")
def run_detection_workflow(
    event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    event = db.get(CtiEvent, event_id)
    if event is None:
        raise HTTPException(404, "CTI event not found")
    workflow = db.scalar(select(Workflow).where(Workflow.cti_event_id == event_id))
    if workflow is None:
        workflow = Workflow(cti_event_id=event_id)
        db.add(workflow)
        db.commit()
        db.refresh(workflow)
    running = db.scalar(
        select(GraphRun).where(
            GraphRun.workflow_id == workflow.id, GraphRun.status == GraphRunStatus.running
        )
    )
    if running:
        raise HTTPException(409, f"Workflow already running in graph run {running.id}")
    try:
        graph_run = DetectionEngineeringGraph(db).run(workflow.id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(500, str(exc)) from exc
    return {
        "status": "workflow_completed",
        "workflow_id": workflow.id,
        "graph_run_id": graph_run.id,
        "graph_status": graph_run.status,
    }


@router.post("/cti-events/{event_id}/reprocess")
def reprocess_cti_event(
    event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    return run_detection_workflow(event_id, db, _)


@router.get("/misp/events", response_model=ListResponse)
def misp_events(
    limit: int = Query(50, le=100),
    status: str = Query("all", pattern="^(all|actionable|new)$"),
    deduplicate: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    try:
        items = MispApiService(db).list_events(limit, status_filter=status, deduplicate=deduplicate)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, f"MISP event listing failed: {exc}") from exc
    return ListResponse(items=items, total=len(items), limit=limit, offset=0)


@router.get("/misp/events/{misp_event_id}")
def misp_event_detail(
    misp_event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    try:
        return MispApiService(db).fetch_event(misp_event_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, f"MISP event fetch failed: {exc}") from exc


@router.post("/misp/events/{misp_event_id}/ingest")
def ingest_misp_event(
    misp_event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    try:
        event, workflow, created = MispApiService(db).ingest_event(misp_event_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, f"MISP event ingestion failed: {exc}") from exc
    graph_task_id = None
    if created:
        graph_task = run_graph.delay(workflow.id)
        graph_task_id = graph_task.id
    return {
        "status": "created_and_queued" if created else "already_ingested",
        "cti_event_id": event.id,
        "workflow_id": workflow.id,
        "misp_event_id": event.misp_event_id,
        "graph_task_id": graph_task_id,
    }


@router.post("/misp/events/ingest-all-new")
def ingest_all_new_misp_events(
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    try:
        result = MispApiService(db).ingest_all_new(limit)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, f"MISP bulk ingestion failed: {exc}") from exc
    graph_task_ids = []
    for workflow_id in result.get("workflow_ids", []):
        graph_task_ids.append(run_graph.delay(workflow_id).id)
    return {"status": "completed", **result, "graph_task_ids": graph_task_ids}


@router.get("/misp/ingestion-schedule")
def get_misp_ingestion_schedule(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> dict[str, Any]:
    return MispIngestionScheduleService(db).get()


@router.post("/misp/ingestion-schedule")
def update_misp_ingestion_schedule(
    payload: MispIngestionScheduleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    return MispIngestionScheduleService(db).update(payload.model_dump())


@router.get("/graph-runs", response_model=ListResponse)
def graph_runs(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(GraphRun)) or 0
    rows = db.scalars(
        select(GraphRun).order_by(GraphRun.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = to_dict(row)
        workflow = db.get(Workflow, row.workflow_id)
        item["cti_event_id"] = workflow.cti_event_id if workflow else None
        item["trigger_source"] = "analyst_resume" if row.resume_from_node else "cti_ingestion"
        item["selected_route"] = row.current_node
        item["terminal_result"] = workflow.status if workflow else None
        item["terminal_reason"] = workflow.terminal_reason if workflow else row.failure_reason
        items.append(item)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/graph-runs/{run_id}")
def graph_run(
    run_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    run = db.get(GraphRun, run_id)
    if run is None:
        raise HTTPException(404, "Graph run not found")
    return to_dict(run)


@router.get("/graph-runs/{run_id}/timeline", response_model=ListResponse)
def graph_timeline(
    run_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    rows = db.scalars(
        select(GraphNodeRun)
        .where(GraphNodeRun.graph_run_id == run_id)
        .order_by(GraphNodeRun.started_at)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = to_dict(row)
        ai = db.scalar(select(AiInteraction).where(AiInteraction.graph_node_run_id == row.id))
        if ai:
            item["ai_usage"] = {
                "provider": ai.provider,
                "model": ai.model,
                "prompt_version": ai.prompt_version,
                "tokens": ai.total_tokens,
                "cost": ai.estimated_cost,
                "latency_ms": ai.latency_ms,
                "fixture": ai.provider == "fixture",
            }
        output = row.output_snapshot or {}
        item["selected_route"] = (
            output.get("policy_decision")
            or output.get("terminal_status")
            or output.get("analyst_action")
        )
        item["terminal_reason"] = output.get("terminal_status") or row.failure_reason
        item["proposal_id"] = output.get("proposal_id")
        items.append(item)
    return ListResponse(items=items, total=len(items), limit=len(items), offset=0)


@router.get("/graph-runs/{run_id}/events")
def graph_events(
    run_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> StreamingResponse:
    def stream() -> Any:
        run = db.get(GraphRun, run_id)
        if run is None:
            yield "event: error\ndata: graph_run_not_found\n\n"
        else:
            yield f"event: graph\ndata: {run.current_node or 'pending'}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/ai/dashboard")
def ai_dashboard(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> dict[str, Any]:
    session = db.scalars(
        select(AiReasoningSession).order_by(AiReasoningSession.started_at.desc())
    ).first()
    if session is None:
        return {
            "current_session": None,
            "watcher_status": {},
            "revisions": [],
            "confidence_timeline": [],
            "trust_timeline": [],
            "reasoning_timeline": [],
            "provider": None,
            "tokens": 0,
            "latency_ms": None,
            "consumption": ConsumptionStatusService(db).summary(),
            "limits": {
                "confidence_target": get_settings().reasoning_confidence_target,
                "trust_target": get_settings().reasoning_trust_target,
            },
        }
    watchers = db.scalars(
        select(AiWatcherResult)
        .where(AiWatcherResult.session_id == session.id)
        .order_by(AiWatcherResult.created_at.desc())
    ).all()
    revisions = db.scalars(
        select(AiReasoningRevision)
        .where(AiReasoningRevision.session_id == session.id)
        .order_by(AiReasoningRevision.created_at)
    ).all()
    confidence = db.scalars(
        select(AiConfidenceEvent)
        .where(AiConfidenceEvent.session_id == session.id)
        .order_by(AiConfidenceEvent.created_at)
    ).all()
    interactions = db.scalars(
        select(AiInteraction)
        .where(AiInteraction.graph_run_id == session.graph_run_id)
        .order_by(AiInteraction.created_at)
    ).all()
    watcher_counts: dict[str, int] = {}
    for watcher in watchers:
        watcher_counts[watcher.status] = watcher_counts.get(watcher.status, 0) + 1
    return {
        "current_session": to_dict(session),
        "watcher_status": watcher_counts,
        "watchers": [to_dict(row) for row in watchers[:50]],
        "revisions": [to_dict(row) for row in revisions],
        "confidence_timeline": [to_dict(row) for row in confidence],
        "trust_timeline": (session.session_summary or {}).get("trust_progression", []),
        "reasoning_timeline": [to_dict(row) for row in revisions]
        + [to_dict(row) for row in confidence],
        "provider": interactions[-1].provider if interactions else None,
        "model": interactions[-1].model if interactions else None,
        "tokens": sum(interaction.total_tokens for interaction in interactions),
        "latency_ms": sum((interaction.latency_ms or 0) for interaction in interactions)
        if interactions
        else None,
        "termination_reason": session.termination_reason,
        "consumption": ConsumptionStatusService(db).summary(),
        "limits": {
            "confidence_target": get_settings().reasoning_confidence_target,
            "trust_target": get_settings().reasoning_trust_target,
        },
    }


@router.get("/ai/sessions", response_model=ListResponse)
def ai_sessions(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(AiReasoningSession)) or 0
    rows = db.scalars(
        select(AiReasoningSession)
        .order_by(AiReasoningSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ListResponse(
        items=[to_dict(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/ai/sessions/{session_id}")
def ai_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    session = db.get(AiReasoningSession, session_id)
    if session is None:
        raise HTTPException(404, "AI reasoning session not found")
    return {
        "session": to_dict(session),
        "revisions": [
            to_dict(row)
            for row in db.scalars(
                select(AiReasoningRevision)
                .where(AiReasoningRevision.session_id == session_id)
                .order_by(AiReasoningRevision.created_at)
            ).all()
        ],
        "watchers": [
            to_dict(row)
            for row in db.scalars(
                select(AiWatcherResult)
                .where(AiWatcherResult.session_id == session_id)
                .order_by(AiWatcherResult.created_at)
            ).all()
        ],
        "confidence_events": [
            to_dict(row)
            for row in db.scalars(
                select(AiConfidenceEvent)
                .where(AiConfidenceEvent.session_id == session_id)
                .order_by(AiConfidenceEvent.created_at)
            ).all()
        ],
    }


@router.get("/ai/workflow")
def ai_workflow(
    graph_run_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    run = (
        db.get(GraphRun, graph_run_id)
        if graph_run_id
        else db.scalars(select(GraphRun).order_by(GraphRun.created_at.desc())).first()
    )
    session = (
        db.scalar(select(AiReasoningSession).where(AiReasoningSession.graph_run_id == run.id))
        if run
        else None
    )
    if run and session is None:
        session = db.scalars(
            select(AiReasoningSession)
            .where(AiReasoningSession.workflow_id == run.workflow_id)
            .order_by(AiReasoningSession.started_at.desc())
        ).first()
    nodes = []
    for descriptor in AI_WORKFLOW_NODES:
        node_name = descriptor["node"]
        node_run = (
            db.scalars(
                select(GraphNodeRun)
                .where(GraphNodeRun.graph_run_id == run.id, GraphNodeRun.node_name == node_name)
                .order_by(GraphNodeRun.started_at.desc())
            ).first()
            if run
            else None
        )
        confidence = (
            db.scalars(
                select(AiConfidenceEvent)
                .where(
                    AiConfidenceEvent.graph_run_id == run.id,
                    AiConfidenceEvent.node_name == node_name,
                )
                .order_by(AiConfidenceEvent.created_at.desc())
            ).first()
            if run
            else None
        )
        watchers = (
            db.scalars(
                select(AiWatcherResult)
                .where(
                    AiWatcherResult.graph_run_id == run.id, AiWatcherResult.node_name == node_name
                )
                .order_by(AiWatcherResult.created_at.desc())
            ).all()
            if run
            else []
        )
        nodes.append(
            {
                **descriptor,
                "stage": descriptor.get("stage", node_name),
                "runtime_mapping": node_name,
                "status": node_run.status if node_run else "not_started",
                "execution_time_ms": node_run.duration_ms if node_run else None,
                "confidence": confidence.confidence_score if confidence else None,
                "watcher_failures": sum(1 for watcher in watchers if watcher.status == "FAIL"),
                "watcher_warnings": sum(1 for watcher in watchers if watcher.status == "WARNING"),
                "graph_node_run_id": node_run.id if node_run else None,
            }
        )
    return {
        "graph_run": to_dict(run) if run else None,
        "session": to_dict(session) if session else None,
        "routes": {
            "satisfied": "queue_review when validation succeeds",
            "not_satisfied": "repair_candidate until repair limit or no meaningful improvement",
            "manual_resume": "approved or repair_candidate from analyst review",
        },
        "limits": {
            "max_revisions": get_settings().reasoning_max_revisions,
            "max_repair_attempts": get_settings().max_repair_attempts,
            "min_improvement_delta": get_settings().reasoning_min_improvement_delta,
            "confidence_target": get_settings().reasoning_confidence_target,
            "trust_target": get_settings().reasoning_trust_target,
        },
        "nodes": nodes,
    }


@router.get("/ai/consumption")
def ai_consumption(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> dict[str, Any]:
    return ConsumptionStatusService(db).summary()


@router.get("/proposals", response_model=ListResponse)
def proposals(
    limit: int = Query(50, le=100),
    offset: int = 0,
    deduplicate: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(Proposal)) or 0
    rows = db.scalars(
        select(Proposal).order_by(Proposal.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = to_dict(row)
        behavior = db.get(Behavior, row.behavior_id)
        item["behavior_summary"] = behavior.summary if behavior else None
        mappings = db.scalars(
            select(AttackMapping).where(
                AttackMapping.behavior_id == row.behavior_id, AttackMapping.verified.is_(True)
            )
        ).all()
        item["attack_techniques"] = [mapping.technique_id for mapping in mappings]
        items.append(item)
    if deduplicate:
        items = collapse_duplicate_proposals(items)
        total = len(items)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/proposals/{proposal_id}")
def proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    item = db.get(Proposal, proposal_id)
    if item is None:
        raise HTTPException(404, "Proposal not found")
    return to_dict(item)


@router.get("/proposals/{proposal_id}/workspace")
def proposal_workspace(
    proposal_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    behavior = db.get(Behavior, proposal.behavior_id)
    workflow = db.get(Workflow, proposal.workflow_id)
    event = db.get(CtiEvent, workflow.cti_event_id) if workflow else None
    attack = db.scalars(
        select(AttackMapping).where(AttackMapping.behavior_id == proposal.behavior_id)
    ).all()
    coverage = db.scalars(
        select(CoverageResult).where(CoverageResult.behavior_id == proposal.behavior_id)
    ).all()
    visibility = db.scalars(
        select(VisibilityResult).where(VisibilityResult.behavior_id == proposal.behavior_id)
    ).all()
    revisions = db.scalars(
        select(ProposalRevision)
        .where(ProposalRevision.proposal_id == proposal_id)
        .order_by(ProposalRevision.revision_number)
    ).all()
    validations = []
    for revision in revisions:
        validation = db.scalar(
            select(ValidationResult).where(ValidationResult.proposal_revision_id == revision.id)
        )
        if validation:
            validations.append(to_dict(validation))
    actions = db.scalars(
        select(ReviewAction)
        .where(ReviewAction.proposal_id == proposal_id)
        .order_by(ReviewAction.created_at)
    ).all()
    graph_runs_for_workflow = db.scalars(
        select(GraphRun)
        .where(GraphRun.workflow_id == proposal.workflow_id)
        .order_by(GraphRun.created_at)
    ).all()
    artifacts = db.scalars(
        select(DeploymentArtifact)
        .where(DeploymentArtifact.proposal_id == proposal_id)
        .order_by(DeploymentArtifact.created_at)
    ).all()
    policies = db.scalars(
        select(PolicyDecision)
        .where(PolicyDecision.behavior_id == proposal.behavior_id)
        .order_by(PolicyDecision.created_at)
    ).all()
    ai_interactions = db.scalars(
        select(AiInteraction)
        .join(GraphNodeRun, AiInteraction.graph_node_run_id == GraphNodeRun.id)
        .join(GraphRun, GraphNodeRun.graph_run_id == GraphRun.id)
        .where(GraphRun.workflow_id == proposal.workflow_id)
        .order_by(AiInteraction.created_at)
    ).all()
    return {
        "proposal": to_dict(proposal),
        "cti_event": to_dict(event) if event else None,
        "workflow": to_dict(workflow) if workflow else None,
        "behavior": to_dict(behavior) if behavior else None,
        "attack_mappings": [to_dict(row) for row in attack],
        "coverage_results": [to_dict(row) for row in coverage],
        "visibility_results": [to_dict(row) for row in visibility],
        "revisions": [to_dict(row) for row in revisions],
        "validation_results": validations,
        "review_actions": [to_dict(row) for row in actions],
        "graph_runs": [to_dict(row) for row in graph_runs_for_workflow],
        "deployment_artifacts": [to_dict(row) for row in artifacts],
        "policy_decisions": [to_dict(row) for row in policies],
        "ai_interactions": [to_dict(row) for row in ai_interactions],
    }


@router.get("/proposals/{proposal_id}/revisions", response_model=ListResponse)
def proposal_revisions(
    proposal_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    rows = db.scalars(
        select(ProposalRevision)
        .where(ProposalRevision.proposal_id == proposal_id)
        .order_by(ProposalRevision.revision_number)
    ).all()
    return ListResponse(
        items=[to_dict(row) for row in rows], total=len(rows), limit=len(rows), offset=0
    )


@router.get("/proposal-revisions/{revision_id}/validation")
def revision_validation(
    revision_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    result = db.scalar(
        select(ValidationResult).where(ValidationResult.proposal_revision_id == revision_id)
    )
    if result is None:
        raise HTTPException(404, "Validation result not found")
    return to_dict(result)


@router.post("/proposals/{proposal_id}/approve")
def approve(
    proposal_id: str,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    revision = latest_revision(db, proposal_id)
    if payload.revision_number and payload.revision_number != revision.revision_number:
        raise HTTPException(409, "Stale revision")
    validation = latest_validation(db, revision.id)
    if (
        not validation.schema_valid
        or not validation.sigma_valid
        or not validation.compilation_success
    ):
        raise HTTPException(422, "Current revision is not validated for approval")
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status not in {
        ProposalStatus.ready_review,
        ProposalStatus.approved,
        ProposalStatus.deployed,
    }:
        raise HTTPException(409, f"Proposal cannot be approved from status {proposal.status}")
    if proposal.status == ProposalStatus.deployed:
        artifact = db.scalars(
            select(DeploymentArtifact)
            .where(
                DeploymentArtifact.proposal_id == proposal_id,
                DeploymentArtifact.proposal_revision_id == revision.id,
            )
            .order_by(DeploymentArtifact.created_at.desc())
        ).first()
        return {
            "status": "approved",
            "graph_run_id": None,
            "proposal_id": proposal_id,
            "artifact_id": artifact.id if artifact else None,
            "idempotent": True,
        }
    existing_action = db.scalars(
        select(ReviewAction)
        .where(
            ReviewAction.proposal_id == proposal_id,
            ReviewAction.proposal_revision_id == revision.id,
            ReviewAction.action == ReviewActionType.approve,
        )
        .order_by(ReviewAction.created_at.desc())
    ).first()
    if existing_action and proposal.status == ProposalStatus.approved:
        return {
            "status": "approved",
            "graph_run_id": None,
            "proposal_id": proposal_id,
            "artifact_id": None,
            "idempotent": True,
        }
    db.add(
        ReviewAction(
            proposal_id=proposal_id,
            proposal_revision_id=revision.id,
            analyst_id=user.id,
            action=ReviewActionType.approve,
            comment=payload.comment,
        )
    )
    db.commit()
    try:
        graph_run = DetectionEngineeringGraph(db).run(revision.workflow_id, "approved", proposal_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(500, str(exc)) from exc
    artifacts = db.scalars(
        select(DeploymentArtifact)
        .where(DeploymentArtifact.proposal_id == proposal_id)
        .order_by(DeploymentArtifact.created_at.desc())
    ).all()
    return {
        "status": "approved",
        "graph_run_id": graph_run.id,
        "proposal_id": proposal_id,
        "artifact_id": artifacts[0].id if artifacts else None,
    }


@router.post("/proposals/{proposal_id}/request-changes")
def request_changes(
    proposal_id: str,
    payload: RequestChangesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    revision = latest_revision(db, proposal_id)
    if payload.revision_number and payload.revision_number != revision.revision_number:
        raise HTTPException(409, "Stale revision")
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != ProposalStatus.ready_review:
        raise HTTPException(409, f"Proposal cannot request changes from status {proposal.status}")
    db.add(
        ReviewAction(
            proposal_id=proposal_id,
            proposal_revision_id=revision.id,
            analyst_id=user.id,
            action=ReviewActionType.request_changes,
            comment=payload.comment,
        )
    )
    proposal.status = ProposalStatus.changes_requested
    db.commit()
    try:
        graph_run = DetectionEngineeringGraph(db).run(
            revision.workflow_id, "repair_candidate", proposal_id, payload.comment
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(500, str(exc)) from exc
    refreshed = db.get(Proposal, proposal_id)
    if refreshed is None:
        raise HTTPException(404, "Proposal not found after repair")
    return {
        "status": "changes_requested_repaired",
        "graph_run_id": graph_run.id,
        "proposal_id": proposal_id,
        "current_revision_number": refreshed.current_revision_number,
    }


@router.post("/proposals/{proposal_id}/reject")
def reject(
    proposal_id: str,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    revision = latest_revision(db, proposal_id)
    if payload.revision_number and payload.revision_number != revision.revision_number:
        raise HTTPException(409, "Stale revision")
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status == ProposalStatus.rejected:
        return {
            "status": "rejected",
            "graph_run_id": None,
            "proposal_id": proposal_id,
            "idempotent": True,
        }
    if proposal.status not in {ProposalStatus.ready_review, ProposalStatus.changes_requested}:
        raise HTTPException(409, f"Proposal cannot be rejected from status {proposal.status}")
    db.add(
        ReviewAction(
            proposal_id=proposal_id,
            proposal_revision_id=revision.id,
            analyst_id=user.id,
            action=ReviewActionType.reject,
            comment=payload.comment,
        )
    )
    db.commit()
    try:
        graph_run = DetectionEngineeringGraph(db).run(revision.workflow_id, "approved", proposal_id)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"status": "rejected", "graph_run_id": graph_run.id, "proposal_id": proposal_id}


@router.get("/telemetry-sources", response_model=ListResponse)
def telemetry_sources(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    return page(db, TelemetrySource, limit, offset)


@router.post("/telemetry-sources")
def create_telemetry(
    payload: TelemetrySourceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> dict[str, Any]:
    item = TelemetrySource(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return to_dict(item)


@router.patch("/telemetry-sources/{source_id}")
def update_telemetry(
    source_id: str,
    payload: TelemetrySourceCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> dict[str, Any]:
    item = db.get(TelemetrySource, source_id)
    if item is None:
        raise HTTPException(404, "Telemetry source not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return to_dict(item)


@router.get("/detections", response_model=ListResponse)
def detections(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(DetectionCatalog)) or 0
    rows = db.scalars(
        select(DetectionCatalog)
        .order_by(DetectionCatalog.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = to_dict(row)
        mappings = db.scalars(
            select(DetectionAttackMapping).where(DetectionAttackMapping.detection_id == row.id)
        ).all()
        item["attack_mappings"] = [
            {"technique_id": mapping.technique_id, "tactic_id": mapping.tactic_id}
            for mapping in mappings
        ]
        item["proposal_id"] = (
            row.normalized_logic.get("proposal_id")
            if isinstance(row.normalized_logic, dict)
            else None
        )
        item["revision_number"] = (
            row.normalized_logic.get("revision_number")
            if isinstance(row.normalized_logic, dict)
            else None
        )
        item["compiled_query"] = (
            row.normalized_logic.get("compiled_outputs", {}).get("query")
            if isinstance(row.normalized_logic, dict)
            else None
        )
        item["quality_score"] = (
            row.normalized_logic.get("quality_score")
            if isinstance(row.normalized_logic, dict)
            else None
        )
        items.append(item)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/detections/{detection_id}")
def detection_detail(
    detection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    item = db.get(DetectionCatalog, detection_id)
    if item is None:
        raise HTTPException(404, "Detection not found")
    result = to_dict(item)
    mappings = db.scalars(
        select(DetectionAttackMapping).where(DetectionAttackMapping.detection_id == item.id)
    ).all()
    result["attack_mappings"] = [
        {"technique_id": mapping.technique_id, "tactic_id": mapping.tactic_id}
        for mapping in mappings
    ]
    return result


@router.post("/detections/import")
def import_detection(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> dict[str, Any]:
    from app.models.enums import DetectionStatus, DetectionType
    from app.models.models import DetectionCatalog
    from app.services.fingerprinting import fingerprint_behavior

    content = str(payload.get("content", ""))
    if not content:
        raise HTTPException(422, "Detection content is required")
    normalized_logic = payload.get("normalized_logic") or {"content": content}
    detection = DetectionCatalog(
        name=str(payload.get("name", "Imported Detection")),
        detection_type=DetectionType(str(payload.get("detection_type", "sigma"))),
        source=str(payload.get("source", "admin_import")),
        content=content,
        normalized_logic=normalized_logic,
        behavior_fingerprint=fingerprint_behavior(normalized_logic),
        status=DetectionStatus(str(payload.get("status", "active"))),
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)
    return to_dict(detection)


@router.get("/attack/coverage")
def attack_coverage(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> ListResponse:
    techniques = db.scalars(select(AttackTechnique).order_by(AttackTechnique.technique_id)).all()
    items: list[dict[str, Any]] = []
    for technique in techniques:
        detection_mappings = db.scalars(
            select(DetectionAttackMapping).where(
                DetectionAttackMapping.technique_id == technique.technique_id
            )
        ).all()
        verified_behavior_count = (
            db.scalar(
                select(func.count())
                .select_from(AttackMapping)
                .where(
                    AttackMapping.technique_id == technique.technique_id,
                    AttackMapping.verified.is_(True),
                )
            )
            or 0
        )
        items.append(
            {
                "technique_id": technique.technique_id,
                "name": technique.name,
                "tactics": technique.tactics,
                "platforms": technique.platforms,
                "coverage_status": "covered" if detection_mappings else "not_covered",
                "linked_detection_ids": [mapping.detection_id for mapping in detection_mappings],
                "recent_behavior_count": verified_behavior_count,
            }
        )
    return ListResponse(items=items, total=len(items), limit=len(items), offset=0)


@router.get("/policy-decisions", response_model=ListResponse)
def policy_decisions(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    total = db.scalar(select(func.count()).select_from(PolicyDecision)) or 0
    rows = db.scalars(
        select(PolicyDecision)
        .order_by(PolicyDecision.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ListResponse(
        items=[to_dict(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/attack/techniques/{technique_id}")
def attack_technique(
    technique_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    item = db.get(AttackTechnique, technique_id)
    if item is None:
        raise HTTPException(404, "Technique not found")
    return to_dict(item)


@router.get("/automation-runs", response_model=ListResponse)
def automation_runs(
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> ListResponse:
    return graph_runs(limit, offset, db, _)


@router.get("/system-health", response_model=ListResponse)
def system_health(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin, UserRole.analyst))
) -> ListResponse:
    settings = get_settings()
    misp_status = MispConnectivityService(db).check()
    sigma_health = SigmaValidationService().health_probe()
    deepseek_configured = bool(
        settings.deepseek_api_key and settings.deepseek_api_key.get_secret_value().strip()
    )
    ai_status = (
        "fixture"
        if settings.ai_fixture_mode
        else "live_configured"
        if deepseek_configured
        else "live_blocked_missing_credentials"
    )
    items: list[dict[str, Any]] = [
        {"component": "backend", "status": "healthy", "details": {"api": "responding"}},
        {"component": "postgresql", "status": "healthy", "details": {"query": "select 1"}},
        {
            "component": "ai_provider",
            "status": ai_status,
            "details": {
                "model": settings.deepseek_model,
                "fixture_mode": settings.ai_fixture_mode,
                "live_configured": deepseek_configured,
                "live_blocked_missing_credentials": (
                    not settings.ai_fixture_mode and not deepseek_configured
                ),
            },
        },
        {"component": "misp_api", "status": misp_status["status"], "details": misp_status},
        {
            "component": "pysigma",
            "status": sigma_health["status"],
            "details": {"sigma_target": settings.sigma_target, **sigma_health["details"]},
        },
        {
            "component": "nginx",
            "status": "external",
            "details": {"ingress": "http://localhost:8080"},
        },
    ]
    try:
        Redis.from_url(settings.redis_url).ping()
        items.append(
            {"component": "redis", "status": "healthy", "details": {"broker": "reachable"}}
        )
    except RedisError as exc:
        items.append({"component": "redis", "status": "unhealthy", "details": {"error": str(exc)}})
    persisted = db.scalars(
        select(SystemHealthCheck).order_by(SystemHealthCheck.checked_at.desc()).limit(20)
    ).all()
    items.extend(to_dict(row) for row in persisted)
    return ListResponse(items=items, total=len(items), limit=len(items), offset=0)


@router.get("/settings", response_model=ListResponse)
def settings(
    db: Session = Depends(get_db), _: User = Depends(require_role(UserRole.admin))
) -> ListResponse:
    return page(db, Setting, 100, 0)


@router.patch("/settings/{key}")
def update_setting(
    key: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> dict[str, Any]:
    item = db.get(Setting, key)
    if item is None:
        item = Setting(key=key, value=payload.value)
        db.add(item)
    else:
        item.value = payload.value
    db.commit()
    return to_dict(item)


@router.get("/deployment-artifacts/{artifact_id}")
def deployment_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> dict[str, Any]:
    item = db.get(DeploymentArtifact, artifact_id)
    if item is None:
        raise HTTPException(404, "Artifact not found")
    return to_dict(item)


@router.get("/deployment-artifacts/{artifact_id}/download")
def download_deployment_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.analyst)),
) -> FileResponse:
    item = db.get(DeploymentArtifact, artifact_id)
    if item is None:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(
        item.file_path, media_type="application/x-yaml", filename=f"{artifact_id}.yml"
    )


def latest_revision(db: Session, proposal_id: str) -> ProposalRevision:
    revision = db.scalars(
        select(ProposalRevision)
        .where(ProposalRevision.proposal_id == proposal_id)
        .order_by(ProposalRevision.revision_number.desc())
    ).first()
    if revision is None:
        raise HTTPException(404, "Proposal revision not found")
    return revision


def latest_validation(db: Session, revision_id: str) -> ValidationResult:
    validation = db.scalar(
        select(ValidationResult).where(ValidationResult.proposal_revision_id == revision_id)
    )
    if validation is None:
        raise HTTPException(404, "Validation result not found")
    return validation
