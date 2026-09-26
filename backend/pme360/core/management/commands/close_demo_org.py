"""Clôt une démo « marque blanche » après la présentation. Refusé en production.

  python manage.py close_demo_org banque-atlantique

- organisation suspendue (la page de connexion redevient neutre) ;
- comptes de démonstration désactivés, accès retirés ;
- fichiers supprimés du stockage et clés de l'organisation détruites (les copies éventuelles deviennent illisibles).
Le journal d'audit, inaltérable par conception, est conservé.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pme360.accounts.models import UserMembership
from pme360.audit import services as audit
from pme360.core.tenancy import system_context, tenant_context
from pme360.documents.models import DocumentVersion
from pme360.documents.storage import get_storage
from pme360.organizations import keys
from pme360.organizations.models import Organization, OrganizationKey
from pme360.reports.models import Report

from .create_demo_org import RESERVED
from .seed_demo import ensure_not_production


class Command(BaseCommand):
    help = "Clôt une démo de prospect : suspension, comptes désactivés, fichiers et clés détruits."

    def add_arguments(self, parser):
        parser.add_argument("slug")

    def handle(self, *args, slug, **options):
        ensure_not_production()
        if slug in RESERVED:
            raise CommandError("Cette organisation n'est pas une démo de prospect.")
        with system_context():
            organization = Organization.objects.filter(slug=slug).first()
            if organization is None:
                raise CommandError("Démo introuvable.")
            memberships = UserMembership.objects.filter(organization=organization).select_related("user")
            users = {m.user for m in memberships}
            if any(not u.email.endswith(f".{slug}@demo.test") for u in users):
                raise CommandError("Des comptes réels appartiennent à cette organisation : clôture refusée.")
            paths = list(
                DocumentVersion.objects.filter(organization=organization).values_list("storage_key", flat=True)
            ) + list(Report.objects.filter(organization=organization).values_list("storage_key", flat=True))
        storage = get_storage()
        removed = 0
        for path in paths:
            try:
                storage.delete(path)
                removed += 1
            except Exception as exc:  # fichier déjà absent
                self.stderr.write(f"{path} : {exc}")
        with system_context():
            memberships.update(is_active=False, valid_to=timezone.localdate())
            for user in users:
                user.is_active = False
                user.save(update_fields=["is_active"])
            OrganizationKey.objects.filter(organization=organization).delete()
            organization.status = Organization.Status.SUSPENDUE
            organization.save(update_fields=["status", "updated_at"])
        keys.clear_cache()
        with tenant_context(organization.id):
            audit.record(
                "organization.demo_closed",
                instance=organization,
                actor_type="SYSTEM",
                after={"files_deleted": removed, "accounts_disabled": len(users)},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Démo « {organization.name} » close : {removed} fichier(s) supprimé(s), "
                f"{len(users)} compte(s) désactivé(s), clés détruites."
            )
        )
