from rest_framework import serializers

from pme360.scoring.models import ScoreSnapshot

from .models import (
    Criterion,
    CriterionAssessment,
    Diagnostic,
    Dimension,
    FrameworkVersion,
    MetricDefinition,
    Pillar,
    Question,
)


class NamedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class FrameworkVersionSerializer(serializers.ModelSerializer):
    framework_code = serializers.CharField(source="framework.code", read_only=True)
    framework_name = serializers.CharField(source="framework.name", read_only=True)
    published_by_name = serializers.CharField(source="published_by.full_name", read_only=True, default=None)

    class Meta:
        model = FrameworkVersion
        fields = [
            "id",
            "framework_code",
            "framework_name",
            "version",
            "status",
            "published_at",
            "published_by_name",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class MetricDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricDefinition
        fields = ["code", "name", "formula", "formula_label", "unit", "bands", "weight"]
        read_only_fields = fields


class CriterionSerializer(serializers.ModelSerializer):
    metrics = MetricDefinitionSerializer(many=True, read_only=True)
    rubric = serializers.ListField(child=serializers.CharField(), read_only=True)
    evidence_document_types = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Criterion
        fields = [
            "code",
            "name",
            "lens",
            "weight",
            "is_critical",
            "rubric",
            "declarative_cap_level",
            "applicability",
            "evidence_policy",
            "evidence_document_types",
            "sector_module",
            "metrics",
        ]
        read_only_fields = fields


class DimensionSerializer(serializers.ModelSerializer):
    pillar = serializers.CharField(source="pillar.code", read_only=True)
    criteria = CriterionSerializer(many=True, read_only=True)

    class Meta:
        model = Dimension
        fields = ["code", "name", "short_name", "description", "pillar", "weight", "sector_module_share", "criteria"]
        read_only_fields = fields


class PillarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pillar
        fields = ["code", "name", "weight"]
        read_only_fields = fields


class FrameworkVersionDetailSerializer(FrameworkVersionSerializer):
    pillars = serializers.SerializerMethodField()
    dimensions = serializers.SerializerMethodField()
    settings = serializers.JSONField(read_only=True)

    class Meta(FrameworkVersionSerializer.Meta):
        fields = [*FrameworkVersionSerializer.Meta.fields, "pillars", "dimensions", "settings"]
        read_only_fields = fields

    def get_pillars(self, obj) -> PillarSerializer(many=True):
        return PillarSerializer(Pillar.objects.filter(framework_version=obj).order_by("order"), many=True).data

    def get_dimensions(self, obj) -> DimensionSerializer(many=True):
        dimensions = (
            Dimension.objects.filter(framework_version=obj)
            .select_related("pillar")
            .prefetch_related("criteria__metrics")
            .order_by("order")
        )
        return DimensionSerializer(dimensions, many=True).data


class CloneSerializer(serializers.Serializer):
    version = serializers.RegexField(r"^\d+\.\d+\.\d+$", max_length=20)


class DiagnosticSerializer(serializers.ModelSerializer):
    pme = NamedRefSerializer(read_only=True, source="pme_ref")
    framework_version = serializers.CharField(source="framework_version.version", read_only=True)
    validated_by_name = serializers.CharField(source="validated_by.full_name", read_only=True, default=None)
    lead_advisor_name = serializers.CharField(source="lead_advisor.full_name", read_only=True, default=None)
    snapshot_id = serializers.SerializerMethodField()

    class Meta:
        model = Diagnostic
        fields = [
            "id",
            "pme",
            "type",
            "status",
            "reference_date",
            "framework_version",
            "submitted_at",
            "validated_at",
            "validated_by_name",
            "lead_advisor_name",
            "cancel_reason",
            "created_at",
            "snapshot_id",
        ]
        read_only_fields = fields

    def get_snapshot_id(self, obj) -> str | None:
        snapshot = ScoreSnapshot.objects.filter(diagnostic=obj).values_list("pk", flat=True).first()
        return str(snapshot) if snapshot else None


class StartDiagnosticSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Diagnostic.Type.choices)
    reference_date = serializers.DateField(required=False)


class OptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    level = serializers.IntegerField(required=False)


class QuestionnaireQuestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    text = serializers.CharField()
    help_text = serializers.CharField(allow_blank=True)
    why_text = serializers.CharField(allow_blank=True)
    type = serializers.ChoiceField(choices=Question.Type.choices)
    required = serializers.BooleanField()
    options = OptionSerializer(many=True)
    value = serializers.JSONField(allow_null=True)
    answered = serializers.BooleanField()
    source = serializers.CharField(allow_null=True)
    evidence_hint = serializers.CharField(allow_blank=True)
    criterion = serializers.CharField(allow_null=True)
    is_critical = serializers.BooleanField()


class QuestionnaireStepSerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    questions = QuestionnaireQuestionSerializer(many=True)


class ProgressSerializer(serializers.Serializer):
    required = serializers.IntegerField()
    required_answered = serializers.IntegerField()
    answered = serializers.IntegerField()
    completion = serializers.FloatField()
    submit_threshold = serializers.FloatField()


class QuestionnaireSerializer(serializers.Serializer):
    diagnostic = DiagnosticSerializer()
    editable = serializers.BooleanField()
    progress = ProgressSerializer()
    steps = QuestionnaireStepSerializer(many=True)


class AnswerItemSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=40)
    value = serializers.JSONField(allow_null=True)


class AnswerBatchSerializer(serializers.Serializer):
    answers = AnswerItemSerializer(many=True, allow_empty=False, max_length=200)


class AnswerBatchResultSerializer(serializers.Serializer):
    changed = serializers.IntegerField()
    progress = ProgressSerializer()


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class ReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CriterionAssessment.Status.choices)
    level_final = serializers.IntegerField(min_value=0, max_value=4, required=False, allow_null=True)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    corroborated = serializers.BooleanField(default=False)


class AssessmentSerializer(serializers.ModelSerializer):
    criterion = serializers.CharField(source="criterion.code", read_only=True)
    reviewer_name = serializers.CharField(source="reviewer.full_name", read_only=True)

    class Meta:
        model = CriterionAssessment
        fields = [
            "criterion",
            "status",
            "level_declared",
            "level_final",
            "corroborated",
            "comment",
            "reviewer_name",
            "reviewed_at",
        ]
        read_only_fields = fields


class ReviewSuggestionSerializer(serializers.Serializer):
    """Proposition du pré-diagnostic IA (Document 4, fonction F) : jamais une décision."""

    id = serializers.UUIDField()
    proposed_level = serializers.IntegerField(allow_null=True)
    justification = serializers.CharField()
    sources = serializers.ListField(child=serializers.CharField())
    confidence = serializers.FloatField()
    status = serializers.CharField()
    analysis = serializers.UUIDField(allow_null=True, source="analysis_id")


class ReviewCriterionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    dimension = serializers.CharField()
    lens = serializers.CharField()
    is_critical = serializers.BooleanField()
    evidence_policy = serializers.CharField()
    rubric = serializers.ListField(child=serializers.CharField())
    result = serializers.JSONField()
    answers = serializers.JSONField()
    assessment = AssessmentSerializer(allow_null=True)
    suggestion = ReviewSuggestionSerializer(allow_null=True)


class ReviewDimensionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    result = serializers.JSONField()
    criteria = ReviewCriterionSerializer(many=True)


class ReviewPayloadSerializer(serializers.Serializer):
    diagnostic = DiagnosticSerializer()
    preview = serializers.JSONField()
    pending = serializers.ListField(child=serializers.CharField())
    dimensions = ReviewDimensionSerializer(many=True)


class AcceptResultSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
