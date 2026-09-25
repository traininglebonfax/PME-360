"""Écriture et vérification du journal d'audit chaîné."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, models
from django.utils import timezone

from pme360.core.request_context import get_request_context
from pme360.core.tenancy import current_org_id, rls_bypassed, system_context, tenant_context

from .models import AuditLog

GENESIS = "0" * 64
_UNSET = object()


def to_json(data):
    """Normalise une valeur en JSON pur : c'est cette forme qui est hachée ET stockée."""
    if data is None:
        return None
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def snapshot(instance: models.Model, fields: list[str] | tuple[str, ...]) -> dict:
    """État sérialisable des ``fields`` d'une instance (clés étrangères sous forme d'identifiant)."""
    data = {}
    for name in fields:
        field = instance._meta.get_field(name)
        attname = field.attname if field.is_relation else name
        data[name] = getattr(instance, attname)
    return to_json(data)


def diff(before: dict | None, after: dict | None) -> tuple[dict | None, dict | None]:
    """Réduit before/after aux seuls champs modifiés."""
    if before is None or after is None:
        return before, after
    changed = [key for key in after if before.get(key) != after.get(key)]
    return {key: before.get(key) for key in changed}, {key: after[key] for key in changed}


def _digest(prev_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def _payload(entry: AuditLog) -> dict:
    return {
        "organization_id": str(entry.organization_id) if entry.organization_id else None,
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "actor_type": entry.actor_type,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "pme_id": str(entry.pme_id) if entry.pme_id else None,
        "before": entry.before,
        "after": entry.after,
        "ip": entry.ip,
        "user_agent": entry.user_agent,
        "request_id": entry.request_id,
        "at": entry.at.isoformat(),
    }


def record(
    action: str,
    *,
    instance: models.Model | None = None,
    entity_type: str = "",
    entity_id: str | uuid.UUID = "",
    before: dict | None = None,
    after: dict | None = None,
    pme_id: uuid.UUID | None = None,
    actor=None,
    actor_type: str | None = None,
    organization_id=_UNSET,
) -> AuditLog:
    """Ajoute une entrée au journal de l'organisation (courante par défaut)."""
    org_id = current_org_id() if organization_id is _UNSET else organization_id
    if isinstance(org_id, str):
        org_id = uuid.UUID(org_id)
    if not rls_bypassed() and (org_id is None or org_id != current_org_id()):
        # Écriture dans le journal d'une autre organisation que le tenant courant (ex. connexion) ou dans le
        # journal plateforme (org_id None) : on se place dans le contexte correspondant.
        context = system_context() if org_id is None else tenant_context(org_id)
        with context:
            return record(
                action,
                instance=instance,
                entity_type=entity_type,
                entity_id=entity_id,
                before=before,
                after=after,
                pme_id=pme_id,
                actor=actor,
                actor_type=actor_type,
                organization_id=org_id,
            )

    ctx = get_request_context() or {}
    actor_id = getattr(actor, "pk", None) or ctx.get("user_id")
    if instance is not None:
        entity_type = entity_type or instance._meta.model_name
        entity_id = entity_id or instance.pk

    with connection.cursor() as cursor:
        # Sérialise les écritures d'une même organisation pour garantir l'ordre de la chaîne.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [f"audit:{org_id or 'platform'}"])
    last = AuditLog.objects.filter(organization_id=org_id).order_by("-id").values_list("hash", flat=True).first()

    entry = AuditLog(
        organization_id=org_id,
        actor_id=actor_id,
        actor_type=actor_type or (AuditLog.ActorType.USER if actor_id else AuditLog.ActorType.SYSTEM),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else "",
        pme_id=pme_id,
        before=to_json(before),
        after=to_json(after),
        ip=ctx.get("ip"),
        user_agent=ctx.get("user_agent", ""),
        request_id=ctx.get("request_id", ""),
        at=timezone.now(),
        prev_hash=last or GENESIS,
    )
    entry.hash = _digest(entry.prev_hash, _payload(entry))
    entry.save(force_insert=True)
    return entry


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    entries_checked: int
    first_invalid_id: int | None = None


def verify_chain(organization_id: uuid.UUID | None) -> ChainVerification:
    """Recalcule toute la chaîne d'une organisation ; détecte toute altération ou suppression."""
    expected_prev = GENESIS
    count = 0
    for entry in AuditLog.objects.filter(organization_id=organization_id).order_by("id").iterator(chunk_size=500):
        count += 1
        if entry.prev_hash != expected_prev or entry.hash != _digest(entry.prev_hash, _payload(entry)):
            return ChainVerification(valid=False, entries_checked=count, first_invalid_id=entry.id)
        expected_prev = entry.hash
    return ChainVerification(valid=True, entries_checked=count)
