import hashlib
from datetime import datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import (
    AiConfidenceEvent,
    AiReasoningRevision,
    AiReasoningSession,
    AiWatcherResult,
    CtiConsumptionRecord,
    GraphNodeRun,
    GraphRun,
    MispPollState,
    Workflow,
)


PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


class WatcherEngine:
    def evaluate_behavior_extraction(self, normalized_cti: dict[str, Any], response: dict[str, Any]) -> list[dict[str, Any]]:
        behaviors = response.get("behaviors", []) if isinstance(response, dict) else []
        attributes = normalized_cti.get("attributes", []) if isinstance(normalized_cti, dict) else []
        evidence_refs = {f"attribute:{attr.get('id')}" for attr in attributes if isinstance(attr, dict)}
        evidence_refs.update({f"attribute:{index}" for index, _ in enumerate(attributes, start=1)})
        return [
            self._schema("schema", bool(behaviors), "Behavior extraction returned structured behavior objects"),
            self._schema(
                "evidence",
                all(ref.get("ref") in evidence_refs for behavior in behaviors for ref in behavior.get("evidence_refs", [])),
                "Every extracted behavior cites normalized CTI evidence",
            ),
            self._schema(
                "attack",
                all(behavior.get("proposed_attack_mappings") for behavior in behaviors),
                "Behavior extraction proposes ATT&CK mappings for deterministic verification",
                warning=True,
            ),
            self._schema(
                "hallucination",
                all(any(str(attr.get("value", "")) in str(behavior) for attr in attributes if isinstance(attr, dict)) for behavior in behaviors) if behaviors else False,
                "Extracted behavior remains anchored to event observables",
                warning=True,
            ),
            {"watcher_name": "safety", "status": PASS, "message": "No executable action was taken by the AI provider", "details": {"scope": "structured_output_only"}},
        ]

    def evaluate_candidate(
        self,
        candidate: dict[str, Any],
        validation: dict[str, Any],
        telemetry_fields: list[str],
        ai_confidence: float,
    ) -> list[dict[str, Any]]:
        duplicate = validation.get("duplicate_result", {}) if isinstance(validation, dict) else {}
        duplicate_status = duplicate.get("status") or validation.get("duplicate_status")
        safety_text = str(candidate).lower()
        return [
            self._schema("schema", bool(candidate.get("title") and candidate.get("detection")), "Sigma candidate contains required structured fields"),
            self._schema("sigma", bool(validation.get("valid")), "pySigma validation and compilation completed successfully"),
            self._schema("confidence", ai_confidence >= 0.45, "AI confidence is above the minimum usable threshold", warning=True),
            self._schema("duplicate", duplicate_status != "exact_duplicate", f"Duplicate status is {duplicate_status or 'unknown'}"),
            self._schema("telemetry", bool(telemetry_fields), "Required telemetry fields are available to validate detection feasibility", warning=True),
            self._schema("hallucination", bool(candidate.get("detection")), "Detection logic is present and bounded to structured Sigma fields"),
            self._schema("safety", not (safety_text.count("delete ") > 2 or "supervisor_safety_fail" in safety_text), "Candidate does not contain unsafe operational instructions", warning=False),
        ]

    def _schema(self, name: str, condition: bool, message: str, warning: bool = False) -> dict[str, Any]:
        if condition:
            return {"watcher_name": name, "status": PASS, "message": message, "details": {"passed": True}}
        return {"watcher_name": name, "status": WARNING if warning else FAIL, "message": message, "details": {"passed": False}}


