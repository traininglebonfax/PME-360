import structlog
from celery import shared_task
from django.utils import timezone

from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme

from . import services

logger = structlog.get_logger(__name__)


def run_daily_for(today) -> dict:
    """Planificateur quotidien (Document 8, § 4) : obligations, échéances, statuts, relances, alertes."""
    totals = {"pmes": 0, "obligations": 0, "deadlines_created": 0, "reminders": 0}
    with system_context():
        organizations = list(
            Organization.objects.filter(status=Organization.Status.ACTIVE).values_list("id", flat=True)
        )
    for organization_id in organizations:
        with tenant_context(organization_id):
            for pme in Pme.objects.exclude(lifecycle_status=Pme.LifecycleStatus.SORTIE).select_related(
                "sector", "legal_form"
            ):
                stats = services.run_for_pme(pme, today)
                totals["pmes"] += 1
                for key in ("obligations", "deadlines_created", "reminders"):
                    totals[key] += stats[key]
    logger.info("compliance.daily_run", **totals, date=today.isoformat())
    return totals


@shared_task
def run_daily() -> dict:
    return run_daily_for(timezone.localdate())
