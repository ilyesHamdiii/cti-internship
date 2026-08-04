from datetime import datetime, timedelta
import hashlib
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import CtiConsumptionRecord, CtiEvent, GraphRun, MispPollState, Setting, Workflow

logger = logging.getLogger(__name__)

SCHEDULE_SETTING_KEY = "misp_ingestion_schedule"


class MispIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def normalize_event(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        event = raw_event.get("Event", raw_event)
        if not isinstance(event, dict) or not (event.get("id") or event.get("uuid")):
            raise ValueError("invalid_source_event")
        attributes = event.get("Attribute", [])
        return {
            "misp_event_id": str(event.get("id") or event.get("uuid")),
            "title": event.get("info", "Untitled MISP event"),
            "published": bool(event.get("published", False)),
            "timestamp": event.get("timestamp"),
            "tags": [tag.get("name", "") for tag in event.get("Tag", [])],
            "attributes": [
                {
                    "id": str(attr.get("id", index)),
                    "type": attr.get("type", "text"),
                    "category": attr.get("category", "Other"),
                    "value": attr.get("value", ""),
                    "comment": attr.get("comment", ""),
                }
                for index, attr in enumerate(attributes, start=1)
            ],
            "evidence_text": "\n".join(str(attr.get("value", "")) for attr in attributes),
        }

    def ingest_raw_event(self, raw_event: dict[str, Any], trigger_source: str = "manual", strategy: str = "manual", requested_misp_event_id: str | None = None) -> tuple[CtiEvent, Workflow, bool]:
        requested_at = datetime.utcnow()
        normalized = self.normalize_event(raw_event)
        misp_event_id = normalized["misp_event_id"]
        existing = self.db.scalar(select(CtiEvent).where(CtiEvent.misp_event_id == misp_event_id))
        if existing is not None:
            workflow = existing.workflow
            running = self.db.scalars(select(GraphRun).where(GraphRun.workflow_id == workflow.id).order_by(GraphRun.created_at.desc())).first() if workflow else None
            running_status = str(getattr(running.status, "value", running.status)) if running else ""
            status = "already_processing" if running and running_status == "running" else "duplicate"
            self._record_consumption(
                requested_misp_event_id or misp_event_id,
                misp_event_id,
                trigger_source,
                strategy,
                status,
                "Workflow already running for this MISP event" if status == "already_processing" else "MISP event already exists in cti_events",
                cti_event_id=existing.id,
                workflow_id=workflow.id if workflow else None,
                requested_at=requested_at,
            )
            return existing, existing.workflow, False
        cti_event = CtiEvent(
            misp_event_id=misp_event_id,
            title=normalized["title"],
            raw_event=raw_event,
            normalized_event=normalized,
            received_at=datetime.utcnow(),
        )
        self.db.add(cti_event)
        self.db.flush()
        workflow = Workflow(cti_event_id=cti_event.id)
        self.db.add(workflow)
        self.db.flush()
        self._record_consumption(
            requested_misp_event_id or misp_event_id,
            misp_event_id,
            trigger_source,
            strategy,
            "consumed",
            "MISP event normalized and workflow created",
            cti_event_id=cti_event.id,
            workflow_id=workflow.id,
            consumed_at=datetime.utcnow(),
            requested_at=requested_at,
        )
        self.db.commit()
        self.db.refresh(cti_event)
        self.db.refresh(workflow)
        return cti_event, workflow, True

    def _record_consumption(
        self,
        requested_misp_event_id: str | None,
        resolved_misp_event_id: str | None,
        trigger_source: str,
        strategy: str,
        status: str,
        reason: str,
        cti_event_id: str | None = None,
        workflow_id: str | None = None,
        consumed_at: datetime | None = None,
        requested_at: datetime | None = None,
        error_code: str | None = None,
    ) -> None:
        completed_at = datetime.utcnow()
        key_material = f"{trigger_source}:{strategy}:{requested_misp_event_id}:{resolved_misp_event_id}:{status}:{completed_at.isoformat()}"
        self.db.add(
            CtiConsumptionRecord(
                misp_event_id=resolved_misp_event_id,
                requested_misp_event_id=requested_misp_event_id,
                resolved_misp_event_id=resolved_misp_event_id,
                cti_event_id=cti_event_id,
                workflow_id=workflow_id,
                trigger_source=trigger_source,
                trigger_mode=strategy,
                strategy=strategy,
                status=status,
                reason=reason,
                skip_reason=reason if status == "skipped" else None,
                failure_reason=reason if status in {"failed", "invalid_source_event"} else None,
                error_code=error_code,
                consumed_at=consumed_at,
                requested_at=requested_at or completed_at,
                completed_at=completed_at,
                idempotency_key=hashlib.sha256(key_material.encode()).hexdigest(),
                created_at=completed_at,
            )
        )
        self.db.commit()


class MispApiService:
    def __init__(self, db: Session):
        self.db = db

    def _client(self) -> Any:
        settings = get_settings()
        if settings.misp_api_key is None:
            raise ValueError("misp_api_key_missing")
        from pymisp import PyMISP

        return PyMISP(
            settings.misp_url,
            settings.misp_api_key.get_secret_value(),
            ssl=settings.misp_verify_tls,
        )

    def list_events(self, limit: int = 50, status_filter: str = "all", deduplicate: bool = True) -> list[dict[str, Any]]:
        client = self._client()
        events = client.search(controller="events", metadata=True, limit=limit)
        result: list[dict[str, Any]] = []
        for raw in events if isinstance(events, list) else []:
            event = raw.get("Event", raw)
            event_id = str(event.get("id") or event.get("uuid"))
            ingested = self.db.scalar(select(CtiEvent).where(CtiEvent.misp_event_id == event_id))
            workflow = ingested.workflow if ingested else None
            current_run = None
            if workflow:
                current_run = self.db.scalars(
                    select(GraphRun)
                    .where(GraphRun.workflow_id == workflow.id)
                    .order_by(GraphRun.created_at.desc())
                ).first()
            if ingested is None:
                status = "new"
            elif current_run and str(current_run.status) == "running":
                status = "processing"
            elif workflow and str(workflow.status) in {"failed"}:
                status = "failed"
            elif workflow and str(workflow.status) in {"waiting_review", "deployed", "rejected"}:
                status = "processed"
            else:
                status = "already_ingested"
            can_ingest = status == "new"
            actionable = status in {"new", "failed"}
            result.append(
                {
                    "misp_event_id": event_id,
                    "uuid": event.get("uuid"),
                    "title": event.get("info", "Untitled MISP event"),
                    "published": bool(event.get("published", False)),
                    "timestamp": event.get("timestamp"),
                    "attribute_count": int(event.get("attribute_count") or 0),
                    "ingestion_status": status,
                    "actionable": actionable,
                    "can_ingest": can_ingest,
                    "cti_event_id": ingested.id if ingested else None,
                    "workflow_id": workflow.id if workflow else None,
                    "workflow_status": workflow.status if workflow else None,
                    "graph_run_id": current_run.id if current_run else None,
                    "graph_status": current_run.status if current_run else None,
                }
            )
        if deduplicate:
            result = collapse_duplicate_misp_events(result)
        def sort_key(item: dict[str, Any]) -> tuple[int, int]:
            try:
                timestamp = int(item.get("timestamp") or 0)
            except (TypeError, ValueError):
                timestamp = 0
            return (0 if item["can_ingest"] else 1 if item["actionable"] else 2, -timestamp)

        result.sort(key=sort_key)
        if status_filter == "actionable":
            return [item for item in result if item["actionable"]]
        if status_filter == "new":
            return [item for item in result if item["can_ingest"]]
        return result

    def fetch_event(self, misp_event_id: str) -> dict[str, Any]:
        event = self._client().get_event(misp_event_id, pythonify=False)
        payload = event.get("Event", event) if isinstance(event, dict) else None
        if not event or not isinstance(payload, dict) or not (payload.get("id") or payload.get("uuid")):
            raise ValueError("misp_event_not_found")
        return event

    def ingest_event(self, misp_event_id: str, trigger_source: str = "manual", strategy: str = "manual") -> tuple[CtiEvent, Workflow, bool]:
        try:
            raw = self.fetch_event(misp_event_id)
        except Exception as exc:
            MispIngestionService(self.db)._record_consumption(
                misp_event_id,
                None,
                trigger_source,
                strategy,
                "failed",
                "MISP event was not found or could not be fetched",
                error_code="MISP_EVENT_NOT_FOUND" if "not_found" in str(exc) else "MISP_FETCH_FAILED",
            )
            raise
        return MispIngestionService(self.db).ingest_raw_event(raw, trigger_source=trigger_source, strategy=strategy, requested_misp_event_id=misp_event_id)

    def ingest_all_new(self, limit: int = 50) -> dict[str, Any]:
        created = 0
        existing = 0
        skipped = 0
        workflow_ids: list[str] = []
        cti_event_ids: list[str] = []
        for event in self.list_events(limit, status_filter="all", deduplicate=False):
            if event["ingestion_status"] != "new":
                skipped += 1
                MispIngestionService(self.db)._record_consumption(
                    str(event["misp_event_id"]),
                    str(event["misp_event_id"]),
                    "manual",
                    "batch",
                    "skipped",
                    f"Batch skipped event with status {event['ingestion_status']}",
                    cti_event_id=event.get("cti_event_id"),
                    workflow_id=event.get("workflow_id"),
                )
                continue
            _, _, was_created = self.ingest_event(str(event["misp_event_id"]), trigger_source="manual", strategy="batch")
            if was_created:
                created += 1
                raw_cti = self.db.scalar(select(CtiEvent).where(CtiEvent.misp_event_id == str(event["misp_event_id"])))
                if raw_cti and raw_cti.workflow:
                    cti_event_ids.append(raw_cti.id)
                    workflow_ids.append(raw_cti.workflow.id)
            else:
                existing += 1
        return {"created": created, "existing": existing, "skipped": skipped, "cti_event_ids": cti_event_ids, "workflow_ids": workflow_ids}


def collapse_duplicate_misp_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(canonical_misp_title(str(event.get("title") or "")), []).append(event)

    collapsed: list[dict[str, Any]] = []
    for group in grouped.values():
        ranked = sorted(group, key=duplicate_rank)
        representative = dict(ranked[0])
        if len(group) > 1:
            representative["duplicate_count"] = len(group)
            representative["duplicate_misp_event_ids"] = [item["misp_event_id"] for item in group]
            representative["duplicate_cti_event_ids"] = [item["cti_event_id"] for item in group if item.get("cti_event_id")]
            representative["title"] = canonical_display_title(str(representative.get("title") or "Untitled MISP event"))
        else:
            representative["duplicate_count"] = 1
            representative["duplicate_misp_event_ids"] = [representative["misp_event_id"]]
            representative["duplicate_cti_event_ids"] = [representative["cti_event_id"]] if representative.get("cti_event_id") else []
        collapsed.append(representative)
    return collapsed


def duplicate_rank(event: dict[str, Any]) -> tuple[int, int]:
    try:
        timestamp = int(event.get("timestamp") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    status = str(event.get("ingestion_status") or "")
    status_rank = {"new": 0, "failed": 1, "processing": 2, "already_ingested": 3, "processed": 4}.get(status, 5)
    return (status_rank, -timestamp)


def canonical_misp_title(title: str) -> str:
    cleaned = canonical_display_title(title).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip() or "untitled"


def canonical_display_title(title: str) -> str:
    cleaned = re.sub(r"\bcti-platform-[a-z0-9_-]*-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip() or title


class MispPollingService:
    def __init__(self, db: Session):
        self.db = db

    def poll(self) -> dict[str, int]:
        settings = get_settings()
        logger.info("misp_poll_started")
        schedule = MispIngestionScheduleService(self.db)
        due = schedule.due_status()
        if due.get("configured") and not due["due"]:
            logger.info("misp_poll_skipped_not_due next_run_at=%s", due.get("next_run_at"))
            return {
                "discovered": 0,
                "created": 0,
                "enqueued": 0,
                "skipped": 1,
                "reason": "not_due",
                "next_run_at": due.get("next_run_at"),
            }
        if settings.misp_api_key is None:
            logger.warning("misp_poll_skipped_missing_api_key")
            return {"discovered": 0, "created": 0, "enqueued": 0}
        from pymisp import PyMISP

        client = PyMISP(
            settings.misp_url,
            settings.misp_api_key.get_secret_value(),
            ssl=settings.misp_verify_tls,
        )
        state = self.db.get(MispPollState, 1)
        if state is None:
            state = MispPollState(id=1)
            self.db.add(state)
            self.db.commit()
        search_args: dict[str, Any] = {"controller": "events", "metadata": False}
        if state.last_event_timestamp:
            search_args["timestamp"] = int(state.last_event_timestamp.timestamp())
        try:
            events = client.search(**search_args)
        except Exception:
            self.db.add(
                CtiConsumptionRecord(
                    trigger_source="scheduler",
                    strategy="scheduled",
                    status="failed",
                    reason="MISP scheduled poll failed",
                    created_at=datetime.utcnow(),
                )
            )
            self.db.commit()
            logger.exception("misp_poll_failed")
            raise
        logger.info("misp_poll_events_returned count=%s", len(events) if isinstance(events, list) else 0)
        discovered = 0
        created = 0
        enqueued = 0
        ingestion = MispIngestionService(self.db)
        newest_id = state.last_event_id
        newest_time = state.last_event_timestamp
        for raw in events if isinstance(events, list) else []:
            discovered += 1
            event, workflow, was_created = ingestion.ingest_raw_event(raw, trigger_source="scheduler", strategy="scheduled")
            if was_created:
                created += 1
                from app.workers.tasks import run_graph

                run_graph.delay(workflow.id)
                enqueued += 1
                logger.info("misp_event_ingested event_id=%s workflow_id=%s", event.misp_event_id, workflow.id)
            else:
                logger.info("misp_event_duplicate_skipped event_id=%s", event.misp_event_id)
            newest_id = event.misp_event_id
            newest_time = event.received_at
        state.last_event_id = newest_id
        state.last_event_timestamp = newest_time
        state.updated_at = datetime.utcnow()
        schedule.mark_completed()
        self.db.commit()
        logger.info("misp_poll_finished discovered=%s created=%s enqueued=%s", discovered, created, enqueued)
        return {"discovered": discovered, "created": created, "enqueued": enqueued}


class MispIngestionScheduleService:
    def __init__(self, db: Session):
        self.db = db

    def get(self) -> dict[str, Any]:
        item = self.db.get(Setting, SCHEDULE_SETTING_KEY)
        if item is None:
            return self._default_schedule()
        value = dict(item.value)
        value.setdefault("configured", True)
        value.setdefault("enabled", value.get("mode") != "disabled")
        return value

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "disabled")
        enabled = bool(payload.get("enabled", True)) and mode != "disabled"
        now = datetime.utcnow()
        schedule = {
            "configured": True,
            "enabled": enabled,
            "mode": mode if enabled else "disabled",
            "interval_seconds": get_settings().misp_poll_interval_seconds if mode == "interval" else None,
            "time_of_day": payload.get("time_of_day"),
            "weekday": payload.get("weekday"),
            "timezone_offset_minutes": int(payload.get("timezone_offset_minutes") or 0),
            "last_triggered_at": None,
            "updated_at": now.isoformat(),
        }
        schedule["next_run_at"] = self._next_run_at(schedule, payload.get("run_at"), now).isoformat() if enabled else None
        item = self.db.get(Setting, SCHEDULE_SETTING_KEY)
        if item is None:
            item = Setting(key=SCHEDULE_SETTING_KEY, value=schedule)
            self.db.add(item)
        else:
            existing = dict(item.value)
            schedule["last_triggered_at"] = existing.get("last_triggered_at")
            item.value = schedule
        self.db.commit()
        return schedule

    def due_status(self) -> dict[str, Any]:
        schedule = self.get()
        if not schedule.get("configured"):
            return {"configured": False, "due": True, **schedule}
        if not schedule.get("enabled") or schedule.get("mode") == "disabled":
            return {"configured": True, "due": False, **schedule}
        next_run = self._parse_datetime(schedule.get("next_run_at"))
        if next_run is None:
            return {"configured": True, "due": True, **schedule}
        return {"configured": True, "due": datetime.utcnow() >= next_run, **schedule}

    def mark_completed(self) -> dict[str, Any]:
        item = self.db.get(Setting, SCHEDULE_SETTING_KEY)
        if item is None:
            return self._default_schedule()
        schedule = dict(item.value)
        now = datetime.utcnow()
        schedule["last_triggered_at"] = now.isoformat()
        if schedule.get("mode") == "once":
            schedule["enabled"] = False
            schedule["mode"] = "disabled"
            schedule["next_run_at"] = None
        elif schedule.get("enabled"):
            schedule["next_run_at"] = self._next_run_after_completion(schedule, now).isoformat()
        schedule["updated_at"] = now.isoformat()
        item.value = schedule
        return schedule

    def _default_schedule(self) -> dict[str, Any]:
        settings = get_settings()
        next_interval = datetime.utcnow() + timedelta(seconds=settings.misp_poll_interval_seconds)
        return {
            "configured": False,
            "enabled": True,
            "mode": "interval",
            "interval_seconds": settings.misp_poll_interval_seconds,
            "next_run_at": next_interval.isoformat(),
            "last_triggered_at": None,
        }

    def _next_run_at(self, schedule: dict[str, Any], run_at: Any, now: datetime) -> datetime:
        mode = schedule["mode"]
        if mode == "once":
            parsed = self._parse_datetime(run_at)
            return parsed if parsed and parsed > now else now
        if mode == "interval":
            return now + timedelta(seconds=get_settings().misp_poll_interval_seconds)
        if mode == "hourly":
            return now + timedelta(hours=1)
        local_now = now + timedelta(minutes=int(schedule.get("timezone_offset_minutes") or 0))
        hour, minute = self._parse_time(schedule.get("time_of_day") or "00:00")
        local_target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if mode == "daily":
            if local_target <= local_now:
                local_target += timedelta(days=1)
        elif mode == "weekly":
            target_weekday = int(schedule.get("weekday") or 0)
            days_ahead = (target_weekday - local_now.weekday()) % 7
            local_target += timedelta(days=days_ahead)
            if local_target <= local_now:
                local_target += timedelta(days=7)
        return local_target - timedelta(minutes=int(schedule.get("timezone_offset_minutes") or 0))

    def _next_run_after_completion(self, schedule: dict[str, Any], now: datetime) -> datetime:
        mode = str(schedule.get("mode") or "disabled")
        if mode == "interval":
            return now + timedelta(seconds=int(schedule.get("interval_seconds") or get_settings().misp_poll_interval_seconds))
        if mode == "hourly":
            return now + timedelta(hours=1)
        if mode == "daily":
            return self._next_run_at(schedule, None, now + timedelta(seconds=1))
        if mode == "weekly":
            base = self._parse_datetime(schedule.get("next_run_at")) or now
            return base + timedelta(days=7)
        return now

    def _parse_time(self, value: str) -> tuple[int, int]:
        hour, minute = value.split(":", 1)
        return int(hour), int(minute)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed


class MispConnectivityService:
    def __init__(self, db: Session):
        self.db = db

    def check(self) -> dict[str, Any]:
        settings = get_settings()
        configured = bool(settings.misp_url and settings.misp_api_key)
        result: dict[str, Any] = {
            "configured": configured,
            "reachable": False,
            "authenticated": False,
            "polling_successfully": False,
            "url": settings.misp_url,
            "verify_tls": settings.misp_verify_tls,
        }
        if not configured:
            result["status"] = "not_configured"
            result["reason"] = "CTI_MISP_URL or CTI_MISP_API_KEY is missing"
            return result

        headers = {
            "Authorization": settings.misp_api_key.get_secret_value(),
            "Accept": "application/json",
        }
        try:
            with httpx.Client(verify=settings.misp_verify_tls, timeout=10.0, follow_redirects=True) as client:
                heartbeat = client.get(f"{settings.misp_url.rstrip('/')}/users/heartbeat")
                result["reachable"] = heartbeat.status_code < 500
                auth_response = client.get(f"{settings.misp_url.rstrip('/')}/users/view/me", headers=headers)
        except httpx.RequestError as exc:
            result["status"] = "unreachable"
            result["reason"] = str(exc)
            return result

        if not result["reachable"]:
            result["status"] = "unreachable"
            result["reason"] = f"heartbeat returned HTTP {heartbeat.status_code}"
            return result
        if auth_response.status_code in {401, 403}:
            result["status"] = "authentication_failed"
            result["reason"] = f"authenticated probe returned HTTP {auth_response.status_code}"
            return result
        if auth_response.status_code >= 400:
            result["status"] = "unreachable"
            result["reason"] = f"authenticated user probe returned HTTP {auth_response.status_code}"
            return result

        state = self.db.get(MispPollState, 1)
        result["authenticated"] = True
        result["polling_successfully"] = bool(state and state.updated_at)
        result["last_poll_at"] = state.updated_at.isoformat() if state and state.updated_at else None
        result["last_event_id"] = state.last_event_id if state else None
        result["status"] = "healthy" if result["polling_successfully"] else "authenticated"
        if result["status"] == "authenticated":
            result["reason"] = "MISP API authentication works; no scheduler poll state has been persisted yet"
        return result
