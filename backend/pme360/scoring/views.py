from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.diagnostic.models import Diagnostic
from pme360.diagnostic.views import scoped_diagnostic, scoped_pme, serialize
from pme360.pmes.models import Pme

from . import services
from .models import ScoreSnapshot


class SnapshotSummarySerializer(serializers.ModelSerializer):
    framework_version = serializers.CharField(source="framework_version.version", read_only=True)
    diagnostic_type = serializers.CharField(source="diagnostic.type", read_only=True, default=None)
    maturity_label = serializers.SerializerMethodField()

    class Meta:
        model = ScoreSnapshot
        fields = [
            "id",
            "kind",
            "reference_date",
            "computed_at",
            "framework_version",
            "engine_version",
            "global_score",
            "imo",
            "ipe",
            "risk_index",
            "digital_index",
            "confidence",
            "maturity_level",
            "maturity_label",
            "intervention_priority",
            "quadrant",
            "diagnostic_type",
        ]
        read_only_fields = fields

    def get_maturity_label(self, obj) -> str | None:
        return obj.result.get("maturity", {}).get("label")


class SnapshotDetailSerializer(SnapshotSummarySerializer):
    result = serializers.JSONField(read_only=True)

    class Meta(SnapshotSummarySerializer.Meta):
        fields = [*SnapshotSummarySerializer.Meta.fields, "result"]
        read_only_fields = fields


class HealthCheckSerializer(serializers.Serializer):
    snapshot = SnapshotDetailSerializer(allow_null=True)
    baseline = SnapshotSummarySerializer(allow_null=True)
    history = SnapshotSummarySerializer(many=True)
    live = SnapshotDetailSerializer(
        allow_null=True, help_text="Score courant : preuves vérifiées depuis la validation."
    )
    open_diagnostic = serializers.JSONField(allow_null=True)


def scoped_snapshot(request, snapshot_id) -> ScoreSnapshot:
    pmes = get_access(request).pme_queryset(Pme.objects.all())
    return get_object_or_404(
        ScoreSnapshot.objects.select_related("framework_version", "diagnostic").filter(pme__in=pmes), pk=snapshot_id
    )


class HealthCheckView(APIView):
    """« PME Health Check » (Document 6, § 10) : dernier snapshot figé, référence, historique, diagnostic en cours."""

    required_permissions = "pme.view"

    @extend_schema(responses=HealthCheckSerializer)
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        snapshots = list(
            ScoreSnapshot.objects.filter(pme=pme, is_frozen=True)
            .select_related("framework_version", "diagnostic")
            .order_by("reference_date", "computed_at")
        )
        baseline = next((s for s in snapshots if s.kind == ScoreSnapshot.Kind.BASELINE), None)
        live = (
            ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE)
            .select_related("framework_version")
            .first()
        )
        if live and (not snapshots or live.result.get("source_diagnostic") != str(snapshots[-1].diagnostic_id)):
            live = None  # score courant d'un diagnostic antérieur : non pertinent
        open_diagnostic = (
            Diagnostic.objects.filter(pme=pme)
            .exclude(status__in=[Diagnostic.Status.VALIDE, Diagnostic.Status.ANNULE])
            .select_related("pme", "framework_version", "validated_by", "lead_advisor")
            .first()
        )
        return Response(
            {
                "snapshot": SnapshotDetailSerializer(snapshots[-1]).data if snapshots else None,
                "baseline": SnapshotSummarySerializer(baseline).data if baseline else None,
                "history": SnapshotSummarySerializer(snapshots, many=True).data,
                "live": SnapshotDetailSerializer(live).data if live else None,
                "open_diagnostic": serialize(open_diagnostic) if open_diagnostic else None,
            }
        )


class SnapshotDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=SnapshotDetailSerializer)
    def get(self, request, snapshot_id):
        return Response(SnapshotDetailSerializer(scoped_snapshot(request, snapshot_id)).data)


class SnapshotCompareView(APIView):
    """Explication de l'écart entre deux snapshots d'une même PME (Document 6, § 8)."""

    required_permissions = "pme.view"

    @extend_schema(responses=dict)
    def get(self, request, snapshot_id, other_id):
        after = scoped_snapshot(request, snapshot_id)
        before = scoped_snapshot(request, other_id)
        if before.pme_id != after.pme_id:
            return Response({"detail": "Les snapshots doivent concerner la même PME."}, status=400)
        return Response(services.compare(before, after))


class DiagnosticPreviewView(APIView):
    """Résultat provisoire (non enregistré) d'un diagnostic en cours."""

    required_permissions = "diagnostic.validate"

    @extend_schema(responses=dict)
    def get(self, request, diagnostic_id):
        return Response(services.compute(scoped_diagnostic(request, diagnostic_id)))
