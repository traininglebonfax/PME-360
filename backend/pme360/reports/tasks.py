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
