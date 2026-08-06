from __future__ import annotations

import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import CtiEvent, GraphRun, Workflow
from app.services.misp import MispPollingService

SCENARIOS = {
    "powershell": "PowerShell downloads and executes remote content with encoded command arguments.",
    "wmi": "wmic process call create calc.exe on a remote Windows host.",
    "visibility_gap": "Cloud-only account manipulation with missing telemetry for cloud audit events.",
    "multi": "PowerShell encoded command followed by rundll32.exe suspicious execution.",
}


def main() -> None:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "powershell"
    value = SCENARIOS[scenario]
    settings = get_settings()
    if settings.misp_api_key is None:
        raise RuntimeError("CTI_MISP_API_KEY is required")
    marker = f"cti-platform-{scenario}-{uuid4()}"
    payload = {
        "Event": {
            "info": f"CTI Platform Scenario {scenario} {marker}",
            "distribution": "0",
            "threat_level_id": "2",
            "analysis": "0",
            "published": False,
            "Attribute": [
                {
                    "type": "text",
                    "category": "External analysis",
                    "to_ids": False,
                    "value": value,
                    "comment": marker,
                }
            ],
        }
    }
    headers = {
        "Authorization": settings.misp_api_key.get_secret_value(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(
        verify=settings.misp_verify_tls, timeout=30.0, follow_redirects=True
    ) as client:
        created = None
        for attempt in range(1, 7):
            try:
                response = client.post(
                    f"{settings.misp_url.rstrip('/')}/events/add", headers=headers, json=payload
                )
                response.raise_for_status()
                created = response.json()
                break
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    if status_code < 500 and status_code not in {401, 403, 429}:
                        raise
                if attempt == 6:
                    raise
                wait_seconds = attempt * 5
                print(f"misp_event_create_retry attempt={attempt} wait_seconds={wait_seconds}")
                time.sleep(wait_seconds)
        if created is None:
            raise RuntimeError("failed to create MISP event")
    print(f"scenario={scenario}")
    print(f"marker={marker}")
    print(f"created_misp_event_id={created.get('Event', created).get('id')}")
    db = SessionLocal()
    try:
        print(f"poll_result={MispPollingService(db).poll()}")
    finally:
        db.close()
    deadline = time.time() + 120
    event = workflow = graph_run = None
    while time.time() < deadline:
        db = SessionLocal()
        try:
            event = db.scalars(
                select(CtiEvent)
                .where(CtiEvent.title.contains(marker))
                .order_by(CtiEvent.received_at.desc())
            ).first()
            workflow = (
                db.scalar(select(Workflow).where(Workflow.cti_event_id == event.id))
                if event
                else None
            )
            graph_run = (
                db.scalars(
                    select(GraphRun)
                    .where(GraphRun.workflow_id == workflow.id)
                    .order_by(GraphRun.created_at.desc())
                ).first()
                if workflow
                else None
            )
            if event and workflow and graph_run and graph_run.status != "running":
                break
        finally:
            db.close()
        time.sleep(3)
    if not event or not workflow or not graph_run:
        raise RuntimeError("scenario did not reach graph run")
    print(f"cti_event_id={event.id}")
    print(f"misp_event_id={event.misp_event_id}")
    print(f"workflow_id={workflow.id}")
    print(f"workflow_status={workflow.status}")
    print(f"graph_run_id={graph_run.id}")
    print(f"graph_status={graph_run.status}")


if __name__ == "__main__":
    main()
