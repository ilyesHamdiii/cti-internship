import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DetectionStatus, DetectionType
from app.models.models import (
    AttackMapping,
    Behavior,
    DetectionAttackMapping,
    DetectionCatalog,
    DeploymentArtifact,
    ProposalRevision,
    ValidationResult,
)


class DeploymentService:
    def __init__(self, db: Session, artifact_root: str = "/artifacts"):
        self.db = db
        self.artifact_root = Path(artifact_root)

    def create_artifact(self, revision: ProposalRevision) -> DeploymentArtifact:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        path = self.artifact_root / f"proposal-{revision.proposal_id}-rev-{revision.revision_number}.yml"
        path.write_text(revision.sigma_yaml, encoding="utf-8")
        checksum = hashlib.sha256(revision.sigma_yaml.encode("utf-8")).hexdigest()
        existing = self.db.scalar(
            select(DeploymentArtifact).where(
                DeploymentArtifact.proposal_id == revision.proposal_id,
                DeploymentArtifact.proposal_revision_id == revision.id,
                DeploymentArtifact.artifact_type == "sigma_package",
            )
        )
        if existing:
            return existing
        artifact = DeploymentArtifact(
            proposal_id=revision.proposal_id,
            proposal_revision_id=revision.id,
            artifact_type="sigma_package",
            file_path=str(path),
            checksum=checksum,
            artifact_metadata={"revision_number": revision.revision_number},
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def publish_detection(self, revision: ProposalRevision, artifact: DeploymentArtifact) -> DetectionCatalog:
        behavior = self.db.get(Behavior, revision.behavior_id)
        validation = self.db.scalar(
            select(ValidationResult).where(ValidationResult.proposal_revision_id == revision.id)
        )
        if behavior is None:
            raise ValueError("behavior_not_found")
        if validation is None or not validation.compilation_success:
            raise ValueError("validated_compilation_required")

        compiled_outputs = validation.compiled_outputs or {}
        normalized_logic = {
            "sigma": revision.sigma_json,
            "compiled_outputs": compiled_outputs,
            "proposal_id": revision.proposal_id,
            "proposal_revision_id": revision.id,
            "revision_number": revision.revision_number,
            "workflow_id": revision.workflow_id,
            "behavior_id": revision.behavior_id,
            "quality_score": validation.quality_score,
            "validation": {
                "schema_valid": validation.schema_valid,
                "sigma_valid": validation.sigma_valid,
                "compilation_success": validation.compilation_success,
                "duplicate_status": validation.duplicate_status,
                "telemetry_verified": validation.telemetry_verified,
                "attack_verified": validation.attack_verified,
                "warnings": validation.warnings,
                "errors": validation.errors,
            },
            "deployment_artifact_id": artifact.id,
        }
        name = str(revision.sigma_json.get("title") or behavior.summary)[:300]
        detection = self.db.scalar(
            select(DetectionCatalog).where(
                DetectionCatalog.source == "generated",
                DetectionCatalog.behavior_fingerprint == behavior.fingerprint,
            )
        )
        if detection is None:
            detection = DetectionCatalog(
                name=name,
                detection_type=DetectionType.sigma,
                source="generated",
                content=revision.sigma_yaml,
                normalized_logic=normalized_logic,
                behavior_fingerprint=behavior.fingerprint,
                status=DetectionStatus.active,
            )
            self.db.add(detection)
            self.db.flush()
        else:
            detection.name = name
            detection.content = revision.sigma_yaml
            detection.normalized_logic = normalized_logic
            detection.status = DetectionStatus.active

        mappings = self.db.scalars(
            select(AttackMapping).where(AttackMapping.behavior_id == revision.behavior_id, AttackMapping.verified.is_(True))
        ).all()
        for mapping in mappings:
            existing_mapping = self.db.scalar(
                select(DetectionAttackMapping).where(
                    DetectionAttackMapping.detection_id == detection.id,
                    DetectionAttackMapping.technique_id == mapping.technique_id,
                    DetectionAttackMapping.tactic_id == mapping.tactic_id,
                )
            )
            if existing_mapping is None:
                self.db.add(
                    DetectionAttackMapping(
                        detection_id=detection.id,
                        technique_id=mapping.technique_id,
                        tactic_id=mapping.tactic_id,
                    )
                )
        self.db.commit()
        self.db.refresh(detection)
        return detection
