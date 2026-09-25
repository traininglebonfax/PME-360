"""Référentiel de diagnostic versionné et sessions de diagnostic (Document 3, § 3.3 et § 3.4 ; Document 5).

Un ``FrameworkVersion`` publié est IMMUABLE (ADR-004) : un trigger PostgreSQL interdit toute modification de la
version et de son contenu (piliers, dimensions, critères, questions, indicateurs). Chaque table de contenu porte
``framework_version_id`` pour que le trigger puisse vérifier le statut sans jointure.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel

# --- Référentiel ---------------------------------------------------------------------------------------------


class Framework(TenantModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)

    class Meta:
        db_table = "framework"
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="framework_unique_code")]

    def __str__(self) -> str:
        return self.code


class FrameworkVersion(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        PUBLISHED = "PUBLISHED", "Publiée"
        RETIRED = "RETIRED", "Retirée"

    framework = models.ForeignKey(Framework, on_delete=models.PROTECT, related_name="versions")
    version = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)
    # Niveaux de maturité, bandes de confiance, IMD, règles de priorité : configuration du moteur (Document 6).
    settings = models.JSONField(default=dict)

    class Meta:
        db_table = "framework_version"
        ordering = ["-published_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["framework", "version"], name="framework_version_unique"),
            models.UniqueConstraint(
                fields=["framework"], condition=Q(status="PUBLISHED"), name="framework_one_published_version"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.framework.code} v{self.version}"


class VersionedContent(TenantModel):
    framework_version = models.ForeignKey(FrameworkVersion, on_delete=models.CASCADE, related_name="+")
    code = models.CharField(max_length=40)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order"]

    def __str__(self) -> str:
        return self.code


class Pillar(VersionedContent):
    name = models.CharField(max_length=200)
    weight = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta(VersionedContent.Meta):
        db_table = "pillar"
        constraints = [models.UniqueConstraint(fields=["framework_version", "code"], name="pillar_unique_code")]


class Dimension(VersionedContent):
    pillar = models.ForeignKey(Pillar, on_delete=models.CASCADE, related_name="dimensions")
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=60)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    # Part du module sectoriel dans la dimension (Document 6, § 2.3) ; 0 = pas de module sectoriel.
    sector_module_share = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta(VersionedContent.Meta):
        db_table = "dimension"
        constraints = [models.UniqueConstraint(fields=["framework_version", "code"], name="dimension_unique_code")]


class Criterion(VersionedContent):
    class Lens(models.TextChoices):
        CONFORMITE = "C", "Conformité"
        ORGANISATION = "O", "Organisation"
        PERFORMANCE = "P", "Performance"
        RISQUE = "R", "Maîtrise des risques"

    class EvidencePolicy(models.TextChoices):
        NONE = "NONE", "Aucune"
        RECOMMENDED = "RECOMMENDED", "Recommandée"
        REQUIRED = "REQUIRED", "Obligatoire"

    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=300)
    lens = models.CharField(max_length=1, choices=Lens.choices)
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    is_critical = models.BooleanField(default=False)
    rubric = models.JSONField(default=list, help_text="Ancres descriptives des niveaux 0 à 4.")
    declarative_cap_level = models.PositiveSmallIntegerField(default=2)
    applicability = models.JSONField(null=True, blank=True, help_text="Règle JSON Logic sur le profil de la PME.")
    evidence_policy = models.CharField(max_length=12, choices=EvidencePolicy.choices, default=EvidencePolicy.NONE)
    evidence_document_types = models.JSONField(default=list, help_text="Codes des types de documents (Document 8).")
    sector_module = models.CharField(max_length=40, blank=True, help_text="Code secteur ; vide = tronc commun.")

    class Meta(VersionedContent.Meta):
        db_table = "criterion"
        constraints = [models.UniqueConstraint(fields=["framework_version", "code"], name="criterion_unique_code")]


class Question(VersionedContent):
    class Type(models.TextChoices):
        SINGLE = "SINGLE", "Choix unique"
        BOOLEAN = "BOOLEAN", "Oui / non"
        NUMBER = "NUMBER", "Nombre"
        AMOUNT = "AMOUNT", "Montant (FCFA)"
        PERCENT = "PERCENT", "Pourcentage"
        TEXT = "TEXT", "Texte"

    class Audience(models.TextChoices):
        PME = "PME", "PME"
        CONSEILLER = "CONSEILLER", "Conseiller"
        LES_DEUX = "LES_DEUX", "Les deux"

    criterion = models.ForeignKey(Criterion, null=True, blank=True, on_delete=models.CASCADE, related_name="questions")
    dimension = models.ForeignKey(Dimension, null=True, blank=True, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    help_text = models.TextField(blank=True)
    why_text = models.TextField(blank=True, help_text="« Pourquoi cette question ? » en langage simple.")
    type = models.CharField(max_length=10, choices=Type.choices)
    options = models.JSONField(default=list, help_text="[{value, label, level}] ; level = niveau du critère.")
    visibility = models.JSONField(null=True, blank=True, help_text="Règle JSON Logic (profil + réponses).")
    target_audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.LES_DEUX)
    is_required = models.BooleanField(default=True)
    # Clé d'alimentation : variable du profil (« profile.has_stock ») ou donnée d'indicateur (« input.ca_n »).
    feeds = models.CharField(max_length=60, blank=True)
    evidence_hint = models.CharField(max_length=300, blank=True, help_text="Preuve demandée pour les niveaux élevés.")

    class Meta(VersionedContent.Meta):
        db_table = "question"
        constraints = [
            models.UniqueConstraint(fields=["framework_version", "code"], name="question_unique_code"),
            models.CheckConstraint(
                condition=Q(criterion__isnull=False) | Q(dimension__isnull=False), name="question_has_parent"
            ),
        ]


class MetricDefinition(VersionedContent):
    """Indicateur calculé : Indicateur → formule → données → résultat → interprétation → source (Document 6, § 7)."""

    class Unit(models.TextChoices):
        PERCENT = "PERCENT", "%"
        RATIO = "RATIO", "ratio"
        DAYS = "DAYS", "jours"
        YEARS = "YEARS", "années"
        AMOUNT = "AMOUNT", "FCFA"

    criterion = models.ForeignKey(Criterion, null=True, blank=True, on_delete=models.CASCADE, related_name="metrics")
    name = models.CharField(max_length=200)
    formula = models.CharField(max_length=300)
    formula_label = models.CharField(max_length=300, help_text="Formule en clair.")
    unit = models.CharField(max_length=8, choices=Unit.choices)
    # [{"upto": seuil exclusif ou null, "points": 0..100, "label": "..."}], évaluées dans l'ordre.
    bands = models.JSONField(default=list)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    class Meta(VersionedContent.Meta):
        db_table = "metric_definition"
        constraints = [models.UniqueConstraint(fields=["framework_version", "code"], name="metric_unique_code")]


# --- Sessions de diagnostic ----------------------------------------------------------------------------------


class Diagnostic(TenantModel):
    class Type(models.TextChoices):
        INITIAL = "INITIAL", "Diagnostic initial"
        SUIVI = "SUIVI", "Diagnostic de suivi"
        REEVALUATION = "REEVALUATION", "Réévaluation complète"
        CLOTURE = "CLOTURE", "Diagnostic de clôture"

    class Status(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        EN_COLLECTE = "EN_COLLECTE", "En collecte"
        ANALYSE_IA = "ANALYSE_IA", "Analyse IA"
        EN_REVUE = "EN_REVUE", "En revue"
        VALIDE = "VALIDE", "Validé"
        ANNULE = "ANNULE", "Annulé"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.PROTECT, related_name="diagnostics")
    framework_version = models.ForeignKey(FrameworkVersion, on_delete=models.PROTECT, related_name="diagnostics")
    type = models.CharField(max_length=14, choices=Type.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.EN_COLLECTE)
    reference_date = models.DateField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    lead_advisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "diagnostic"
        ordering = ["-reference_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["pme"], condition=~Q(status__in=["VALIDE", "ANNULE"]), name="diagnostic_one_open_per_pme"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} — {self.reference_date}"

    @property
    def is_open(self) -> bool:
        return self.status not in (self.Status.VALIDE, self.Status.ANNULE)


class Answer(TenantModel):
    class Source(models.TextChoices):
        PME = "PME", "Déclaré par la PME"
        CONSEILLER = "CONSEILLER", "Saisi par le conseiller"
        IA_PREREMPLI = "IA_PREREMPLI", "Pré-rempli par l'IA"
        REPRISE = "REPRISE", "Repris du diagnostic précédent"

    diagnostic = models.ForeignKey(Diagnostic, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    value = models.JSONField(null=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    answered_at = models.DateTimeField()
    source = models.CharField(max_length=14, choices=Source.choices)

    class Meta:
        db_table = "answer"
        constraints = [models.UniqueConstraint(fields=["diagnostic", "question"], name="answer_unique")]


class AnswerHistory(TenantModel):
    """Historique en ajout seul des réponses (valeur précédente conservée)."""

    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="history")
    value = models.JSONField(null=True)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    answered_at = models.DateTimeField()
    source = models.CharField(max_length=14)

    class Meta:
        db_table = "answer_history"
        ordering = ["-answered_at"]


class CriterionAssessment(TenantModel):
    """Revue humaine d'un critère : niveau validé, modifié (justifié) ou critère non applicable."""

    class Status(models.TextChoices):
        VALIDE = "VALIDE", "Validé"
        MODIFIE = "MODIFIE", "Modifié"
        NON_APPLICABLE = "NON_APPLICABLE", "Non applicable"

    diagnostic = models.ForeignKey(Diagnostic, on_delete=models.CASCADE, related_name="assessments")
    criterion = models.ForeignKey(Criterion, on_delete=models.PROTECT, related_name="assessments")
    status = models.CharField(max_length=16, choices=Status.choices)
    level_declared = models.PositiveSmallIntegerField(null=True, blank=True)
    level_final = models.PositiveSmallIntegerField(null=True, blank=True)
    corroborated = models.BooleanField(default=False, help_text="Déclaratif corroboré (entretien, visite).")
    comment = models.TextField(blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField()

    class Meta:
        db_table = "criterion_assessment"
        constraints = [
            models.UniqueConstraint(fields=["diagnostic", "criterion"], name="assessment_unique"),
            models.CheckConstraint(
                condition=Q(level_final__isnull=True) | Q(level_final__lte=4), name="assessment_level_range"
            ),
        ]
