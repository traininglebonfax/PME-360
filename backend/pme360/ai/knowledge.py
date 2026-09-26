"""Base de connaissances (Document 4, § 8) : indexation et recherche filtrée par périmètre AVANT le classement.

Recherche plein texte PostgreSQL (dictionnaire français) avec re-classement ; la composante vectorielle attend le
choix d'un fournisseur d'embeddings (décision D-09) et se greffera sur la même table.
Sources : référentiel, registre réglementaire (règles VÉRIFIÉES uniquement), documents de la PME (après
vérification humaine), historique de la PME (diagnostics validés, scores).
"""

from __future__ import annotations

import re

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import F, Q
from django.utils import timezone

from pme360.pmes.models import Pme

from .models import KnowledgeChunk

CHUNK_SIZE = 1200
STOPWORDS = {
    "les", "des", "une", "est", "que", "qui", "pour", "dans", "sur", "par", "avec", "son", "ses", "aux", "quel",
    "quels", "quelle", "quelles", "pas", "plus", "mon", "nos", "leur", "leurs", "cette", "ces", "fait", "comment",
    "pourquoi", "elle", "il", "sont", "ont", "été", "être", "avoir", "the",
}  # fmt: skip


def chunks(text: str, size: int = CHUNK_SIZE) -> list[tuple[int | None, str]]:
    """Découpage par page (saut de page ``\\f``) puis par paragraphes, sans couper un paragraphe si possible."""
    pages = text.split("\f")
    result = []
    for number, page in enumerate(pages, start=1):
        current = ""
        for paragraph in re.split(r"\n\s*\n|\n(?=[A-ZÉÈ0-9])", page):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if current and len(current) + len(paragraph) > size:
                result.append((number if len(pages) > 1 else None, current))
                current = ""
            current = f"{current}\n{paragraph}".strip() if current else paragraph[: size * 2]
        if current:
            result.append((number if len(pages) > 1 else None, current))
    return result


def index(
    source_type: str, source_id, label: str, parts: list[tuple[int | None, str]], *, pme=None, source_date=None
) -> int:
    KnowledgeChunk.objects.filter(source_type=source_type, source_id=str(source_id)).delete()
    KnowledgeChunk.objects.bulk_create(
        [
            KnowledgeChunk(
                pme=pme,
                source_type=source_type,
                source_id=str(source_id),
                source_label=label[:300],
                source_date=source_date,
                page=page,
                position=position,
                text=text,
            )
            for position, (page, text) in enumerate(parts)
            if text.strip()
        ]
    )
    KnowledgeChunk.objects.filter(source_type=source_type, source_id=str(source_id)).update(
        search_vector=SearchVector("source_label", weight="A", config="french")
        + SearchVector("text", weight="B", config="french")
    )
    return len(parts)


def remove(source_type: str, source_id) -> None:
    KnowledgeChunk.objects.filter(source_type=source_type, source_id=str(source_id)).delete()


# --- Sources ---------------------------------------------------------------------------------------------------


def index_framework(version) -> int:
    from pme360.diagnostic.models import Criterion

    parts = []
    for criterion in Criterion.objects.filter(framework_version=version).select_related("dimension").order_by("order"):
        levels = "\n".join(f"Niveau {i} : {anchor}" for i, anchor in enumerate(criterion.rubric))
        parts.append((None, f"{criterion.dimension.name} — {criterion.code} {criterion.name}\n{levels}".strip()))
    return index(
        KnowledgeChunk.Source.REFERENTIEL,
        version.pk,
        f"Référentiel {version.framework.code} v{version.version}",
        parts,
        source_date=timezone.localdate(),
    )


def index_regulatory() -> int:
    """Uniquement les règles au statut VÉRIFIÉ (Document 4, § 8.1) ; les autres sont retirées de l'index."""
    from pme360.compliance.models import RegulatoryRule

    count = 0
    for rule in RegulatoryRule.objects.all():
        if rule.status == RegulatoryRule.Status.VERIFIE:
            count += index(
                KnowledgeChunk.Source.REGLEMENTATION,
                rule.pk,
                f"{rule.code} — {rule.title}",
                [(None, f"{rule.title}\n{rule.content}\nSource : {rule.source_reference}")],
                source_date=rule.verified_at,
            )
        else:
            remove(KnowledgeChunk.Source.REGLEMENTATION, rule.pk)
    return count


