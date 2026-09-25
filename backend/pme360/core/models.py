"""Modèles de base : horodatage, auteur, appartenance à un tenant, outbox des événements de domaine."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from .ids import uuid7
from .tenancy import current_org_id, rls_bypassed


class TimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True


class TenantManager(models.Manager):
    """Filtre applicatif sur le tenant courant (doublé par la RLS PostgreSQL)."""

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        if rls_bypassed():
            return queryset
        org_id = current_org_id()
        if org_id is None:
            return queryset.none()
        return queryset.filter(organization_id=org_id)

    def bulk_create(self, objs, *args, **kwargs):
        """``bulk_create`` n'appelle pas ``save()`` : on y renseigne aussi l'organisation courante."""
        org_id = current_org_id()
        for obj in objs:
            if getattr(obj, "organization_id", None) is None:
                if org_id is None:
                    raise ImproperlyConfigured(f"{type(obj).__name__} créé hors contexte de tenant.")
                obj.organization_id = org_id
        return super().bulk_create(objs, *args, **kwargs)


class TenantModel(TimeStampedModel):
    """Toute table métier : ``organization_id`` obligatoire, filtré par le manager et protégé par la RLS.

    Chaque table concrète DOIT recevoir une politique RLS dans ses migrations (``pme360.core.rls.EnableRLS``) ;
    ``tests/test_rls.py`` échoue si une table en est dépourvue.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs) -> None:
        if self.organization_id is None:
            org_id = current_org_id()
            if org_id is None:
                raise ImproperlyConfigured(
                    f"{type(self).__name__} créé hors contexte de tenant : organization_id introuvable."
                )
            self.organization_id = org_id
        super().save(*args, **kwargs)


class DomainEvent(TenantModel):
    """Outbox transactionnelle (Document 2, § 7, ADR-008) : écrite dans la même transaction que le fait métier."""

    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = "domain_event_outbox"
        indexes = [models.Index(fields=["processed_at", "created_at"], name="outbox_pending_idx")]

    def __str__(self) -> str:
        return f"{self.event_type} {self.id}"
