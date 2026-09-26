"""Tableau de bord auditeur (Document 9, § 5 ; V1) : lecture seule.

- activité du journal sur une période (par domaine, par type d'acteur, principaux acteurs, événements sensibles) ;
- revue humaine des propositions de l'IA : pré-diagnostic par dimension et lecture de documents ;
- échantillonnage reproductible de dossiers PME (même graine → même échantillon) ;
- export CSV du journal filtré (l'export est lui-même journalisé).
"""

from __future__ import annotations

import csv
import io
import random
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count
from django.utils import timezone

from .labels import label_for
from .models import AuditLog

DOMAINS = {
    "auth": "Connexions et sécurité",
    "user": "Utilisateurs et accès",
    "role": "Utilisateurs et accès",
    "organization": "Organisation",
    "programme": "Programmes",
    "cohort": "Programmes",
    "pme": "PME",
    "diagnostic": "Diagnostics",
    "assessment": "Diagnostics",
    "score": "Scores",
    "document": "Documents",
    "ai": "Intelligence artificielle",
    "plan": "Accompagnement",
    "action": "Accompagnement",
    "recommendation": "Accompagnement",
    "rule": "Accompagnement",
    "report": "Rapports",
    "framework": "Configuration",
    "workflow": "Configuration",
    "notification_template": "Configuration",
    "document_type": "Configuration",
    "obligation": "Configuration",
    "regulatory_rule": "Configuration",
    "deadline": "Conformité",
    "alert": "Alertes",
    "audit": "Contrôle",
}
# Événements qu'un auditeur examine en priorité.
SENSITIVE_PREFIXES = (
    "auth.login_failed",
    "user.",
    "role.",
    "framework.published",
    "workflow.activated",
    "regulatory_rule.",
    "document.infected",
    "audit.exported",
    "pme.lifecycle_changed",
    "organization.key_rotated",
)


def domain_of(action: str) -> str:
    return DOMAINS.get(action.split(".", 1)[0], "Autres")


def period(start, end) -> tuple[datetime, datetime]:
    today = timezone.localdate()
    start = start or today - timedelta(days=29)
    end = end or today
    tz = timezone.get_current_timezone()
    return datetime.combine(start, time.min, tz), datetime.combine(end, time.max, tz)


def overview(start, end) -> dict:
    since, until = period(start, end)
    entries = AuditLog.objects.filter(at__gte=since, at__lte=until)
    by_action = dict(entries.values_list("action").annotate(n=Count("id")).values_list("action", "n"))
    domains = Counter()
    for action, n in by_action.items():
        domains[domain_of(action)] += n
    actors = (
        entries.filter(actor__isnull=False)
        .values("actor_id", "actor__full_name")
        .annotate(n=Count("id"))
        .order_by("-n")[:8]
    )
    sensitive = entries.filter(
        action__regex=r"^(" + "|".join(p.replace(".", r"\.") for p in SENSITIVE_PREFIXES) + ")"
    ).select_related("actor")[:15]
    return {
        "from": since.date(),
        "to": until.date(),
        "total": sum(by_action.values()),
        "by_actor_type": dict(entries.values_list("actor_type").annotate(n=Count("id")).values_list("actor_type", "n")),
        "by_domain": [{"domain": d, "count": n} for d, n in domains.most_common()],
        "top_actors": [{"id": a["actor_id"], "name": a["actor__full_name"], "count": a["n"]} for a in actors],
        "login_failures": by_action.get("auth.login_failed", 0),
        "sensitive": [
            {
                "id": e.id,
                "at": e.at,
                "action": e.action,
                "label": label_for(e.action),
                "actor_name": e.actor.full_name if e.actor else None,
                "actor_type": e.actor_type,
                "entity_type": e.entity_type,
                "pme_id": e.pme_id,
            }
            for e in sensitive
        ],
        "ai_review": ai_review(since, until),
    }


