from collections.abc import Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from app.db.session import SessionLocal
from app.graph.runner import DetectionEngineeringGraph
from app.services.misp import MispPollingService
from app.workers.celery_app import celery_app

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class CeleryTask(Protocol[P, R_co]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...

    def delay(self, *args: P.args, **kwargs: P.kwargs) -> Any: ...


def celery_task(*args: Any, **kwargs: Any) -> Callable[[Callable[P, R_co]], CeleryTask[P, R_co]]:
    return cast(
        Callable[[Callable[P, R_co]], CeleryTask[P, R_co]], celery_app.task(*args, **kwargs)
    )


@celery_task(name="app.workers.tasks.run_graph")
def run_graph(
    workflow_id: str,
    resume_from_node: str | None = None,
    proposal_id: str | None = None,
    analyst_comment: str | None = None,
) -> str:
    db = SessionLocal()
    try:
        graph_run = DetectionEngineeringGraph(db).run(
            workflow_id, resume_from_node, proposal_id, analyst_comment
        )
        return graph_run.id
    finally:
        db.close()


@celery_task(name="app.workers.tasks.poll_misp")
def poll_misp() -> dict[str, Any]:
    db = SessionLocal()
    try:
        return MispPollingService(db).poll()
    finally:
        db.close()
