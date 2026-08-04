from enum import StrEnum


class UserRole(StrEnum):
    admin = "Admin"
    analyst = "Analyst"


class CtiEventStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_repair = "waiting_repair"
    ready_review = "ready_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"
    covered = "covered"
    visibility_gap = "visibility_gap"
    insufficient_evidence = "insufficient_evidence"


class WorkflowStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_review = "waiting_review"
    approved = "approved"
    deployed = "deployed"
    rejected = "rejected"
    failed = "failed"
    completed = "completed"


class GraphRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class NodeStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class ProposalStatus(StrEnum):
    ready_review = "ready_review"
    approved = "approved"
    changes_requested = "changes_requested"
    rejected = "rejected"
    superseded = "superseded"
    deployed = "deployed"


class ReviewActionType(StrEnum):
    approve = "approve"
    request_changes = "request_changes"
    reject = "reject"


class CoverageStatus(StrEnum):
    covered = "covered"
    partial = "partial"
    not_covered = "not_covered"


class VisibilityStatus(StrEnum):
    visible = "visible"
    partial = "partial"
    gap = "gap"


class DetectionType(StrEnum):
    sigma = "sigma"
    spl = "spl"
    kql = "kql"
    yara = "yara"
    other = "other"


class DetectionStatus(StrEnum):
    active = "active"
    deprecated = "deprecated"
    draft = "draft"


class PolicyDecisionValue(StrEnum):
    already_covered = "already_covered"
    visibility_gap = "visibility_gap"
    insufficient_evidence = "insufficient_evidence"
    generate_candidate = "generate_candidate"