class ConfidenceEngine:
    def assess(
        self,
        validation: dict[str, Any],
        watchers: list[dict[str, Any]],
        ai_confidence: float,
        repair_count: int,
        coverage_status: str | None,
        visibility_status: str | None,
        duplicate_status: str | None,
    ) -> dict[str, Any]:
        validation_score = 1.0 if validation.get("valid") else 0.25 if validation.get("repairable") else 0.0
        watcher_score = self._watcher_score(watchers)
        telemetry_score = 1.0 if visibility_status == "visible" else 0.55 if visibility_status else 0.35
        coverage_score = 0.85 if coverage_status == "not_covered" else 0.45 if coverage_status == "covered" else 0.65
        duplicate_score = {
            "unique": 1.0,
            "near_duplicate": 0.65,
            "overlapping": 0.55,
            "supersedes": 0.75,
            "unknown": 0.5,
            "exact_duplicate": 0.0,
        }.get(str(duplicate_status or "unknown"), 0.5)
        repair_penalty = min(0.24, repair_count * 0.08)
        score = (
            ai_confidence * 0.25
            + validation_score * 0.25
            + watcher_score * 0.20
            + telemetry_score * 0.10
            + coverage_score * 0.10
            + duplicate_score * 0.10
            - repair_penalty
        )
        score = max(0.0, min(1.0, score))
        return {
            "score": round(score, 4),
            "factors": {
                "ai_confidence": ai_confidence,
                "validation_score": validation_score,
                "watcher_score": watcher_score,
                "telemetry_score": telemetry_score,
                "coverage_score": coverage_score,
                "duplicate_score": duplicate_score,
                "repair_penalty": repair_penalty,
            },
        }

    def _watcher_score(self, watchers: list[dict[str, Any]]) -> float:
        if not watchers:
            return 0.0
        value = 0.0
        for watcher in watchers:
            status = watcher.get("status")
            value += 1.0 if status == PASS else 0.55 if status == WARNING else 0.0
        return value / len(watchers)


class TrustEngine:
    def assess(self, validation: dict[str, Any], watchers: list[dict[str, Any]], confidence: float) -> dict[str, Any]:
        fail_count = sum(1 for watcher in watchers if watcher.get("status") == FAIL)
        warning_count = sum(1 for watcher in watchers if watcher.get("status") == WARNING)
        safety_failed = any(
            watcher.get("watcher_name") == "safety" and watcher.get("status") == FAIL
            for watcher in watchers
        )
        deterministic = 1.0 if validation.get("valid") else 0.2 if validation.get("repairable") else 0.0
        trust = max(0.0, min(1.0, deterministic * 0.55 + confidence * 0.25 + (1 - min(1, fail_count / 3)) * 0.20 - warning_count * 0.03))
        if safety_failed:
            recommendation = "reject"
        elif fail_count:
            recommendation = "request_changes" if validation.get("repairable") else "reject"
        elif trust >= 0.88 and validation.get("valid"):
            recommendation = "approve"
        elif trust >= 0.75 and validation.get("valid"):
            recommendation = "approve_with_warning" if warning_count else "approve"
        elif validation.get("valid"):
            recommendation = "needs_review"
        elif validation.get("repairable"):
            recommendation = "request_changes"
        else:
            recommendation = "reject"
        return {"score": round(trust, 4), "recommendation": recommendation, "fail_count": fail_count, "warning_count": warning_count}


