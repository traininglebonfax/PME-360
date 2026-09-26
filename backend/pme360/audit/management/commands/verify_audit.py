"""Vérifie la chaîne de hachage du journal d'audit de chaque organisation et de la plateforme."""

from django.core.management.base import BaseCommand, CommandError

from pme360.audit.services import verify_chain
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Organization


class Command(BaseCommand):
    help = "Vérifie l'intégrité du journal d'audit chaîné (toutes organisations)."

    def handle(self, *args, **options):
        with system_context():
            organizations = list(Organization.objects.values_list("id", "slug"))
            scopes = [(None, "plateforme", system_context)]
        scopes += [(org_id, slug, lambda org_id=org_id: tenant_context(org_id)) for org_id, slug in organizations]
        broken = []
        for org_id, label, context in scopes:
            with context():
                result = verify_chain(org_id)
            state = "intègre" if result.valid else f"ALTÉRÉE à l'entrée {result.first_invalid_id}"
            self.stdout.write(f"{label} : {result.entries_checked} entrée(s), chaîne {state}")
            if not result.valid:
                broken.append(label)
        if broken:
            raise CommandError(f"Journal d'audit altéré : {', '.join(broken)}")
        self.stdout.write(self.style.SUCCESS("Journal d'audit intègre."))
