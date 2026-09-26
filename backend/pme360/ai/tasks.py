from celery import shared_task

from pme360.core.tenancy import system_context, tenant_context


@shared_task
def run_prediagnostic(diagnostic_id: str) -> int:
    """Pré-diagnostic asynchrone après la soumission (Document 4, fonction F)."""
    from pme360.diagnostic.models import Diagnostic
    from pme360.notifications import services as notifications

    from . import prediagnostic

    with system_context():
        organization_id = Diagnostic.objects.filter(pk=diagnostic_id).values_list("organization_id", flat=True).first()
    if organization_id is None:
        return 0
    with tenant_context(organization_id):
        diagnostic = Diagnostic.objects.select_related("pme").get(pk=diagnostic_id)
        if diagnostic.status != Diagnostic.Status.EN_REVUE:
            return 0
        count = prediagnostic.run(diagnostic)
        if count:
            notifications.notify(
                notifications.recipients(diagnostic.pme, ["CONSEILLER"]),
                "PREDIAGNOSTIC_READY",
                {"pme": diagnostic.pme.legal_name, "count": count},
                link=f"/diagnostics/{diagnostic.pk}/revue",
                pme=diagnostic.pme,
            )
        return count
