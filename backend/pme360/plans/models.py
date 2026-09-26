"""Recommandations, plans d'accompagnement et actions (Document 3, § 3.6 ; Document 7, § 2 à 7).

Du diagnostic validé au score mis à jour : règles → recommandations notées (Impact × Urgence × Risque × Effort)
→ revue du conseiller → plan versionné (horizons J1–30 à 12 mois) → actions avec dépendances et livrables →
livrables vérifiés → action terminée → critère porté au niveau visé (progrès vérifié) → score courant recalculé.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from pme360.core.models import TenantModel


class DeliverableTemplate(TenantModel):
    """Bibliothèque de livrables (Document 7, § 7) : instructions en langage simple et critères de vérification."""

    code = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30)
    format = models.CharField(max_length=10, help_text="docx, xlsx, pdf…")
    document_type_code = models.CharField(
        max_length=40, help_text="Type de document sous lequel le livrable est déposé."
    )
    instructions = models.TextField(help_text="Comment le remplir, en langage simple.")
    example = models.TextField(blank=True, help_text="Exemple rempli fictif (extrait).")
    verification_criteria = models.JSONField(default=list, help_text="Points contrôlés par le conseiller.")
    file_storage_key = models.CharField(max_length=300, blank=True)
    version = models.CharField(max_length=20, default="1.0")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "deliverable_template"
        ordering = ["category", "title"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="deliverable_template_unique_code")
        ]

    def __str__(self) -> str:
        return self.code


class SupportOffer(TenantModel):
    """Catalogue d'offres d'accompagnement (Document 7, § 3.4)."""

    class Provider(models.TextChoices):
        GUDE = "GUDE", "L'organisation d'accompagnement"
        PARTENAIRE = "PARTENAIRE", "Partenaire"
        PME_SEULE = "PME_SEULE", "PME en autonomie"

    code = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    dimension_code = models.CharField(max_length=10)
    objective = models.TextField()
    description = models.TextField(blank=True)
    typical_duration_days = models.PositiveIntegerField(default=30)
    effort = models.PositiveSmallIntegerField(
        default=2, help_text="1 (< 1 semaine, gratuit) à 5 (> 3 mois ou coûteux)."
    )
    target_criteria = models.JSONField(default=list, help_text="Critères améliorés par l'offre.")
    target_level = models.PositiveSmallIntegerField(default=3, help_text="Niveau visé (indicateur de réussite).")
    deliverables = models.JSONField(default=list, help_text="Codes des modèles de livrables attendus.")
    required_document_types = models.JSONField(default=list)
    sub_actions = models.JSONField(default=list, help_text="Étapes proposées (titres).")
    depends_on = models.JSONField(default=list, help_text="Codes d'offres à terminer d'abord (si elles sont au plan).")
    estimated_cost_min = models.PositiveIntegerField(default=0)
    estimated_cost_max = models.PositiveIntegerField(default=0)
    provider_type = models.CharField(max_length=12, choices=Provider.choices, default=Provider.GUDE)
    is_growth = models.BooleanField(default=False, help_text="Offre de croissance (horizon 12 mois, niveau ≥ N3).")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "support_offer"
        ordering = ["dimension_code", "code"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="support_offer_unique_code")]

    def __str__(self) -> str:
        return self.code

    @property
    def success_indicator(self) -> str:
        return f"{', '.join(self.target_criteria)} au niveau ≥ {self.target_level}" if self.target_criteria else ""


class RecommendationRule(TenantModel):
    """Règle de recommandation « SI … ALORS proposer … » en JSON Logic (Document 7, § 3.1). Versionnée."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    code = models.CharField(max_length=40)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=200)
    condition = models.JSONField()
    offer = models.ForeignKey(SupportOffer, on_delete=models.PROTECT, related_name="rules")
    impact = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Vide : calculé.")
    urgency = models.PositiveSmallIntegerField(null=True, blank=True)
    risk = models.PositiveSmallIntegerField(null=True, blank=True)
    problem_template = models.CharField(max_length=300)
    rationale_template = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    tested_at = models.DateTimeField(null=True, blank=True)
    test_result = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "recommendation_rule"
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code", "version"], name="recommendation_rule_unique"),
            models.UniqueConstraint(
                fields=["organization", "code"], condition=Q(status="ACTIVE"), name="recommendation_rule_one_active"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"


class Recommendation(TenantModel):
    class Source(models.TextChoices):
        REGLE = "REGLE", "Règle"
        IA = "IA", "IA"
        CONSEILLER = "CONSEILLER", "Conseiller"

    class Status(models.TextChoices):
        PROPOSEE = "PROPOSEE", "Proposée"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        REJETEE = "REJETEE", "Rejetée"
        CONVERTIE = "CONVERTIE", "Convertie en action"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="recommendations")
    diagnostic = models.ForeignKey("diagnostic.Diagnostic", on_delete=models.PROTECT, related_name="recommendations")
    offer = models.ForeignKey(SupportOffer, on_delete=models.PROTECT, related_name="recommendations")
    source = models.CharField(max_length=10, choices=Source.choices)
    rules = models.JSONField(default=list, help_text="[{code, version}] des règles ayant proposé l'offre.")
    problem = models.CharField(max_length=300)
    rationale = models.TextField()
    evidence_refs = models.JSONField(default=dict)
    impact = models.PositiveSmallIntegerField()
    urgency = models.PositiveSmallIntegerField()
    risk = models.PositiveSmallIntegerField()
    effort = models.PositiveSmallIntegerField()
    scoring_details = models.JSONField(default=dict, help_text="Comment chaque axe a été proposé.")
    priority_computed = models.DecimalField(max_digits=5, decimal_places=1)
    priority_final = models.DecimalField(max_digits=5, decimal_places=1)
    priority_override_reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSEE)
    decision_reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "recommendation"
        ordering = ["-priority_final"]
        constraints = [
            models.UniqueConstraint(fields=["diagnostic", "offer"], name="recommendation_unique_offer"),
            models.CheckConstraint(
                condition=Q(impact__range=(1, 5)) & Q(urgency__range=(1, 5)), name="recommendation_axes_1"
            ),
            models.CheckConstraint(
                condition=Q(risk__range=(1, 5)) & Q(effort__range=(1, 5)), name="recommendation_axes_2"
            ),
        ]