def on_document_decision(document) -> None:
    """Un document n'est indexé qu'après vérification humaine favorable ; sinon il est retiré de l'index."""
    from pme360.documents.models import Document

    if document.conformity_status not in (Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE):
        remove(KnowledgeChunk.Source.DOCUMENT, document.pk)
        return
    version = document.versions.order_by("-version_no").first()
    if version is None or not version.text_content.strip():
        remove(KnowledgeChunk.Source.DOCUMENT, document.pk)
        return
    index(
        KnowledgeChunk.Source.DOCUMENT,
        document.pk,
        f"{document.title} (v{version.version_no})",
        chunks(version.text_content),
        pme=document.pme,
        source_date=timezone.localtime(document.verified_at).date() if document.verified_at else None,
    )


def index_pme_history(pme) -> int:
    from pme360.scoring.models import ScoreSnapshot

    parts = []
    for snapshot in ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("reference_date"):
        result = snapshot.result
        dims = "; ".join(
            f"{d['short_name']} {d['score']:.0f}/100"
            for d in result.get("dimensions", [])
            if d.get("score") is not None
        )
        parts.append(
            (
                None,
                f"Diagnostic du {snapshot.reference_date:%d/%m/%Y} ({snapshot.get_kind_display()}) : score global "
                f"{snapshot.global_score}/100, niveau {snapshot.maturity_level or '—'}, priorité "
                f"{snapshot.intervention_priority or '—'}. Dimensions : {dims}.",
            )
        )
    return index(KnowledgeChunk.Source.HISTORIQUE, pme.pk, f"Historique — {pme.legal_name}", parts, pme=pme)


def reindex_organization() -> dict:
    """Réindexation complète du tenant courant (commande ``ai_reindex``, seed)."""
    from pme360.diagnostic.models import FrameworkVersion
    from pme360.documents.models import Document

    counts = {"referentiel": 0, "reglementation": index_regulatory(), "documents": 0, "historique": 0}
    for version in FrameworkVersion.objects.filter(status=FrameworkVersion.Status.PUBLISHED).select_related(
        "framework"
    ):
        counts["referentiel"] += index_framework(version)
    for document in Document.objects.filter(verification_status=Document.Verification.VERIFIE_HUMAIN):
        on_document_decision(document)
        counts["documents"] += 1
    for pme in Pme.objects.all():
        counts["historique"] += index_pme_history(pme)
    return counts


# --- Recherche -------------------------------------------------------------------------------------------------


def _query(text: str) -> SearchQuery | None:
    words = [w for w in re.findall(r"[a-zA-Zà-ÿÀ-ß0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS]
    if not words:
        return None
    return SearchQuery(" | ".join(dict.fromkeys(words)), search_type="raw", config="french")


def search(access, text: str, *, pme: Pme | None = None, limit: int = 8) -> list[dict]:
    """Recherche dans le périmètre de l'utilisateur : filtre de sécurité (RLS + PME visibles) puis classement."""
    query = _query(text)
    if query is None:
        return []
    visible = access.pme_queryset(Pme.objects.all())
    if pme is not None:
        if not visible.filter(pk=pme.pk).exists():
            return []
        scope = Q(pme__isnull=True) | Q(pme=pme)
    else:
        scope = Q(pme__isnull=True) | Q(pme__in=visible.values("pk"))
    rows = (
        KnowledgeChunk.objects.filter(scope)
        .filter(search_vector=query)
        .annotate(rank=SearchRank(F("search_vector"), query))
        .order_by("-rank")[: limit * 3]
    )
    ranked = sorted(rows, key=lambda c: -(c.rank * (1.2 if pme is not None and c.pme_id == pme.pk else 1.0)))
    return [
        {
            "source_type": c.source_type,
            "source_label": c.source_label,
            "source_id": c.source_id,
            "pme_id": str(c.pme_id) if c.pme_id else None,
            "page": c.page,
            "date": c.source_date.isoformat() if c.source_date else None,
            "text": c.text[:800],
            "rank": round(float(c.rank), 4),
        }
        for c in ranked[:limit]
    ]
