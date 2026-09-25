"""Moteur d'alertes (Document 7, § 8) : règles configurables par tenant, alertes dédoublonnées et résolues
automatiquement lorsque la condition disparaît."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class Severity(models.TextChoices):
    INFO = "INFO", "Information"
    MOYENNE = "MOYENNE", "Moyenne"
    ELEVEE = "ELEVEE", "Élevée"
    CRITIQUE = "CRITIQUE", "Critique"


class AlertRule(TenantModel):
    code = models.CharField(max_length=40)
    kind = models.CharField(max_length=40, help_text="Type d'alerte évalué par le moteur.")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    params = models.JSONField(default=dict, help_text="Seuils de la règle (jours, points, pourcentages…).")
    recipients = models.JSONField(
        default=list, help_text="Destinataires : PME, CONSEILLER, RESPONSABLE_PROGRAMME, EXPERT."
    )
    is_active = models.BooleanField(default=True)
    available_in_phase = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "alert_rule"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="alert_rule_unique_code")]

    def __str__(self) -> str:
        return self.code


class Alert(TenantModel):
    class Status(models.TextChoices):
        OUVERTE = "OUVERTE", "Ouverte"
        PRISE_EN_COMPTE = "PRISE_EN_COMPTE", "Prise en compte"
        RESOLUE = "RESOLUE", "Résolue"
        IGNOREE = "IGNOREE", "Ignorée"

    OPEN = (Status.OUVERTE, Status.PRISE_EN_COMPTE)

    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="alerts")
    rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT, related_name="alerts")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    title = models.CharField(max_length=250)
    message = models.TextField()
    details = models.JSONField(default=dict)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    dedup_key = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OUVERTE)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        db_table = "alert"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "dedup_key"],
                condition=Q(status__in=["OUVERTE", "PRISE_EN_COMPTE"]),
                name="alert_one_open_per_key",
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "severity"], name="alert_status_idx")]

    def __str__(self) -> str:
        return self.title
