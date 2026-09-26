"""Réindexe la base de connaissances (référentiel, règles vérifiées, documents, historique) de chaque tenant."""

from django.core.management.base import BaseCommand

from pme360.ai.knowledge import reindex_organization
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Organization


class Command(BaseCommand):
    help = "Réindexe la base de connaissances de toutes les organisations."

    def handle(self, *args, **options):
        with system_context():
            organizations = list(Organization.objects.values_list("id", "name"))
        for organization_id, name in organizations:
            with tenant_context(organization_id):
                counts = reindex_organization()
            self.stdout.write(f"{name} : {counts}")
