"""PME (niveau 1 : connaître) et référentiels associés (Document 3, § 3.2)."""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class ReferenceItem(TenantModel):
    """Élément de nomenclature configurable par tenant."""

    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class Sector(ReferenceItem):
    class Meta(ReferenceItem.Meta):
        db_table = "sector"
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="sector_unique_code")]


class LegalForm(ReferenceItem):
    is_company = models.BooleanField(
        default=True, help_text="Société (statuts, organes sociaux) vs entreprise individuelle."
    )

    class Meta(ReferenceItem.Meta):
        db_table = "legal_form"
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="legal_form_unique_code")]


class Region(ReferenceItem):
    class Kind(models.TextChoices):
        REGION = "REGION", "Région"
        DISTRICT_AUTONOME = "DISTRICT_AUTONOME", "District autonome"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.REGION)

    class Meta(ReferenceItem.Meta):
        db_table = "region"
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="region_unique_code")]


class Pme(TenantModel):
    class LifecycleStatus(models.TextChoices):
        PROSPECT = "PROSPECT", "Prospect"
        ONBOARDING = "ONBOARDING", "Intégration"
        DIAGNOSTIC_EN_COURS = "DIAGNOSTIC_EN_COURS", "Diagnostic en cours"
        ACCOMPAGNEMENT_ACTIF = "ACCOMPAGNEMENT_ACTIF", "Accompagnement actif"
        SUSPENDU = "SUSPENDU", "Suspendu"
        SORTIE = "SORTIE", "Sortie du programme"
        SUIVI_POST_PROGRAMME = "SUIVI_POST_PROGRAMME", "Suivi post-programme"

    class SizeCategory(models.TextChoices):
        # Déclarée en phase 1 ; calculée à partir de ``size_rule`` une fois REG-PME-01 vérifiée (Document 8, § 2).
        NON_DETERMINEE = "NON_DETERMINEE", "Non déterminée"
        MICRO = "MICRO", "Micro-entreprise"
        PETITE = "PETITE", "Petite entreprise"
        MOYENNE = "MOYENNE", "Moyenne entreprise"
        HORS_PME = "HORS_PME", "Hors PME"

    class ExitReason(models.TextChoices):
        DIPLOMEE = "DIPLOMEE", "Diplômée"
        ABANDON = "ABANDON", "Abandon"
        REORIENTATION = "REORIENTATION", "Réorientation"

    legal_name = models.CharField("raison sociale", max_length=250)
    trade_name = models.CharField("sigle ou nom commercial", max_length=250, blank=True)
    legal_form = models.ForeignKey(LegalForm, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    rccm_number = models.CharField("n° RCCM", max_length=60, blank=True)
    ncc = models.CharField("n° de compte contribuable", max_length=30, blank=True)
    cnps_employer_number = models.CharField("n° employeur CNPS", max_length=30, blank=True)
    creation_date = models.DateField(null=True, blank=True)
    sector = models.ForeignKey(Sector, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    commune = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    headcount = models.PositiveIntegerField("effectif déclaré", null=True, blank=True)
    size_category = models.CharField(max_length=20, choices=SizeCategory.choices, default=SizeCategory.NON_DETERMINEE)
    lifecycle_status = models.CharField(
        max_length=30, choices=LifecycleStatus.choices, default=LifecycleStatus.PROSPECT
    )
    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    exited_at = models.DateTimeField(null=True, blank=True)
    exit_reason = models.CharField(max_length=20, choices=ExitReason.choices, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pme"
        ordering = ["legal_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "rccm_number"], condition=~Q(rccm_number=""), name="pme_unique_rccm"
            ),
            models.UniqueConstraint(fields=["organization", "ncc"], condition=~Q(ncc=""), name="pme_unique_ncc"),
        ]
        indexes = [
            GinIndex(fields=["legal_name"], opclasses=["gin_trgm_ops"], name="pme_legal_name_trgm"),
            models.Index(fields=["organization", "lifecycle_status"], name="pme_lifecycle_idx"),
        ]

    def __str__(self) -> str:
        return self.legal_name


class PmePerson(TenantModel):
    """Dirigeant, associé ou contact. Données personnelles minimales (RM-10)."""

    class Role(models.TextChoices):
        GERANT = "GERANT", "Gérant"
        DG = "DG", "Directeur général"
        PCA = "PCA", "Président du conseil d'administration"
        PRESIDENT = "PRESIDENT", "Président"
        ASSOCIE = "ASSOCIE", "Associé"
        DIRECTEUR = "DIRECTEUR", "Directeur"
        CONTACT = "CONTACT", "Contact"

    class Gender(models.TextChoices):
        FEMME = "F", "Femme"
        HOMME = "H", "Homme"

    pme = models.ForeignKey(Pme, on_delete=models.CASCADE, related_name="persons")
    full_name = models.CharField(max_length=200)
    role = models.CharField(max_length=20, choices=Role.choices)
    share_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_primary_contact = models.BooleanField(default=False)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True, help_text="Facultatif (statistiques).")
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Facultatif (statistiques).")

    class Meta:
        db_table = "pme_person"
        ordering = ["-is_primary_contact", "full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["pme"], condition=Q(is_primary_contact=True), name="pme_person_one_primary_contact"
            ),
            models.CheckConstraint(
                condition=Q(share_pct__isnull=True) | Q(share_pct__gte=0, share_pct__lte=100),
                name="pme_person_share_pct_range",
            ),
        ]


class PmeAssignment(TenantModel):
    class RoleInPme(models.TextChoices):
        CONSEILLER_PRINCIPAL = "CONSEILLER_PRINCIPAL", "Conseiller principal"
        EXPERT = "EXPERT", "Expert"

    pme = models.ForeignKey(Pme, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pme_assignments")
    role_in_pme = models.CharField(max_length=30, choices=RoleInPme.choices)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "pme_assignment"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["pme"],
                condition=Q(end_date__isnull=True, role_in_pme="CONSEILLER_PRINCIPAL"),
                name="pme_one_active_principal_advisor",
            ),
            models.UniqueConstraint(
                fields=["pme", "user", "role_in_pme"],
                condition=Q(end_date__isnull=True),
                name="pme_assignment_active_unique",
            ),
        ]


class PmeEnrollment(TenantModel):
    pme = models.ForeignKey(Pme, on_delete=models.CASCADE, related_name="enrollments")
    cohort = models.ForeignKey("organizations.Cohort", on_delete=models.PROTECT, related_name="enrollments")
    enrolled_at = models.DateField()
    exited_at = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "pme_enrollment"
        ordering = ["-enrolled_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pme", "cohort"], condition=Q(exited_at__isnull=True), name="pme_enrollment_active_unique"
            )
        ]
