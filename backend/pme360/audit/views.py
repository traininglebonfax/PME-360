from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .labels import label_for
from .models import AuditLog
from .services import verify_chain


class AuditLogSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "at",
            "action",
            "label",
            "actor",
            "actor_name",
            "actor_type",
            "entity_type",
            "entity_id",
            "pme_id",
            "before",
            "after",
            "ip",
            "request_id",
            "hash",
        ]

    def get_label(self, obj) -> str:
        return label_for(obj.action)

    def get_actor_name(self, obj) -> str | None:
        return obj.actor.full_name if obj.actor else None


class AuditLogListView(ListAPIView):
    """Journal d'audit de l'organisation active (lecture seule)."""

    serializer_class = AuditLogSerializer
    required_permissions = "audit.view"

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor")
        params = self.request.query_params
        for param in ("entity_type", "entity_id", "pme_id", "action"):
            if value := params.get(param):
                queryset = queryset.filter(**{param: value})
        if actor := params.get("actor"):
            queryset = queryset.filter(actor_id=actor)
        if start := parse_datetime(params.get("from", "") or ""):
            queryset = queryset.filter(at__gte=start)
        if end := parse_datetime(params.get("to", "") or ""):
            queryset = queryset.filter(at__lte=end)
        return queryset

    pagination_class = None

    @extend_schema(
        parameters=[
            OpenApiParameter(name, str)
            for name in ("entity_type", "entity_id", "pme_id", "action", "actor", "from", "to")
        ]
    )
    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset().order_by("-id")[: int(request.query_params.get("limit", 200) or 200)]
        return Response(self.get_serializer(queryset, many=True).data)


class ChainVerificationSerializer(serializers.Serializer):
    valid = serializers.BooleanField()
    entries_checked = serializers.IntegerField()
    first_invalid_id = serializers.IntegerField(allow_null=True)


class AuditVerifyView(APIView):
    """Recalcule la chaîne de hash du journal de l'organisation (détection d'altération)."""

    required_permissions = "audit.view"

    @extend_schema(responses=ChainVerificationSerializer)
    def get(self, request):
        result = verify_chain(request.organization_id)
        return Response(ChainVerificationSerializer(result.__dict__).data)
