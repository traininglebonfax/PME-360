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


class PmeReportsView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=ReportSerializer(many=True))
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        reports = Report.objects.filter(pme=pme).select_related("generated_by")
        return Response(ReportSerializer(reports, many=True).data)


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
        pmes = get_access(request).pme_queryset(Pme.objects.all())
        report = get_object_or_404(Report.objects.filter(pme__in=pmes), pk=report_id)
        content = services.read_pdf(report)
        audit.record("report.downloaded", instance=report, pme_id=report.pme_id, after={"version": report.version})
        response = HttpResponse(content, content_type="application/pdf")
        name = f"rapport-diagnostic-v{report.version}-{report.period}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["Cache-Control"] = "private, no-store"
        return response
