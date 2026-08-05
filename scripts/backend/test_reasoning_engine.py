from types import SimpleNamespace

from app.graph import runner
from app.graph.runner import DetectionEngineeringGraph
from app.services.reasoning import ConfidenceEngine, SatisfactionEngine, TrustEngine, WatcherEngine


def test_behavior_watchers_fail_when_evidence_is_missing() -> None:
    normalized = {"attributes": [{"id": "1", "value": "powershell.exe -enc AAA"}]}
    response = {
        "behaviors": [
            {
                "summary": "PowerShell encoded command",
                "evidence_refs": [{"ref": "attribute:99"}],
                "proposed_attack_mappings": [{"technique_id": "T1059.001"}],
            }
        ]
    }

    watchers = WatcherEngine().evaluate_behavior_extraction(normalized, response)

    assert any(
        watcher["watcher_name"] == "evidence" and watcher["status"] == "FAIL"
        for watcher in watchers
    )


def test_candidate_watchers_and_confidence_reward_valid_unique_detection() -> None:
    candidate = {
        "title": "Suspicious PowerShell Encoded Command",
        "detection": {"selection": {"CommandLine|contains": "-enc"}, "condition": "selection"},
    }
    validation = {
        "valid": True,
        "repairable": False,
        "duplicate_status": "unique",
        "duplicate_result": {"status": "unique"},
    }
    watchers = WatcherEngine().evaluate_candidate(
        candidate, validation, ["Image", "CommandLine"], 0.9
    )

    confidence = ConfidenceEngine().assess(
        validation, watchers, 0.9, 0, "not_covered", "visible", "unique"
    )

    assert all(watcher["status"] == "PASS" for watcher in watchers)
    assert confidence["score"] >= 0.85


def test_trust_engine_does_not_approve_invalid_candidate_on_ai_confidence_alone() -> None:
    validation = {"valid": False, "repairable": True}
    watchers = [{"watcher_name": "sigma", "status": "FAIL", "message": "invalid", "details": {}}]

    result = TrustEngine().assess(validation, watchers, confidence=0.99)

    assert result["recommendation"] == "request_changes"
    assert result["score"] < 0.7


def test_route_validation_repairs_repairable_invalid_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: SimpleNamespace(
            max_repair_attempts=3, reasoning_max_revisions=3, reasoning_min_improvement_delta=0.03
        ),
    )
    graph = object.__new__(DetectionEngineeringGraph)

    route = graph._route_validation(
        {
            "validation": {"valid": False, "repairable": True, "confidence_delta": 0.2},
            "repair_attempts": 0,
        }
    )

    assert route == "repairable_invalid"


def test_route_validation_stops_on_max_revision_exhaustion(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: SimpleNamespace(
            max_repair_attempts=3, reasoning_max_revisions=2, reasoning_min_improvement_delta=0.03
        ),
    )
    graph = object.__new__(DetectionEngineeringGraph)
    state = {
        "validation": {"valid": False, "repairable": True, "confidence_delta": 0.2},
        "repair_attempts": 2,
    }

    route = graph._route_validation(state)

    assert route == "unrepairable_invalid"
    assert state["reasoning_termination_reason"] == "repair_limit_reached"


def test_route_validation_stops_on_minimum_improvement(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "get_settings",
        lambda: SimpleNamespace(
            max_repair_attempts=3, reasoning_max_revisions=3, reasoning_min_improvement_delta=0.03
        ),
    )
    graph = object.__new__(DetectionEngineeringGraph)
    state = {
        "validation": {"valid": False, "repairable": True, "confidence_delta": 0.01},
        "repair_attempts": 1,
    }

    route = graph._route_validation(state)

    assert route == "unrepairable_invalid"
    assert state["reasoning_termination_reason"] == "no_meaningful_improvement"


def test_trust_engine_rejects_nonrepairable_watcher_failure() -> None:
    validation = {"valid": False, "repairable": False}
    watchers = [{"watcher_name": "safety", "status": "FAIL", "message": "unsafe", "details": {}}]

    result = TrustEngine().assess(validation, watchers, confidence=0.95)

    assert result["recommendation"] == "reject"


