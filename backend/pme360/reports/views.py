"""Rapports : liste, génération d'une nouvelle version, téléchargement du PDF archivé."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.audit import services as audit
from pme360.core.permissions import get_access
from pme360.diagnostic.views import scoped_diagnostic, scoped_pme
from pme360.pmes.models import Pme

from . import services
from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    generated_by_name = serializers.CharField(source="generated_by.full_name", read_only=True, default=None)
    confidence = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "type",
            "pme",
            "diagnostic",
            "version",
            "title",
            "period",
            "template_version",
            "size_bytes",
            "sha256",
            "engine",
            "confidence",
            "generated_by_name",
            "generated_at",
        ]
        read_only_fields = fields


class PmeReportRequestSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[(t.value, t.label) for t in Report.PME_TYPES])


class PmeReportsView(APIView):
    """Rapports d'une PME ; édition d'un rapport de suivi, annuel ou de conformité (Document 9, § 7)."""

    required_permissions = "pme.view"

    @extend_schema(responses=ReportSerializer(many=True))
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        reports = Report.objects.filter(pme=pme).select_related("generated_by")
        return Response(ReportSerializer(reports, many=True).data)

    @extend_schema(request=PmeReportRequestSerializer, responses={201: ReportSerializer})
    def post(self, request, pme_id):
        access = get_access(request)
        if access.is_pme_user or not access.has("report.generate"):
            raise PermissionDenied("Le rapport est édité par votre conseiller.")
        pme = scoped_pme(request, pme_id)
        serializer = PmeReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.generate_pme_report(pme, serializer.validated_data["type"], request.user)
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


class DiagnosticReportView(APIView):
    """Génère une nouvelle version du rapport de diagnostic (les versions précédentes restent archivées)."""

    required_permissions = "report.generate"

    @extend_schema(request=None, responses={201: ReportSerializer})
    def post(self, request, diagnostic_id):
        if get_access(request).is_pme_user:
            raise PermissionDenied("Le rapport est édité par votre conseiller.")
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        report = services.generate_diagnostic_report(diagnostic, request.user)
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ReportPdfView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses={(200, "application/pdf"): OpenApiResponse(description="PDF archivé")})
    def get(self, request, report_id):
        from rest_framework.exceptions import NotFound

        access = get_access(request)
        report = get_object_or_404(Report.objects.all(), pk=report_id)
        if report.type == Report.Type.PORTEFEUILLE:
            if not services.can_read_portfolio_report(report, access):
                raise NotFound()
        elif not access.pme_queryset(Pme.objects.filter(pk=report.pme_id)).exists():
            raise NotFound()
        content = services.read_pdf(report)
        audit.record("report.downloaded", instance=report, pme_id=report.pme_id, after={"version": report.version})
        response = HttpResponse(content, content_type="application/pdf")
        kind = {
            Report.Type.PORTEFEUILLE: "portefeuille",
            Report.Type.SUIVI: "suivi",
            Report.Type.ANNUEL: "annuel",
            Report.Type.CONFORMITE: "conformite",
        }.get(report.type, "diagnostic")
        name = f"rapport-{kind}-v{report.version}-{report.period}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["Cache-Control"] = "private, no-store"
        return response


class PortfolioReportRequestSerializer(serializers.Serializer):
    period = serializers.RegexField(r"^\d{4}-T[1-4]$", required=False, allow_blank=True, default="")
    programme_id = serializers.UUIDField(required=False, allow_null=True)
    cohort_id = serializers.UUIDField(required=False, allow_null=True)
    include_names = serializers.BooleanField(required=False, default=False)


class PortfolioReportSerializer(ReportSerializer):
    scope_label = serializers.SerializerMethodField()
    include_names = serializers.SerializerMethodField()
    pme_count = serializers.SerializerMethodField()

    class Meta(ReportSerializer.Meta):
        fields = [*ReportSerializer.Meta.fields, "scope_label", "include_names", "pme_count"]
        read_only_fields = fields

    @staticmethod
    def get_scope_label(report) -> str:
        return report.scope.get("label", "")

    @staticmethod
    def get_include_names(report) -> bool:
        return bool(report.scope.get("include_names"))

    @staticmethod
    def get_pme_count(report) -> int:
        return len(report.scope.get("pme_ids", []))


class PortfolioReportsView(APIView):
    """Rapports trimestriels de portefeuille visibles par l'utilisateur ; génération d'une nouvelle édition."""

    required_permissions = "dashboard.portfolio"

    @extend_schema(responses=PortfolioReportSerializer(many=True))
    def get(self, request):
        access = get_access(request)
        reports = Report.objects.filter(type=Report.Type.PORTEFEUILLE).select_related("generated_by")
        readable = sorted(
            (r for r in reports if services.can_read_portfolio_report(r, access)),
            key=lambda r: (r.period, r.version),
            reverse=True,
        )
        return Response(PortfolioReportSerializer(readable, many=True).data)

    @extend_schema(request=PortfolioReportRequestSerializer, responses={201: PortfolioReportSerializer})
    def post(self, request):
        from pme360.organizations.models import Cohort, Programme

        access = get_access(request)
        if access.is_pme_user or not access.has("report.generate"):
            raise PermissionDenied()
        serializer = PortfolioReportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        programme = (
            get_object_or_404(Programme.objects.all(), pk=data["programme_id"]) if data.get("programme_id") else None
        )
        cohort = get_object_or_404(Cohort.objects.all(), pk=data["cohort_id"]) if data.get("cohort_id") else None
        report = services.generate_portfolio_report(
            access,
            data["period"] or None,
            programme=programme,
            cohort=cohort,
            include_names=data["include_names"],
            user=request.user,
        )
        return Response(PortfolioReportSerializer(report).data, status=status.HTTP_201_CREATED)
