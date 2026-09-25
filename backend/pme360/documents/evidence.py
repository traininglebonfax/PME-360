"""Preuves documentaires alimentant le moteur de scoring (RM-01 : pas de conformité sans preuve vérifiée)."""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from pme360.scoring.engine import Evidence

from .models import Document


def verified_documents(pme, as_of: date | None = None) -> dict[str, tuple[int, date]]:
    """Type de document → (niveau prouvé, date de vérification) pour les preuves valides à ``as_of``."""
    as_of = as_of or timezone.localdate()
    proofs: dict[str, tuple[int, date]] = {}
    documents = Document.objects.filter(
        pme=pme,
        deleted_at__isnull=True,
        integrity_status=Document.Integrity.SAIN,
        verification_status=Document.Verification.VERIFIE_HUMAIN,
        conformity_status__in=[Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE],
        verified_at__date__lte=as_of,
    ).select_related("document_type")
    for document in documents:
        if document.expires_at and document.expires_at < as_of:
            continue
        level = document.document_type.evidence_level
        if document.conformity_status == Document.Conformity.CONFORME_SOUS_RESERVE:
            level = max(level - 1, 0)  # une réserve ne prouve pas pleinement la pratique
        verified_on = timezone.localtime(document.verified_at).date()
        current = proofs.get(document.document_type.code)
        if current is None or level > current[0]:
            proofs[document.document_type.code] = (level, verified_on)
    return proofs


def evidence_for(criteria_documents: dict[str, list[str]], proofs: dict[str, tuple[int, date]]) -> dict[str, Evidence]:
    """Critère → meilleure preuve parmi les types de documents qui le justifient."""
    evidence = {}
    for criterion, types in criteria_documents.items():
        best = max((proofs[t] for t in types if t in proofs), default=None, key=lambda p: p[0])
        if best:
            evidence[criterion] = Evidence(verified=True, level=best[0], source="DOCUMENT_VERIFIE", dated=best[1])
    return evidence
