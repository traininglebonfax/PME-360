from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    Action,
    ActionPlan,
    ActionTransition,
    Comment,
    Deliverable,
    DeliverableTemplate,
    Recommendation,
    RecommendationRule,
    SupportOffer,
)


class DeliverableTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliverableTemplate
        fields = [
            "id",
            "code",
            "title",
            "category",
            "format",
            "document_type_code",
            "instructions",
            "example",
            "verification_criteria",
            "version",
            "is_active",
        ]
        read_only_fields = fields


class SupportOfferSerializer(serializers.ModelSerializer):
    provider_label = serializers.CharField(source="get_provider_type_display", read_only=True)
    success_indicator = serializers.CharField(read_only=True)

    class Meta:
        model = SupportOffer
        fields = [
            "id",
            "code",
            "title",
            "dimension_code",
            "objective",
            "description",
            "typical_duration_days",
            "effort",
            "target_criteria",
            "target_level",
            "deliverables",
            "required_document_types",
            "sub_actions",
            "depends_on",
            "estimated_cost_min",
            "estimated_cost_max",
            "provider_type",
            "provider_label",
            "is_growth",
            "is_active",
            "success_indicator",
        ]
        read_only_fields = fields


class OfferRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportOffer
        fields = ["id", "code", "title", "dimension_code", "typical_duration_days", "target_criteria", "target_level"]
        read_only_fields = fields


class RecommendationSerializer(serializers.ModelSerializer):
    offer = OfferRefSerializer(read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)
    priority_computed = serializers.FloatField(read_only=True)
    priority_final = serializers.FloatField(read_only=True)

    class Meta:
        model = Recommendation
        fields = [
            "id",
            "diagnostic",
            "offer",
            "source",
            "rules",
            "problem",
            "rationale",
            "evidence_refs",
            "impact",
            "urgency",
            "risk",
            "effort",
            "scoring_details",
            "priority_computed",
            "priority_final",
            "priority_override_reason",
            "status",
            "decision_reason",
            "decided_by_name",
            "decided_at",
        ]
        read_only_fields = fields


class RecommendationDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["PROPOSEE", "ACCEPTEE", "REJETEE"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    impact = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    urgency = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    risk = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    effort = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    priority_reason = serializers.CharField(required=False, allow_blank=True, default="")


class ManualRecommendationSerializer(serializers.Serializer):
    offer_code = serializers.CharField()
    problem = serializers.CharField(max_length=300)
    rationale = serializers.CharField()


class DeliverableSerializer(serializers.ModelSerializer):
    template = DeliverableTemplateSerializer(read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True, default=None)

    class Meta:
        model = Deliverable
        fields = ["id", "title", "document_type_code", "status", "reason", "document", "document_title", "template"]
        read_only_fields = fields


class ActionRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Action
        fields = ["id", "human_ref", "title", "status"]
        read_only_fields = fields


class ActionSerializer(serializers.ModelSerializer):
    priority_score = serializers.FloatField(read_only=True)
    advisor_name = serializers.CharField(source="advisor_user.full_name", read_only=True, default=None)
    owner_name = serializers.CharField(source="owner_user.full_name", read_only=True, default=None)
    offer_code = serializers.CharField(source="offer.code", read_only=True, default=None)
    pme_name = serializers.CharField(source="pme.legal_name", read_only=True)
    depends_on = serializers.SerializerMethodField()
    deliverables_total = serializers.SerializerMethodField()
    deliverables_conform = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Action
        fields = [
            "id",
            "human_ref",
            "plan",
            "pme",
            "pme_name",
            "offer_code",
            "dimension_code",
            "target_criteria",
            "target_level",
            "problem",
            "objective",
            "title",
            "why",
            "sub_actions",
            "owner_type",
            "owner_name",
            "advisor_name",
            "priority_score",
            "phase",
            "position",
            "start_date",
            "due_date",
            "started_at",
            "status",
            "waiting_on",
            "estimated_cost_min",
            "estimated_cost_max",
            "success_indicator",
            "completed_at",
            "abandon_reason",
            "depends_on",
            "deliverables_total",
            "deliverables_conform",
            "overdue",
        ]
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(ActionRefSerializer(many=True))
    def get_depends_on(action) -> list[dict]:
        return ActionRefSerializer([link.depends_on_action for link in action.dependency_links.all()], many=True).data

    @staticmethod
    def get_deliverables_total(action) -> int:
        return len(action.deliverables.all())

    @staticmethod
    def get_deliverables_conform(action) -> int:
        return sum(1 for d in action.deliverables.all() if d.status == Deliverable.Status.CONFORME)

    def get_overdue(self, action) -> bool:
        today = self.context.get("today")
        return bool(today and action.due_date < today and action.status not in (*Action.TERMINAL, Action.Status.BLOQUE))


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    author_is_pme = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "body", "visibility", "author_name", "author_is_pme", "created_at"]
        read_only_fields = fields

    @staticmethod
    def get_author_is_pme(comment) -> bool:
        return comment.author.memberships.filter(role__is_pme_role=True).exists()


class CommentWriteSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)
    visibility = serializers.ChoiceField(choices=Comment.Visibility.choices, required=False, default="INTERNE_GUDE")


class TransitionSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)

    class Meta:
        model = ActionTransition
        fields = ["id", "from_status", "to_status", "actor_name", "actor_type", "reason", "created_at"]
        read_only_fields = fields


