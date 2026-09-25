from celery import shared_task

from . import pipeline


@shared_task(autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=5)
def process_version(version_id: str) -> None:
    pipeline.process(version_id)
