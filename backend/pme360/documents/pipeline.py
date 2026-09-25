"""Traitement asynchrone d'une version déposée (Document 2, § 7 : file « documents »).

Lecture du texte natif, contrôles déterministes, puis passage en vérification humaine. La classification,
l'extraction structurée, l'OCR et les contrôles croisés par IA arrivent en phase 4 (Document 4).
"""

from __future__ import annotations

import io
import re
import zipfile

import structlog
from django.utils import timezone

from pme360.audit import services as audit
from pme360.compliance.models import Deadline
from pme360.core import events
from pme360.core.tenancy import system_context, tenant_context
from pme360.notifications import services as notifications

from .models import Document, DocumentCheck, DocumentVersion
from .storage import get_storage

logger = structlog.get_logger(__name__)
MIN_TEXT_PER_PAGE = 25


def _xml_text(xml: bytes) -> str:
    return re.sub(r"\s+", " ", re.sub(rb"<[^>]+>", b" ", xml).decode("utf-8", "ignore")).strip()


def extract_text(content: bytes, extension: str) -> tuple[str, str, int | None]:
    """(statut, texte, nombre de pages)."""
    try:
        if extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content), strict=False)
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            enough = len(text) >= MIN_TEXT_PER_PAGE * max(len(pages), 1)
            return (DocumentVersion.Text.TEXTE_NATIF if enough else DocumentVersion.Text.OCR_REQUIS), text, len(pages)
        if extension in (".docx", ".xlsx"):
            archive = zipfile.ZipFile(io.BytesIO(content))
            part = "word/document.xml" if extension == ".docx" else "xl/sharedStrings.xml"
            text = _xml_text(archive.read(part)) if part in archive.namelist() else ""
            return DocumentVersion.Text.TEXTE_NATIF, text, None
        if extension == ".csv":
            for encoding in ("utf-8", "cp1252"):
                try:
                    return DocumentVersion.Text.TEXTE_NATIF, content.decode(encoding), None
                except UnicodeDecodeError:
                    continue
        return DocumentVersion.Text.OCR_REQUIS, "", None  # images, anciens formats : lecture optique (phase 4)
    except Exception:
        logger.exception("document.text_extraction_failed", extension=extension)
        return DocumentVersion.Text.ERREUR, "", None


def _check(version: DocumentVersion, code: str, result: str, message: str, **details) -> None:
    DocumentCheck.objects.update_or_create(
        version=version, check_code=code, defaults={"result": result, "message": message, "details": details}
    )


def process(version_id: str) -> None:
    with system_context():
        organization_id = (
            DocumentVersion.objects.filter(pk=version_id).values_list("organization_id", flat=True).first()
        )
    if organization_id is None:
        return
    with tenant_context(organization_id):
        version = DocumentVersion.objects.select_related("document__document_type", "document__deadline").get(
            pk=version_id
        )
        document = version.document
        if version.processed_at or version.av_status != DocumentVersion.Antivirus.SAIN:
            return  # idempotent : déjà traité, ou fichier refusé
        content = get_storage().get(version.storage_key)
        status, text, pages = extract_text(content, version.extension)
        version.text_status, version.text_content, version.page_count = status, text[:500_000], pages
        R = DocumentCheck.Result
        if version.duplicate_of_id:
            _check(
                version,
                "DOUBLON",
                R.ALERTE,
                "Fichier identique à un document déjà déposé.",
                duplicate_of=str(version.duplicate_of_id),
            )
        else:
            _check(version, "DOUBLON", R.OK, "Aucun doublon.")
        if status == DocumentVersion.Text.OCR_REQUIS:
            _check(
                version,
                "QUALITE_LECTURE",
                R.NON_DETERMINE,
                "Document scanné ou image : lecture visuelle par le conseiller.",
            )
        elif status == DocumentVersion.Text.ERREUR:
            _check(version, "QUALITE_LECTURE", R.ALERTE, "Le texte du document n'a pas pu être lu.")
        else:
            _check(version, "QUALITE_LECTURE", R.OK, "Texte lisible.")
        today = timezone.localdate()
        if document.expires_at:
            valid = document.expires_at >= today
            _check(
                version,
                "DATE_VALIDITE",
                R.OK if valid else R.ECHEC,
                "Document en cours de validité." if valid else "La date de validité déclarée est dépassée.",
                expires_at=document.expires_at.isoformat(),
            )
        else:
            _check(version, "DATE_VALIDITE", R.NON_DETERMINE, "Date de validité à confirmer lors de la vérification.")
        if document.deadline_id and document.period_start and document.period_end:
            deadline = document.deadline
            covers = document.period_start <= deadline.period_start and document.period_end >= deadline.period_end
            _check(
                version,
                "PERIODE_ATTENDUE",
                R.OK if covers else R.ALERTE,
                f"Période attendue : {deadline.period_label}.",
                expected=deadline.period_label,
            )
        version.processed_at = timezone.now()
        version.save(update_fields=["text_status", "text_content", "page_count", "processed_at", "updated_at"])

        # Aucune conformité automatique par défaut (Document 4, § 7) : vérification humaine requise.
        # Une décision humaine déjà rendue (vérification plus rapide que le traitement) n'est jamais écrasée.
        decided = (
            Document.objects.filter(pk=document.pk)
            .exclude(verification_status=Document.Verification.NON_VERIFIE)
            .exists()
        )
        if not decided:
            document.verification_status = Document.Verification.VERIF_HUMAINE_REQUISE
            document.save(update_fields=["verification_status", "updated_at"])
            if document.deadline_id:
                Deadline.objects.filter(
                    pk=document.deadline_id, status__in=[Deadline.Status.RECU, Deadline.Status.EN_ANALYSE]
                ).update(status=Deadline.Status.VERIF_HUMAINE_REQUISE)
        audit.record(
            "document.analyzed",
            instance=document,
            pme_id=document.pme_id,
            actor_type="SYSTEM",
            after={
                "version": version.version_no,
                "text": status,
                "pages": pages,
                "checks": {c.check_code: c.result for c in version.checks.all()},
            },
        )
        events.emit("document.analyzed", pme_id=str(document.pme_id), document_id=str(document.pk))
        if not decided:
            notifications.notify(
                notifications.recipients(document.pme, ["CONSEILLER"]),
                "DOCUMENT_TO_VERIFY",
                {"document": document.title, "pme": document.pme.legal_name},
                link=f"/verifications/{document.pk}",
                pme=document.pme,
            )
