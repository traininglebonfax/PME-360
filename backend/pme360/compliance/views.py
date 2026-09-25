from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.diagnostic.views import scoped_pme
from pme360.documents.serializers import DocumentSerializer, PmeRefSerializer
from pme360.pmes.models import Pme

from . import services
from .models import Deadline, ObligationTemplate, RegulatoryRule


class DeadlineSerializer(serializers.ModelSerializer):
    obligation = serializers.CharField(source="pme_obligation.template.name", read_only=True)
    obligation_code = serializers.CharField(source="pme_obligation.template.code", read_only=True)
    nature = serializers.CharField(source="pme_obligation.template.nature", read_only=True)
    is_critical = serializers.BooleanField(source="pme_obligation.template.is_critical", read_only=True)
    document_type = serializers.CharField(source="pme_obligation.template.document_type.code", read_only=True)
    document_type_name = serializers.CharField(source="pme_obligation.template.document_type.name", read_only=True)
    pme = serializers.SerializerMethodField()
    days_to_due = serializers.SerializerMethodField()

    class Meta:
        model = Deadline
        fields = [
            "id",
            "pme",
            "obligation",
            "obligation_code",
            "nature",
            "is_critical",
            "document_type",
            "document_type_name",
            "period_label",
            "period_start",
            "period_end",
            "due_date",
            "days_to_due",
            "status",
            "closed_at",
        ]
        read_only_fields = fields

    def get_pme(self, obj) -> PmeRefSerializer:
        return {"id": str(obj.pme_id), "name": obj.pme.legal_name}

    def get_days_to_due(self, obj) -> int:
        return (obj.due_date - timezone.localdate()).days


class RateSerializer(serializers.Serializer):
    rate = serializers.FloatField(allow_null=True)
    eligible = serializers.IntegerField()
    points = serializers.FloatField()
    counts = serializers.DictField(child=serializers.IntegerField())


class FolderItemSerializer(serializers.Serializer):
    document_type = serializers.DictField()
    required = serializers.BooleanField()
    criteria = serializers.ListField(child=serializers.CharField())
    obligation = serializers.CharField(allow_null=True)
    state = serializers.CharField()
    documents = DocumentSerializer(many=True)


class FolderCategorySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    items = FolderItemSerializer(many=True)


class ComplianceFolderSerializer(serializers.Serializer):
    rate = RateSerializer()
    categories = FolderCategorySerializer(many=True)


def deadline_queryset():
    return Deadline.objects.select_related("pme", "pme_obligation__template__document_type")


class ComplianceFolderView(APIView):
    """Dossier numérique de conformité (Document 8, § 3) et taux de conformité documentaire (§ 6)."""

    required_permissions = "pme.view"

    @extend_schema(responses=ComplianceFolderSerializer)
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        payload = {"rate": services.compliance_rate(pme), "categories": services.compliance_folder(pme)}
        return Response(ComplianceFolderSerializer(payload).data)


class PmeDeadlinesView(APIView):
    required_permissions = "pme.view"

    @extend_schema(
        parameters=[OpenApiParameter("scope", str, enum=["open", "all"])], responses=DeadlineSerializer(many=True)
    )
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        deadlines = deadline_queryset().filter(pme=pme)
        if request.query_params.get("scope", "open") == "open":
            deadlines = deadlines.filter(
                status__in=[
                    *Deadline.OPEN,
                    Deadline.Status.RECU,
                    Deadline.Status.EN_ANALYSE,
                    Deadline.Status.VERIF_HUMAINE_REQUISE,
                ]
            )
        return Response(DeadlineSerializer(deadlines.order_by("due_date"), many=True).data)


class UpcomingDeadlinesView(APIView):
    """Échéances du périmètre (tableau de bord conseiller) : en retard et à venir."""

    required_permissions = "pme.view"

    @extend_schema(parameters=[OpenApiParameter("days", int)], responses=DeadlineSerializer(many=True))
    def get(self, request):
        pmes = get_access(request).pme_queryset(Pme.objects.all())
        horizon = timezone.localdate() + timedelta(days=int(request.query_params.get("days", 30)))
        deadlines = deadline_queryset().filter(pme__in=pmes, due_date__lte=horizon, status__in=Deadline.OPEN)
        return Response(DeadlineSerializer(deadlines.order_by("due_date")[:200], many=True).data)


class WaiveSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class DeadlineWaiveView(APIView):
    required_permissions = "document.verify"

    @extend_schema(request=WaiveSerializer, responses=DeadlineSerializer)
    def post(self, request, deadline_id):
        pmes = get_access(request).pme_queryset(Pme.objects.all())
        deadline = get_object_or_404(deadline_queryset().filter(pme__in=pmes), pk=deadline_id)
        serializer = WaiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            DeadlineSerializer(services.waive(deadline, serializer.validated_data["reason"], request.user)).data
        )


