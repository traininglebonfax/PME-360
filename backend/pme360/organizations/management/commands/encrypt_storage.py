"""Chiffre les fichiers déposés avant la V1 et, après une rotation, rechiffre avec la clé active.

  python manage.py encrypt_storage                 # fichiers en clair → chiffrés avec la clé de leur organisation
  python manage.py encrypt_storage --reencrypt     # aussi les fichiers chiffrés avec une ancienne version de clé
  python manage.py encrypt_storage --dry-run       # inventaire sans écriture

Idempotent ; chaque fichier est relu et vérifié (même contenu déchiffré) avant d'être remplacé.
"""

from django.core.management.base import BaseCommand

from pme360.core.tenancy import system_context
from pme360.documents.models import DocumentVersion
from pme360.documents.storage import get_storage
from pme360.organizations import keys
from pme360.organizations.models import OrganizationKey
from pme360.reports.models import Report


class Command(BaseCommand):
    help = "Chiffre les fichiers existants avec la clé de leur organisation (chiffrement enveloppe, V1)."

    def add_arguments(self, parser):
        parser.add_argument("--reencrypt", action="store_true", help="Rechiffrer aussi avec la version de clé active.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, reencrypt=False, dry_run=False, **options):
        storage = get_storage()
        if not hasattr(storage, "get_raw"):
            self.stderr.write("Chiffrement désactivé (PME360_STORAGE_ENCRYPTION=false) : rien à faire.")
            return
        with system_context():
            paths = list(DocumentVersion.objects.exclude(storage_key="").values_list("storage_key", flat=True))
            paths += list(Report.objects.exclude(storage_key="").values_list("storage_key", flat=True))
            active = dict(
                OrganizationKey.objects.filter(status=OrganizationKey.Status.ACTIVE).values_list(
                    "organization_id", "version"
                )
            )
        counts = {"chiffrés": 0, "rechiffrés": 0, "déjà à jour": 0, "absents": 0, "erreurs": 0}
        for path in paths:
            try:
                raw = storage.get_raw(path)
            except (FileNotFoundError, OSError):
                counts["absents"] += 1
                continue
            except Exception:  # objet absent du stockage S3
                counts["absents"] += 1
                continue
            version = keys.key_version(raw)
            org_id = keys.organization_of(path)
            if version is not None and (not reencrypt or version == active.get(org_id)):
                counts["déjà à jour"] += 1
                continue
            try:
                plain = keys.decrypt(path, raw)
                encrypted = keys.encrypt(path, plain)
                if keys.decrypt(path, encrypted) != plain:
                    raise keys.StorageKeyError("Vérification après chiffrement échouée.")
                if not dry_run:
                    storage.put_raw(path, encrypted)
                counts["chiffrés" if version is None else "rechiffrés"] += 1
            except Exception as exc:
                counts["erreurs"] += 1
                self.stderr.write(f"{path} : {exc}")
        summary = " · ".join(f"{n} {label}" for label, n in counts.items())
        self.stdout.write(("[simulation] " if dry_run else "") + summary)
