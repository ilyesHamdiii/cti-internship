from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.models import (
    Behavior,
    CoverageResult,
    CtiEvent,
    GraphNodeRun,
    GraphRun,
    Proposal,
    ProposalRevision,
    ValidationResult,
    VisibilityResult,
    Workflow,
)
from app.services.bootstrap import seed_baseline
from app.services.misp import MispIngestionService
from app.workers.tasks import run_graph

SAMPLE_MISP_EVENT = {
    "Event": {
        "id": "900001",
        "uuid": "demo-powershell-encoded-001",
        "info": "Demo CTI - encoded PowerShell execution",
        "published": True,
        "timestamp": "1784476800",
        "Tag": [{"name": "tlp:white"}, {"name": "attack-pattern:T1059.001"}],
        "Attribute": [
            {
                "id": "1",
                "type": "text",
                "category": "Payload delivery",
                "value": "powershell.exe -NoProfile -EncodedCommand SQBFAFgA",
                "comment": "Observed process command line from local demo event.",
            },
            {
                "id": "2",
                "type": "ip-dst",
                "category": "Network activity",
                "value": "203.0.113.42",
                "comment": "Documentation-reserved sample infrastructure.",
            },
        ],
    }
}


def count(db: Session, model: Any) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def main() -> None:
    db = SessionLocal()
    try:
        seed_baseline(db)
        event, workflow, created = MispIngestionService(db).ingest_raw_event(SAMPLE_MISP_EVENT)
        proposal_count = (
            db.scalar(
                select(func.count())
                .select_from(Proposal)
                .where(Proposal.workflow_id == workflow.id)
            )
            or 0
        )
        graph_count = (
            db.scalar(
                select(func.count())
                .select_from(GraphRun)
                .where(GraphRun.workflow_id == workflow.id)
            )
            or 0
        )
        task_id = None
        if created or proposal_count == 0 or graph_count == 0:
            result = run_graph.delay(workflow.id)
            task_id = result.id
            result.get(timeout=90)

        latest_run = db.scalars(
            select(GraphRun)
            .where(GraphRun.workflow_id == workflow.id)
            .order_by(GraphRun.created_at.desc())
        ).first()
        latest_proposal = db.scalars(
            select(Proposal)
            .where(Proposal.workflow_id == workflow.id)
            .order_by(Proposal.updated_at.desc())
        ).first()
        latest_revision = (
            db.scalars(
                select(ProposalRevision)
                .where(ProposalRevision.proposal_id == latest_proposal.id)
                .order_by(ProposalRevision.revision_number.desc())
            ).first()
            if latest_proposal
            else None
        )
        print("CTI local demo bootstrap complete")
        print(f"created_event={created}")
        print(f"misp_event_id={event.misp_event_id}")
        print(f"workflow_id={workflow.id}")
        print(f"celery_task_id={task_id or 'not_enqueued_existing_demo'}")
        print(f"graph_run_id={latest_run.id if latest_run else 'none'}")
        print(f"graph_status={latest_run.status if latest_run else 'none'}")
        print(f"proposal_id={latest_proposal.id if latest_proposal else 'none'}")
        print(f"revision={latest_revision.revision_number if latest_revision else 'none'}")
        print("row_counts:")
        for model in [
            CtiEvent,
            Workflow,
            GraphRun,
            GraphNodeRun,
            Behavior,
            CoverageResult,
            VisibilityResult,
            Proposal,
            ProposalRevision,
            ValidationResult,
        ]:
            print(f"  {model.__tablename__}={count(db, model)}")
        print("login_email=admin@example.com")
        print("login_password=admin123")
        print(f"finished_at={datetime.now(UTC).isoformat()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