class SatisfactionEngine:
    mandatory_watchers = {"schema", "safety", "sigma", "telemetry"}

    def assess(self, validation: dict[str, Any], watchers: list[dict[str, Any]], confidence: float, trust: float) -> dict[str, Any]:
        settings = get_settings()
        by_name = {str(watcher.get("watcher_name")): watcher for watcher in watchers}
        failing = [watcher for watcher in watchers if watcher.get("status") == FAIL]
        warnings = [watcher for watcher in watchers if watcher.get("status") == WARNING]
        duplicate_status = str(validation.get("duplicate_status") or "unknown")
        missing_mandatory = [name for name in self.mandatory_watchers if by_name.get(name, {}).get("status") != PASS]
        if by_name.get("safety", {}).get("status") == FAIL:
            return self._result(False, "blocking_fail", "reject", "safety", "safety_watcher_failed", False, warnings)
        if by_name.get("evidence", {}).get("status") == FAIL:
            return self._result(False, "blocking_fail", "terminal_insufficient_evidence", "evidence", "evidence_watcher_failed", False, warnings)
        if by_name.get("telemetry", {}).get("status") in {FAIL, WARNING}:
            return self._result(False, "repairable_fail" if validation.get("repairable") else "blocking_fail", "terminal_visibility_gap", "telemetry", "telemetry_watcher_failed", bool(validation.get("repairable")), warnings)
        if duplicate_status == "exact_duplicate":
            return self._result(False, "blocking_fail", "terminal_covered", "duplicate", "exact_duplicate", False, warnings)
        if missing_mandatory:
            route = "repair_candidate" if validation.get("repairable") else "terminal_failed"
            return self._result(False, "repairable_fail", route, missing_mandatory[0], "mandatory_watcher_failed", bool(validation.get("repairable")), warnings)
        if not validation.get("valid"):
            route = "repair_candidate" if validation.get("repairable") else "terminal_failed"
            return self._result(False, "repairable_fail", route, "sigma", "sigma_validation_failed", bool(validation.get("repairable")), warnings)
        if confidence < settings.reasoning_confidence_target:
            return self._result(False, "repairable_fail", "repair_candidate" if validation.get("repairable") else "queue_review", "confidence", "confidence_below_target", bool(validation.get("repairable")), warnings)
        if trust < settings.reasoning_trust_target:
            return self._result(False, "warning", "queue_review", "trust", "trust_below_target", False, warnings)
        if failing:
            return self._result(False, "repairable_fail", "repair_candidate" if validation.get("repairable") else "terminal_failed", str(failing[0].get("watcher_name")), "watcher_failed", bool(validation.get("repairable")), warnings)
        return self._result(True, "pass", "queue_review", None, "satisfied", False, warnings)

    def _result(self, satisfied: bool, aggregate: str, route: str, watcher: str | None, reason: str, repairable: bool, warnings: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "satisfied": satisfied,
            "aggregate": aggregate,
            "route_selected": route,
            "watcher": watcher,
            "blocking_reason": reason,
            "repairable": repairable,
            "warnings": warnings,
            "policy_result": "review" if route == "queue_review" else route.replace("terminal_", ""),
        }


