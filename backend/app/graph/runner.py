import asyncio
import hashlib
from datetime import datetime
from typing import Any, Callable

from fastapi.encoders import jsonable_encoder
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import (
    CoverageStatus,
    CtiEventStatus,
    GraphRunStatus,
    NodeStatus,
    PolicyDecisionValue,
    ProposalStatus,
    ReviewActionType,
    VisibilityStatus,
    WorkflowStatus,
)
from app.models.models import (
    AiInteraction,
    AttackMapping,
    Behavior,
    CoverageResult,
    CtiEvent,
    GraphNodeRun,
    GraphRun,
    Proposal,
    PolicyDecision,
    ProposalRevision,
    ReviewAction,
    TelemetrySource,
    ValidationResult,
    VisibilityResult,
    Workflow,
)
from app.schemas.ai import BehaviorCandidate
from app.services.ai import DeepSeekClient
from app.services.attack import AttackVerificationService
from app.services.coverage import CoverageService
from app.services.deployment import DeploymentService
from app.services.duplicates import DuplicateDetectionService
from app.services.fingerprinting import fingerprint_behavior
from app.services.policy import decide_policy
from app.services.reasoning import ConfidenceEngine, SatisfactionEngine, ReasoningService, TrustEngine, WatcherEngine
from app.services.sigma import SigmaValidationService
from app.services.telemetry import TelemetryService


