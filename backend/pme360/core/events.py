"""Événements de domaine : écriture dans l'outbox, puis distribution asynchrone (au moins une fois)."""

from collections import defaultdict
from collections.abc import Callable

from .models import DomainEvent

_handlers: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(list)


def emit(event_type: str, **payload) -> DomainEvent:
    """Enregistre l'événement dans la transaction courante (tenant courant)."""
    return DomainEvent.objects.create(event_type=event_type, payload=payload)


def subscribe(event_type: str):
    """Décorateur : les gestionnaires DOIVENT être idempotents (livraison au moins une fois)."""

    def decorator(func: Callable[[DomainEvent], None]):
        _handlers[event_type].append(func)
        return func

    return decorator


def handlers_for(event_type: str) -> list[Callable[[DomainEvent], None]]:
    return list(_handlers.get(event_type, []))
