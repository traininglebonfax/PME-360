"""Exécute le planificateur quotidien (échéances, relances, alertes) — utile sans Celery Beat."""

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from pme360.compliance.tasks import run_daily_for


class Command(BaseCommand):
    help = "Planificateur quotidien de conformité : obligations, échéances, relances, alertes."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="day", help="Date simulée (AAAA-MM-JJ), par défaut aujourd'hui.")

    def handle(self, *args, day: str | None = None, **options):
        today = datetime.date.fromisoformat(day) if day else timezone.localdate()
        totals = run_daily_for(today)
        self.stdout.write(self.style.SUCCESS(f"{today} : {totals}"))
