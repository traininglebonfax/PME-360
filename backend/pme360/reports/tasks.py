from celery import shared_task

from pme360.core.tenancy import system_context, tenant_context


@shared_task
def generate_diagnostic_report(diagnostic_id: str, user_id: str | None = None) -> str | None:
    """Rapport de diagnostic généré à la validation (Document 9, § 7)."""
    from pme360.accounts.models import User
    from pme360.diagnostic.models import Diagnostic

    from . import services

    with system_context():
        organization_id = Diagnostic.objects.filter(pk=diagnostic_id).values_list("organization_id", flat=True).first()
    if organization_id is None:
        return None
    with tenant_context(organization_id):
        diagnostic = Diagnostic.objects.select_related("pme").get(pk=diagnostic_id)
        user = User.objects.filter(pk=user_id).first() if user_id else None
        return str(services.generate_diagnostic_report(diagnostic, user).pk)


@shared_task
def generate_quarterly_portfolio_reports() -> int:
    """Début de trimestre : rapport anonymisé de l'organisation entière pour le trimestre écoulé."""
    from pme360.core.exceptions import BusinessError
    from pme360.organizations.models import Organization
    from pme360.pmes.models import Pme

    from . import portfolio_builder, services

    count = 0
    with system_context():
        organizations = list(Organization.objects.filter(status="ACTIVE").values_list("id", flat=True))
    for organization_id in organizations:
        with tenant_context(organization_id):
            ids = [str(pk) for pk in Pme.objects.values_list("pk", flat=True)]
            if not ids:
                continue
            scope = portfolio_builder.ReportScope(organization_id=organization_id, pme_ids=ids)
            try:
                services.generate_portfolio_report(scope, None)
                count += 1
            except BusinessError:
                continue
    return count
