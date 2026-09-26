"""Registre réglementaire, obligations et échéances (Document 3, § 3.5 ; Document 8).

RM-08 : une obligation adossée à une règle réglementaire ne peut être ACTIVE que si la règle est VÉRIFIÉE
(source officielle lue, date et vérificateur renseignés). Les obligations « programme » (transmission d'une
preuve à l'organisation d'accompagnement) et « bonne pratique » ne dépendent d'aucune règle légale.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class RegulatoryRule(TenantModel):
    class Status(models.TextChoices):
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        PRE_VERIFIE = "PRE_VERIFIE", "Pré-vérifiée (source identifiée)"
        VERIFIE = "VERIFIE", "Vérifiée"
        OBSOLETE = "OBSOLETE", "Obsolète"
        HORS_PERIMETRE = "HORS_PERIMETRE", "Hors périmètre"

    code = models.CharField(max_length=40)
    title = models.CharField(max_length=250)
    content = models.TextField(help_text="Ce qui a été identifié (et ce qui reste à confirmer).")
    authority = models.CharField(max_length=60)
    sources = models.JSONField(default=list, help_text="[{title, url}] — sources officielles puis secondaires.")
    source_reference = models.CharField(max_length=250, blank=True, help_text="Texte et article précis.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.A_VERIFIER)
    verified_at = models.DateField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verification_note = models.TextField(blank=True)
    review_due_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "regulatory_rule"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="regulatory_rule_unique_code"),
            models.CheckConstraint(
                condition=~Q(status="VERIFIE")
                | (Q(verified_at__isnull=False) & Q(verified_by__isnull=False) & ~Q(source_reference="")),
                name="regulatory_rule_verified_is_documented",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class ObligationTemplate(TenantModel):
    class Nature(models.TextChoices):
        REGLEMENTAIRE = "REGLEMENTAIRE", "Réglementaire"
        PROGRAMME = "PROGRAMME", "Programme (transmission à l'organisation)"
        BONNE_PRATIQUE = "BONNE_PRATIQUE", "Bonne pratique"

    class Frequency(models.TextChoices):
        PONCTUELLE = "PONCTUELLE", "Ponctuelle"
        MENSUELLE = "MENSUELLE", "Mensuelle"
        TRIMESTRIELLE = "TRIMESTRIELLE", "Trimestrielle"
        SEMESTRIELLE = "SEMESTRIELLE", "Semestrielle"
        ANNUELLE = "ANNUELLE", "Annuelle"

    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    nature = models.CharField(max_length=16, choices=Nature.choices)
    document_type = models.ForeignKey("documents.DocumentType", on_delete=models.PROTECT, related_name="+")
    regulatory_rule = models.ForeignKey(
        RegulatoryRule, null=True, blank=True, on_delete=models.PROTECT, related_name="obligations"
    )
    frequency = models.CharField(max_length=14, choices=Frequency.choices)
    # Périodicité dépendant du profil (ex. CNPS mensuelle à partir de 20 salariés) : JSON Logic → une fréquence.
    frequency_rule = models.JSONField(null=True, blank=True)
    due_days_after_period_end = models.PositiveIntegerField(default=30)
    applicability = models.JSONField(null=True, blank=True, help_text="JSON Logic sur le profil de la PME.")
    reminder_offsets = models.JSONField(
        default=list, help_text="Jours relatifs à l'échéance, ex. [-30,-15,-7,0,7,15,30]."
    )
    is_critical = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = "obligation_template"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="obligation_template_unique_code")]

    def __str__(self) -> str:
        return self.code


class PmeObligation(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDUE = "SUSPENDUE", "Suspendue"
        DISPENSEE = "DISPENSEE", "Dispensée"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="obligations")
    template = models.ForeignKey(ObligationTemplate, on_delete=models.PROTECT, related_name="pme_obligations")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    frequency = models.CharField(max_length=14, choices=ObligationTemplate.Frequency.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    waiver_reason = models.TextField(blank=True)

    class Meta:
        db_table = "pme_obligation"
        constraints = [models.UniqueConstraint(fields=["pme", "template"], name="pme_obligation_unique")]

    def __str__(self) -> str:
        return f"{self.pme} — {self.template}"


class Deadline(TenantModel):
    class Status(models.TextChoices):
        A_FOURNIR = "A_FOURNIR", "À fournir"
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        RECU = "RECU", "Reçu"
        EN_ANALYSE = "EN_ANALYSE", "En analyse"
        VERIF_HUMAINE_REQUISE = "VERIF_HUMAINE_REQUISE", "Vérification humaine requise"
        CONFORME = "CONFORME", "Conforme"
        CONFORME_SOUS_RESERVE = "CONFORME_SOUS_RESERVE", "Conforme sous réserve"
        NON_CONFORME = "NON_CONFORME", "Non conforme"
        EXPIRE = "EXPIRE", "Document expiré"
        INCOHERENT = "INCOHERENT", "Document incohérent"
        EN_RETARD = "EN_RETARD", "En retard"
        DISPENSE = "DISPENSE", "Dispensée"

    OPEN = (
        Status.A_FOURNIR,
        Status.EN_ATTENTE,
        Status.EN_RETARD,
        Status.NON_CONFORME,
        Status.INCOHERENT,
        Status.EXPIRE,
    )

    pme_obligation = models.ForeignKey(PmeObligation, on_delete=models.CASCADE, related_name="deadlines")
    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="deadlines")
    period_label = models.CharField(max_length=40)
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=22, choices=Status.choices, default=Status.A_FOURNIR)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "deadline"
        ordering = ["due_date"]
        constraints = [
            models.UniqueConstraint(fields=["pme_obligation", "period_start"], name="deadline_unique_period")
        ]
        indexes = [models.Index(fields=["organization", "due_date", "status"], name="deadline_due_idx")]

    def __str__(self) -> str:
        return f"{self.period_label} — {self.pme_obligation.template.name}"


class DeadlineReminder(TenantModel):
    """Relance envoyée (une seule fois par échéance et par décalage : idempotence du planificateur)."""

    deadline = models.ForeignKey(Deadline, on_delete=models.CASCADE, related_name="reminders")
    offset_days = models.IntegerField()
    sent_on = models.DateField()

    class Meta:
        db_table = "deadline_reminder"
        constraints = [models.UniqueConstraint(fields=["deadline", "offset_days"], name="deadline_reminder_unique")]

    def __str__(self) -> str:
        return f"{self.deadline_id} J{self.offset_days:+d}"