class DetectionEngineeringGraph:
    nodes = [
        "consume_cti",
        "extract_behaviors",
        "verify_attack_mapping",
        "coverage_analysis",
        "visibility_analysis",
        "policy_decision",
        "generate_candidate",
        "validate_candidate",
        "repair_candidate",
        "queue_review",
        "approved",
        "deployment",
    ]

    def __init__(self, db: Session):
        self.db = db
        self.ai = DeepSeekClient()
        self.sigma = SigmaValidationService()
        self.reasoning = ReasoningService(db)
        self.watchers = WatcherEngine()
        self.confidence = ConfidenceEngine()
        self.trust = TrustEngine()
        self.satisfaction = SatisfactionEngine()
        self.compiled_graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(dict)
        graph.add_node("entry", lambda state: state)
        for name, fn in [
            ("consume_cti", self.consume_cti),
            ("extract_behaviors", self.extract_behaviors),
            ("verify_attack_mapping", self.verify_attack_mapping),
            ("coverage_analysis", self.coverage_analysis),
            ("visibility_analysis", self.visibility_analysis),
            ("policy_decision", self.policy_decision),
            ("generate_candidate", self.generate_candidate),
            ("validate_candidate", self.validate_candidate),
            ("repair_candidate", self.repair_candidate),
            ("queue_review", self.queue_review),
            ("approved", self.approved),
            ("deployment", self.deployment),
            ("terminal_covered", self.terminal_covered),
            ("terminal_visibility_gap", self.terminal_visibility_gap),
            ("terminal_insufficient_evidence", self.terminal_insufficient_evidence),
            ("terminal_failed", self.terminal_failed),
            ("terminal_rejected", self.terminal_rejected),
            ("advance_behavior", self.advance_behavior),
        ]:
            graph.add_node(name, self._langgraph_node(name, fn))
        graph.add_edge(START, "entry")
        graph.add_conditional_edges("entry", self._route_entry, {"consume_cti": "consume_cti", "repair_candidate": "repair_candidate", "approved": "approved"})
        graph.add_edge("consume_cti", "extract_behaviors")
        graph.add_conditional_edges("extract_behaviors", self._route_after_extract, {"verify_attack_mapping": "verify_attack_mapping", "terminal_insufficient_evidence": "terminal_insufficient_evidence"})
        graph.add_edge("verify_attack_mapping", "coverage_analysis")
        graph.add_edge("coverage_analysis", "visibility_analysis")
        graph.add_edge("visibility_analysis", "policy_decision")
        graph.add_conditional_edges(
            "policy_decision",
            self._route_policy,
            {
                "already_covered": "terminal_covered",
                "visibility_gap": "terminal_visibility_gap",
                "insufficient_evidence": "terminal_insufficient_evidence",
                "generate_candidate": "generate_candidate",
            },
        )
        graph.add_edge("generate_candidate", "validate_candidate")
        graph.add_conditional_edges(
            "validate_candidate",
            self._route_validation,
            {"valid": "queue_review", "repairable_invalid": "repair_candidate", "unrepairable_invalid": "terminal_failed"},
        )
        graph.add_conditional_edges("repair_candidate", self._route_repair, {"repaired": "validate_candidate", "attempts_exhausted": "terminal_failed"})
        graph.add_conditional_edges("queue_review", self._route_next_behavior, {"advance_behavior": "advance_behavior", END: END})
        graph.add_conditional_edges("terminal_covered", self._route_next_behavior, {"advance_behavior": "advance_behavior", END: END})
        graph.add_conditional_edges("terminal_visibility_gap", self._route_next_behavior, {"advance_behavior": "advance_behavior", END: END})
        graph.add_conditional_edges("terminal_insufficient_evidence", self._route_next_behavior, {"advance_behavior": "advance_behavior", END: END})
        graph.add_edge("terminal_failed", END)
        graph.add_conditional_edges("approved", self._route_approved, {"deployment": "deployment", "terminal_rejected": "terminal_rejected", "repair_candidate": "repair_candidate", END: END})
        graph.add_edge("deployment", END)
        graph.add_edge("terminal_rejected", END)
        graph.add_edge("advance_behavior", "verify_attack_mapping")
        return graph.compile()

    def _langgraph_node(self, name: str, fn: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def node(state: dict[str, Any]) -> dict[str, Any]:
            graph_run = self.db.get(GraphRun, state["graph_run_id"])
            self._run_node(graph_run, name, state, fn)
            return state

        return node

    def run(
        self,
        workflow_id: str,
        resume_from_node: str | None = None,
        proposal_id: str | None = None,
        analyst_comment: str | None = None,
    ) -> GraphRun:
        workflow = self.db.get(Workflow, workflow_id)
        if workflow is None:
            raise ValueError("workflow_not_found")
        graph_run = GraphRun(
            workflow_id=workflow_id,
            resume_from_node=resume_from_node,
            status=GraphRunStatus.running,
            started_at=datetime.utcnow(),
        )
        self.db.add(graph_run)
        workflow.status = WorkflowStatus.running
        self.db.commit()
        session = self.reasoning.start_session(workflow, graph_run, resume_from_node)
        state: dict[str, Any] = {
            "workflow_id": workflow_id,
            "graph_run_id": graph_run.id,
            "reasoning_session_id": session.id,
            "cti_event_id": workflow.cti_event_id,
            "proposal_id": proposal_id,
            "resume_from_node": resume_from_node,
            "analyst_comment": analyst_comment,
        }
        try:
            if resume_from_node in {"repair_candidate", "approved"}:
                self._inherit_context(graph_run, state, resume_from_node)
            final_state = self.compiled_graph.invoke(state)
            state.update(final_state)
            graph_run.status = GraphRunStatus.succeeded
            graph_run.finished_at = datetime.utcnow()
            graph_run.duration_ms = int((graph_run.finished_at - graph_run.started_at).total_seconds() * 1000)
            if resume_from_node == "approved" and state.get("analyst_action") == ReviewActionType.approve:
                workflow.status = WorkflowStatus.deployed
                termination_reason = "analyst_approved_deployed"
            elif resume_from_node == "approved" and state.get("analyst_action") == ReviewActionType.reject:
                workflow.status = WorkflowStatus.rejected
                termination_reason = "analyst_rejected"
            elif state.get("terminal_status") == "rejected":
                workflow.status = WorkflowStatus.rejected
                termination_reason = "rejected"
            elif state.get("terminal_status") == "covered":
                workflow.status = WorkflowStatus.completed
                termination_reason = "already_covered"
            elif state.get("terminal_status") in {"visibility_gap", "insufficient_evidence"}:
                workflow.status = WorkflowStatus.completed
                termination_reason = str(state.get("terminal_status"))
            elif state.get("terminal_status") == "failed":
                workflow.status = WorkflowStatus.failed
                termination_reason = state.get("reasoning_termination_reason") or "failed"
            else:
                workflow.status = WorkflowStatus.waiting_review
                termination_reason = state.get("reasoning_termination_reason") or "queued_for_human_review"
            self.reasoning.finish_session(graph_run.id, "completed", termination_reason)
            self.db.commit()
        except Exception as exc:
            graph_run.status = GraphRunStatus.failed
            graph_run.failure_reason = str(exc)
            graph_run.finished_at = datetime.utcnow()
            workflow.status = WorkflowStatus.failed
            workflow.terminal_reason = str(exc)
            self.reasoning.finish_session(graph_run.id, "failed", str(exc))
            self.db.commit()
            raise
        return graph_run

    def _run_node(self, graph_run: GraphRun, name: str, state: dict[str, Any], fn: Callable[[dict[str, Any]], None]) -> None:
        started = datetime.utcnow()
        node = GraphNodeRun(
            graph_run_id=graph_run.id,
            node_name=name,
            previous_node=graph_run.current_node,
            status=NodeStatus.running,
            input_snapshot=self._snapshot(state),
            started_at=started,
        )
        graph_run.previous_node = graph_run.current_node
        graph_run.current_node = name
        self.reasoning.update_node(graph_run.id, name)
        self.db.add(node)
        self.db.commit()
        try:
            fn(state)
            node.status = NodeStatus.succeeded
            node.output_snapshot = self._snapshot(state)
        except Exception as exc:
            node.status = NodeStatus.failed
            node.failure_reason = str(exc)
            raise
        finally:
            node.finished_at = datetime.utcnow()
            node.duration_ms = int((node.finished_at - started).total_seconds() * 1000)
            self.db.commit()

    def _snapshot(self, state: dict[str, Any]) -> dict[str, Any]:
        return jsonable_encoder(state)

    def _route_entry(self, state: dict[str, Any]) -> str:
        if state.get("resume_from_node") == "repair_candidate":
            return "repair_candidate"
        if state.get("resume_from_node") == "approved":
            return "approved"
        return "consume_cti"

    def _route_after_extract(self, state: dict[str, Any]) -> str:
        if state.get("behavior_ids"):
            state["behavior_index"] = 0
            state["behavior_id"] = state["behavior_ids"][0]
            return "verify_attack_mapping"
        return "terminal_insufficient_evidence"

    def _route_policy(self, state: dict[str, Any]) -> str:
        return str(state.get("policy_decision", "insufficient_evidence"))

    def _route_validation(self, state: dict[str, Any]) -> str:
        validation = state.get("validation", {})
        decision = state.get("satisfaction_decision") or {}
        selected = decision.get("route_selected")
        if selected == "queue_review":
            state["reasoning_termination_reason"] = decision.get("blocking_reason") or "satisfied"
            return "valid"
        if selected == "terminal_visibility_gap":
            state["terminal_status"] = "visibility_gap"
            return "unrepairable_invalid"
        if selected == "terminal_insufficient_evidence":
            state["terminal_status"] = "insufficient_evidence"
            return "unrepairable_invalid"
        if selected == "terminal_covered":
            state["terminal_status"] = "covered"
            return "unrepairable_invalid"
        if selected == "reject":
            state["terminal_status"] = "rejected"
            return "unrepairable_invalid"
        settings = get_settings()
        confidence_delta = float(validation.get("confidence_delta", 0.0) or 0.0)
        if state.get("repair_attempts", 0) > 0 and confidence_delta < settings.reasoning_min_improvement_delta:
            state["reasoning_termination_reason"] = "no_meaningful_improvement"
            return "unrepairable_invalid"
        if (selected == "repair_candidate" or (not selected and not validation.get("valid"))) and validation.get("repairable") and state.get("repair_attempts", 0) < min(settings.max_repair_attempts, settings.reasoning_max_revisions):
            return "repairable_invalid"
        state["reasoning_termination_reason"] = "repair_limit_reached"
        return "unrepairable_invalid"

    def _route_repair(self, state: dict[str, Any]) -> str:
        return "attempts_exhausted" if state.get("repair_attempts", 0) > min(get_settings().max_repair_attempts, get_settings().reasoning_max_revisions) else "repaired"

    def _route_approved(self, state: dict[str, Any]) -> str:
        action = state.get("analyst_action")
        if action == ReviewActionType.approve:
            return "deployment"
        if action == ReviewActionType.reject:
            return "terminal_rejected"
        if action == ReviewActionType.request_changes:
            return "repair_candidate"
        return END

    def _route_next_behavior(self, state: dict[str, Any]) -> str:
        next_index = int(state.get("behavior_index", 0)) + 1
        return "advance_behavior" if next_index < len(state.get("behavior_ids", [])) else END

    def advance_behavior(self, state: dict[str, Any]) -> None:
        state["behavior_index"] = int(state.get("behavior_index", 0)) + 1
        state["behavior_id"] = state["behavior_ids"][state["behavior_index"]]
        for key in ["candidate", "validation", "previous_validation", "policy_decision", "proposal_id", "repair_attempts"]:
            state.pop(key, None)

    def terminal_covered(self, state: dict[str, Any]) -> None:
        state["terminal_status"] = "covered"
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event:
            event.status = CtiEventStatus.covered

    def terminal_visibility_gap(self, state: dict[str, Any]) -> None:
        state["terminal_status"] = "visibility_gap"
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event:
            event.status = CtiEventStatus.visibility_gap

    def terminal_insufficient_evidence(self, state: dict[str, Any]) -> None:
        state["terminal_status"] = "insufficient_evidence"
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event:
            event.status = CtiEventStatus.insufficient_evidence

    def terminal_failed(self, state: dict[str, Any]) -> None:
        terminal_status = state.get("terminal_status") or "failed"
        state["terminal_status"] = terminal_status
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event:
            if terminal_status == "visibility_gap":
                event.status = CtiEventStatus.visibility_gap
            elif terminal_status == "insufficient_evidence":
                event.status = CtiEventStatus.insufficient_evidence
            elif terminal_status == "covered":
                event.status = CtiEventStatus.covered
            elif terminal_status == "rejected":
                event.status = CtiEventStatus.rejected
            else:
                event.status = CtiEventStatus.failed

    def terminal_rejected(self, state: dict[str, Any]) -> None:
        state["terminal_status"] = "rejected"
        proposal = self.db.get(Proposal, state["proposal_id"])
        if proposal:
            proposal.status = ProposalStatus.rejected
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event:
            event.status = CtiEventStatus.rejected

    def _inherit_context(self, graph_run: GraphRun, state: dict[str, Any], until_node: str) -> None:
        if not state.get("proposal_id"):
            return
        revision = self._latest_revision(state["proposal_id"])
        state["behavior_id"] = revision.behavior_id
        state["candidate"] = revision.sigma_json
        state["proposal_revision_id"] = revision.id
        state["revision_number"] = revision.revision_number
        for name in self.nodes:
            if name == until_node:
                break
            previous = self.db.scalars(
                select(GraphNodeRun)
                .where(GraphNodeRun.graph_run_id == revision.graph_run_id, GraphNodeRun.node_name == name)
                .order_by(GraphNodeRun.started_at.desc())
            ).first()
            inherited = GraphNodeRun(
                graph_run_id=graph_run.id,
                node_name=name,
                previous_node=graph_run.current_node,
                status=NodeStatus.skipped,
                input_snapshot={"inherited_from_graph_run_id": revision.graph_run_id, "state": "inherited"},
                output_snapshot=previous.output_snapshot if previous else {"state": "inherited"},
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                duration_ms=0,
            )
            graph_run.previous_node = graph_run.current_node
            graph_run.current_node = name
            self.db.add(inherited)
        self.db.commit()

    def consume_cti(self, state: dict[str, Any]) -> None:
        event = self.db.get(CtiEvent, state["cti_event_id"])
        if event is None:
            raise ValueError("cti_event_not_found")
        event.status = CtiEventStatus.running
        state["normalized_cti"] = event.normalized_event

    def extract_behaviors(self, state: dict[str, Any]) -> None:
        response, usage = asyncio.run(self.ai.analyze_cti(state["normalized_cti"]))
        response_payload = response.model_dump()
        extraction_watchers = self.watchers.evaluate_behavior_extraction(state["normalized_cti"], response_payload)
        self.reasoning.record_watchers(state["graph_run_id"], "extract_behaviors", extraction_watchers)
        behavior_ids: list[str] = []
        for candidate in response.behaviors:
            if self._evidence_refs_valid(state["normalized_cti"], [ref.model_dump() for ref in candidate.evidence_refs]):
                behavior_ids.append(self._persist_behavior(state, candidate))
        state["behavior_ids"] = behavior_ids
        if behavior_ids:
            state["behavior_index"] = 0
            state["behavior_id"] = behavior_ids[0]
        self.reasoning.record_confidence(
            state["graph_run_id"],
            "extract_behaviors",
            "cti_event",
            state["cti_event_id"],
            "behavior_extraction",
            float(response.structured_justification.confidence),
            {"behavior_count": len(behavior_ids), "watchers": extraction_watchers},
        )
        self._persist_ai_interaction(state, "extract_behaviors", response_payload, usage, response.structured_justification.model_dump())

    def _evidence_refs_valid(self, normalized_cti: dict[str, Any], refs: list[dict[str, Any]]) -> bool:
        attributes = normalized_cti.get("attributes", [])
        valid_refs = {f"attribute:{attr.get('id')}" for attr in attributes if isinstance(attr, dict)}
        valid_refs.update({f"attribute:{index}" for index, _ in enumerate(attributes, start=1)})
        return bool(refs) and all(ref.get("ref") in valid_refs for ref in refs)

    def _persist_behavior(self, state: dict[str, Any], candidate: BehaviorCandidate) -> str:
        payload = {
            "summary": candidate.summary,
            "behavior_type": candidate.behavior_type,
            "observables": candidate.observables,
            "attack": [m.technique_id for m in candidate.proposed_attack_mappings],
            "telemetry": candidate.required_telemetry,
        }
        behavior = Behavior(
            cti_event_id=state["cti_event_id"],
            workflow_id=state["workflow_id"],
            source_graph_run_id=state["graph_run_id"],
            summary=candidate.summary,
            behavior_type=candidate.behavior_type,
            evidence_refs=[ref.model_dump() for ref in candidate.evidence_refs],
            observables=candidate.observables,
            fingerprint=fingerprint_behavior(payload),
            confidence=candidate.confidence,
        )
        self.db.add(behavior)
        self.db.flush()
        state.setdefault("behavior_candidates", {})[behavior.id] = candidate.model_dump()
        self.db.commit()
        return behavior.id

    def verify_attack_mapping(self, state: dict[str, Any]) -> None:
        candidate = BehaviorCandidate.model_validate(state["behavior_candidates"][state["behavior_id"]])
        verifier = AttackVerificationService(self.db)
        verified = 0
        for proposed in candidate.proposed_attack_mappings:
            result = verifier.verify(proposed, candidate)
            technique = result["technique"]
            mapping = AttackMapping(
                behavior_id=state["behavior_id"],
                technique_id=proposed.technique_id,
                technique_name=getattr(technique, "name", proposed.technique_name),
                tactic_id=proposed.tactic_id,
                tactic_name=proposed.tactic_name,
                verified=bool(result["verified"]),
                verification_status=str(result["status"]),
                attack_version=result.get("attack_version"),
                verification_details=result.get("details"),
                evidence_refs=[ref.model_dump() for ref in proposed.evidence_refs],
                confidence=proposed.confidence,
            )
            self.db.add(mapping)
            verified += 1 if result["verified"] else 0
        state["verified_mapping_count"] = verified
        session = self.reasoning.session_for_run(state["graph_run_id"])
        if session:
            summary = dict(session.session_summary or {})
            summary.setdefault("behaviors_processed", []).append(state["behavior_id"])
            accepted = [mapping.technique_id for mapping in self.db.scalars(select(AttackMapping).where(AttackMapping.behavior_id == state["behavior_id"], AttackMapping.verified.is_(True))).all()]
            rejected = [mapping.technique_id for mapping in self.db.scalars(select(AttackMapping).where(AttackMapping.behavior_id == state["behavior_id"], AttackMapping.verified.is_(False))).all()]
            summary.setdefault("accepted_attack", []).extend(accepted)
            summary.setdefault("rejected_attack", []).extend(rejected)
            session.session_summary = summary
        self.db.commit()

    def coverage_analysis(self, state: dict[str, Any]) -> None:
        behavior = self.db.get(Behavior, state["behavior_id"])
        candidate = state["behavior_candidates"][state["behavior_id"]]
        result = CoverageService(self.db).analyze(behavior.fingerprint, candidate)
        self.db.add(
            CoverageResult(
                workflow_id=state["workflow_id"],
                graph_run_id=state["graph_run_id"],
                behavior_id=state["behavior_id"],
                coverage_status=result["status"],
                matching_detection_ids=result["matches"],
                similarity_score=result["score"],
                deterministic_rationale=result["rationale"],
            )
        )
        state["coverage_status"] = result["status"]

    def visibility_analysis(self, state: dict[str, Any]) -> None:
        candidate = BehaviorCandidate.model_validate(state["behavior_candidates"][state["behavior_id"]])
        result = TelemetryService(self.db).analyze(candidate.required_telemetry)
        self.db.add(
            VisibilityResult(
                workflow_id=state["workflow_id"],
                graph_run_id=state["graph_run_id"],
                behavior_id=state["behavior_id"],
                visibility_status=result["status"],
                required_sources=candidate.required_telemetry,
                available_source_ids=result["available_source_ids"],
                missing_sources=result["missing_sources"],
                deterministic_rationale=result["rationale"],
            )
        )
        state["visibility_status"] = result["status"]

    def policy_decision(self, state: dict[str, Any]) -> None:
        behavior = self.db.get(Behavior, state["behavior_id"])
        decision = decide_policy(
            behavior.confidence,
            CoverageStatus(state["coverage_status"]),
            VisibilityStatus(state["visibility_status"]),
            state["verified_mapping_count"],
        )
        state["policy_decision"] = decision
        session = self.reasoning.session_for_run(state["graph_run_id"])
        if session:
            summary = dict(session.session_summary or {})
            summary.setdefault("policy_decisions", []).append({"behavior_id": state["behavior_id"], "decision": decision})
            session.session_summary = summary
        self.db.add(
            PolicyDecision(
                workflow_id=state["workflow_id"],
                graph_run_id=state["graph_run_id"],
                behavior_id=state["behavior_id"],
                coverage_status=CoverageStatus(state["coverage_status"]),
                visibility_status=VisibilityStatus(state["visibility_status"]),
                evidence_sufficient=behavior.confidence >= 0.45 and state["verified_mapping_count"] > 0,
                verified_mapping_count=state["verified_mapping_count"],
                decision=PolicyDecisionValue(decision),
                deterministic_rationale={
                    "confidence": behavior.confidence,
                    "coverage_status": state["coverage_status"],
                    "visibility_status": state["visibility_status"],
                    "verified_mapping_count": state["verified_mapping_count"],
                },
            )
        )
        self.db.commit()

    def generate_candidate(self, state: dict[str, Any]) -> None:
        behavior = self.db.get(Behavior, state["behavior_id"])
        mappings = self.db.scalars(select(AttackMapping).where(AttackMapping.behavior_id == state["behavior_id"], AttackMapping.verified.is_(True))).all()
        response, usage = asyncio.run(self.ai.generate_sigma({"behavior": {"summary": behavior.summary, "observables": behavior.observables, "evidence_refs": behavior.evidence_refs}, "attack_mappings": [jsonable_encoder(mapping) for mapping in mappings], "coverage_status": state.get("coverage_status"), "visibility_status": state.get("visibility_status")}))
        state["candidate"] = response.sigma.model_dump()
        state["candidate_justification"] = response.structured_justification.model_dump()
        state["candidate_confidence"] = response.confidence
        state["token_usage"] = usage["token_usage"]
        state["estimated_cost"] = usage["estimated_cost"]
        self.reasoning.record_confidence(
            state["graph_run_id"],
            "generate_candidate",
            "behavior",
            state["behavior_id"],
            "ai_generation",
            float(response.confidence),
            {"prompt_version": usage.get("prompt_version"), "repair_attempts": state.get("repair_attempts", 0)},
        )
        self._persist_ai_interaction(state, "generate_candidate", response.model_dump(), usage, response.structured_justification.model_dump())

    def validate_candidate(self, state: dict[str, Any]) -> None:
        previous_validation = state.get("validation")
        previous_confidence = float((previous_validation or {}).get("confidence_assessment", {}).get("score", 0.0)) if isinstance(previous_validation, dict) else None
        mappings = self.db.scalars(select(AttackMapping).where(AttackMapping.behavior_id == state["behavior_id"], AttackMapping.verified.is_(True))).all()
        required = [mapping.technique_id for mapping in mappings]
        visibility = self.db.scalars(select(VisibilityResult).where(VisibilityResult.behavior_id == state["behavior_id"]).order_by(VisibilityResult.id.desc())).first()
        telemetry_fields: list[str] = []
        if visibility:
            for source in visibility.required_sources:
                telemetry_fields.extend(str(field) for field in source.get("fields", []))
        if self._enum_value(state.get("visibility_status")) == "gap":
            telemetry_fields = []
        state["validation"] = self.sigma.validate(state["candidate"], required, telemetry_fields)
        duplicate = DuplicateDetectionService(self.db).analyze(
            state["candidate"],
            state["validation"].get("compiled_outputs", {}).get("query"),
        )
        state["validation"]["duplicate_status"] = duplicate["status"]
        state["validation"]["duplicate_result"] = duplicate
        state["validation"].setdefault("warnings", [])
        if duplicate["status"] in {"near_duplicate", "overlapping", "unknown", "supersedes"}:
            state["validation"]["warnings"].append({"code": "duplicate_candidate", "message": f"Candidate is {duplicate['status']}"})
        if duplicate["status"] == "exact_duplicate":
            state["validation"]["valid"] = False
            state["validation"]["repairable"] = False
            state["validation"].setdefault("errors", []).append({"code": "exact_duplicate", "message": "Candidate exactly duplicates an active catalog detection"})
        candidate_payload = state["candidate"]
        watcher_results = self.watchers.evaluate_candidate(candidate_payload, state["validation"], telemetry_fields, float(state.get("candidate_confidence", 0.0)))
        self.reasoning.record_watchers(state["graph_run_id"], "validate_candidate", watcher_results)
        confidence = self.confidence.assess(
            state["validation"],
            watcher_results,
            float(state.get("candidate_confidence", 0.0)),
            int(state.get("repair_attempts", 0) or 0),
            self._enum_value(state.get("coverage_status")),
            self._enum_value(state.get("visibility_status")),
            str(state["validation"].get("duplicate_status") or "unknown"),
        )
        trust = self.trust.assess(state["validation"], watcher_results, confidence["score"])
        state["validation"]["watcher_results"] = watcher_results
        state["validation"]["confidence_assessment"] = confidence
        state["validation"]["trust_assessment"] = trust
        state["validation"]["confidence_delta"] = round(confidence["score"] - (previous_confidence or 0.0), 4)
        decision = self.satisfaction.assess(state["validation"], watcher_results, confidence["score"], trust["score"])
        state["satisfaction_decision"] = decision
        state["validation"]["satisfaction_decision"] = decision
        if decision.get("route_selected") == "reject":
            state["terminal_status"] = "rejected"
        elif decision.get("route_selected") == "terminal_visibility_gap":
            state["terminal_status"] = "visibility_gap"
        elif decision.get("route_selected") == "terminal_insufficient_evidence":
            state["terminal_status"] = "insufficient_evidence"
        elif decision.get("route_selected") == "terminal_covered":
            state["terminal_status"] = "covered"
        self.reasoning.record_confidence(
            state["graph_run_id"],
            "validate_candidate",
            "behavior",
            state["behavior_id"],
            "proposal_confidence",
            confidence["score"],
            confidence["factors"],
        )
        self.reasoning.update_trust(state["graph_run_id"], trust["score"], trust["recommendation"])
        self.reasoning.record_revision(
            state["graph_run_id"],
            state.get("behavior_id"),
            state.get("proposal_id"),
            "validate_candidate",
            "initial_validation" if not state.get("repair_attempts") else "post_repair_validation",
            candidate_payload,
            previous_validation,
            state["validation"],
            previous_confidence,
            confidence["score"],
            "validation_succeeded" if state["validation"].get("valid") else None,
            candidate_before=state.get("candidate_before"),
            candidate_after=candidate_payload,
            changed_fields=state.get("last_changed_fields", []),
            watcher_results=watcher_results,
            ai_confidence=float(state.get("candidate_confidence", 0.0)),
            trust_score=trust["score"],
            recommendation=trust["recommendation"],
            stopping_decision=decision["aggregate"],
            stopping_reason=decision["blocking_reason"],
            route_selected=decision["route_selected"],
        )

    def repair_candidate(self, state: dict[str, Any]) -> None:
        prior_revision_summary: dict[str, Any] = {}
        if "candidate" not in state and state.get("proposal_id"):
            revision = self._latest_revision(state["proposal_id"])
            state["behavior_id"] = revision.behavior_id
            state["candidate"] = revision.sigma_json
            prior_revision_summary = {
                "proposal_revision_id": revision.id,
                "revision_number": revision.revision_number,
                "change_summary": revision.structured_justification.get("change_summary", []),
                "confidence": revision.confidence,
            }
        state["repair_attempts"] = state.get("repair_attempts", 0) + 1
        state["candidate_before"] = jsonable_encoder(state.get("candidate"))
        behavior = self.db.get(Behavior, state["behavior_id"])
        mappings = self.db.scalars(select(AttackMapping).where(AttackMapping.behavior_id == state["behavior_id"], AttackMapping.verified.is_(True))).all()
        visibility = self.db.scalars(select(VisibilityResult).where(VisibilityResult.behavior_id == state["behavior_id"]).order_by(VisibilityResult.id.desc())).first()
        telemetry_sources = self.db.scalars(select(TelemetrySource).where(TelemetrySource.enabled.is_(True))).all()
        validation = state.get("validation") or {}
        session = self.reasoning.session_for_run(state["graph_run_id"])
        memory = session.session_summary if session else {}
        compiled_outputs = validation.get("compiled_outputs") if isinstance(validation, dict) else {}
        response, usage = asyncio.run(
            self.ai.repair_sigma(
                {
                    "analyst_comment": state.get("analyst_comment"),
                    "candidate": state["candidate"],
                    "behavior": jsonable_encoder(behavior) if behavior else None,
                    "behavior_evidence": behavior.evidence_refs if behavior else [],
                    "observables": behavior.observables if behavior else [],
                    "verified_attack_mappings": [jsonable_encoder(mapping) for mapping in mappings],
                    "available_telemetry": [jsonable_encoder(source) for source in telemetry_sources],
                    "telemetry_result": jsonable_encoder(visibility) if visibility else None,
                    "compiler_errors": (compiled_outputs or {}).get("compiler_errors", []),
                    "validation_errors": validation.get("errors", []) if isinstance(validation, dict) else [],
                    "validation": validation,
                    "prior_revision_summary": prior_revision_summary,
                    "previous_change_history": state.get("candidate_justification", {}).get("change_summary", []),
                    "session_memory": memory,
                    "repair_history": memory.get("repair_history", []) if isinstance(memory, dict) else [],
                    "watcher_failures": memory.get("watcher_failures", []) if isinstance(memory, dict) else [],
                    "validation_history": memory.get("validation_history", []) if isinstance(memory, dict) else [],
                }
            )
        )
        state["candidate"] = response.sigma.model_dump()
        state["candidate_justification"] = response.structured_justification.model_dump()
        state["last_changed_fields"] = response.model_dump().get("fields_changed", [])
        state["candidate_confidence"] = response.confidence
        state["token_usage"] = usage["token_usage"]
        state["estimated_cost"] = usage["estimated_cost"]
        self._persist_ai_interaction(state, "repair_candidate", response.model_dump(), usage, response.structured_justification.model_dump())

    def queue_review(self, state: dict[str, Any]) -> None:
        validation = state["validation"]
        if not validation["valid"]:
            raise ValueError("invalid_candidate_cannot_enter_review")
        state["reasoning_termination_reason"] = state.get("reasoning_termination_reason") or "validation_succeeded"
        candidate = validation["candidate"]
        sigma_yaml = self.sigma.to_yaml(candidate)
        proposal = self.db.get(Proposal, state.get("proposal_id")) if state.get("proposal_id") else None
        if proposal is None:
            proposal = Proposal(
                behavior_id=state["behavior_id"],
                workflow_id=state["workflow_id"],
                confidence=state.get("candidate_confidence", 0.0),
                quality_score=validation["quality_score"],
            )
            self.db.add(proposal)
            self.db.flush()
            revision_number = 1
        else:
            revision_number = proposal.current_revision_number + 1
            proposal.current_revision_number = revision_number
            proposal.status = ProposalStatus.ready_review
            proposal.quality_score = validation["quality_score"]
        revision = ProposalRevision(
            proposal_id=proposal.id,
            behavior_id=state["behavior_id"],
            workflow_id=state["workflow_id"],
            graph_run_id=state["graph_run_id"],
            revision_number=revision_number,
            sigma_yaml=sigma_yaml,
            sigma_json=candidate.model_dump(),
            structured_justification=state.get("candidate_justification", {}),
            confidence=state.get("candidate_confidence", 0.0),
            token_usage=state.get("token_usage", {}),
            estimated_cost=state.get("estimated_cost", 0.0),
        )
        self.db.add(revision)
        self.db.flush()
        self.db.add(
            ValidationResult(
                proposal_revision_id=revision.id,
                schema_valid=True,
                sigma_valid=True,
                compilation_success=True,
                quality_score=validation["quality_score"],
                duplicate_status=validation.get("duplicate_status", "unique"),
                telemetry_verified=True,
                attack_verified=True,
                errors=validation["errors"],
                warnings=validation["warnings"],
                compiled_outputs={**validation["compiled_outputs"], "duplicate_result": validation.get("duplicate_result")},
            )
        )
        event = self.db.get(CtiEvent, state["cti_event_id"])
        event.status = CtiEventStatus.ready_review
        self.db.commit()
        state["proposal_id"] = proposal.id
        state["revision_number"] = revision_number
        self.reasoning.attach_proposal_revision(state["graph_run_id"], proposal.id, revision.id)

    def approved(self, state: dict[str, Any]) -> None:
        action = self.db.scalars(
            select(ReviewAction)
            .where(ReviewAction.proposal_id == state["proposal_id"])
            .order_by(ReviewAction.created_at.desc())
        ).first()
        if action is None:
            raise ValueError("analyst_action_required")
        state["analyst_action"] = action.action
        if action.action == ReviewActionType.reject:
            proposal = self.db.get(Proposal, state["proposal_id"])
            proposal.status = ProposalStatus.rejected
            event = self.db.get(CtiEvent, state["cti_event_id"])
            if event:
                event.status = CtiEventStatus.rejected

    def deployment(self, state: dict[str, Any]) -> None:
        revision = self._latest_revision(state["proposal_id"])
        deployment = DeploymentService(self.db)
        artifact = deployment.create_artifact(revision)
        detection = deployment.publish_detection(revision, artifact)
        proposal = self.db.get(Proposal, state["proposal_id"])
        proposal.status = ProposalStatus.deployed
        workflow = self.db.get(Workflow, proposal.workflow_id)
        workflow.status = WorkflowStatus.deployed
        event = self.db.get(CtiEvent, workflow.cti_event_id)
        if event:
            event.status = CtiEventStatus.approved
        state["deployment_artifact_id"] = artifact.id
        state["detection_id"] = detection.id

    def _latest_revision(self, proposal_id: str) -> ProposalRevision:
        revision = self.db.scalars(
            select(ProposalRevision)
            .where(ProposalRevision.proposal_id == proposal_id)
            .order_by(ProposalRevision.revision_number.desc())
        ).first()
        if revision is None:
            raise ValueError("proposal_revision_not_found")
        return revision

    def _persist_ai_interaction(self, state: dict[str, Any], node_name: str, response: dict[str, Any], usage: dict[str, Any], justification: dict[str, Any]) -> None:
        node = self.db.scalars(
            select(GraphNodeRun)
            .where(GraphNodeRun.graph_run_id == state["graph_run_id"], GraphNodeRun.node_name == node_name)
            .order_by(GraphNodeRun.started_at.desc())
        ).first()
        if node is None:
            return
        token_usage = usage["token_usage"]
        idempotency_material = f"{state['graph_run_id']}:{node_name}:{usage['input_hash']}"
        idempotency_key = hashlib.sha256(idempotency_material.encode()).hexdigest()
        existing = self.db.scalars(select(AiInteraction).where(AiInteraction.idempotency_key == idempotency_key)).first()
        if existing:
            return
        self.db.add(
            AiInteraction(
                graph_run_id=state["graph_run_id"],
                graph_node_run_id=node.id,
                provider=usage["provider"],
                model=usage["model"],
                prompt_version=usage["prompt_version"],
                schema_name=usage["schema_name"],
                input_hash=usage["input_hash"],
                request_json={
                    "node": node_name,
                    "system_prompt_version": usage.get("system_prompt_version"),
                    "input_summary": usage.get("input_summary"),
                    "payload": jsonable_encoder(usage.get("request_payload", {})),
                },
                response_json=response,
                structured_justification=justification,
                confidence=float(justification.get("confidence", 0.0)),
                prompt_tokens=token_usage.get("prompt_tokens", 0),
                completion_tokens=token_usage.get("completion_tokens", 0),
                total_tokens=token_usage.get("total_tokens", 0),
                estimated_cost=usage["estimated_cost"],
                latency_ms=usage.get("latency_ms"),
                response_hash=usage.get("response_hash"),
                idempotency_key=idempotency_key,
                error_json=usage.get("error_json"),
            )
        )
        graph_run = self.db.get(GraphRun, state["graph_run_id"])
        graph_run.total_tokens += token_usage.get("total_tokens", 0)
        graph_run.estimated_cost = float(graph_run.estimated_cost) + usage["estimated_cost"]

    def _enum_value(self, value: Any) -> str:
        return str(getattr(value, "value", value or ""))
