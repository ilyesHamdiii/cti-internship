from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    CoverageStatus,
    CtiEventStatus,
    DetectionStatus,
    DetectionType,
    GraphRunStatus,
    NodeStatus,
    PolicyDecisionValue,
    ProposalStatus,
    ReviewActionType,
    UserRole,
    VisibilityStatus,
    WorkflowStatus,
)


def now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class CtiEvent(Base):
    __tablename__ = "cti_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    misp_event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="misp")
    title: Mapped[str | None] = mapped_column(String(500))
    raw_event: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_event: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[CtiEventStatus] = mapped_column(
        Enum(CtiEventStatus), default=CtiEventStatus.pending, nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )

    workflow: Mapped["Workflow"] = relationship(back_populates="cti_event", uselist=False)
    behaviors: Mapped[list["Behavior"]] = relationship(back_populates="cti_event")


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    cti_event_id: Mapped[str] = mapped_column(
        ForeignKey("cti_events.id"), unique=True, nullable=False
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus), default=WorkflowStatus.pending, nullable=False
    )
    terminal_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    cti_event: Mapped[CtiEvent] = relationship(back_populates="workflow")
    graph_runs: Mapped[list["GraphRun"]] = relationship(back_populates="workflow")


class GraphRun(Base):
    __tablename__ = "graph_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    resume_from_node: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[GraphRunStatus] = mapped_column(
        Enum(GraphRunStatus), default=GraphRunStatus.pending, nullable=False
    )
    current_node: Mapped[str | None] = mapped_column(String(100))
    previous_node: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)

    workflow: Mapped[Workflow] = relationship(back_populates="graph_runs")


class GraphNodeRun(Base):
    __tablename__ = "graph_node_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_node: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus), default=NodeStatus.pending, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(Text)


class AiInteraction(Base):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ai_interaction_idempotency_key"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    graph_node_run_id: Mapped[str] = mapped_column(ForeignKey("graph_node_runs.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    structured_justification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AiReasoningSession(Base):
    __tablename__ = "ai_reasoning_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(
        ForeignKey("graph_runs.id"), unique=True, nullable=False
    )
    cti_event_id: Mapped[str] = mapped_column(ForeignKey("cti_events.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False)
    current_node: Mapped[str | None] = mapped_column(String(100))
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    approval_recommendation: Mapped[str] = mapped_column(
        String(50), default="needs_review", nullable=False
    )
    termination_reason: Mapped[str | None] = mapped_column(String(200))
    session_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class AiReasoningRevision(Base):
    __tablename__ = "ai_reasoning_revisions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_reasoning_sessions.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    parent_reasoning_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_reasoning_revisions.id")
    )
    behavior_id: Mapped[str | None] = mapped_column(ForeignKey("behaviors.id"))
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("proposals.id"))
    proposal_revision_id: Mapped[str | None] = mapped_column(ForeignKey("proposal_revisions.id"))
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    improvements: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    confidence_before: Mapped[float | None] = mapped_column(Float)
    confidence_after: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    validation_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation_delta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    termination_reason: Mapped[str | None] = mapped_column(String(200))
    candidate_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    candidate_before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    candidate_after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    watcher_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    validation_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    calculated_confidence: Mapped[float | None] = mapped_column(Float)
    trust_score: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(String(50))
    stopping_decision: Mapped[str | None] = mapped_column(String(100))
    stopping_reason: Mapped[str | None] = mapped_column(String(200))
    route_selected: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AiWatcherResult(Base):
    __tablename__ = "ai_watcher_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_reasoning_sessions.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    watcher_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class AiConfidenceEvent(Base):
    __tablename__ = "ai_confidence_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_reasoning_sessions.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100))
    confidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    factors: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Behavior(Base):
    __tablename__ = "behaviors"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    cti_event_id: Mapped[str] = mapped_column(ForeignKey("cti_events.id"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    source_graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    behavior_type: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    observables: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)

    cti_event: Mapped[CtiEvent] = relationship(back_populates="behaviors")


class AttackTechnique(Base):
    __tablename__ = "attack_techniques"

    technique_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tactics: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    data_sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)


