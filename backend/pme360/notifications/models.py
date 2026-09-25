"""Notifications (Document 7, § 8.3) : in-app et e-mail ; WhatsApp / SMS en V2.

La notification est un EFFET (d'une alerte, d'une échéance, d'une décision) : l'historique de référence reste
l'alerte, l'échéance ou le journal d'audit.
"""

from django.conf import settings
from django.db import models

from pme360.core.models import TenantModel


class NotificationTemplate(TenantModel):
    """Modèle de message par événement, modifiable par l'organisation (variables : ``{pme}``, ``{document}``…)."""

    event_code = models.CharField(max_length=60)
    subject = models.CharField(max_length=200)
    body = models.TextField()

    class Meta:
        db_table = "notification_template"
        constraints = [
            models.UniqueConstraint(fields=["organization", "event_code"], name="notification_template_unique")
        ]

    def __str__(self) -> str:
        return self.event_code


class Notification(TenantModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    pme = models.ForeignKey("pmes.Pme", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    event_code = models.CharField(max_length=60)
    title = models.CharField(max_length=200)
    body = models.TextField()
    link = models.CharField(max_length=300, blank=True)
    severity = models.CharField(max_length=10, default="INFO")
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "user", "read_at"], name="notification_inbox_idx")]

    def __str__(self) -> str:
        return self.title


class NotificationPreference(TenantModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    event_code = models.CharField(max_length=60)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=True)

    class Meta:
        db_table = "notification_preference"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "event_code"], name="notification_preference_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.event_code}"
