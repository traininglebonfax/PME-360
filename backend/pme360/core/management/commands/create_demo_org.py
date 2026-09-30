"""Crée une démo complète au nom d'un prospect (marque blanche). Refusé en production.

  python manage.py create_demo_org --nom "Banque Atlantique" --couleur "#0055A4"
  python manage.py create_demo_org --nom "Incubateur Akwaba" --court "Akwaba" --type INCUBATEUR --logo logo.png

Organisation distincte (étanche), comptes dédiés ``<compte>.<slug>@demo.test``, 6 PME fictives, diagnostics,
documents, plan d'accompagnement et rapports ; identité visuelle du prospect. Idempotent (relançable).
Après la présentation : ``python manage.py close_demo_org <slug>``.
"""

import base64
import mimetypes
from pathlib import Path

from django.core.management.base import CommandError
from django.utils.text import slugify

from pme360.organizations.branding import validate
from pme360.organizations.models import Organization
from seeds import tenant_demo

from .seed_demo import Command as SeedCommand
from .seed_demo import ensure_not_production

RESERVED = {"pme360-demo", "banque-demo"}


class Command(SeedCommand):
    help = "Crée une démo complète (organisation, comptes, PME fictives) au nom d'un prospect, sans trace d'une autre."

    def add_arguments(self, parser):
        parser.add_argument("--nom", required=True, help="Nom de l'organisation du prospect.")
        parser.add_argument("--court", help="Nom court affiché dans les libellés (défaut : --nom).")
        parser.add_argument("--slug", help="Identifiant d'adresse (défaut : calculé depuis --nom).")
        parser.add_argument("--produit", default="PME360", help="Nom du produit affiché (défaut : PME360).")
        parser.add_argument("--couleur", default="#2E4A6B", help="Couleur principale #RRGGBB (texte blanc lisible).")
        parser.add_argument("--logo", help="Fichier PNG, JPEG ou WebP (150 Ko au plus).")
        parser.add_argument(
            "--type", default="BANQUE", choices=[c for c, _ in Organization.Type.choices], help="Type d'organisation."
        )

    def handle(self, *args, nom, court=None, slug=None, produit="PME360", couleur="#2E4A6B", logo=None, **options):
        ensure_not_production()
        slug = slugify(slug or nom)[:60]
        if not slug or slug in RESERVED:
            raise CommandError("Identifiant réservé ou vide : précisez --slug.")
        logo_uri = None
        if logo:
            path = Path(logo)
            if not path.is_file():
                raise CommandError(f"Logo introuvable : {logo}")
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            logo_uri = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
        # Contrôles d'identité identiques à l'écran d'administration (contraste, format du logo).
        branding = validate(
            {"product_name": produit, "short_name": court or nom, "primary_color": couleur, "logo": logo_uri}
        )
        self.data = tenant_demo.build(
            slug,
            f"{nom} (DÉMO)",
            short_name=branding["short_name"],
            product_name=branding["product_name"],
            color=branding["primary_color"],
            logo=branding.get("logo"),
            org_type=options["type"],
        )
        self.primary = slug
        self.load()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Démo prête : http://localhost:3010/connexion?org={slug}"))
        self.stdout.write(f"À la fin de la présentation : python manage.py close_demo_org {slug}")