class ActionPlan(TenantModel):
    class Status(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        EN_VALIDATION = "EN_VALIDATION", "En validation"
        VALIDE = "VALIDE", "Validé"
        EN_COURS = "EN_COURS", "En cours"
        CLOS = "CLOS", "Clos"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="action_plans")
    diagnostic = models.ForeignKey("diagnostic.Diagnostic", on_delete=models.PROTECT, related_name="action_plans")
    title = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.BROUILLON)
    horizon_start = models.DateField()
    capacity = models.PositiveSmallIntegerField(default=5, help_text="Actions simultanées maximum par horizon.")
    submitted_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.TextField(blank=True)

    class Meta:
        db_table = "action_plan"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["pme", "version"], name="action_plan_unique_version"),
            models.UniqueConstraint(
                fields=["pme"],
                condition=Q(status__in=["BROUILLON", "EN_VALIDATION", "VALIDE", "EN_COURS"]),
                name="action_plan_one_open",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} (v{self.version})"


class Action(TenantModel):
    class Status(models.TextChoices):
        BLOQUE = "BLOQUE", "Bloquée (dépendance)"
        NON_COMMENCE = "NON_COMMENCE", "Non commencée"
        EN_COURS = "EN_COURS", "En cours"
        DOCUMENT_DEMANDE = "DOCUMENT_DEMANDE", "Document demandé"
        DOCUMENT_RECU = "DOCUMENT_RECU", "Document reçu"
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        CONFORME = "CONFORME", "Conforme"
        NON_CONFORME = "NON_CONFORME", "Non conforme"
        TERMINE = "TERMINE", "Terminée"
        EN_ATTENTE_PME = "EN_ATTENTE_PME", "En attente de la PME"
        EN_ATTENTE_GUDE = "EN_ATTENTE_GUDE", "En attente de l'organisation"
        ABANDONNE = "ABANDONNE", "Abandonnée"

    TERMINAL = (Status.TERMINE, Status.ABANDONNE)

    class Phase(models.TextChoices):
        J1_30 = "J1_30", "Jours 1–30"
        J31_60 = "J31_60", "Jours 31–60"
        J61_90 = "J61_90", "Jours 61–90"
        M6 = "M6", "6 mois"
        M12 = "M12", "12 mois"

    class Owner(models.TextChoices):
        PME = "PME", "PME"
        GUDE = "GUDE", "L'organisation d'accompagnement"
        PARTENAIRE = "PARTENAIRE", "Partenaire"

    human_ref = models.CharField(max_length=20)
    plan = models.ForeignKey(ActionPlan, on_delete=models.CASCADE, related_name="actions")
    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="actions")
    recommendation = models.ForeignKey(
        Recommendation, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    offer = models.ForeignKey(SupportOffer, null=True, blank=True, on_delete=models.PROTECT, related_name="actions")
    dimension_code = models.CharField(max_length=10)
    target_criteria = models.JSONField(default=list)
    target_level = models.PositiveSmallIntegerField(null=True, blank=True)
    problem = models.CharField(max_length=300)
    objective = models.TextField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    why = models.TextField(blank=True, help_text="Pourquoi cette action, en langage PME.")
    sub_actions = models.JSONField(default=list, help_text="[{title, done}]")
    owner_type = models.CharField(max_length=10, choices=Owner.choices, default=Owner.PME)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    advisor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    priority_score = models.DecimalField(max_digits=5, decimal_places=1)
    phase = models.CharField(max_length=8, choices=Phase.choices)
    position = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField()
    started_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NON_COMMENCE)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    waiting_on = models.CharField(max_length=4, blank=True, help_text="PME | GUDE : partie à qui le retard est imputé.")
    estimated_cost_min = models.PositiveIntegerField(default=0)
    estimated_cost_max = models.PositiveIntegerField(default=0)
    success_indicator = models.CharField(max_length=300, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    abandon_reason = models.TextField(blank=True)
    depends_on = models.ManyToManyField(
        "self", symmetrical=False, blank=True, through="ActionDependency", related_name="dependents"
    )

    class Meta:
        db_table = "action"
        ordering = ["position", "due_date"]
        constraints = [models.UniqueConstraint(fields=["organization", "human_ref"], name="action_unique_ref")]
        indexes = [models.Index(fields=["organization", "pme", "status"], name="action_pme_status_idx")]

    def __str__(self) -> str:
        return self.human_ref


class ActionDependency(TenantModel):
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="dependency_links")
    depends_on_action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="dependent_links")
    kind = models.CharField(max_length=12, default="FIN_DEBUT")

    class Meta:
        db_table = "action_dependency"
        constraints = [
            models.UniqueConstraint(fields=["action", "depends_on_action"], name="action_dependency_unique"),
            models.CheckConstraint(
                condition=~Q(action=models.F("depends_on_action")), name="action_dependency_not_self"
            ),
        ]


