from app.workers.celery_app import celery_app


def test_worker_tasks_are_registered_and_routed_to_default_queue() -> None:
    assert "app.workers.tasks.run_graph" in celery_app.tasks
    assert "app.workers.tasks.poll_misp" in celery_app.tasks
    assert celery_app.conf.task_default_queue == "default"
