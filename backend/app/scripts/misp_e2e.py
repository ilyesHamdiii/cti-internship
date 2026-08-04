from __future__ import annotations

from datetime import datetime
import time
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import CtiEvent, GraphRun, Workflow
from app.services.misp import MispPollingService


def create_misp_event() -> dict[str, Any]:
    settings = get_settings()
    if settings.misp_api_key is None:
        raise RuntimeError("CTI_MISP_API_KEY is required")

    marker = f"cti-platform-e2e-{uuid4()}"
    payload = {
        "Event": {
            "info": f"CTI Platform E2E PowerShell Test {marker}",
            "distribution": "0",
            "threat_level_id": "2",
            "analysis": "0",
            "published": False,
            "Attribute": [
                {
                    "type": "text",
                    "category": "External analysis",
                    "to_ids": False,
                    "value": "PowerShell downloads and executes remote content with encoded command arguments.",
                    "comment": marker,
                },
                {
                    "type": "ip-dst",
                    "category": "Network activity",
                    "to_ids": True,
                    "value": "203.0.113.44",
                    "comment": marker,
                },
            ],
            "Tag": [{"name": "tlp:amber"}],
        }
    }
    headers = {
        "Authorization": settings.misp_api_key.get_secret_value(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(verify=settings.misp_verify_tls, timeout=30.0, follow_redirects=True) as client:
        response = client.post(
            f"{settings.misp_url.rstrip('/')}/events/add",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return {"marker": marker, "response": data}


def find_platform_event(marker: str) -> tuple[CtiEvent | None, Workflow | None, GraphRun | None]:
    db = SessionLocal()
    try:
        event = db.scalars(
            select(CtiEvent)
            .where(CtiEvent.title.contains(marker))
            .order_by(CtiEvent.received_at.desc())
        ).first()
        workflow = db.scalar(select(Workflow).where(Workflow.cti_event_id == event.id)) if event else None
        graph_run = None
        if workflow:
            graph_run = db.scalars(
                select(GraphRun)
                .where(GraphRun.workflow_id == workflow.id)
                .order_by(GraphRun.created_at.desc())
            ).first()
        return event, workflow, graph_run
    finally:
        db.close()


def main() -> None:
    created = create_misp_event()
    marker = created["marker"]
    print(f"created_misp_event_marker={marker}")

    db = SessionLocal()
    try:
        poll_result = MispPollingService(db).poll()
        print(f"poll_result={poll_result}")
    finally:
        db.close()

    deadline = time.time() + 120
    event = None
    workflow = None
    graph_run = None
    while time.time() < deadline:
        event, workflow, graph_run = find_platform_event(marker)
        if event and workflow and graph_run:
            break
        time.sleep(5)

    if not event or not workflow or not graph_run:
        raise RuntimeError("MISP event was not ingested into a workflow and graph run before timeout")

    print(f"cti_event_id={event.id}")
    print(f"misp_event_id={event.misp_event_id}")
    print(f"workflow_id={workflow.id}")
    print(f"workflow_status={workflow.status}")
    print(f"graph_run_id={graph_run.id}")
    print(f"graph_status={graph_run.status}")
    print(f"finished_at={datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    main()
