from celery import shared_task

from . import services


@shared_task(name="pme360.analytics.tasks.refresh_views", ignore_result=True)
def refresh_views() -> None:
    services.refresh()