class ReasoningService:
    def __init__(self, db: Session):
        self.db = db

    def start_session(self, workflow: Workflow, graph_run: GraphRun, resume_from_node: str | None = None) -> AiReasoningSession:
        if resume_from_node:
            existing_for_workflow = self.db.scalars(
                select(AiReasoningSession)
                .where(AiReasoningSession.workflow_id == workflow.id)
                .order_by(AiReasoningSession.started_at.desc())
            ).first()
            if existing_for_workflow:
                existing_for_workflow.status = "running"
                existing_for_workflow.ended_at = None
                summary = self._memory(existing_for_workflow)
                summary.setdefault("graph_run_lineage", []).append(graph_run.id)
                existing_for_workflow.session_summary = summary
                existing_for_workflow.updated_at = datetime.utcnow()
                self.db.commit()
                return existing_for_workflow
        existing = self.db.scalar(select(AiReasoningSession).where(AiReasoningSession.graph_run_id == graph_run.id))
        if existing:
            return existing
        session = AiReasoningSession(
            workflow_id=workflow.id,
            graph_run_id=graph_run.id,
            cti_event_id=workflow.cti_event_id,
            session_summary={
                "current_workflow": workflow.id,
                "behaviors_processed": [],
                "accepted_attack": [],
                "rejected_attack": [],
                "repair_history": [],
                "validation_history": [],
                "watcher_failures": [],
                "confidence_progression": [],
                "policy_decisions": [],
                "duplicates": [],
                "trust_progression": [],
                "repair_strategies_attempted": [],
                "repair_strategies_rejected": [],
                "selected_telemetry_fields": [],
                "observables_used": [],
                "candidate_selections": [],
                "current_proposal_id": None,
                "current_proposal_revision_id": None,
                "terminal_state": None,
                "graph_run_lineage": [graph_run.id],
                "current_revision": 0,
            },
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(session)
        self.db.commit()
        return session

    def session_for_run(self, graph_run_id: str) -> AiReasoningSession | None:
        direct = self.db.scalar(select(AiReasoningSession).where(AiReasoningSession.graph_run_id == graph_run_id))
        if direct:
            return direct
        graph_run = self.db.get(GraphRun, graph_run_id)
        if graph_run is None:
            return None
        return self.db.scalars(select(AiReasoningSession).where(AiReasoningSession.workflow_id == graph_run.workflow_id).order_by(AiReasoningSession.started_at.desc())).first()

    def update_node(self, graph_run_id: str, node_name: str) -> None:
        session = self.session_for_run(graph_run_id)
        if session:
            session.current_node = node_name
            session.updated_at = datetime.utcnow()
            self.db.commit()

    def record_watchers(self, graph_run_id: str, node_name: str, watchers: list[dict[str, Any]]) -> None:
        session = self.session_for_run(graph_run_id)
        if session is None:
            return
        for watcher in watchers:
            self.db.add(
                AiWatcherResult(
                    session_id=session.id,
                    graph_run_id=graph_run_id,
                    node_name=node_name,
                    watcher_name=str(watcher["watcher_name"]),
                    status=str(watcher["status"]),
                    message=str(watcher["message"]),
                    details=jsonable_encoder(watcher.get("details", {})),
                    created_at=datetime.utcnow(),
                )
            )
        summary = dict(session.session_summary or {})
        failures = summary.setdefault("watcher_failures", [])
        failures.extend(jsonable_encoder(watcher) for watcher in watchers if watcher.get("status") == FAIL)
        session.session_summary = summary
        session.updated_at = datetime.utcnow()
        self.db.commit()

    def record_confidence(self, graph_run_id: str, node_name: str, target_type: str, target_id: str | None, confidence_type: str, score: float, factors: dict[str, Any]) -> None:
        session = self.session_for_run(graph_run_id)
        if session is None:
            return
        self.db.add(
            AiConfidenceEvent(
                session_id=session.id,
                graph_run_id=graph_run_id,
                node_name=node_name,
                target_type=target_type,
                target_id=target_id,
                confidence_type=confidence_type,
                confidence_score=score,
                factors=jsonable_encoder(factors),
                created_at=datetime.utcnow(),
            )
        )
        session.confidence_score = score
        summary = dict(session.session_summary or {})
        summary.setdefault("confidence_progression", []).append({"node": node_name, "score": score, "type": confidence_type, "factors": jsonable_encoder(factors)})
        session.session_summary = summary
        session.updated_at = datetime.utcnow()
        self.db.commit()

    def record_revision(
        self,
        graph_run_id: str,
        behavior_id: str | None,
        proposal_id: str | None,
        stage: str,
        reason: str,
        candidate_snapshot: dict[str, Any] | None,
        validation_before: dict[str, Any] | None,
        validation_after: dict[str, Any] | None,
        confidence_before: float | None,
        confidence_after: float,
        termination_reason: str | None = None,
        candidate_before: dict[str, Any] | None = None,
        candidate_after: dict[str, Any] | None = None,
        changed_fields: list[str] | None = None,
        watcher_results: list[dict[str, Any]] | None = None,
        ai_confidence: float | None = None,
        trust_score: float | None = None,
        recommendation: str | None = None,
        stopping_decision: str | None = None,
        stopping_reason: str | None = None,
        route_selected: str | None = None,
    ) -> None:
        session = self.session_for_run(graph_run_id)
        if session is None:
            return
        parent = self.db.scalars(select(AiReasoningRevision).where(AiReasoningRevision.session_id == session.id).order_by(AiReasoningRevision.revision_number.desc())).first()
        revision_number = session.current_revision + 1
        delta = round(confidence_after - (confidence_before or 0.0), 4)
        improvements = self._improvements(validation_before, validation_after, delta)
        self.db.add(
            AiReasoningRevision(
                session_id=session.id,
                graph_run_id=graph_run_id,
                parent_reasoning_revision_id=parent.id if parent else None,
                behavior_id=behavior_id,
                proposal_id=proposal_id,
                proposal_revision_id=None,
                revision_number=revision_number,
                stage=stage,
                reason=reason,
                improvements=improvements,
                confidence_before=confidence_before,
                confidence_after=confidence_after,
                confidence_delta=delta,
                validation_before=jsonable_encoder(validation_before),
                validation_after=jsonable_encoder(validation_after),
                validation_delta={"confidence_delta": delta, "valid_after": bool((validation_after or {}).get("valid"))},
                termination_reason=termination_reason,
                candidate_snapshot=jsonable_encoder(candidate_snapshot),
                candidate_before=jsonable_encoder(candidate_before),
                candidate_after=jsonable_encoder(candidate_after or candidate_snapshot),
                changed_fields=changed_fields or [],
                watcher_results=jsonable_encoder(watcher_results or []),
                validation_results=jsonable_encoder(validation_after),
                ai_confidence=ai_confidence,
                calculated_confidence=confidence_after,
                trust_score=trust_score,
                recommendation=recommendation,
                stopping_decision=stopping_decision,
                stopping_reason=stopping_reason,
                route_selected=route_selected,
                created_at=datetime.utcnow(),
            )
        )
        session.current_revision = revision_number
        session.confidence_score = confidence_after
        session.termination_reason = termination_reason or session.termination_reason
        summary = dict(session.session_summary or {})
        summary["current_revision"] = revision_number
        summary.setdefault("repair_history", []).append({"stage": stage, "reason": reason, "improvements": improvements, "confidence_delta": delta})
        summary.setdefault("validation_history", []).append(jsonable_encoder(validation_after or {}))
        if validation_after and validation_after.get("duplicate_status"):
            summary.setdefault("duplicates", []).append(validation_after.get("duplicate_status"))
        if candidate_after or candidate_snapshot:
            selection = (candidate_after or candidate_snapshot or {}).get("detection", {}).get("selection") if isinstance(candidate_after or candidate_snapshot, dict) else None
            summary.setdefault("candidate_selections", []).append(jsonable_encoder(selection or {}))
        if trust_score is not None:
            summary.setdefault("trust_progression", []).append({"graph_run_id": graph_run_id, "score": trust_score, "recommendation": recommendation})
        session.session_summary = summary
        session.updated_at = datetime.utcnow()
        self.db.commit()

    def update_trust(self, graph_run_id: str, score: float, recommendation: str) -> None:
        session = self.session_for_run(graph_run_id)
        if session:
            session.trust_score = score
            session.approval_recommendation = recommendation
            session.updated_at = datetime.utcnow()
            self.db.commit()

    def attach_proposal_revision(self, graph_run_id: str, proposal_id: str, proposal_revision_id: str) -> None:
        session = self.session_for_run(graph_run_id)
        if not session:
            return
        revision = self.db.scalars(select(AiReasoningRevision).where(AiReasoningRevision.session_id == session.id).order_by(AiReasoningRevision.revision_number.desc())).first()
        if revision:
            revision.proposal_id = proposal_id
            revision.proposal_revision_id = proposal_revision_id
        summary = self._memory(session)
        summary["current_proposal_id"] = proposal_id
        summary["current_proposal_revision_id"] = proposal_revision_id
        session.session_summary = summary
        self.db.commit()

    def finish_session(self, graph_run_id: str, status: str, termination_reason: str | None) -> None:
        session = self.session_for_run(graph_run_id)
        if session:
            session.status = status
            session.termination_reason = termination_reason
            session.ended_at = datetime.utcnow()
            session.updated_at = datetime.utcnow()
            summary = self._memory(session)
            summary["terminal_state"] = termination_reason
            session.session_summary = summary
            self.db.commit()

    def _improvements(self, before: dict[str, Any] | None, after: dict[str, Any] | None, confidence_delta: float) -> list[str]:
        improvements: list[str] = []
        if confidence_delta > 0:
            improvements.append(f"confidence increased by {confidence_delta:.2f}")
        if before and after and before.get("valid") != after.get("valid"):
            improvements.append(f"validation changed from {before.get('valid')} to {after.get('valid')}")
        if after and after.get("quality_score") is not None:
            improvements.append(f"quality score {after.get('quality_score')}")
        return improvements or ["no measurable improvement"]

    def _memory(self, session: AiReasoningSession) -> dict[str, Any]:
        summary = dict(session.session_summary or {})
        for key, default in {
            "accepted_attack": [],
            "rejected_attack": [],
            "watcher_failures": [],
            "validation_history": [],
            "repair_strategies_attempted": [],
            "repair_strategies_rejected": [],
            "selected_telemetry_fields": [],
            "observables_used": [],
            "candidate_selections": [],
            "confidence_progression": [],
            "trust_progression": [],
            "duplicates": [],
            "policy_decisions": [],
            "graph_run_lineage": [],
        }.items():
            summary.setdefault(key, default)
        return summary


class ConsumptionStatusService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self) -> dict[str, Any]:
        settings = get_settings()
        from app.services.misp import MispIngestionScheduleService

        schedule = MispIngestionScheduleService(self.db).get()
        state = self.db.get(MispPollState, 1)
        last_success = state.updated_at if state else None
        scheduled_next = schedule.get("next_run_at") if schedule.get("configured") else None
        if scheduled_next:
            next_poll = scheduled_next
        elif last_success:
            next_poll = (last_success + timedelta(seconds=settings.misp_poll_interval_seconds)).isoformat()
        else:
            next_poll = None
        counts = {
            status: self.db.scalar(select(func.count()).select_from(CtiConsumptionRecord).where(CtiConsumptionRecord.status == status)) or 0
            for status in ["pending", "consumed", "skipped", "failed", "duplicate", "invalid_source_event", "already_processing"]
        }
        records = self.db.scalars(select(CtiConsumptionRecord).order_by(CtiConsumptionRecord.created_at.desc()).limit(25)).all()
        redis_status = "unknown"
        try:
            Redis.from_url(settings.redis_url).ping()
            redis_status = "reachable"
        except Exception:
            redis_status = "unreachable"
        return {
            "last_misp_poll": state.updated_at.isoformat() if state and state.updated_at else None,
            "last_successful_poll": last_success.isoformat() if last_success else None,
            "next_scheduled_poll": next_poll,
            "poll_interval_seconds": settings.misp_poll_interval_seconds,
            "ingestion_schedule": schedule,
            "strategy_options": ["manual", "scheduled", "immediate", "batch"],
            "counts": counts,
            "scheduler_status": redis_status,
            "worker_status": redis_status,
            "polling_status": "polling_successfully" if last_success else "not_polled",
            "queue": [
                {
                    "id": row.id,
                    "misp_event_id": row.misp_event_id,
                    "requested_misp_event_id": row.requested_misp_event_id,
                    "resolved_misp_event_id": row.resolved_misp_event_id,
                    "cti_event_id": row.cti_event_id,
                    "workflow_id": row.workflow_id,
                    "trigger_source": row.trigger_source,
                    "strategy": row.strategy,
                    "trigger_mode": row.trigger_mode,
                    "status": row.status,
                    "reason": row.reason,
                    "skip_reason": row.skip_reason,
                    "failure_reason": row.failure_reason,
                    "error_code": row.error_code,
                    "idempotency_key": row.idempotency_key,
                    "consumed_at": row.consumed_at.isoformat() if row.consumed_at else None,
                    "requested_at": row.requested_at.isoformat() if row.requested_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "created_at": row.created_at.isoformat(),
                }
                for row in records
            ],
        }


def latest_node_duration(db: Session, graph_run_id: str, node_name: str) -> int | None:
    node = db.scalars(select(GraphNodeRun).where(GraphNodeRun.graph_run_id == graph_run_id, GraphNodeRun.node_name == node_name).order_by(GraphNodeRun.started_at.desc())).first()
    return node.duration_ms if node else None
