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


def generate_portfolio_report(
    access, period: str | None = None, *, programme=None, cohort=None, include_names: bool = False, user=None
) -> Report:
    """Rapport trimestriel de portefeuille (Document 9, § 7) : données figées, PDF archivé, versionné."""
    from pme360.documents.storage import get_storage

    from . import portfolio_builder

    data = portfolio_builder.portfolio_report_data(
        access, period, programme=programme, cohort=cohort, include_names=include_names, generated_by=user
    )
    scope = data["scope"]
    period_label = data["period"]["label"]
    same = Report.objects.filter(type=Report.Type.PORTEFEUILLE, period=period_label).filter(
        scope__programme_id=scope["programme_id"], scope__cohort_id=scope["cohort_id"]
    )
    version = (same.aggregate(m=Max("version"))["m"] or 0) + 1
    context = {
        "d": {**data, "groups": [("Secteurs", data["by_sector"]), ("Régions", data["by_region"])]},
        "version": version,
    }
    content, engine = pdf.render_pdf("reports/portfolio.html", context)
    scope_key = hashlib.sha256(str(scope).encode()).hexdigest()[:8]
    key = f"reports/{access.organization_id}/portefeuille/{period_label}-{scope_key}-v{version}.pdf"
    get_storage().put(key, content, "application/pdf")
    report = Report.objects.create(
        type=Report.Type.PORTEFEUILLE,
        version=version,
        title=f"Rapport de portefeuille {period_label} — {scope['label']}",
        period=period_label,
        scope=scope,
        template_version=portfolio_builder.TEMPLATE_VERSION,
        data_snapshot=data,
        storage_key=key,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        engine=engine,
        generated_by=user,
        generated_at=timezone.now(),
        created_by=user,
    )
    audit.record(
        "report.generated",
        instance=report,
        actor=user,
        actor_type="USER" if user else "SYSTEM",
        after={
            "type": report.type,
            "period": period_label,
            "scope": scope["label"],
            "pmes": len(scope["pme_ids"]),
            "include_names": include_names,
            "version": version,
        },
    )
    return report


def can_read_portfolio_report(report: Report, access) -> bool:
    """Lisible par qui voit le portefeuille ET toutes les PME du périmètre du rapport."""
    from pme360.pmes.models import Pme

    if access.is_pme_user or not (access.has("dashboard.portfolio") or access.has("report.generate")):
        return False
    visible = {str(pk) for pk in access.pme_queryset(Pme.objects.all()).values_list("pk", flat=True)}
    return set(report.scope.get("pme_ids", [])) <= visible