class AttackMapping(Base):
    __tablename__ = "attack_mappings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    behavior_id: Mapped[str] = mapped_column(ForeignKey("behaviors.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(String(32), nullable=False)
    technique_name: Mapped[str] = mapped_column(String(300), nullable=False)
    tactic_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tactic_name: Mapped[str] = mapped_column(String(200), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(100), nullable=False)
    attack_version: Mapped[str | None] = mapped_column(String(50))
    verification_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class DetectionCatalog(Base):
    __tablename__ = "detection_catalog"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    detection_type: Mapped[DetectionType] = mapped_column(Enum(DetectionType), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_logic: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    behavior_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DetectionStatus] = mapped_column(
        Enum(DetectionStatus), default=DetectionStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class DetectionAttackMapping(Base):
    __tablename__ = "detection_attack_mappings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    detection_id: Mapped[str] = mapped_column(ForeignKey("detection_catalog.id"), nullable=False)
    technique_id: Mapped[str] = mapped_column(String(32), nullable=False)
    tactic_id: Mapped[str] = mapped_column(String(100), nullable=False)


class TelemetrySource(Base):
    __tablename__ = "telemetry_sources"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class DetectionTelemetryRequirement(Base):
    __tablename__ = "detection_telemetry_requirements"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    detection_id: Mapped[str] = mapped_column(ForeignKey("detection_catalog.id"), nullable=False)
    telemetry_source_id: Mapped[str] = mapped_column(
        ForeignKey("telemetry_sources.id"), nullable=False
    )
    required_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class CoverageResult(Base):
    __tablename__ = "coverage_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    behavior_id: Mapped[str] = mapped_column(ForeignKey("behaviors.id"), nullable=False)
    coverage_status: Mapped[CoverageStatus] = mapped_column(Enum(CoverageStatus), nullable=False)
    matching_detection_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    deterministic_rationale: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class VisibilityResult(Base):
    __tablename__ = "visibility_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    behavior_id: Mapped[str] = mapped_column(ForeignKey("behaviors.id"), nullable=False)
    visibility_status: Mapped[VisibilityStatus] = mapped_column(
        Enum(VisibilityStatus), nullable=False
    )
    required_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    available_source_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    deterministic_rationale: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    behavior_id: Mapped[str] = mapped_column(ForeignKey("behaviors.id"), nullable=False)
    coverage_status: Mapped[CoverageStatus] = mapped_column(Enum(CoverageStatus), nullable=False)
    visibility_status: Mapped[VisibilityStatus] = mapped_column(
        Enum(VisibilityStatus), nullable=False
    )
    evidence_sufficient: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verified_mapping_count: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[PolicyDecisionValue] = mapped_column(Enum(PolicyDecisionValue), nullable=False)
    deterministic_rationale: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    behavior_id: Mapped[str] = mapped_column(
        ForeignKey("behaviors.id"), unique=True, nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus), default=ProposalStatus.ready_review, nullable=False
    )
    current_revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class ProposalRevision(Base):
    __tablename__ = "proposal_revisions"
    __table_args__ = (
        UniqueConstraint("proposal_id", "revision_number", name="uq_revision_number"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    behavior_id: Mapped[str] = mapped_column(ForeignKey("behaviors.id"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    graph_run_id: Mapped[str] = mapped_column(ForeignKey("graph_runs.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sigma_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    sigma_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    structured_justification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    proposal_revision_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_revisions.id"), nullable=False
    )
    schema_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sigma_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    compilation_success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    duplicate_status: Mapped[str] = mapped_column(String(50), nullable=False)
    telemetry_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attack_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    compiled_outputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        UniqueConstraint("proposal_revision_id", "action", name="uq_review_action_revision_action"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    proposal_revision_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_revisions.id"), nullable=False
    )
    analyst_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[ReviewActionType] = mapped_column(Enum(ReviewActionType), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class DeploymentArtifact(Base):
    __tablename__ = "deployment_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "proposal_revision_id", "artifact_type", name="uq_deployment_artifact_revision_type"
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), nullable=False)
    proposal_revision_id: Mapped[str] = mapped_column(
        ForeignKey("proposal_revisions.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class MispPollState(Base):
    __tablename__ = "misp_poll_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_event_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    last_event_id: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, onupdate=now, nullable=False
    )


class CtiConsumptionRecord(Base):
    __tablename__ = "cti_consumption_records"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    misp_event_id: Mapped[str | None] = mapped_column(String(100))
    requested_misp_event_id: Mapped[str | None] = mapped_column(String(100))
    resolved_misp_event_id: Mapped[str | None] = mapped_column(String(100))
    cti_event_id: Mapped[str | None] = mapped_column(ForeignKey("cti_events.id"))
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id"))
    trigger_source: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_mode: Mapped[str | None] = mapped_column(String(50))
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)


class SystemHealthCheck(Base):
    __tablename__ = "system_health_checks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    component: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