def ai_review(since, until) -> dict:
    """Taux de modification des propositions de l'IA par la revue humaine (Document 9, § 5)."""
    from pme360.ai.models import CriterionSuggestion, DocumentExtraction
    from pme360.diagnostic.models import Criterion, Dimension

    suggestions = CriterionSuggestion.objects.filter(updated_at__gte=since, updated_at__lte=until).exclude(
        status=CriterionSuggestion.Status.PROPOSEE
    )
    criterion_dimension = {}
    for code, dimension_code in Criterion.objects.values_list("code", "dimension__code"):
        criterion_dimension.setdefault(code, dimension_code)
    names = dict(Dimension.objects.values_list("code", "short_name"))
    counts: dict[str, Counter] = defaultdict(Counter)
    for code, status in suggestions.values_list("criterion_code", "status"):
        counts[criterion_dimension.get(code, "?")][status] += 1
    dimensions = []
    for code in sorted(counts):
        c = counts[code]
        reviewed = c["ACCEPTEE"] + c["MODIFIEE"] + c["ECARTEE"]
        dimensions.append(
            {
                "dimension": code,
                "name": names.get(code, code),
                "reviewed": reviewed,
                "accepted": c["ACCEPTEE"],
                "modified": c["MODIFIEE"],
                "rejected": c["ECARTEE"],
                "change_rate": round((c["MODIFIEE"] + c["ECARTEE"]) / reviewed, 3) if reviewed else None,
            }
        )
    extractions = Counter(
        DocumentExtraction.objects.filter(reviewed_at__gte=since, reviewed_at__lte=until).values_list(
            "status", flat=True
        )
    )
    reviewed_docs = extractions["VALIDEE"] + extractions["CORRIGEE"] + extractions["REJETEE"]
    total_suggestions = sum(d["reviewed"] for d in dimensions)
    changed = sum(d["modified"] + d["rejected"] for d in dimensions)
    return {
        "suggestions_reviewed": total_suggestions,
        "suggestions_change_rate": round(changed / total_suggestions, 3) if total_suggestions else None,
        "by_dimension": dimensions,
        "documents_reviewed": reviewed_docs,
        "documents_validated": extractions["VALIDEE"],
        "documents_corrected": extractions["CORRIGEE"],
        "documents_rejected": extractions["REJETEE"],
        "documents_change_rate": round((extractions["CORRIGEE"] + extractions["REJETEE"]) / reviewed_docs, 3)
        if reviewed_docs
        else None,
    }


def sample(access, size: int, seed: str) -> list[dict]:
    """Échantillon reproductible de dossiers PME du périmètre (tirage déterministe à partir de la graine)."""
    from pme360.ai.models import CriterionSuggestion
    from pme360.diagnostic.models import Diagnostic
    from pme360.documents.models import Document
    from pme360.pmes.models import Pme

    ids = sorted(str(pk) for pk in access.pme_queryset(Pme.objects.all()).values_list("pk", flat=True))
    # Tirage volontairement déterministe (reproductibilité par la graine), sans enjeu cryptographique.
    chosen = random.Random(seed).sample(ids, min(size, len(ids)))  # noqa: S311
    pmes = {str(p.pk): p for p in Pme.objects.filter(pk__in=chosen).select_related("sector", "region")}
    items = []
    for pk in chosen:
        pme = pmes[pk]
        diagnostic = (
            Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-validated_at").first()
        )
        documents = Document.objects.filter(pme=pme, deleted_at__isnull=True)
        items.append(
            {
                "id": pme.pk,
                "name": pme.legal_name,
                "sector": pme.sector.name if pme.sector_id else "",
                "region": pme.region.name if pme.region_id else "",
                "lifecycle_status": pme.lifecycle_status,
                "last_validated_diagnostic": diagnostic.validated_at if diagnostic else None,
                "documents": documents.count(),
                "documents_verified": documents.filter(verification_status="VERIFIE_HUMAIN").count(),
                "ai_suggestions_changed": CriterionSuggestion.objects.filter(
                    diagnostic__pme=pme, status__in=["MODIFIEE", "ECARTEE"]
                ).count(),
                "audit_entries": AuditLog.objects.filter(pme_id=pme.pk).count(),
            }
        )
    return items


CSV_COLUMNS = ["id", "at", "action", "label", "actor", "actor_type", "entity_type", "entity_id", "pme_id", "ip", "hash"]


def export_csv(queryset) -> str:
    buffer = io.StringIO()
    buffer.write("﻿")  # Excel : UTF-8
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["N°", "Date", "Action", "Libellé", "Acteur", "Type d'acteur", "Objet", "Identifiant", "PME", "IP", "Empreinte"]
    )
    for e in queryset.select_related("actor").order_by("id").iterator(chunk_size=500):
        writer.writerow(
            [
                e.id,
                timezone.localtime(e.at).strftime("%d/%m/%Y %H:%M:%S"),
                e.action,
                label_for(e.action),
                e.actor.full_name if e.actor else "",
                e.actor_type,
                e.entity_type,
                e.entity_id,
                e.pme_id or "",
                e.ip or "",
                e.hash,
            ]
        )
    return buffer.getvalue()