# --- Registre réglementaire et obligations (administration) ---------------------------------------------------


class RegulatoryRuleSerializer(serializers.ModelSerializer):
    verified_by_name = serializers.CharField(source="verified_by.full_name", read_only=True, default=None)
    sources = serializers.ListField(child=serializers.DictField(child=serializers.CharField()), read_only=True)
    obligations = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = RegulatoryRule
        fields = [
            "id",
            "code",
            "title",
            "content",
            "authority",
            "sources",
            "source_reference",
            "status",
            "verified_at",
            "verified_by_name",
            "verification_note",
            "review_due_at",
            "obligations",
        ]
        read_only_fields = fields


class ObligationTemplateSerializer(serializers.ModelSerializer):
    document_type = serializers.CharField(source="document_type.code", read_only=True)
    document_type_name = serializers.CharField(source="document_type.name", read_only=True)
    regulatory_rule = serializers.CharField(source="regulatory_rule.code", read_only=True, default=None)
    regulatory_status = serializers.CharField(source="regulatory_rule.status", read_only=True, default=None)
    reminder_offsets = serializers.ListField(child=serializers.IntegerField(), read_only=True)
    pmes = serializers.SerializerMethodField()

    class Meta:
        model = ObligationTemplate
        fields = [
            "id",
            "code",
            "name",
            "description",
            "nature",
            "document_type",
            "document_type_name",
            "regulatory_rule",
            "regulatory_status",
            "frequency",
            "frequency_rule",
            "due_days_after_period_end",
            "applicability",
            "reminder_offsets",
            "is_critical",
            "is_active",
            "pmes",
        ]
        read_only_fields = fields

    def get_pmes(self, obj) -> int:
        return obj.pme_obligations.count()


class VerifyRuleSerializer(serializers.Serializer):
    source_reference = serializers.CharField(max_length=250)
    verified_at = serializers.DateField()
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class RuleStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c for c in RegulatoryRule.Status.choices if c[0] != "VERIFIE"])
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class RegulatoryRuleListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=RegulatoryRuleSerializer(many=True))
    def get(self, request):
        rules = RegulatoryRule.objects.select_related("verified_by").prefetch_related("obligations")
        return Response(RegulatoryRuleSerializer(rules, many=True).data)


class RegulatoryRuleVerifyView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=VerifyRuleSerializer, responses=RegulatoryRuleSerializer)
    def post(self, request, rule_id):
        rule = get_object_or_404(RegulatoryRule, pk=rule_id)
        serializer = VerifyRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            RegulatoryRuleSerializer(services.verify_rule(rule, request.user, **serializer.validated_data)).data
        )


class RegulatoryRuleStatusView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=RuleStatusSerializer, responses=RegulatoryRuleSerializer)
    def post(self, request, rule_id):
        rule = get_object_or_404(RegulatoryRule, pk=rule_id)
        serializer = RuleStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(RegulatoryRuleSerializer(services.set_rule_status(rule, data["status"], data["note"])).data)


class ObligationTemplateListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=ObligationTemplateSerializer(many=True))
    def get(self, request):
        templates = ObligationTemplate.objects.select_related("document_type", "regulatory_rule")
        return Response(ObligationTemplateSerializer(templates, many=True).data)


class ActivationSerializer(serializers.Serializer):
    active = serializers.BooleanField()


class ObligationTemplateActivationView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=ActivationSerializer, responses=ObligationTemplateSerializer)
    def post(self, request, template_id):
        template = get_object_or_404(ObligationTemplate.objects.select_related("regulatory_rule"), pk=template_id)
        serializer = ActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            ObligationTemplateSerializer(
                services.set_template_active(template, serializer.validated_data["active"])
            ).data
        )


class RunResultSerializer(serializers.Serializer):
    pmes = serializers.IntegerField()
    obligations = serializers.IntegerField()
    deadlines_created = serializers.IntegerField()
    reminders = serializers.IntegerField()


class ComplianceRunView(APIView):
    """Exécute immédiatement le planificateur quotidien pour l'organisation (administration, démonstration)."""

    required_permissions = "org.configure"

    @extend_schema(request=None, responses=RunResultSerializer)
    def post(self, request):
        totals = {"pmes": 0, "obligations": 0, "deadlines_created": 0, "reminders": 0}
        today = timezone.localdate()
        for pme in Pme.objects.exclude(lifecycle_status=Pme.LifecycleStatus.SORTIE):
            stats = services.run_for_pme(pme, today)
            totals["pmes"] += 1
            for key in ("obligations", "deadlines_created", "reminders"):
                totals[key] += stats[key]
        return Response(totals)
