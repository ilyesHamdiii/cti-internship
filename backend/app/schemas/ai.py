from typing import Literal

from pydantic import BaseModel, Field


class EvidenceRef(BaseModel):
    ref: str
    excerpt: str
    source_field: str


class StructuredJustification(BaseModel):
    decision_factors: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    attack_rationale: list[str] = Field(default_factory=list)
    coverage_rationale: list[str] = Field(default_factory=list)
    telemetry_rationale: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    uncertainties: list[str] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)


class ProposedAttackMapping(BaseModel):
    technique_id: str
    technique_name: str
    tactic_id: str
    tactic_name: str
    evidence_refs: list[EvidenceRef]
    confidence: float = Field(ge=0, le=1)


class BehaviorCandidate(BaseModel):
    behavior_key: str | None = None
    summary: str
    behavior_type: str
    actor_action: str = ""
    target: str = ""
    execution_mechanism: str = ""
    evidence_refs: list[EvidenceRef]
    observables: list[dict[str, str]]
    proposed_attack_mappings: list[ProposedAttackMapping]
    required_telemetry: list[dict[str, object]]
    confidence: float = Field(ge=0, le=1)
    uncertainties: list[str] = Field(default_factory=list)


class CtiAnalysisResponse(BaseModel):
    behaviors: list[BehaviorCandidate]
    structured_justification: StructuredJustification


class SigmaCandidate(BaseModel):
    title: str
    id: str | None = None
    status: Literal["experimental", "test", "stable"] = "experimental"
    description: str
    author: str | None = None
    date: str | None = None
    references: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    logsource: dict[str, str]
    detection: dict[str, object]
    fields: list[str] = Field(default_factory=list)
    falsepositives: list[str] = Field(default_factory=list)
    level: Literal["low", "medium", "high", "critical"] = "medium"


class SigmaGenerationResponse(BaseModel):
    sigma: SigmaCandidate
    detection_intent: list[str]
    false_positive_notes: list[str]
    structured_justification: StructuredJustification
    confidence: float = Field(ge=0, le=1)
    uncertainties: list[str] = Field(default_factory=list)


class SigmaRepairResponse(SigmaGenerationResponse):
    addressed_failures: list[str]
    instruction_interpretation: str = ""
    fields_changed: list[str] = Field(default_factory=list)
    selections_added: dict[str, object] = Field(default_factory=dict)
    selections_removed: dict[str, object] = Field(default_factory=dict)
    selections_modified: dict[str, object] = Field(default_factory=dict)
    validation_failures_addressed: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    detection_value_evidence: list[dict[str, object]] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
