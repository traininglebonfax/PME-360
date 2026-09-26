"""Rapports générés (Document 3, § 3.9 ; Document 9, § 7) : données figées, PDF archivé, jamais modifié.

Une correction produit une nouvelle version : la table est en ajout seul.
"""

from django.conf import settings
from django.db import models

from pme360.core.models import TenantModel


class Report(TenantModel):
    class Type(models.TextChoices):
        DIAGNOSTIC = "DIAGNOSTIC", "Rapport de diagnostic"
        PORTEFEUILLE = "PORTEFEUILLE", "Rapport de portefeuille"

    type = models.CharField(max_length=14, choices=Type.choices)
    pme = models.ForeignKey("pmes.Pme", null=True, blank=True, on_delete=models.CASCADE, related_name="reports")
    diagnostic = models.ForeignKey(
        "diagnostic.Diagnostic", null=True, blank=True, on_delete=models.PROTECT, related_name="reports"
    )
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=250)
    period = models.CharField(max_length=60, blank=True)
    template_version = models.CharField(max_length=20)
    data_snapshot = models.JSONField(help_text="Données figées au moment de la génération.")
    storage_key = models.CharField(max_length=300)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    engine = models.CharField(max_length=20, help_text="Moteur de rendu PDF utilisé.")
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    generated_at = models.DateTimeField()

    class Meta:
        db_table = "report"
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["diagnostic", "version"],
                condition=models.Q(type="DIAGNOSTIC"),
                name="report_diagnostic_version",
            )
        ]