class ActionDetailSerializer(ActionSerializer):
    deliverables = DeliverableSerializer(many=True, read_only=True)
    transitions = TransitionSerializer(many=True, read_only=True)
    dependents = serializers.SerializerMethodField()
    rationale = serializers.CharField(source="recommendation.rationale", read_only=True, default=None)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta(ActionSerializer.Meta):
        fields = [
            *ActionSerializer.Meta.fields,
            "deliverables",
            "transitions",
            "dependents",
            "rationale",
            "allowed_transitions",
        ]
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(ActionRefSerializer(many=True))
    def get_dependents(action) -> list[dict]:
        return ActionRefSerializer([link.action for link in action.dependent_links.all()], many=True).data

    @extend_schema_field(serializers.ListField(child=serializers.ChoiceField(choices=Action.Status.choices)))
    def get_allowed_transitions(self, action) -> list[str]:
        from .services import MANUAL, PME_ALLOWED

        allowed = sorted(MANUAL.get(action.status, set()))
        access = self.context.get("access")
        if access is not None and access.is_pme_user:
            allowed = [s for s in allowed if s in PME_ALLOWED]
        return allowed


class ActionUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    start_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    phase = serializers.ChoiceField(choices=Action.Phase.choices, required=False)
    owner_type = serializers.ChoiceField(choices=Action.Owner.choices, required=False)
    sub_actions = serializers.ListField(child=serializers.DictField(), required=False)


class ActionTransitionRequestSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=Action.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class DependencyRequestSerializer(serializers.Serializer):
    depends_on = serializers.UUIDField()


class PlanSerializer(serializers.ModelSerializer):
    accepted_offline = serializers.SerializerMethodField()
    validated_by_name = serializers.CharField(source="validated_by.full_name", read_only=True, default=None)
    accepted_by_name = serializers.CharField(source="accepted_by.full_name", read_only=True, default=None)
    pme_name = serializers.CharField(source="pme.legal_name", read_only=True)

    class Meta:
        model = ActionPlan
        fields = [
            "id",
            "pme",
            "pme_name",
            "diagnostic",
            "title",
            "version",
            "status",
            "horizon_start",
            "capacity",
            "submitted_at",
            "validated_by_name",
            "validated_at",
            "accepted_by_name",
            "accepted_at",
            "accepted_offline",
            "closed_at",
            "close_reason",
            "created_at",
        ]
        read_only_fields = fields

    @staticmethod
    def get_accepted_offline(plan) -> bool:
        """Acceptation enregistrée par l'équipe (PME sans accès au portail)."""
        return bool(plan.accepted_by_id) and not plan.accepted_by.memberships.filter(role__is_pme_role=True).exists()


class PlanProgressSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    done = serializers.IntegerField()
    rate = serializers.FloatField(allow_null=True)


class PlanDetailSerializer(PlanSerializer):
    actions = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta(PlanSerializer.Meta):
        fields = [*PlanSerializer.Meta.fields, "actions", "progress"]
        read_only_fields = fields

    @extend_schema_field(ActionSerializer(many=True))
    def get_actions(self, plan) -> list[dict]:
        actions = plan.actions.select_related("offer", "advisor_user", "owner_user", "pme").prefetch_related(
            "deliverables", "dependency_links__depends_on_action"
        )
        return ActionSerializer(actions, many=True, context=self.context).data

    @staticmethod
    @extend_schema_field(PlanProgressSerializer)
    def get_progress(plan) -> dict:
        statuses = list(plan.actions.values_list("status", flat=True))
        done = sum(1 for s in statuses if s == Action.Status.TERMINE)
        counted = [s for s in statuses if s != Action.Status.ABANDONNE]
        return {"total": len(statuses), "done": done, "rate": round(done / len(counted), 3) if counted else None}


class PlanGenerateSerializer(serializers.Serializer):
    horizon_start = serializers.DateField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class PlanTransitionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "validate", "accept", "accept_offline", "reopen", "close"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PlanReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class RuleSerializer(serializers.ModelSerializer):
    offer_code = serializers.CharField(source="offer.code", read_only=True)
    offer_title = serializers.CharField(source="offer.title", read_only=True)
    condition_text = serializers.SerializerMethodField()
    problem_readable = serializers.SerializerMethodField()
    rationale_readable = serializers.SerializerMethodField()
    editable_visually = serializers.SerializerMethodField()

    def _labels(self) -> dict:
        from .rule_labels import labels

        if "labels" not in self.context:
            self.context["labels"] = labels()
        return self.context["labels"]

    def get_condition_text(self, rule) -> str:
        from .rule_labels import describe

        return describe(rule.condition, self._labels())

    def get_problem_readable(self, rule) -> str:
        from .rule_labels import readable_template

        return readable_template(rule.problem_template, self._labels())

    def get_rationale_readable(self, rule) -> str:
        from .rule_labels import readable_template

        return readable_template(rule.rationale_template, self._labels())

    @staticmethod
    def get_editable_visually(rule) -> bool:
        from .rule_labels import is_simple

        return is_simple(rule.condition)

    class Meta:
        model = RecommendationRule
        fields = [
            "id",
            "code",
            "version",
            "name",
            "condition",
            "condition_text",
            "editable_visually",
            "offer_code",
            "offer_title",
            "impact",
            "urgency",
            "risk",
            "problem_template",
            "rationale_template",
            "problem_readable",
            "rationale_readable",
            "status",
            "tested_at",
            "test_result",
            "created_at",
        ]
        read_only_fields = fields


class RuleWriteSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Z0-9\-]{3,40}$")
    name = serializers.CharField(max_length=200)
    condition = serializers.JSONField()
    offer_code = serializers.CharField()
    impact = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    urgency = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    risk = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    problem_template = serializers.CharField(max_length=300)
    rationale_template = serializers.CharField()


class RuleVariableSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    type = serializers.ChoiceField(choices=["score", "level", "boolean", "rate", "count", "maturity"])
    group = serializers.CharField()


class RuleTestResultSerializer(serializers.Serializer):
    evaluated = serializers.IntegerField()
    matched = serializers.ListField(child=serializers.DictField())
