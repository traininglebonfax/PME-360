import structlog
from celery import shared_task
from django.utils import timezone

from .events import handlers_for
from .models import DomainEvent
from .tenancy import system_context, tenant_context

logger = structlog.get_logger(__name__)
MAX_ATTEMPTS = 10


@shared_task
def dispatch_outbox(batch_size: int = 100) -> int:
    """Distribue les événements en attente ; chaque gestionnaire s'exécute dans le tenant de l'événement."""
    processed = 0
    with system_context():
        events = list(
            DomainEvent.objects.select_for_update(skip_locked=True)
            .filter(processed_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
            .order_by("created_at")[:batch_size]
        )
        for event in events:
            try:
                with tenant_context(event.organization_id):
                    for handler in handlers_for(event.event_type):
                        handler(event)
                event.processed_at = timezone.now()
                processed += 1
            except Exception as exc:  # l'événement sera retenté
                event.attempts += 1
                event.last_error = repr(exc)[:2000]
                logger.exception("outbox.handler_failed", event_id=str(event.id), event_type=event.event_type)
            event.save(update_fields=["processed_at", "attempts", "last_error", "updated_at"])
    return processed
