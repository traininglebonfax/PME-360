"""Génération des rapports (Document 9, § 7) : données figées → PDF archivé → nouvelle version à chaque correction."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError

from . import builders, pdf
from .models import Report


def generate_diagnostic_report(diagnostic, user=None) -> Report:
    from pme360.diagnostic.models import Diagnostic
    from pme360.documents.storage import get_storage
    from pme360.notifications import services as notifications

    if diagnostic.status != Diagnostic.Status.VALIDE:
        raise BusinessError("Le rapport porte sur un diagnostic validé.", code="invalid_status")
    data = builders.diagnostic_report_data(diagnostic, generated_by=user)
    version = (Report.objects.filter(diagnostic=diagnostic).aggregate(m=Max("version"))["m"] or 0) + 1
    content, engine = pdf.render_pdf("reports/diagnostic.html", {"d": data, "version": version})
    pme = diagnostic.pme
    key = f"reports/{pme.organization_id}/{pme.pk}/diagnostic-{diagnostic.pk}-v{version}.pdf"
    get_storage().put(key, content, "application/pdf")
    confidence = data["score"]["confidence"]
    report = Report.objects.create(
        type=Report.Type.DIAGNOSTIC,
        pme=pme,
        diagnostic=diagnostic,
        version=version,
        title=f"Rapport de diagnostic — {pme.legal_name}",
        period=diagnostic.reference_date.isoformat(),
        template_version=builders.TEMPLATE_VERSION,
        data_snapshot=data,
        storage_key=key,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        engine=engine,
        confidence=Decimal(str(round(confidence, 3))) if confidence is not None else None,
        generated_by=user,
        generated_at=timezone.now(),
        created_by=user,
    )
    audit.record(
        "report.generated",
        instance=report,
        pme_id=pme.pk,
        actor=user,
        actor_type="USER" if user else "SYSTEM",
        after={"type": report.type, "version": version, "sha256": report.sha256, "engine": engine},
    )
    notifications.notify(
        notifications.pme_users(pme) + notifications.recipients(pme, ["CONSEILLER"]),
        "REPORT_READY",
        {"pme": pme.legal_name, "version": version},
        link=f"/pme/{pme.pk}?onglet=rapports",
        pme=pme,
    )
    return report


def read_pdf(report: Report) -> bytes:
    """Contenu archivé, vérifié contre son empreinte (intégrité du rapport)."""
    from pme360.documents.storage import get_storage

    content = get_storage().get(report.storage_key)
    if hashlib.sha256(content).hexdigest() != report.sha256:
        raise BusinessError("Le fichier archivé ne correspond pas à son empreinte.", code="integrity_error")
    return content
