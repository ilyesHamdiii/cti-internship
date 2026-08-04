import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DetectionStatus
from app.models.models import DetectionCatalog
from app.services.fingerprinting import similarity_score


class DuplicateDetectionService:
    def __init__(self, db: Session):
        self.db = db

    def analyze(self, candidate: dict[str, Any], compiled_query: str | None) -> dict[str, Any]:
        if not comparable(candidate, compiled_query):
            return {
                "status": "unknown",
                "matches": [],
                "matched_detection_id": None,
                "score": 0.0,
                "threshold": None,
                "similarity_features": {"candidate_comparable": False, "compiled_query_present": bool(compiled_query)},
                "rationale": {"decision_factors": ["insufficient_comparable_signal"]},
                "recommended_action": "allow_review_without_uniqueness_claim",
            }
        detections = self.db.scalars(select(DetectionCatalog).where(DetectionCatalog.status == DetectionStatus.active)).all()
        candidate_fingerprint = canonical_fingerprint(candidate)
        declared_supersedes = candidate.get("supersedes_detection_id") or candidate.get("replaces_detection_id")
        best = duplicate_result("unique", None, 0.0, "no_active_catalog_match", None, {"candidate_fingerprint": candidate_fingerprint})
        for detection in detections:
            normalized = detection.normalized_logic or {}
            existing_sigma = normalized.get("sigma") or normalized.get("content") or normalized
            score = similarity_score(candidate, existing_sigma)
            existing_query = (normalized.get("compiled_outputs") or {}).get("query")
            if compiled_query and existing_query and compiled_query == existing_query:
                score = max(score, 1.0)
            elif compiled_query and existing_query:
                score = max(score, query_similarity(compiled_query, existing_query))
            if canonical_fingerprint(existing_sigma) == candidate_fingerprint:
                status = "exact_duplicate"
                score = 1.0
            elif declared_supersedes and str(declared_supersedes) == str(detection.id):
                status = "supersedes"
                score = max(score, 0.9)
            elif score >= 0.86:
                status = "near_duplicate"
            elif score >= 0.65:
                status = "overlapping"
            else:
                status = "unique"
            if score > best["score"]:
                best = duplicate_result(
                    status,
                    detection.id if status != "unique" else None,
                    score,
                    "canonical_sigma_similarity" if status != "supersedes" else "declared_supersedes_active_detection",
                    threshold_for(status),
                    {
                        "candidate_fingerprint": candidate_fingerprint,
                        "existing_query_present": bool(existing_query),
                        "compiled_query_equal": bool(compiled_query and existing_query and compiled_query == existing_query),
                    },
                )
        return best


def canonical_fingerprint(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str).lower()


def query_similarity(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-z0-9_.\\\\-]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9_.\\\\-]+", right.lower()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def comparable(candidate: dict[str, Any], compiled_query: str | None) -> bool:
    detection = candidate.get("detection")
    return isinstance(detection, dict) and bool(detection.get("selection")) and bool(compiled_query)


def threshold_for(status: str) -> float | None:
    return {
        "exact_duplicate": 1.0,
        "near_duplicate": 0.86,
        "overlapping": 0.65,
        "supersedes": 0.9,
        "unique": 0.65,
        "unknown": None,
    }.get(status)


def recommended_action(status: str) -> str:
    return {
        "unique": "allow_review",
        "exact_duplicate": "block_generation_or_mark_covered",
        "near_duplicate": "allow_review_with_warning",
        "overlapping": "display_overlap_evidence",
        "supersedes": "require_analyst_confirmation_before_replacement",
        "unknown": "allow_review_without_uniqueness_claim",
    }[status]


def duplicate_result(status: str, detection_id: str | None, score: float, factor: str, threshold: float | None, features: dict[str, object]) -> dict[str, Any]:
    return {
        "status": status,
        "matches": [detection_id] if detection_id else [],
        "matched_detection_id": detection_id,
        "score": score,
        "threshold": threshold,
        "similarity_features": features,
        "rationale": {"decision_factors": [factor], "thresholds": {"exact_duplicate": 1.0, "near_duplicate": 0.86, "overlapping": 0.65, "supersedes": 0.9}},
        "recommended_action": recommended_action(status),
    }
