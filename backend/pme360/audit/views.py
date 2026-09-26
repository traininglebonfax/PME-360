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


# --- Tableau de bord auditeur (V1) ---------------------------------------------------------------------------


class DomainCountSerializer(serializers.Serializer):
    domain = serializers.CharField()
    count = serializers.IntegerField()


class ActorCountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class SensitiveEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    label = serializers.CharField()
    actor_name = serializers.CharField(allow_null=True)
    actor_type = serializers.CharField()
    entity_type = serializers.CharField()
    pme_id = serializers.UUIDField(allow_null=True)


class DimensionReviewSerializer(serializers.Serializer):
    dimension = serializers.CharField()
    name = serializers.CharField()
    reviewed = serializers.IntegerField()
    accepted = serializers.IntegerField()
    modified = serializers.IntegerField()
    rejected = serializers.IntegerField()
    change_rate = serializers.FloatField(allow_null=True)


class AiReviewSerializer(serializers.Serializer):
    suggestions_reviewed = serializers.IntegerField()
    suggestions_change_rate = serializers.FloatField(allow_null=True)
    by_dimension = DimensionReviewSerializer(many=True)
    documents_reviewed = serializers.IntegerField()
    documents_validated = serializers.IntegerField()
    documents_corrected = serializers.IntegerField()
    documents_rejected = serializers.IntegerField()
    documents_change_rate = serializers.FloatField(allow_null=True)


class AuditOverviewSerializer(serializers.Serializer):
    period_start = serializers.DateField(source="from")
    period_end = serializers.DateField(source="to")
    total = serializers.IntegerField()
    by_actor_type = serializers.DictField(child=serializers.IntegerField())
    by_domain = DomainCountSerializer(many=True)
    top_actors = ActorCountSerializer(many=True)
    login_failures = serializers.IntegerField()
    sensitive = SensitiveEntrySerializer(many=True)
    ai_review = AiReviewSerializer()


class SampleItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    sector = serializers.CharField()
    region = serializers.CharField()
    lifecycle_status = serializers.CharField()
    last_validated_diagnostic = serializers.DateTimeField(allow_null=True)
    documents = serializers.IntegerField()
    documents_verified = serializers.IntegerField()
    ai_suggestions_changed = serializers.IntegerField()
    audit_entries = serializers.IntegerField()


class SampleSerializer(serializers.Serializer):
    seed = serializers.CharField()
    size = serializers.IntegerField()
    population = serializers.IntegerField()
    items = SampleItemSerializer(many=True)


def _date(value):
    from django.utils.dateparse import parse_date

    return parse_date(value or "") if value else None


class AuditOverviewView(APIView):
    required_permissions = "audit.view"

    @extend_schema(
        parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)], responses=AuditOverviewSerializer
    )
    def get(self, request):
        from .dashboard import overview

        data = overview(_date(request.query_params.get("from")), _date(request.query_params.get("to")))
        return Response(AuditOverviewSerializer(data).data)


class AuditSampleView(APIView):
    """Échantillon reproductible de dossiers PME : la même graine redonne le même échantillon."""

    required_permissions = "audit.view"

    @extend_schema(
        parameters=[OpenApiParameter("seed", str), OpenApiParameter("size", int)], responses=SampleSerializer
    )
    def get(self, request):
        import secrets

        from pme360.core.permissions import get_access
        from pme360.pmes.models import Pme

        from .dashboard import sample
        from .services import record

        access = get_access(request)
        seed = (request.query_params.get("seed") or "").strip()[:40] or secrets.token_hex(4)
        try:
            size = max(1, min(int(request.query_params.get("size") or 5), 50))
        except ValueError:
            size = 5
        items = sample(access, size, seed)
        record("audit.sampled", entity_type="audit_sample", entity_id=seed, after={"seed": seed, "size": size})
        population = access.pme_queryset(Pme.objects.all()).count()
        return Response(SampleSerializer({"seed": seed, "size": size, "population": population, "items": items}).data)


class AuditExportView(APIView):
    """Export CSV du journal (mêmes filtres que la liste) ; l'export est lui-même journalisé."""

    required_permissions = "audit.view"

    @extend_schema(
        parameters=[OpenApiParameter(name, str) for name in ("action", "actor", "pme_id", "from", "to")],
        responses={(200, "text/csv"): str},
    )
    def get(self, request):
        from django.http import HttpResponse

        from .dashboard import export_csv
        from .services import record

        queryset = AuditLogListView(request=request).get_queryset()
        params = {k: v for k, v in request.query_params.items() if v}
        content = export_csv(queryset)
        record("audit.exported", entity_type="audit_log", after={"filters": params, "rows": content.count("\n") - 1})
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="journal-audit.csv"'
        return response
