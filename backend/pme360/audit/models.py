"""Journal d'audit inaltérable (Document 2, § 8.3 ; Document 3, § 3.9).

- ajout seul : un trigger PostgreSQL interdit UPDATE et DELETE ;
- chaînage par hash : chaque entrée inclut le hash de la précédente de la même organisation ;
- protégé par la RLS : une organisation ne lit que son propre journal.
"""

from django.conf import settings
from django.db import models

from pme360.core.models import TenantManager


class AuditLog(models.Model):
    class ActorType(models.TextChoices):
        USER = "USER", "Utilisateur"
        SYSTEM = "SYSTEM", "Système"
        AI = "AI", "IA"

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    pme_id = models.UUIDField(null=True, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    # Texte brut (et non inet) : la valeur relue doit être identique à la valeur hachée.
    ip = models.CharField(max_length=45, null=True, blank=True)  # noqa: DJ001 — None ≠ "" dans le hash
    user_agent = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    at = models.DateTimeField()
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    objects = TenantManager()

    class Meta:
        db_table = "audit_log"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["organization", "entity_type", "entity_id"], name="audit_entity_idx"),
            models.Index(fields=["organization", "pme_id", "at"], name="audit_pme_idx"),
            models.Index(fields=["organization", "actor", "at"], name="audit_actor_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}:{self.entity_id}"
