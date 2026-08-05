from sqlalchemy.orm import Session

from app.models.models import AttackTechnique
from app.schemas.ai import BehaviorCandidate, ProposedAttackMapping


class AttackVerificationService:
    def __init__(self, db: Session):
        self.db = db

    def verify(
        self, mapping: ProposedAttackMapping, behavior: BehaviorCandidate | None = None
    ) -> dict[str, object]:
        technique = self.db.get(AttackTechnique, mapping.technique_id)
        if technique is None:
            return result(False, "unknown_technique", None, {"reason": "technique_id_not_found"})
        if technique.revoked:
            return result(False, "revoked", technique, {"attack_version": technique.version})
        if technique.deprecated:
            return result(False, "deprecated", technique, {"attack_version": technique.version})
        if (
            mapping.tactic_id not in technique.tactics
            and mapping.tactic_name not in technique.tactics
        ):
            return result(
                False,
                "tactic_mismatch",
                technique,
                {"expected_tactics": technique.tactics, "attack_version": technique.version},
            )
        if mapping.confidence < 0.5:
            return result(
                False,
                "confidence_below_threshold",
                technique,
                {
                    "threshold": 0.5,
                    "confidence": mapping.confidence,
                    "attack_version": technique.version,
                },
            )
        if not mapping.evidence_refs:
            return result(
                False, "missing_evidence", technique, {"attack_version": technique.version}
            )
        if behavior is not None:
            platform = infer_behavior_platform(behavior)
            if platform and not platform_compatible(platform, technique.platforms):
                return result(
                    False,
                    "platform_mismatch",
                    technique,
                    {
                        "behavior_platform": platform,
                        "technique_platforms": technique.platforms,
                        "attack_version": technique.version,
                    },
                )
            behavior_refs = {ref.ref for ref in behavior.evidence_refs}
            mapping_refs = {ref.ref for ref in mapping.evidence_refs}
            if not mapping_refs <= behavior_refs:
                return result(
                    False,
                    "unsupported_evidence",
                    technique,
                    {
                        "behavior_evidence_refs": sorted(behavior_refs),
                        "mapping_evidence_refs": sorted(mapping_refs),
                        "attack_version": technique.version,
                    },
                )
        return result(
            True,
            "verified",
            technique,
            {"attack_version": technique.version, "platforms": technique.platforms},
        )


def result(
    verified: bool, status: str, technique: AttackTechnique | None, details: dict[str, object]
) -> dict[str, object]:
    return {
        "verified": verified,
        "status": status,
        "technique": technique,
        "attack_version": getattr(technique, "version", None),
        "details": details,
    }


def infer_behavior_platform(behavior: BehaviorCandidate) -> str | None:
    context = " ".join(
        [
            behavior.summary,
            behavior.behavior_type,
            behavior.execution_mechanism,
            " ".join(str(item.get("category", "")) for item in behavior.required_telemetry),
        ]
    ).lower()
    if "cloud" in context or "audit" in context:
        return "cloud"
    if any(
        value in context
        for value in ["windows", "powershell", "wmic", "schtasks", "rundll32", "lsass", "process"]
    ):
        return "windows"
    return None


def platform_compatible(platform: str, technique_platforms: list[str]) -> bool:
    normalized = {item.lower() for item in technique_platforms}
    if platform == "cloud":
        return bool(normalized & {"iaas", "saas", "office suite", "identity provider", "cloud"})
    return platform in normalized