class Deliverable(TenantModel):
    class Status(models.TextChoices):
        ATTENDU = "ATTENDU", "Attendu"
        DEPOSE = "DEPOSE", "Déposé"
        A_VERIFIER = "A_VERIFIER", "À vérifier"
        CONFORME = "CONFORME", "Conforme"
        NON_CONFORME = "NON_CONFORME", "Non conforme"

    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="deliverables")
    template = models.ForeignKey(DeliverableTemplate, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    document_type_code = models.CharField(max_length=40)
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="deliverables"
    )
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.ATTENDU)
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "deliverable"
        ordering = ["created_at"]


class Comment(TenantModel):
    """Échange sur une action (Document 3, § 3.6) : interne à l'équipe ou partagé avec la PME. Jamais modifié."""

    class Visibility(models.TextChoices):
        INTERNE_GUDE = "INTERNE_GUDE", "Interne à l'équipe"
        PARTAGE_PME = "PARTAGE_PME", "Partagé avec la PME"

    action = models.ForeignKey("Action", on_delete=models.CASCADE, related_name="comments")
    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="action_comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    visibility = models.CharField(max_length=14, choices=Visibility.choices)

    class Meta:
        db_table = "action_comment"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["organization", "action", "created_at"], name="action_comment_idx")]


class ActionTransition(TenantModel):
    """Journal des transitions d'une action (Document 3, § 3.7 : workflow_transition_log)."""

    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=16)
    to_status = models.CharField(max_length=16)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_type = models.CharField(max_length=10, default="USER")
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "action_transition"
        ordering = ["created_at"]


class CriterionProgress(TenantModel):
    """Progrès vérifié : une action terminée (livrables conformes) porte ses critères au niveau visé.

    Pris en compte par le score courant pour les progrès postérieurs à la validation du diagnostic de référence ;
    un diagnostic ultérieur (revu par un conseiller) le remplace.
    """

    pme = models.ForeignKey("pmes.Pme", on_delete=models.CASCADE, related_name="criterion_progress")
    criterion_code = models.CharField(max_length=20)
    level = models.PositiveSmallIntegerField()
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="progress")
    achieved_at = models.DateTimeField()

    class Meta:
        db_table = "criterion_progress"
        ordering = ["achieved_at"]
        constraints = [models.UniqueConstraint(fields=["action", "criterion_code"], name="criterion_progress_unique")]
