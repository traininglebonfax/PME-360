"""Dépôt, traitement et vérification des documents (Document 1, § 4 étapes 3, 10, 11 ; Document 8, § 5).

Pipeline : dépôt → contrôles du contenu → antivirus (en mémoire, AVANT tout stockage) → stockage chiffré →
traitement asynchrone (lecture du texte, contrôles, doublons) → vérification HUMAINE → statut final.
« Pas de preuve, pas de conformité » : un dépôt n'est jamais synonyme de conformité (Document 1, principe 4).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.accounts.access import AccessContext
from pme360.audit import services as audit
from pme360.compliance.models import Deadline
from pme360.core import events
from pme360.core.exceptions import BusinessError, Conflict
from pme360.notifications import services as notifications
from pme360.pmes import services as pme_services
from pme360.pmes.models import Pme

from . import security
from .antivirus import ScannerUnavailable, get_scanner
from .models import Document, DocumentType, DocumentVersion
from .storage import get_storage

DECISION_LABELS = {
    Document.Conformity.CONFORME: "document validé",
    Document.Conformity.CONFORME_SOUS_RESERVE: "document validé sous réserve",
    Document.Conformity.NON_CONFORME: "document refusé",
    Document.Conformity.INCOHERENT: "document incohérent",
}
DEADLINE_STATUS_FOR_DECISION = {
    Document.Conformity.CONFORME: Deadline.Status.CONFORME,
    Document.Conformity.CONFORME_SOUS_RESERVE: Deadline.Status.CONFORME_SOUS_RESERVE,
    Document.Conformity.NON_CONFORME: Deadline.Status.NON_CONFORME,
    Document.Conformity.INCOHERENT: Deadline.Status.INCOHERENT,
}


@dataclass
class UploadResult:
    document: Document
    version: DocumentVersion
    infected: bool = False


def _storage_key(document: Document, version_no: int, extension: str) -> str:
    return f"org/{document.organization_id}/pme/{document.pme_id}/{document.pk}/v{version_no}{extension}"


def _can_upload(access: AccessContext, pme: Pme) -> None:
    if not access.has("document.upload"):
        raise PermissionDenied("Vous ne pouvez pas déposer de document.")
    if access.is_pme_user and pme.pk not in access.own_pme_ids:
        raise PermissionDenied("Vous ne pouvez déposer que pour votre entreprise.")


def upload(
    access: AccessContext,
    pme: Pme,
    *,
    filename: str,
    content: bytes,
    document_type: DocumentType | None = None,
    document: Document | None = None,
    deadline: Deadline | None = None,
    title: str = "",
    period_start: date | None = None,
    period_end: date | None = None,
    issued_at: date | None = None,
    expires_at: date | None = None,
) -> UploadResult:
    """Dépose un nouveau document, ou une nouvelle version de ``document``."""
    _can_upload(access, pme)
    if document is not None:
        document_type = document.document_type
        if document.pme_id != pme.pk:
            raise ValidationError({"document": ["Document d'une autre PME."]})
    if deadline is not None:
        if deadline.pme_id != pme.pk or deadline.status not in (*Deadline.OPEN, Deadline.Status.RECU):
            raise ValidationError({"deadline": ["Cette échéance n'attend pas de document."]})
        document_type = document_type or deadline.pme_obligation.template.document_type
        if deadline.pme_obligation.template.document_type_id != document_type.pk:
            raise ValidationError({"document_type": ["Le type de document ne correspond pas à l'échéance."]})
    if document_type is None:
        raise ValidationError({"document_type": ["Type de document obligatoire."]})

    try:
        inspection = security.inspect(content, filename)
    except security.RejectedFile as rejected:
        audit.record(
            "document.refused",
            entity_type="pme",
            entity_id=pme.pk,
            pme_id=pme.pk,
            after={"filename": filename[:200], "code": rejected.code, "type": document_type.code},
        )
        raise BusinessError(rejected.message, code=rejected.code) from rejected
    try:
        scan = get_scanner().scan(content)
    except ScannerUnavailable as exc:
        # Échec fermé : sans analyse antivirus, aucun fichier n'est accepté.
        raise BusinessError(
            "L'analyse antivirus est momentanément indisponible. Réessayez dans quelques minutes.",
            code="antivirus_unavailable",
            status_code=503,
        ) from exc

    channel = Document.Channel.PORTAIL_PME if access.is_pme_user else Document.Channel.CONSEILLER
    if document is None:
        document = Document.objects.create(
            pme=pme,
            document_type=document_type,
            deadline=deadline,
            title=title or document_type.name,
            period_start=period_start,
            period_end=period_end,
            issued_at=issued_at,
            expires_at=expires_at,
            uploaded_by=access.user,
            uploaded_via=channel,
            created_by=access.user,
        )
    else:
        document.deadline = deadline or document.deadline
        for field, value in (
            ("period_start", period_start),
            ("period_end", period_end),
            ("issued_at", issued_at),
            ("expires_at", expires_at),
        ):
            if value:
                setattr(document, field, value)
    version_no = document.current_version_no + 1
    sha256 = hashlib.sha256(content).hexdigest()
    duplicate = (
        DocumentVersion.objects.filter(document__pme=pme, sha256=sha256, av_status=DocumentVersion.Antivirus.SAIN)
        .exclude(document=document)
        .first()
    )
    version = DocumentVersion(
        document=document,
        version_no=version_no,
        original_filename=filename[:255],
        extension=inspection.extension,
        mime_detected=inspection.mime,
        sha256=sha256,
        size_bytes=len(content),
        av_engine=scan.engine,
        uploaded_by=access.user,
        duplicate_of=duplicate,
    )

    if not scan.clean:
        version.av_status = DocumentVersion.Antivirus.INFECTE
        version.av_signature = scan.signature or ""
        version.save()
        document.integrity_status = Document.Integrity.REJETE_SECURITE
        document.current_version_no = version_no
        document.save()
        audit.record(
            "document.infected",
            instance=document,
            pme_id=pme.pk,
            after={"filename": filename[:200], "signature": scan.signature, "engine": scan.engine},
        )
        from pme360.alerts import engine as alerts

        alerts.raise_document_anomaly(document, f"Fichier infecté bloqué ({scan.signature}).")
        notifications.notify(
            notifications.recipients(pme, ["CONSEILLER"]) + [access.user],
            "DOCUMENT_REJECTED_SECURITY",
            {"filename": filename, "pme": pme.legal_name},
            pme=pme,
            severity="CRITIQUE",
        )
        return UploadResult(document=document, version=version, infected=True)

    version.av_status = DocumentVersion.Antivirus.SAIN
    version.storage_key = _storage_key(document, version_no, inspection.extension)
    get_storage().put(version.storage_key, content, inspection.mime)
    version.save()
    document.current_version_no = version_no
    document.integrity_status = Document.Integrity.SAIN
    document.verification_status = Document.Verification.NON_VERIFIE
    document.conformity_status = Document.Conformity.NON_EVALUE
    document.decision_reason = ""
    document.verified_by = None
    document.verified_at = None
    document.save()
    if deadline is not None:
        deadline.status = Deadline.Status.RECU
        deadline.save(update_fields=["status", "updated_at"])
    audit.record(
        "document.uploaded",
        instance=document,
        pme_id=pme.pk,
        after={
            "type": document_type.code,
            "version": version_no,
            "filename": filename[:200],
            "size": len(content),
            "sha256": sha256,
            "duplicate_of": duplicate.pk if duplicate else None,
            "deadline": deadline.pk if deadline else None,
        },
    )
    events.emit("document.uploaded", pme_id=str(pme.pk), document_id=str(document.pk), version_id=str(version.pk))
    pme_services.touch(pme)
    version_id = version.pk
    transaction.on_commit(lambda: _enqueue(version_id))
    return UploadResult(document=document, version=version)


def _enqueue(version_id) -> None:
    from .tasks import process_version

    process_version.delay(str(version_id))


# --- Vérification humaine -------------------------------------------------------------------------------------


def _validity(document: Document, today: date) -> str:
    expires = document.expires_at
    if expires is None and document.document_type.validity_days and document.issued_at:
        expires = document.issued_at + timedelta(days=document.document_type.validity_days)
        document.expires_at = expires
    if expires is None:
        return Document.Validity.INDETERMINE
    return Document.Validity.VALIDE if expires >= today else Document.Validity.EXPIRE


def _currency(document: Document, today: date) -> str:
    if document.deadline_id:
        deadline = document.deadline
        if document.period_start is None or document.period_end is None:
            return Document.Currency.INDETERMINE
        covers = document.period_start <= deadline.period_start and document.period_end >= deadline.period_end
        return Document.Currency.A_JOUR if covers else Document.Currency.PERIODE_INCORRECTE
    freshness = document.document_type.freshness_days
    reference = document.period_end or document.issued_at
    if freshness and reference:
        return (
            Document.Currency.A_JOUR if (today - reference).days <= freshness else Document.Currency.PERIODE_ANTERIEURE
        )
    return Document.Currency.INDETERMINE


def verify(
    access: AccessContext,
    document: Document,
    *,
    decision: str,
    reason: str = "",
    period_start: date | None = None,
    period_end: date | None = None,
    issued_at: date | None = None,
    expires_at: date | None = None,
    revise: bool = False,
) -> Document:
    """Décision humaine sur un document (RM-05) ; motif obligatoire hors conformité pleine.

    Une seule décision par version : revenir sur une décision déjà rendue exige ``revise`` et un motif.
    """
    if not access.has("document.verify"):
        raise PermissionDenied()
    # Verrou de ligne : deux clics (ou deux onglets) ne produisent pas deux décisions.
    document = Document.objects.select_for_update().get(pk=document.pk)
    if document.integrity_status != Document.Integrity.SAIN:
        raise BusinessError("Ce document n'a pas passé les contrôles de sécurité.", code="not_verifiable")
    if decision not in DECISION_LABELS:
        raise ValidationError({"decision": ["Décision inconnue."]})
    reason = reason.strip()
    already_decided = document.conformity_status != Document.Conformity.NON_EVALUE
    if already_decided and not revise:
        raise Conflict(
            "Ce document a déjà été examiné. Pour changer la décision, utilisez « Revoir la décision ».",
            code="already_decided",
        )
    if already_decided and not reason:
        raise ValidationError({"reason": ["Expliquez pourquoi la décision est revue."]})
    if decision != Document.Conformity.CONFORME and not reason:
        raise ValidationError({"reason": ["Expliquez à la PME ce qui ne va pas, en langage simple."]})
    for field, value in (
        ("period_start", period_start),
        ("period_end", period_end),
        ("issued_at", issued_at),
        ("expires_at", expires_at),
    ):
        if value is not None:
            setattr(document, field, value)
    today = timezone.localdate()
    before = {"verification": document.verification_status, "conformity": document.conformity_status}
    document.validity_status = _validity(document, today)
    document.currency_status = _currency(document, today)
    if decision in (Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE):
        # Invariant (Document 3, § 4) : pas de conformité sur un document expiré ou d'une autre période.
        if document.validity_status == Document.Validity.EXPIRE:
            raise ValidationError({"expires_at": ["Le document est expiré : il ne peut pas être déclaré conforme."]})
        if document.currency_status in (Document.Currency.PERIODE_INCORRECTE, Document.Currency.PERIODE_ANTERIEURE):
            raise ValidationError({"period_end": ["La période du document ne correspond pas à celle attendue."]})
    document.conformity_status = decision
    document.verification_status = (
        Document.Verification.VERIFIE_HUMAIN
        if decision in (Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE)
        else Document.Verification.REJETE
    )
    document.decision_reason = reason
    document.verified_by = access.user
    document.verified_at = timezone.now()
    document.save()
    if document.deadline_id:
        deadline = document.deadline
        deadline.status = DEADLINE_STATUS_FOR_DECISION[decision]
        deadline.closed_at = timezone.now() if decision != Document.Conformity.NON_CONFORME else None
        deadline.save(update_fields=["status", "closed_at", "updated_at"])
    audit.record(
        "document.decision_revised" if already_decided else "document.verified",
        instance=document,
        pme_id=document.pme_id,
        before=before,
        after={
            "decision": decision,
            "reason": reason,
            "validity": document.validity_status,
            "currency": document.currency_status,
            "expires_at": document.expires_at,
        },
    )
    events.emit("document.verified", pme_id=str(document.pme_id), document_id=str(document.pk), decision=decision)
    notifications.notify(
        notifications.pme_users(document.pme),
        "DOCUMENT_DECISION",
        {"document": document.title, "decision": DECISION_LABELS[decision], "reason": reason},
        link="/espace",
        pme=document.pme,
    )
    after_evidence_change(document.pme)
    from pme360.ai.knowledge import on_document_decision
    from pme360.plans import services as plans

    on_document_decision(document)
    plans.on_document_decision(document)  # livrables et actions liés (phase 5)
    return document


def after_evidence_change(pme: Pme) -> None:
    """Une preuve change : score courant recalculé (RM-01) et alertes réévaluées."""
    from pme360.alerts import engine as alerts
    from pme360.scoring import services as scoring

    scoring.refresh_live(pme)
    alerts.evaluate_pme(pme, timezone.localdate())


# --- Téléchargement par URL signée ----------------------------------------------------------------------------

SIGNING_SALT = "pme360.documents.download"


def download_token(version: DocumentVersion, user) -> str:
    return signing.dumps(
        {"v": str(version.pk), "o": str(version.organization_id), "u": str(user.pk)}, salt=SIGNING_SALT, compress=True
    )


def read_token(token: str, max_age: int) -> dict:
    return signing.loads(token, salt=SIGNING_SALT, max_age=max_age)
