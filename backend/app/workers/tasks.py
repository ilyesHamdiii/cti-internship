from app.db.session import SessionLocal
from app.graph.runner import DetectionEngineeringGraph
from app.services.misp import MispPollingService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_graph")
def run_graph(
    workflow_id: str,
    resume_from_node: str | None = None,
    proposal_id: str | None = None,
    analyst_comment: str | None = None,
) -> str:
    db = SessionLocal()
    try:
        graph_run = DetectionEngineeringGraph(db).run(workflow_id, resume_from_node, proposal_id, analyst_comment)
        return graph_run.id
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.poll_misp")
def poll_misp() -> dict[str, int]:
    db = SessionLocal()
    try:
        return MispPollingService(db).poll()
    finally:
        db.close()
