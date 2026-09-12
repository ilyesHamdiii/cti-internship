from importlib import import_module

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "cti_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "default"}}
celery_app.conf.beat_schedule = {
    "poll-misp": {
        "task": "app.workers.tasks.poll_misp",
        "schedule": settings.misp_poll_interval_seconds,
    }
}

import_module("app.workers.tasks")
