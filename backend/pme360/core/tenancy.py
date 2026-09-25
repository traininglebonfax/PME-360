"""Contexte de tenant : isolation applicative + isolation PostgreSQL (Row-Level Security).

Document 2, § 5 (ADR-003). Deux variables de session PostgreSQL, positionnées localement à la transaction :

- ``app.current_org`` : UUID de l'organisation courante ; les politiques RLS n'exposent que ses lignes ;
- ``app.bypass_rls`` : ``on`` uniquement pour le code système explicite (migrations de données, seed,
  planificateurs, résolution des appartenances à la connexion).

Le même état est porté par des ``ContextVar`` pour que les managers Django filtrent aussi côté application :
un oubli dans l'un des deux niveaux ne suffit pas à exposer des données d'un autre tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from contextvars import ContextVar

from django.db import DatabaseError, connection, transaction

_current_org: ContextVar[uuid.UUID | None] = ContextVar("pme360_current_org", default=None)
_bypass: ContextVar[bool] = ContextVar("pme360_bypass_rls", default=False)


def current_org_id() -> uuid.UUID | None:
    return _current_org.get()


def rls_bypassed() -> bool:
    return _bypass.get()


def _apply_db_settings(org_id: uuid.UUID | None, bypass: bool) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.current_org', %s, true), set_config('app.bypass_rls', %s, true)",
            [str(org_id) if org_id else "", "on" if bypass else "off"],
        )


@contextmanager
def _context(org_id: uuid.UUID | None, bypass: bool) -> Iterator[None]:
    previous_org, previous_bypass = _current_org.get(), _bypass.get()
    with transaction.atomic():
        org_token, bypass_token = _current_org.set(org_id), _bypass.set(bypass)
        _apply_db_settings(org_id, bypass)
        try:
            yield
        finally:
            _current_org.reset(org_token)
            _bypass.reset(bypass_token)
            # En cas d'erreur, le ROLLBACK (TO SAVEPOINT) annule déjà les set_config locaux.
            if not connection.needs_rollback:
                with suppress(DatabaseError):  # transaction cassée : le rollback restaurera l'état
                    _apply_db_settings(previous_org, previous_bypass)


def tenant_context(org_id: uuid.UUID | str | None) -> AbstractContextManager[None]:
    """Exécute un bloc (dans une transaction) avec l'organisation ``org_id`` comme tenant courant.

    ``org_id=None`` : aucun tenant, aucune ligne métier visible.
    """
    if isinstance(org_id, str):
        org_id = uuid.UUID(org_id)
    return _context(org_id, bypass=False)


def system_context() -> AbstractContextManager[None]:
    """Contexte système : RLS contournée. Réservé au code d'infrastructure, jamais aux requêtes utilisateur."""
    return _context(None, bypass=True)
