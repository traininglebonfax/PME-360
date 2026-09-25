"""Affiche le code MFA courant d'un compte de démonstration (démo uniquement, refusé en production)."""

import pyotp
from django.core.management.base import BaseCommand, CommandError

from .seed_demo import demo_totp_secret, ensure_not_production


class Command(BaseCommand):
    help = "Code TOTP courant d'un compte de démonstration (@demo.test)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email: str, **options):
        ensure_not_production()
        if not email.endswith("@demo.test"):
            raise CommandError("Réservé aux comptes de démonstration (@demo.test).")
        self.stdout.write(pyotp.TOTP(demo_totp_secret(email)).now())
