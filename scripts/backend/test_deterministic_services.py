from app.models.enums import CoverageStatus, VisibilityStatus
from app.schemas.ai import BehaviorCandidate, ProposedAttackMapping
from app.services.attack import AttackVerificationService
from app.services.fingerprinting import fingerprint_behavior
from app.services.policy import decide_policy
from app.services.sigma import SigmaValidationService


def test_fingerprint_is_deterministic_for_reordered_payloads() -> None:
    left = {
        "summary": " PowerShell  Encoded ",
        "attack": ["T1059.001"],
        "telemetry": [{"fields": ["b", "a"]}],
    }
    right = {
        "telemetry": [{"fields": ["a", "b"]}],
        "attack": ["T1059.001"],
        "summary": "powershell encoded",
    }
    assert fingerprint_behavior(left) == fingerprint_behavior(right)


def test_policy_already_covered_wins_before_generation() -> None:
    decision = decide_policy(0.9, CoverageStatus.covered, VisibilityStatus.visible, 1)
    assert decision == "already_covered"


def test_policy_visibility_gap_blocks_generation() -> None:
    decision = decide_policy(0.9, CoverageStatus.not_covered, VisibilityStatus.gap, 1)
    assert decision == "visibility_gap"


def test_policy_insufficient_evidence_blocks_generation() -> None:
    decision = decide_policy(0.2, CoverageStatus.not_covered, VisibilityStatus.visible, 1)
    assert decision == "insufficient_evidence"


def test_sigma_validation_requires_condition() -> None:
    result = SigmaValidationService().validate(
        {
            "title": "Bad Rule",
            "description": "This rule has enough text but lacks a condition.",
            "logsource": {"product": "windows"},
            "detection": {"selection": {"Image": "powershell.exe"}},
            "tags": ["attack.T1059.001"],
        },
        ["T1059.001"],
    )
    assert result["valid"] is False
    assert result["repairable"] is True


def test_sigma_validation_accepts_valid_candidate() -> None:
    result = SigmaValidationService().validate(
        {
            "title": "Suspicious PowerShell Encoded Command",
            "description": "Detects PowerShell execution using encoded command arguments from CTI evidence.",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"Image|endswith": "\\powershell.exe", "CommandLine|contains": "-enc"},
                "condition": "selection",
            },
            "tags": ["attack.T1059.001"],
            "falsepositives": ["Administrative scripts"],
            "level": "high",
        },
        ["T1059.001"],
    )
    assert result["valid"] is True
    assert result["quality_score"] >= 75


def test_sigma_validation_accepts_mixed_case_attack_tag() -> None:
    result = SigmaValidationService().validate(
        {
            "title": "Suspicious PowerShell Encoded Command",
            "description": "Detects PowerShell execution using encoded command arguments from CTI evidence.",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"Image|endswith": "\\powershell.exe", "CommandLine|contains": "-enc"},
                "condition": "selection",
            },
            "tags": ["attack.T1059.001"],
            "falsepositives": ["Administrative scripts"],
            "level": "high",
        },
        ["T1059.001"],
    )
    assert result["valid"] is True


class Technique:
    def __init__(
        self,
        technique_id="T1059.001",
        revoked=False,
        deprecated=False,
        tactics=None,
        platforms=None,
    ):
        self.technique_id = technique_id
        self.name = "PowerShell"
        self.revoked = revoked
        self.deprecated = deprecated
        self.tactics = tactics or ["execution"]
        self.platforms = platforms or ["Windows"]
        self.data_sources = ["Process: Process Creation"]
        self.version = "fixture-attack-reference"


class AttackDb:
    def __init__(self, technique):
        self.technique = technique

    def get(self, _model, _id):
        return self.technique


def mapping(**overrides) -> ProposedAttackMapping:
    payload = {
        "technique_id": "T1059.001",
        "technique_name": "PowerShell",
        "tactic_id": "execution",
        "tactic_name": "Execution",
        "evidence_refs": [
            {"ref": "attribute:1", "excerpt": "powershell", "source_field": "attributes"}
        ],
        "confidence": 0.9,
    }
    payload.update(overrides)
    return ProposedAttackMapping.model_validate(payload)


def behavior(**overrides) -> BehaviorCandidate:
    payload = {
        "behavior_key": "powershell_encoded",
        "summary": "PowerShell encoded command execution",
        "behavior_type": "process_execution",
        "actor_action": "execute",
        "target": "PowerShell",
        "execution_mechanism": "powershell.exe -EncodedCommand",
        "evidence_refs": [
            {"ref": "attribute:1", "excerpt": "powershell", "source_field": "attributes"}
        ],
        "observables": [{"type": "process", "value": "powershell.exe -EncodedCommand"}],
        "proposed_attack_mappings": [mapping().model_dump()],
        "required_telemetry": [{"category": "process", "fields": ["Image", "CommandLine"]}],
        "confidence": 0.9,
    }
    payload.update(overrides)
    return BehaviorCandidate.model_validate(payload)


def test_attack_verification_valid_mapping() -> None:
    result = AttackVerificationService(AttackDb(Technique())).verify(mapping(), behavior())

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["attack_version"] == "fixture-attack-reference"


def test_attack_verification_invalid_technique() -> None:
    result = AttackVerificationService(AttackDb(None)).verify(mapping(), behavior())

    assert result["verified"] is False
    assert result["status"] == "unknown_technique"


def test_attack_verification_revoked_technique() -> None:
    result = AttackVerificationService(AttackDb(Technique(revoked=True))).verify(
        mapping(), behavior()
    )

    assert result["verified"] is False
    assert result["status"] == "revoked"


def test_attack_verification_wrong_tactic() -> None:
    result = AttackVerificationService(AttackDb(Technique(tactics=["persistence"]))).verify(
        mapping(), behavior()
    )

    assert result["verified"] is False
    assert result["status"] == "tactic_mismatch"


def test_attack_verification_incompatible_platform() -> None:
    cloud_behavior = behavior(
        summary="Cloud control-plane action without telemetry",
        behavior_type="cloud_activity",
        execution_mechanism="cloud api",
        required_telemetry=[{"category": "cloud_audit", "fields": ["event_name"]}],
    )

    result = AttackVerificationService(AttackDb(Technique(platforms=["Windows"]))).verify(
        mapping(technique_id="T1059.001"), cloud_behavior
    )

    assert result["verified"] is False
    assert result["status"] == "platform_mismatch"


def test_attack_verification_unsupported_evidence() -> None:
    result = AttackVerificationService(AttackDb(Technique())).verify(
        mapping(
            evidence_refs=[{"ref": "attribute:99", "excerpt": "x", "source_field": "attributes"}]
        ),
        behavior(),
    )

    assert result["verified"] is False
    assert result["status"] == "unsupported_evidence"


def test_attack_verification_confidence_below_threshold() -> None:
    result = AttackVerificationService(AttackDb(Technique())).verify(
        mapping(confidence=0.2), behavior()
    )

    assert result["verified"] is False
    assert result["status"] == "confidence_below_threshold"
