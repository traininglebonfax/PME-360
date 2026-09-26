"""Organisations (tenants), programmes et cohortes (Document 3, § 3.1)."""

from django.db import models

from pme360.core.models import TenantModel, TimeStampedModel


class Organization(TimeStampedModel):
    """Tenant. Protégé par une politique RLS sur ``id`` : une session ne voit que son organisation."""

    class Type(models.TextChoices):
        AGENCE_PUBLIQUE = "AGENCE_PUBLIQUE", "Agence ou programme public"
        BANQUE = "BANQUE", "Banque"
        INCUBATEUR = "INCUBATEUR", "Incubateur"
        ONG = "ONG", "ONG"
        BAILLEUR = "BAILLEUR", "Bailleur"
        CABINET = "CABINET", "Cabinet"
        ASSOCIATION = "ASSOCIATION", "Association professionnelle"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDUE = "SUSPENDUE", "Suspendue"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    type = models.CharField(max_length=20, choices=Type.choices)
    country = models.CharField(max_length=2, default="CI")
    branding = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    ai_external_allowed = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "organization"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def setting(self, key: str, default=None):
        """Paramètre de tenant avec valeur par défaut (cf. ``DEFAULT_SETTINGS``)."""
        return self.settings.get(key, DEFAULT_SETTINGS.get(key, default))


# Valeurs par défaut des paramètres de tenant (modifiables par l'ADMIN_ORG).
DEFAULT_SETTINGS = {
    "inactivity_days": 60,  # Document 1, § 7
    "duplicate_name_similarity": 0.55,  # seuil de similarité trigramme pour la détection de doublons
    # IA (Document 4, § 3 et § 7) : quotas et seuils de vérification humaine.
    "ai_monthly_token_quota": 2_000_000,
    "ai_auto_threshold": 0.85,  # confiance du document et de la classification
    "ai_field_threshold": 0.90,  # confiance des champs critiques
}


class Programme(TenantModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    funder = models.CharField(max_length=200, blank=True)
    objectives = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "programme"
        ordering = ["-start_date", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="programme_unique_name")]

    def __str__(self) -> str:
        return self.name


class Cohort(TenantModel):
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="cohorts")
    name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "cohort"
        ordering = ["start_date", "name"]
        constraints = [models.UniqueConstraint(fields=["programme", "name"], name="cohort_unique_name")]

    def __str__(self) -> str:
        return f"{self.programme.name} — {self.name}"


class OrganizationKey(TenantModel):
    """Clé de données propre à l'organisation (chiffrement enveloppe des fichiers, Document 2, § 8.2 ; V1).

    La clé AES-256 n'est jamais stockée en clair : elle est « enveloppée » (chiffrée) par la clé maîtresse de la
    plateforme, conservée hors base (variable d'environnement / coffre). Les anciennes versions restent pour
    relire les fichiers chiffrés avant une rotation ; une seule version est active.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retirée (lecture seule)"

    version = models.PositiveIntegerField()
    wrapped_key = models.TextField(help_text="Clé de données chiffrée par la clé maîtresse (Fernet).")
    master_key_id = models.CharField(max_length=16, help_text="Empreinte de la clé maîtresse ayant enveloppé.")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organization_key"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "version"], name="organization_key_unique_version"),
            models.UniqueConstraint(
                fields=["organization"], condition=models.Q(status="ACTIVE"), name="organization_key_one_active"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} v{self.version}"
