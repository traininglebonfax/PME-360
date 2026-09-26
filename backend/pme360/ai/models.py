"""« AI PME Diagnostic Copilot » (Document 4) : traçabilité, extractions, états financiers, base de connaissances.

Principe cardinal : l'IA lit, classe, extrait, compare et rédige ; elle ne calcule jamais un score ni un ratio.
Tout appel à un modèle passe par ``ai.gateway`` et laisse une trace ``AiAnalysis`` (Document 4, § 11).
"""

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel, TimeStampedModel


class AiAnalysis(TenantModel):
    """Trace d'un appel à la passerelle IA : modèle, prompt, entrées, sortie, confiance, jetons, coût, latence."""

    class Task(models.TextChoices):
        CLASSIFICATION = "CLASSIFICATION", "Classification documentaire"
        EXTRACTION = "EXTRACTION", "Extraction structurée"
        CONTROLE = "CONTROLE", "Contrôles et anomalies"
        ANALYSE_FINANCIERE = "ANALYSE_FINANCIERE", "Interprétation financière"
        PRE_DIAGNOSTIC = "PRE_DIAGNOSTIC", "Pré-diagnostic"
        ASK_AI = "ASK_AI", "Ask AI"

    class Status(models.TextChoices):
        SUCCES = "SUCCES", "Succès"
        SORTIE_INVALIDE = "SORTIE_INVALIDE", "Sortie invalide (vérification humaine)"
        REFUSE_POLITIQUE = "REFUSE_POLITIQUE", "Refusé par la politique du tenant"
        BUDGET_EPUISE = "BUDGET_EPUISE", "Budget épuisé"
        DIFFERE = "DIFFERE", "Fournisseur indisponible : analyse différée"
        ECHEC = "ECHEC", "Échec"

    task = models.CharField(max_length=20, choices=Task.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    pme = models.ForeignKey("pmes.Pme", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    document_version = models.ForeignKey(
        "documents.DocumentVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="ai_analyses"
    )
    diagnostic = models.ForeignKey(
        "diagnostic.Diagnostic", null=True, blank=True, on_delete=models.PROTECT, related_name="ai_analyses"
    )
    provider = models.CharField(max_length=20, help_text="local (règles, sans envoi externe) | anthropic")
    model = models.CharField(max_length=60, help_text="Identifiant exact du modèle (ou du moteur de règles).")
    prompt_code = models.CharField(max_length=60)
    prompt_version = models.CharField(max_length=20)
    input_refs = models.JSONField(default=dict, help_text="Documents, versions, réponses et fragments utilisés.")
    input_hash = models.CharField(max_length=64, db_index=True)
    pseudonymized = models.BooleanField(default=False)
    output = models.JSONField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=1)
    error = models.CharField(max_length=500, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "ai_analysis"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="ai_analysis_org_date_idx"),
            models.Index(fields=["organization", "pme", "task"], name="ai_analysis_pme_task_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.task} {self.status} ({self.model})"


class DocumentExtraction(TenantModel):
    """Résultat IA sur une version : classification, champs extraits, confiance et revue humaine (Document 4, § 7)."""

    class Status(models.TextChoices):
        PROVISOIRE = "PROVISOIRE", "Provisoire (confiance suffisante)"
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        VALIDEE = "VALIDEE", "Validée"
        CORRIGEE = "CORRIGEE", "Corrigée"
        REJETEE = "REJETEE", "Rejetée"
        NON_ANALYSEE = "NON_ANALYSEE", "Non analysée"

    REVIEWED = (Status.VALIDEE, Status.CORRIGEE, Status.REJETEE)

    version = models.OneToOneField("documents.DocumentVersion", on_delete=models.CASCADE, related_name="extraction")
    expected_type = models.CharField(max_length=40)
    classified_type = models.CharField(max_length=40, blank=True)
    classification_confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    schema_code = models.CharField(max_length=40, blank=True)
    schema_version = models.CharField(max_length=20, blank=True)
    data = models.JSONField(default=dict)
    field_confidence = models.JSONField(default=dict)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.NON_ANALYSEE)
    reason = models.CharField(max_length=300, blank=True, help_text="Pourquoi une vérification humaine est requise.")
    classification_analysis = models.ForeignKey(
        AiAnalysis, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    extraction_analysis = models.ForeignKey(
        AiAnalysis, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    corrections = models.JSONField(default=dict, help_text="{champ: {before, after}} (human_review).")
    review_comment = models.TextField(blank=True)

    class Meta:
        db_table = "document_extraction"

    def __str__(self) -> str:
        return f"{self.classified_type or '?'} {self.status}"


class FinancialStatement(TenantModel):
    """États financiers d'un exercice, issus d'une extraction (Document 4, § 4.1).

    Les valeurs portent les noms des données d'indicateurs du référentiel (``ca_n``, ``resultat_net``…) :
    le moteur de scoring calcule les ratios de façon déterministe. Source : DOCUMENT_VERIFIE après revue
    humaine, DOCUMENT_IA tant que l'extraction est seulement provisoire.
    """

    class Status(models.TextChoices):
        PROVISOIRE = "PROVISOIRE", "Provisoire (extraction IA)"
        VERIFIE = "VERIFIE", "Vérifié"
        ECARTE = "ECARTE", "Écarté"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.PROTECT, related_name="financial_statements")
    fiscal_year_end = models.DateField()
    system = models.CharField(max_length=10, blank=True, help_text="NORMAL | SMT | INCONNU")
    values = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices)
    source_version = models.ForeignKey(
        "documents.DocumentVersion", on_delete=models.PROTECT, related_name="financial_statements"
    )
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "financial_statement"
        ordering = ["-fiscal_year_end"]
        constraints = [
            models.UniqueConstraint(fields=["pme", "fiscal_year_end"], name="financial_statement_unique_year")
        ]

    def __str__(self) -> str:
        return f"Exercice clos le {self.fiscal_year_end} ({self.status})"


class KnowledgeChunk(TenantModel):
    """Fragment indexé pour la recherche (Document 4, § 8).

    ``pme`` vide = connaissance de l'organisation (référentiel, registre VÉRIFIÉ) ; sinon réservé au périmètre
    de la PME. Le filtrage de sécurité (RLS + périmètre) est appliqué AVANT le classement.
    """

    class Source(models.TextChoices):
        REFERENTIEL = "REFERENTIEL", "Référentiel de diagnostic"
        REGLEMENTATION = "REGLEMENTATION", "Registre réglementaire (vérifié)"
        DOCUMENT = "DOCUMENT", "Document de la PME"
        HISTORIQUE = "HISTORIQUE", "Historique de la PME"

    pme = models.ForeignKey("pmes.Pme", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    source_type = models.CharField(max_length=16, choices=Source.choices)
    source_id = models.CharField(max_length=64)
    source_label = models.CharField(max_length=300)
    source_date = models.DateField(null=True, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    text = models.TextField()
    search_vector = SearchVectorField(null=True)

    class Meta:
        db_table = "knowledge_chunk"
        indexes = [
            GinIndex(fields=["search_vector"], name="knowledge_chunk_search_idx"),
            models.Index(fields=["organization", "source_type", "source_id"], name="knowledge_chunk_source_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source_label} #{self.position}"


class Conversation(TenantModel):
    """Conversation Ask AI (conservée et auditable) ; ``pme`` vide = portefeuille de l'utilisateur."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    pme = models.ForeignKey("pmes.Pme", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)

    class Meta:
        db_table = "ai_conversation"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class ConversationMessage(TenantModel):
    class Role(models.TextChoices):
        USER = "USER", "Utilisateur"
        ASSISTANT = "ASSISTANT", "Assistant"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    sources = models.JSONField(default=list)
    confidence = models.CharField(max_length=10, blank=True)
    limits = models.JSONField(default=list)
    tool_calls = models.JSONField(default=list)
    analysis = models.ForeignKey(AiAnalysis, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "ai_conversation_message"
        ordering = ["created_at"]


class CriterionSuggestion(TenantModel):
    """Pré-diagnostic IA d'un critère (Document 4, fonction F) : une proposition, jamais une décision."""

    class Status(models.TextChoices):
        PROPOSEE = "PROPOSEE", "Proposée"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        MODIFIEE = "MODIFIEE", "Modifiée par le conseiller"
        ECARTEE = "ECARTEE", "Écartée"

    diagnostic = models.ForeignKey("diagnostic.Diagnostic", on_delete=models.CASCADE, related_name="suggestions")
    criterion_code = models.CharField(max_length=40)
    proposed_level = models.PositiveSmallIntegerField(null=True, blank=True)
    justification = models.TextField()
    sources = models.JSONField(default=list)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSEE)
    analysis = models.ForeignKey(AiAnalysis, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "criterion_suggestion"
        constraints = [
            models.UniqueConstraint(fields=["diagnostic", "criterion_code"], name="criterion_suggestion_unique"),
            models.CheckConstraint(
                condition=Q(proposed_level__isnull=True) | Q(proposed_level__lte=4), name="suggestion_level_range"
            ),
        ]


class EvaluationRun(TimeStampedModel):
    """Passage du jeu d'évaluation (Document 4, § 12) : données fictives, aucune donnée client."""

    dataset = models.CharField(max_length=60)
    provider = models.CharField(max_length=20)
    models_used = models.JSONField(default=dict)
    prompt_versions = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    thresholds = models.JSONField(default=dict)
    passed = models.BooleanField()
    details = models.JSONField(default=list)

    class Meta:
        db_table = "ai_evaluation_run"
        ordering = ["-created_at"]
