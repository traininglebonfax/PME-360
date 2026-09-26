from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from pme360.documents.serializers import DocumentSerializer

from .models import (
    AiAnalysis,
    Conversation,
    ConversationMessage,
    CriterionSuggestion,
    DocumentExtraction,
    EvaluationRun,
)
from .schemas import EXTRACTION_SCHEMAS


class AiAnalysisSerializer(serializers.ModelSerializer):
    """« Voir l'analyse IA » (Document 4, § 11)."""

    requested_by_name = serializers.CharField(source="requested_by.full_name", read_only=True, default=None)
    pme_name = serializers.CharField(source="pme.legal_name", read_only=True, default=None)

    class Meta:
        model = AiAnalysis
        fields = [
            "id",
            "task",
            "status",
            "pme",
            "pme_name",
            "document_version",
            "diagnostic",
            "provider",
            "model",
            "prompt_code",
            "prompt_version",
            "input_refs",
            "pseudonymized",
            "output",
            "confidence",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "latency_ms",
            "attempts",
            "error",
            "requested_by_name",
            "created_at",
        ]
        read_only_fields = fields


class AiAnalysisSummarySerializer(AiAnalysisSerializer):
    class Meta(AiAnalysisSerializer.Meta):
        fields = [f for f in AiAnalysisSerializer.Meta.fields if f not in ("input_refs", "output")]
        read_only_fields = fields


class ExtractionFieldSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()
    critical = serializers.BooleanField()
    value = serializers.JSONField(allow_null=True)
    confidence = serializers.FloatField(allow_null=True)
    corrected = serializers.BooleanField()


class ExtractionSerializer(serializers.ModelSerializer):
    fields_detail = serializers.SerializerMethodField()
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)
    version_no = serializers.IntegerField(source="version.version_no", read_only=True)

    class Meta:
        model = DocumentExtraction
        fields = [
            "id",
            "version_no",
            "status",
            "reason",
            "expected_type",
            "classified_type",
            "classification_confidence",
            "schema_code",
            "schema_version",
            "confidence",
            "fields_detail",
            "classification_analysis",
            "extraction_analysis",
            "corrections",
            "review_comment",
            "reviewed_by_name",
            "reviewed_at",
        ]
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(ExtractionFieldSerializer(many=True))
    def get_fields_detail(extraction) -> list[dict]:
        schema = EXTRACTION_SCHEMAS.get(extraction.schema_code)
        if schema is None:
            return []
        return ExtractionFieldSerializer(
            [
                {
                    "name": f.name,
                    "label": f.label,
                    "type": f.type,
                    "critical": f.critical,
                    "value": extraction.data.get(f.name),
                    "confidence": extraction.field_confidence.get(f.name),
                    "corrected": f.name in extraction.corrections,
                }
                for f in schema.fields
            ],
            many=True,
        ).data


class ExtractionReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[s.value for s in DocumentExtraction.REVIEWED])
    corrections = serializers.DictField(child=serializers.JSONField(allow_null=True), required=False, default=dict)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class AiQueueSummarySerializer(serializers.Serializer):
    status = serializers.CharField()
    confidence = serializers.FloatField(allow_null=True)
    classified_type = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    anomalies = serializers.IntegerField()
    max_severity = serializers.CharField(allow_null=True)


class QueueItemSerializer(DocumentSerializer):
    ai = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = [*DocumentSerializer.Meta.fields, "ai"]
        read_only_fields = fields

    @extend_schema_field(AiQueueSummarySerializer(allow_null=True))
    def get_ai(self, document) -> dict | None:
        summary = self.context.get("ai", {}).get(document.pk)
        return AiQueueSummarySerializer(summary).data if summary else None


class SuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriterionSuggestion
        fields = [
            "id",
            "criterion_code",
            "proposed_level",
            "justification",
            "sources",
            "confidence",
            "status",
            "analysis",
        ]
        read_only_fields = fields


class AiSettingsSerializer(serializers.Serializer):
    external_allowed = serializers.BooleanField()
    monthly_token_quota = serializers.IntegerField(min_value=0)
    auto_threshold = serializers.FloatField(min_value=0.5, max_value=1)
    field_threshold = serializers.FloatField(min_value=0.5, max_value=1)


class AiUsageSerializer(serializers.Serializer):
    tokens = serializers.IntegerField()
    cost_usd = serializers.FloatField()
    since = serializers.DateField()
    by_task = serializers.ListField(child=serializers.DictField())


class AiSettingsPayloadSerializer(AiSettingsSerializer):
    provider = serializers.CharField()
    provider_configured = serializers.BooleanField()
    models = serializers.DictField(child=serializers.CharField())
    prompts = serializers.DictField(child=serializers.CharField())
    local_engine = serializers.CharField()
    usage = AiUsageSerializer()


class FinancialStatementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    fiscal_year_end = serializers.DateField()
    system = serializers.CharField()
    status = serializers.CharField()
    values = serializers.DictField(child=serializers.FloatField())
    confidence = serializers.FloatField(allow_null=True)
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    verified_at = serializers.DateTimeField(allow_null=True)


class FinancialMetricSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    formula = serializers.CharField()
    unit = serializers.CharField()
    value = serializers.FloatField(allow_null=True)
    display = serializers.CharField()
    band = serializers.CharField(allow_null=True)
    points = serializers.FloatField(allow_null=True)
    confidence = serializers.FloatField()
    sources = serializers.ListField(child=serializers.CharField())
    inputs = serializers.DictField(child=serializers.FloatField(allow_null=True))
    missing = serializers.CharField(required=False)


class FinancialAnalysisSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    statements = FinancialStatementSerializer(many=True)
    metrics = FinancialMetricSerializer(many=True)


class InterpretationPointSerializer(serializers.Serializer):
    metric = serializers.CharField()
    comment = serializers.CharField()
    tone = serializers.CharField()


class InterpretationSerializer(serializers.Serializer):
    summary = serializers.CharField()
    points = InterpretationPointSerializer(many=True)
    limits = serializers.ListField(child=serializers.CharField())
    analysis_id = serializers.UUIDField()
    provider = serializers.CharField()
    draft = serializers.BooleanField()


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "role", "content", "sources", "confidence", "limits", "tool_calls", "analysis", "created_at"]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    pme_name = serializers.CharField(source="pme.legal_name", read_only=True, default=None)

    class Meta:
        model = Conversation
        fields = ["id", "title", "pme", "pme_name", "created_at", "updated_at"]
        read_only_fields = fields


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = [*ConversationSerializer.Meta.fields, "messages"]
        read_only_fields = fields


class ConversationCreateSerializer(serializers.Serializer):
    pme_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class QuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)


class EvaluationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationRun
        fields = [
            "id",
            "dataset",
            "provider",
            "models_used",
            "prompt_versions",
            "metrics",
            "thresholds",
            "passed",
            "created_at",
        ]
        read_only_fields = fields


class ReindexSerializer(serializers.Serializer):
    referentiel = serializers.IntegerField()
    reglementation = serializers.IntegerField()
    documents = serializers.IntegerField()
    historique = serializers.IntegerField()
