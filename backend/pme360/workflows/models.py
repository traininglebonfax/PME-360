"""Définitions de workflow configurables par l'organisation (Document 3, § 3.7 ; Document 7, § 2 ; V1).

Les ÉTATS sont fixés par le code (le moteur leur attache des effets : notification, progrès vérifié, déblocage des
dépendances) ; l'organisation configure leurs libellés, les transitions MANUELLES autorisées, qui peut les
déclencher et si un motif est exigé. Une définition active ne se modifie pas : on crée un brouillon, puis on
l'active (la précédente est retirée). Les transitions automatiques restent gérées par le moteur.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class WorkflowDefinition(TenantModel):
    class TargetType(models.TextChoices):
        ACTION = "ACTION", "Action du plan d'accompagnement"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retirée"

    target_type = models.CharField(max_length=12, choices=TargetType.choices)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    # {"CODE": {"label": "...", "pme_label": "..."}}
    states = models.JSONField(default=dict)
    # [{"from", "to", "actors": ["STAFF", "PME"], "reason_required", "button", "pme_button"}]
    transitions = models.JSONField(default=list)
    notes = models.TextField(blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "workflow_definition"
        ordering = ["target_type", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "target_type", "version"], name="workflow_definition_unique_version"
            ),
            models.UniqueConstraint(
                fields=["organization", "target_type"], condition=Q(status="ACTIVE"), name="workflow_one_active"
            ),
            models.UniqueConstraint(
                fields=["organization", "target_type"], condition=Q(status="DRAFT"), name="workflow_one_draft"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.target_type} v{self.version}"
