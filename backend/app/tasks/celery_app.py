from celery import Celery
from kombu import Queue

from app.core.config import settings

celery = Celery(
    "stock_pos",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_default_queue="default",
    task_queues=(
        Queue("default", durable=True),
        Queue("reports", durable=True),
        Queue("maintenance", durable=True),
        Queue("critical", durable=True),
        Queue("telegram", durable=True),
        Queue("exports", durable=True),
    ),
    task_ignore_result=False,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    worker_send_task_events=False,
    # Task modules the workers must import so send_task-by-name resolves
    # (registered tasks were empty before this).
    include=["app.tasks.telegram"],
)