def test_confidence_examples_cover_expected_quadrants() -> None:
    engine = ConfidenceEngine()
    passing_watchers = [{"status": "PASS"}] * 7
    failing_watchers = [{"status": "FAIL"}] * 3

    high_conf_low_trust = TrustEngine().assess(
        {"valid": False, "repairable": False}, failing_watchers, 0.95
    )
    medium_conf_high_trust = TrustEngine().assess(
        {"valid": True},
        passing_watchers,
        engine.assess(
            {"valid": True}, passing_watchers, 0.55, 0, "not_covered", "visible", "unique"
        )["score"],
    )
    high_conf_high_trust = TrustEngine().assess(
        {"valid": True},
        passing_watchers,
        engine.assess(
            {"valid": True}, passing_watchers, 0.95, 0, "not_covered", "visible", "unique"
        )["score"],
    )
    low_conf_low_trust = TrustEngine().assess(
        {"valid": False, "repairable": True}, failing_watchers, 0.2
    )

    assert high_conf_low_trust["recommendation"] == "reject"
    assert medium_conf_high_trust["score"] >= 0.75
    assert high_conf_high_trust["recommendation"] == "approve"
    assert low_conf_low_trust["recommendation"] == "request_changes"


def test_satisfaction_gate_routes_safety_failure_to_reject() -> None:
    decision = SatisfactionEngine().assess(
        validation={"valid": True, "repairable": False, "duplicate_status": "unique"},
        watchers=[
            {"watcher_name": "schema", "status": "PASS"},
            {"watcher_name": "sigma", "status": "PASS"},
            {"watcher_name": "telemetry", "status": "PASS"},
            {"watcher_name": "safety", "status": "FAIL"},
        ],
        confidence=0.95,
        trust=0.2,
    )

    assert decision["route_selected"] == "reject"
    assert decision["blocking_reason"] == "safety_watcher_failed"


def test_satisfaction_gate_routes_visibility_gap_to_terminal() -> None:
    decision = SatisfactionEngine().assess(
        validation={"valid": True, "repairable": False, "duplicate_status": "unique"},
        watchers=[
            {"watcher_name": "schema", "status": "PASS"},
            {"watcher_name": "sigma", "status": "PASS"},
            {"watcher_name": "telemetry", "status": "WARNING"},
            {"watcher_name": "safety", "status": "PASS"},
        ],
        confidence=0.91,
        trust=0.7,
    )

    assert decision["route_selected"] == "terminal_visibility_gap"
    assert decision["blocking_reason"] == "telemetry_watcher_failed"


def test_satisfaction_gate_routes_exact_duplicate_to_covered_terminal() -> None:
    decision = SatisfactionEngine().assess(
        validation={"valid": True, "repairable": False, "duplicate_status": "exact_duplicate"},
        watchers=[
            {"watcher_name": "schema", "status": "PASS"},
            {"watcher_name": "sigma", "status": "PASS"},
            {"watcher_name": "telemetry", "status": "PASS"},
            {"watcher_name": "safety", "status": "PASS"},
        ],
        confidence=0.94,
        trust=0.9,
    )

    assert decision["route_selected"] == "terminal_covered"
    assert decision["blocking_reason"] == "exact_duplicate"


def test_satisfaction_gate_routes_repairable_sigma_failure_to_repair() -> None:
    decision = SatisfactionEngine().assess(
        validation={"valid": False, "repairable": True, "duplicate_status": "unique"},
        watchers=[
            {"watcher_name": "schema", "status": "PASS"},
            {"watcher_name": "sigma", "status": "FAIL"},
            {"watcher_name": "telemetry", "status": "PASS"},
            {"watcher_name": "safety", "status": "PASS"},
        ],
        confidence=0.6,
        trust=0.45,
    )

    assert decision["route_selected"] == "repair_candidate"
    assert decision["blocking_reason"] == "mandatory_watcher_failed"
