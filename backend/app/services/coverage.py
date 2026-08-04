from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CoverageStatus, DetectionStatus
from app.models.models import DetectionCatalog
from app.services.fingerprinting import similarity_score


class CoverageService:
    def __init__(self, db: Session):
        self.db = db

    def analyze(self, fingerprint: str, behavior_payload: dict[str, object]) -> dict[str, object]:
        detections = self.db.scalars(
            select(DetectionCatalog).where(DetectionCatalog.status == DetectionStatus.active)
        ).all()
        exact = [d.id for d in detections if d.behavior_fingerprint == fingerprint]
        if exact:
            return {
                "status": CoverageStatus.covered,
                "matches": exact,
                "score": 1.0,
                "rationale": {"decision_factors": ["exact_behavior_fingerprint_match"]},
            }
        best_score = 0.0
        best_ids: list[str] = []
        for detection in detections:
            score = similarity_score(behavior_payload, detection.normalized_logic)
            if score > best_score:
                best_score = score
                best_ids = [detection.id]
        if best_score >= 0.72:
            status = CoverageStatus.partial
        else:
            status = CoverageStatus.not_covered
            best_ids = []
        return {
            "status": status,
            "matches": best_ids,
            "score": best_score,
            "rationale": {"decision_factors": ["logic_similarity"], "similarity": best_score},
        }
