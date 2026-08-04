from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import VisibilityStatus
from app.models.models import TelemetrySource


class TelemetryService:
    def __init__(self, db: Session):
        self.db = db

    def analyze(self, required_sources: list[dict[str, object]]) -> dict[str, object]:
        sources = self.db.scalars(select(TelemetrySource).where(TelemetrySource.enabled.is_(True))).all()
        available_ids: list[str] = []
        missing: list[dict[str, object]] = []
        for required in required_sources:
            category = str(required.get("category", "")).lower()
            fields = {str(field).lower() for field in required.get("fields", [])}
            matched = [
                source
                for source in sources
                if source.category.lower() == category
                and fields.issubset({field.lower() for field in source.fields})
            ]
            if matched:
                available_ids.extend(source.id for source in matched)
            else:
                missing.append(required)
        if not required_sources:
            status = VisibilityStatus.gap
        elif not missing:
            status = VisibilityStatus.visible
        elif available_ids:
            status = VisibilityStatus.partial
        else:
            status = VisibilityStatus.gap
        return {
            "status": status,
            "available_source_ids": sorted(set(available_ids)),
            "missing_sources": missing,
            "rationale": {"decision_factors": ["authoritative_telemetry_inventory"]},
        }
