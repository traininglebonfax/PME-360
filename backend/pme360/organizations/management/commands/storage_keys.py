"""Gestion des clés de chiffrement des fichiers (exploitation).

python manage.py storage_keys status               # clés par organisation (version active, clé maîtresse)
python manage.py storage_keys rotate <slug>        # nouvelle version de clé pour une organisation
python manage.py storage_keys rewrap               # après ajout d'une nouvelle clé maîtresse EN TÊTE de
                                                   # PME360_STORAGE_MASTER_KEYS : ré-enveloppe toutes les clés
"""

from django.core.management.base import BaseCommand, CommandError

from pme360.audit import services as audit
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations import keys
from pme360.organizations.models import Organization, OrganizationKey


class Command(BaseCommand):
    help = "Clés de chiffrement par organisation : état, rotation, ré-enveloppement."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["status", "rotate", "rewrap"])
        parser.add_argument("organization", nargs="?", help="Slug de l'organisation (rotation).")

    def handle(self, *args, action, organization=None, **options):
        if action == "status":
            current = keys.master_key_id()
            with system_context():
                for org in Organization.objects.order_by("name"):
                    active = OrganizationKey.objects.filter(organization=org, status="ACTIVE").first()
                    total = OrganizationKey.objects.filter(organization=org).count()
                    state = (
                        f"v{active.version} active, {total} version(s)"
                        + ("" if active.master_key_id == current else " — À RÉ-ENVELOPPER")
                        if active
                        else "aucune clé (créée au premier fichier)"
                    )
                    self.stdout.write(f"{org.slug:<24} {state}")
            return
        if action == "rewrap":
            self.stdout.write(
                f"{keys.rewrap_all()} clé(s) ré-enveloppée(s) avec la clé maîtresse {keys.master_key_id()}."
            )
            return
        if not organization:
            raise CommandError("Indiquez le slug de l'organisation.")
        with system_context():
            org = Organization.objects.filter(slug=organization).first()
        if org is None:
            raise CommandError("Organisation inconnue.")
        key = keys.create_key(org.id)
        with tenant_context(org.id):
            audit.record(
                "organization.key_rotated",
                entity_type="organization_key",
                entity_id=key.pk,
                after={"version": key.version},
                actor_type="SYSTEM",
            )
        self.stdout.write(
            f"{org.slug} : clé v{key.version} active. Les fichiers existants restent lisibles ; "
            "« encrypt_storage --reencrypt » les passe sur la nouvelle clé."
        )
