"""Documents et dossier numérique de conformité (Document 3, § 3.5 et § 4 ; Document 8, § 3).

Un document n'a pas UN statut mais plusieurs axes indépendants ; le statut affiché en est dérivé
(``status_display``). Invariant (Document 3, § 4) : CONFORME ⇒ intégrité SAINE, validité VALIDE,
actualité À JOUR et vérification HUMAINE (aucune conformité automatique dans la configuration par défaut).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class DocumentCategory(TenantModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "document_category"
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="document_category_unique_code")]

    def __str__(self) -> str:
        return self.name


class DocumentType(TenantModel):
    class PeriodKind(models.TextChoices):
        AUCUNE = "AUCUNE", "Aucune"
        MOIS = "MOIS", "Mois"
        TRIMESTRE = "TRIMESTRE", "Trimestre"
        SEMESTRE = "SEMESTRE", "Semestre"
        ANNEE = "ANNEE", "Année"
        EXERCICE = "EXERCICE", "Exercice comptable"

    category = models.ForeignKey(DocumentCategory, on_delete=models.PROTECT, related_name="document_types")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    period_kind = models.CharField(max_length=10, choices=PeriodKind.choices, default=PeriodKind.AUCUNE)
    validity_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="Durée de validité depuis la délivrance."
    )
    freshness_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="« À jour » si daté de moins de N jours."
    )
    evidence_level = models.PositiveSmallIntegerField(default=3, help_text="Niveau de critère prouvé par ce document.")
    sensitive = models.BooleanField(default=False, help_text="Données personnelles : jamais envoyé à une IA externe.")
    guidance = models.TextField(blank=True, help_text="Comment l'obtenir / le préparer (langage simple).")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "document_type"
        ordering = ["category__order", "order"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="document_type_unique_code")]

    def __str__(self) -> str:
        return self.name


class Document(TenantModel):
    class Integrity(models.TextChoices):
        EN_SCAN = "EN_SCAN", "Analyse de sécurité en cours"
        SAIN = "SAIN", "Sain"
        REJETE_SECURITE = "REJETE_SECURITE", "Rejeté (sécurité)"

    class Validity(models.TextChoices):
        VALIDE = "VALIDE", "Valide"
        EXPIRE = "EXPIRE", "Expiré"
        INDETERMINE = "INDETERMINE", "Indéterminée"

    class Currency(models.TextChoices):
        A_JOUR = "A_JOUR", "À jour"
        PERIODE_ANTERIEURE = "PERIODE_ANTERIEURE", "Période antérieure"
        PERIODE_INCORRECTE = "PERIODE_INCORRECTE", "Période incorrecte"
        INDETERMINE = "INDETERMINE", "Indéterminée"

    class Verification(models.TextChoices):
        NON_VERIFIE = "NON_VERIFIE", "Non vérifié"
        ANALYSE_IA = "ANALYSE_IA", "Analysé par l'IA"
        VERIF_HUMAINE_REQUISE = "VERIF_HUMAINE_REQUISE", "Vérification humaine requise"
        VERIFIE_HUMAIN = "VERIFIE_HUMAIN", "Vérifié"
        REJETE = "REJETE", "Rejeté"

    class Conformity(models.TextChoices):
        NON_EVALUE = "NON_EVALUE", "Non évalué"
        CONFORME = "CONFORME", "Conforme"
        CONFORME_SOUS_RESERVE = "CONFORME_SOUS_RESERVE", "Conforme sous réserve"
        NON_CONFORME = "NON_CONFORME", "Non conforme"
        INCOHERENT = "INCOHERENT", "Incohérent"

    class Channel(models.TextChoices):
        PORTAIL_PME = "PORTAIL_PME", "Portail PME"
        CONSEILLER = "CONSEILLER", "Conseiller"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.PROTECT, related_name="documents")
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="documents")
    deadline = models.ForeignKey(
        "compliance.Deadline", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    title = models.CharField(max_length=250)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    issued_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    integrity_status = models.CharField(max_length=16, choices=Integrity.choices, default=Integrity.EN_SCAN)
    validity_status = models.CharField(max_length=12, choices=Validity.choices, default=Validity.INDETERMINE)
    currency_status = models.CharField(max_length=20, choices=Currency.choices, default=Currency.INDETERMINE)
    verification_status = models.CharField(
        max_length=22, choices=Verification.choices, default=Verification.NON_VERIFIE
    )
    conformity_status = models.CharField(max_length=22, choices=Conformity.choices, default=Conformity.NON_EVALUE)
    decision_reason = models.TextField(blank=True, help_text="Motif en langage simple, visible par la PME.")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    uploaded_via = models.CharField(max_length=12, choices=Channel.choices)
    current_version_no = models.PositiveIntegerField(default=0)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "pme", "document_type"], name="document_pme_type_idx"),
            models.Index(fields=["organization", "verification_status"], name="document_verification_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def status_display(self) -> str:
        """Statut lisible, dérivé des axes (du plus bloquant au plus favorable)."""
        if self.integrity_status == self.Integrity.REJETE_SECURITE:
            return "REJETE_SECURITE"
        if self.integrity_status == self.Integrity.EN_SCAN:
            return "EN_ANALYSE"
        if self.verification_status == self.Verification.VERIF_HUMAINE_REQUISE:
            return "A_VERIFIER"
        if self.conformity_status in (self.Conformity.CONFORME, self.Conformity.CONFORME_SOUS_RESERVE):
            if self.validity_status == self.Validity.EXPIRE:
                return "EXPIRE"
            return self.conformity_status
        if self.conformity_status != self.Conformity.NON_EVALUE:
            return self.conformity_status
        return "RECU"


class DocumentVersion(TenantModel):
    class Antivirus(models.TextChoices):
        SAIN = "SAIN", "Sain"
        INFECTE = "INFECTE", "Infecté"

    class Text(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        TEXTE_NATIF = "TEXTE_NATIF", "Texte natif extrait"
        OCR_REQUIS = "OCR_REQUIS", "Lecture optique requise (phase 4)"
        ERREUR = "ERREUR", "Erreur de lecture"

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    version_no = models.PositiveIntegerField()
    storage_key = models.CharField(max_length=300, blank=True, help_text="Vide si le fichier a été refusé.")
    original_filename = models.CharField(max_length=255)
    extension = models.CharField(max_length=8)
    mime_detected = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveBigIntegerField()
    av_status = models.CharField(max_length=8, choices=Antivirus.choices)
    av_engine = models.CharField(max_length=40)
    av_signature = models.CharField(max_length=200, blank=True)
    text_status = models.CharField(max_length=12, choices=Text.choices, default=Text.EN_ATTENTE)
    text_content = models.TextField(blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    processed_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "document_version"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(fields=["document", "version_no"], name="document_version_unique"),
            models.CheckConstraint(
                condition=Q(av_status="SAIN") | Q(storage_key=""), name="document_version_infected_never_stored"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document} v{self.version_no}"


class DocumentCheck(TenantModel):
    class Result(models.TextChoices):
        OK = "OK", "OK"
        ALERTE = "ALERTE", "Alerte"
        ECHEC = "ECHEC", "Échec"
        NON_DETERMINE = "NON_DETERMINE", "Non déterminé"

    version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE, related_name="checks")
    check_code = models.CharField(max_length=40)
    result = models.CharField(max_length=14, choices=Result.choices)
    message = models.CharField(max_length=300)
    details = models.JSONField(default=dict)

    class Meta:
        db_table = "document_check"
        constraints = [models.UniqueConstraint(fields=["version", "check_code"], name="document_check_unique")]

    def __str__(self) -> str:
        return f"{self.check_code} {self.result}"
