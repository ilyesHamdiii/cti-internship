from app.models.enums import CoverageStatus, VisibilityStatus


def decide_policy(
    confidence: float,
    coverage_status: CoverageStatus,
    visibility_status: VisibilityStatus,
    verified_mapping_count: int,
) -> str:
    if confidence < 0.45 or verified_mapping_count == 0:
        return "insufficient_evidence"
    if coverage_status == CoverageStatus.covered:
        return "already_covered"
    if visibility_status == VisibilityStatus.gap:
        return "visibility_gap"
    return "generate_candidate"
