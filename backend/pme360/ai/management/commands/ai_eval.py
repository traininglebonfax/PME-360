"""Rejoue le jeu d'évaluation de l'IA documentaire (Document 4, § 12) avant toute activation de prompt ou de modèle."""

import json

from django.core.management.base import BaseCommand, CommandError

from pme360.ai.evaluation import evaluate


class Command(BaseCommand):
    help = "Évalue classification et extraction sur le jeu de documents fictifs ; échoue sous les seuils."

    def add_arguments(self, parser):
        parser.add_argument("--provider", choices=["local", "anthropic"], default="local")
        parser.add_argument("--per-type", type=int, default=12)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, provider, per_type, seed, no_save, **options):
        try:
            run = evaluate(provider=provider, per_type=per_type, seed=seed, save=not no_save)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(run.metrics, ensure_ascii=False, indent=2))
        if not run.passed:
            raise CommandError(f"Seuils non atteints : {run.thresholds}")
        self.stdout.write(self.style.SUCCESS(f"Évaluation réussie ({run.provider})."))
