from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.documents.serializers import PmeRefSerializer
from pme360.pmes.models import Pme

from . import engine
from .models import Alert, AlertRule, Severity


class AlertSerializer(serializers.ModelSerializer):
    rule = serializers.CharField(source="rule.code", read_only=True)
    kind = serializers.CharField(source="rule.kind", read_only=True)
    pme = serializers.SerializerMethodField()
    resolved_by_name = serializers.CharField(source="resolved_by.full_name", read_only=True, default=None)

    class Meta:
        model = Alert
        fields = [
            "id",
            "pme",
            "rule",
            "kind",
            "severity",
            "title",
            "message",
            "details",
            "target_type",
            "target_id",
            "status",
            "created_at",
            "resolved_at",
            "resolved_by_name",
            "resolution_note",
        ]
        read_only_fields = fields

    def get_pme(self, obj) -> PmeRefSerializer:
        return {"id": str(obj.pme_id), "name": obj.pme.legal_name}


class AlertTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[Alert.Status.PRISE_EN_COMPTE, Alert.Status.RESOLUE, Alert.Status.IGNOREE])
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class AlertRuleSerializer(serializers.ModelSerializer):
    recipients = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = AlertRule
        fields = [
            "id",
            "code",
            "kind",
            "name",
            "description",
            "severity",
            "params",
            "recipients",
            "is_active",
            "available_in_phase",
        ]
        read_only_fields = ["id", "code", "kind", "name", "description", "recipients", "available_in_phase"]


SEVERITY_RANK = {s: i for i, s in enumerate(["INFO", "MOYENNE", "ELEVEE", "CRITIQUE"])}


class AlertListView(APIView):
    """Alertes des PME du périmètre (équipes GUDE-PME)."""

    required_permissions = "pme.view"

    @extend_schema(
        parameters=[
            OpenApiParameter("pme", str),
            OpenApiParameter("status", str, enum=["open", "all"]),
            OpenApiParameter("min_severity", str, enum=list(Severity.values)),
        ],
        responses=AlertSerializer(many=True),
    )
    def get(self, request):
        access = get_access(request)
        if access.is_pme_user:
            raise PermissionDenied("Les alertes sont destinées aux équipes d'accompagnement.")
        alerts = Alert.objects.filter(pme__in=access.pme_queryset(Pme.objects.all())).select_related(
            "pme", "rule", "resolved_by"
        )
        if pme := request.query_params.get("pme"):
            alerts = alerts.filter(pme_id=pme)
        if request.query_params.get("status", "open") == "open":
            alerts = alerts.filter(status__in=Alert.OPEN)
        if minimum := request.query_params.get("min_severity"):
            alerts = alerts.filter(
                severity__in=[s for s, rank in SEVERITY_RANK.items() if rank >= SEVERITY_RANK.get(minimum, 0)]
            )
        ordered = sorted(alerts[:500], key=lambda a: (-SEVERITY_RANK[a.severity], -a.created_at.timestamp()))
        return Response(AlertSerializer(ordered, many=True).data)


class AlertTransitionView(APIView):
    required_permissions = "pme.view"

    @extend_schema(request=AlertTransitionSerializer, responses=AlertSerializer)
    def post(self, request, alert_id):
        access = get_access(request)
        if access.is_pme_user:
            raise PermissionDenied()
        alert = get_object_or_404(Alert.objects.filter(pme__in=access.pme_queryset(Pme.objects.all())), pk=alert_id)
        serializer = AlertTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        engine.transition(alert, serializer.validated_data["status"], request.user, serializer.validated_data["note"])
        return Response(AlertSerializer(alert).data)


class AlertRuleListView(APIView):
    required_permissions = {"GET": "pme.view"}

    @extend_schema(responses=AlertRuleSerializer(many=True))
    def get(self, request):
        return Response(AlertRuleSerializer(AlertRule.objects.all(), many=True).data)


class AlertRuleDetailView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=AlertRuleSerializer, responses=AlertRuleSerializer)
    def patch(self, request, rule_id):
        rule = get_object_or_404(AlertRule, pk=rule_id)
        serializer = AlertRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("is_active") and rule.available_in_phase:
            raise serializers.ValidationError(
                {"is_active": [f"Règle disponible à partir de la phase {rule.available_in_phase}."]}
            )
        from pme360.audit import services as audit

        before = {"is_active": rule.is_active, "severity": rule.severity, "params": rule.params}
        serializer.save()
        audit.record(
            "alert_rule.updated",
            instance=rule,
            before=before,
            after={"is_active": rule.is_active, "severity": rule.severity, "params": rule.params},
        )
        return Response(AlertRuleSerializer(rule).data)
