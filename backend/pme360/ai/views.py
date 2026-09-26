import json

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError
from pme360.core.permissions import get_access
from pme360.core.tenancy import tenant_context
from pme360.diagnostic.views import scoped_diagnostic, scoped_pme
from pme360.documents.models import Document
from pme360.documents.views import scoped_documents
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme

from . import ask, gateway, knowledge, prediagnostic, prompts
from . import documents as ai_documents
from .financials import metrics_for
from .models import AiAnalysis, Conversation, CriterionSuggestion, DocumentExtraction, EvaluationRun
from .schemas import INTERPRETATION_SCHEMA
from .serializers import (
    AiAnalysisSerializer,
    AiAnalysisSummarySerializer,
    AiSettingsPayloadSerializer,
    AiSettingsSerializer,
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    EvaluationRunSerializer,
    ExtractionReviewSerializer,
    ExtractionSerializer,
    FinancialAnalysisSerializer,
    InterpretationSerializer,
    QuestionSerializer,
    QueueItemSerializer,
    ReindexSerializer,
    SuggestionSerializer,
)

SEVERITY_ORDER = ["INFO", "MOYENNE", "ELEVEE", "CRITIQUE"]


def _staff(request) -> None:
    from rest_framework.exceptions import PermissionDenied

    if get_access(request).is_pme_user:
        raise PermissionDenied("Réservé aux équipes d'accompagnement.")


def current_extraction(document: Document) -> DocumentExtraction | None:
    return (
        DocumentExtraction.objects.filter(version__document=document, version__version_no=document.current_version_no)
        .select_related("version", "reviewed_by")
        .first()
    )


# --- Documents -------------------------------------------------------------------------------------------------


class VerificationQueueView(APIView):
    """File de vérification priorisée (Document 4, § 7) : anomalies graves, puis confiance faible, puis ancienneté."""

    required_permissions = "document.verify"

    @extend_schema(responses=QueueItemSerializer(many=True))
    def get(self, request):
        documents = list(
            scoped_documents(request)
            .filter(verification_status=Document.Verification.VERIF_HUMAINE_REQUISE)
            .order_by("updated_at")
        )
        summaries = {}
        extractions = DocumentExtraction.objects.filter(version__document__in=documents).select_related("version")
        for extraction in extractions:
            document = next(d for d in documents if d.pk == extraction.version.document_id)
            if extraction.version.version_no != document.current_version_no:
                continue
            anomalies = [c for c in extraction.version.checks.all() if c.details.get("anomaly")]
            severities = [c.details.get("severity", "MOYENNE") for c in anomalies]
            summaries[document.pk] = {
                "status": extraction.status,
                "confidence": float(extraction.confidence) if extraction.confidence is not None else None,
                "classified_type": extraction.classified_type,
                "reason": extraction.reason,
                "anomalies": len(anomalies),
                "max_severity": max(severities, key=SEVERITY_ORDER.index) if severities else None,
            }

        def priority(document):
            summary = summaries.get(document.pk)
            if summary is None:
                return (2, 1.0)
            severity = SEVERITY_ORDER.index(summary["max_severity"]) if summary["max_severity"] else -1
            return (0 if severity >= 2 else 1 if summary["status"] != "PROVISOIRE" else 2, summary["confidence"] or 0)

        documents.sort(key=priority)
        return Response(QueueItemSerializer(documents, many=True, context={"ai": summaries}).data)


class DocumentExtractionView(APIView):
    required_permissions = "document.verify"

    @extend_schema(responses={200: ExtractionSerializer, 204: None})
    def get(self, request, document_id):
        document = get_object_or_404(scoped_documents(request), pk=document_id)
        extraction = current_extraction(document)
        if extraction is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ExtractionSerializer(extraction).data)


class ExtractionReviewView(APIView):
    required_permissions = "ai.review"

    @extend_schema(request=ExtractionReviewSerializer, responses=ExtractionSerializer)
    def post(self, request, document_id):
        document = get_object_or_404(scoped_documents(request), pk=document_id)
        extraction = current_extraction(document)
        if extraction is None:
            raise BusinessError("Aucune analyse IA pour ce document.", code="no_extraction")
        serializer = ExtractionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        extraction = ai_documents.review(
            extraction,
            get_access(request),
            status=data["status"],
            corrections=data["corrections"],
            comment=data["comment"],
        )
        return Response(ExtractionSerializer(extraction).data)


class DocumentReanalyzeView(APIView):
    """Relance l'analyse IA de la version courante (ex. après autorisation de l'IA externe)."""

    required_permissions = "document.verify"

    @extend_schema(request=None, responses={200: ExtractionSerializer, 204: None})
    def post(self, request, document_id):
        from pme360.documents.storage import get_storage

        document = get_object_or_404(scoped_documents(request), pk=document_id)
        version = document.versions.filter(version_no=document.current_version_no).exclude(storage_key="").first()
        if version is None:
            raise BusinessError("Aucune version analysable.", code="no_version")
        extraction = ai_documents.analyze(version, get_storage().get(version.storage_key))
        from django.utils import timezone

        from pme360.alerts import engine as alerts

        alerts.evaluate_kind(document.pme, "INCOHERENCE", timezone.localdate())
        return Response(ExtractionSerializer(extraction).data)


# --- Traçabilité -----------------------------------------------------------------------------------------------


def scoped_analyses(request):
    access = get_access(request)
    visible = access.pme_queryset(Pme.objects.all()).values("pk")
    queryset = AiAnalysis.objects.select_related("pme", "requested_by")
    if access.has("org.configure"):
        return queryset.filter(Q(pme__isnull=True) | Q(pme__in=visible))
    return queryset.filter(pme__in=visible)


class AnalysisListView(APIView):
    required_permissions = "ai.review"

    @extend_schema(
        parameters=[
            OpenApiParameter("pme", str, required=False),
            OpenApiParameter("task", str, required=False),
            OpenApiParameter("document", str, required=False),
            OpenApiParameter("diagnostic", str, required=False),
        ],
        responses=AiAnalysisSummarySerializer(many=True),
    )
    def get(self, request):
        _staff(request)
        queryset = scoped_analyses(request)
        if pme := request.query_params.get("pme"):
            queryset = queryset.filter(pme_id=pme)
        if task := request.query_params.get("task"):
            queryset = queryset.filter(task=task)
        if document := request.query_params.get("document"):
            queryset = queryset.filter(document_version__document_id=document)
        if diagnostic := request.query_params.get("diagnostic"):
            queryset = queryset.filter(diagnostic_id=diagnostic)
        return Response(AiAnalysisSummarySerializer(queryset[:100], many=True).data)


class AnalysisDetailView(APIView):
    required_permissions = "ai.review"

    @extend_schema(responses=AiAnalysisSerializer)
    def get(self, request, analysis_id):
        _staff(request)
        analysis = get_object_or_404(scoped_analyses(request), pk=analysis_id)
        return Response(AiAnalysisSerializer(analysis).data)


# --- Paramètres du tenant --------------------------------------------------------------------------------------


def _settings_payload(organization) -> dict:
    usage = gateway.month_usage(organization.pk)
    month_start = usage["since"]
    by_task = (
        AiAnalysis.objects.filter(created_at__date__gte=month_start)
        .values("task", "provider")
        .annotate(count=Count("id"), tokens=Sum("tokens_in") + Sum("tokens_out"), cost=Sum("cost_usd"))
        .order_by("task", "provider")
    )
    return {
        "external_allowed": organization.ai_external_allowed,
        "monthly_token_quota": organization.setting("ai_monthly_token_quota"),
        "auto_threshold": organization.setting("ai_auto_threshold"),
        "field_threshold": organization.setting("ai_field_threshold"),
        "provider": settings.PME360_AI_PROVIDER,
        "provider_configured": gateway.external_provider() is not None,
        "models": settings.PME360_AI_MODELS,
        "prompts": prompts.versions(),
        "local_engine": prompts.LOCAL_ENGINE_VERSION,
        "usage": {
            **usage,
            "by_task": [
                {
                    "task": row["task"],
                    "provider": row["provider"],
                    "count": row["count"],
                    "tokens": row["tokens"] or 0,
                    "cost_usd": float(row["cost"] or 0),
                }
                for row in by_task
            ],
        },
    }


class AiSettingsView(APIView):
    required_permissions = "org.configure"

    @extend_schema(responses=AiSettingsPayloadSerializer)
    def get(self, request):
        organization = Organization.objects.get(pk=get_access(request).organization_id)
        return Response(AiSettingsPayloadSerializer(_settings_payload(organization)).data)

    @extend_schema(request=AiSettingsSerializer, responses=AiSettingsPayloadSerializer)
    def put(self, request):
        organization = Organization.objects.get(pk=get_access(request).organization_id)
        serializer = AiSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        before = {
            "external_allowed": organization.ai_external_allowed,
            "ai_monthly_token_quota": organization.setting("ai_monthly_token_quota"),
            "ai_auto_threshold": organization.setting("ai_auto_threshold"),
            "ai_field_threshold": organization.setting("ai_field_threshold"),
        }
        organization.ai_external_allowed = data["external_allowed"]
        organization.settings = {
            **organization.settings,
            "ai_monthly_token_quota": data["monthly_token_quota"],
            "ai_auto_threshold": data["auto_threshold"],
            "ai_field_threshold": data["field_threshold"],
        }
        organization.save(update_fields=["ai_external_allowed", "settings", "updated_at"])
        audit.record(
            "ai.settings_changed",
            instance=organization,
            before=before,
            after={
                "external_allowed": data["external_allowed"],
                **{f"ai_{k}": v for k, v in data.items() if k != "external_allowed"},
            },
        )
        return Response(AiSettingsPayloadSerializer(_settings_payload(organization)).data)


# --- Pré-diagnostic ----------------------------------------------------------------------------------------------


class SuggestionListView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(responses=SuggestionSerializer(many=True))
    def get(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        return Response(SuggestionSerializer(CriterionSuggestion.objects.filter(diagnostic=diagnostic), many=True).data)

    @extend_schema(request=None, responses=SuggestionSerializer(many=True))
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        if diagnostic.status != "EN_REVUE":
            raise BusinessError("Le pré-diagnostic porte sur un diagnostic en revue.", code="invalid_status")
        prediagnostic.run(diagnostic, user=request.user)
        return Response(SuggestionSerializer(CriterionSuggestion.objects.filter(diagnostic=diagnostic), many=True).data)


# --- Analyse financière --------------------------------------------------------------------------------------------


def _financial_payload(pme) -> dict:
    analysis = metrics_for(pme)
    return {
        "as_of": analysis["as_of"],
        "metrics": analysis["metrics"],
        "statements": [
            {
                "id": s.pk,
                "fiscal_year_end": s.fiscal_year_end,
                "system": s.system,
                "status": s.status,
                "values": s.values,
                "confidence": float(s.confidence) if s.confidence is not None else None,
                "document_id": s.source_version.document_id,
                "document_title": s.source_version.document.title,
                "verified_at": s.verified_at,
            }
            for s in analysis["statements"]
        ],
    }


class FinancialAnalysisView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=FinancialAnalysisSerializer)
    def get(self, request, pme_id):
        _staff(request)
        pme = scoped_pme(request, pme_id)
        return Response(FinancialAnalysisSerializer(_financial_payload(pme)).data)


class FinancialInterpretationView(APIView):
    """Commentaire des ratios (brouillon à relire avant publication, Document 4, fonction D)."""

    required_permissions = "ai.review"

    @extend_schema(request=None, responses=InterpretationSerializer)
    def post(self, request, pme_id):
        _staff(request)
        pme = scoped_pme(request, pme_id)
        metrics = metrics_for(pme)["metrics"]
        public = [
            {k: m.get(k) for k in ("code", "name", "formula", "display", "band", "points", "sources", "missing")}
            for m in metrics
        ]
        outcome = gateway.run(
            prompt_code="finance.interpret",
            content=f"<donnees>\n{json.dumps(public, ensure_ascii=False, default=str)}\n</donnees>",
            schema=INTERPRETATION_SCHEMA,
            context={"metrics": metrics},
            pme=pme,
            input_refs={"pme": str(pme.pk), "metrics": [m["code"] for m in metrics]},
            user=request.user,
        )
        if not outcome.ok:
            raise BusinessError(
                "Le commentaire n'a pas pu être rédigé.", code="ai_unavailable", reason=outcome.analysis.error
            )
        return Response(
            InterpretationSerializer(
                {**outcome.output, "analysis_id": outcome.analysis.pk, "provider": outcome.provider, "draft": True}
            ).data
        )


# --- Ask AI --------------------------------------------------------------------------------------------------------


class ConversationListView(APIView):
    required_permissions = "ai.ask"

    @extend_schema(
        parameters=[OpenApiParameter("pme", str, required=False)], responses=ConversationSerializer(many=True)
    )
    def get(self, request):
        conversations = Conversation.objects.filter(user=request.user).select_related("pme")
        if pme := request.query_params.get("pme"):
            conversations = conversations.filter(pme_id=pme)
        return Response(ConversationSerializer(conversations[:50], many=True).data)

    @extend_schema(request=ConversationCreateSerializer, responses={201: ConversationSerializer})
    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pme = (
            scoped_pme(request, serializer.validated_data["pme_id"])
            if serializer.validated_data.get("pme_id")
            else None
        )
        title = serializer.validated_data["title"] or (f"Questions sur {pme.legal_name}" if pme else "Mon portefeuille")
        conversation = Conversation.objects.create(user=request.user, pme=pme, title=title)
        return Response(ConversationSerializer(conversation).data, status=status.HTTP_201_CREATED)


def _conversation(request, conversation_id) -> Conversation:
    conversation = get_object_or_404(Conversation.objects.select_related("pme"), pk=conversation_id, user=request.user)
    if conversation.pme_id:
        scoped_pme(request, conversation.pme_id)  # périmètre toujours revérifié
    return conversation


class ConversationDetailView(APIView):
    required_permissions = "ai.ask"

    @extend_schema(responses=ConversationDetailSerializer)
    def get(self, request, conversation_id):
        return Response(ConversationDetailSerializer(_conversation(request, conversation_id)).data)


class EventStreamRenderer(BaseRenderer):
    """Accepte ``Accept: text/event-stream`` (client SSE) ; le flux lui-même est écrit par la vue."""

    media_type = "text/event-stream"
    format = "sse"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Seules les erreurs (validation, droits) passent par ici : corps JSON lisible par le client.
        return json.dumps(data, ensure_ascii=False, default=str).encode()


class ConversationAskView(APIView):
    """Question au Copilot : réponse diffusée en Server-Sent Events (status, delta, done)."""

    required_permissions = "ai.ask"
    renderer_classes = [JSONRenderer, EventStreamRenderer]

    @extend_schema(
        request=QuestionSerializer,
        responses={(200, "text/event-stream"): str},
        parameters=[OpenApiParameter("format", exclude=True)],
    )
    def post(self, request, conversation_id):
        conversation = _conversation(request, conversation_id)
        serializer = QuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data["question"]
        access = get_access(request)
        organization_id = request.organization_id
        conversation_id = conversation.pk

        def stream():
            # Le flux est consommé après la sortie du middleware : on rouvre le contexte de tenant.
            with tenant_context(organization_id):
                current = Conversation.objects.select_related("pme").get(pk=conversation_id)
                try:
                    for event in ask.ask(current, question, access):
                        yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                except Exception:
                    import structlog

                    structlog.get_logger(__name__).exception("ai.ask_failed")
                    payload = {"type": "error", "text": "L'assistant a rencontré une erreur. Réessayez."}
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(stream(), content_type="text/event-stream; charset=utf-8")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


# --- Évaluation et index -------------------------------------------------------------------------------------------


class EvaluationListView(APIView):
    required_permissions = "org.configure"

    @extend_schema(responses=EvaluationRunSerializer(many=True))
    def get(self, request):
        return Response(EvaluationRunSerializer(EvaluationRun.objects.all()[:20], many=True).data)

    @extend_schema(request=None, responses={201: EvaluationRunSerializer})
    def post(self, request):
        from .evaluation import evaluate

        run = evaluate(provider="local")
        audit.record("ai.evaluation_run", instance=run, after={"passed": run.passed, "metrics": run.metrics})
        return Response(EvaluationRunSerializer(run).data, status=status.HTTP_201_CREATED)


class ReindexView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=None, responses=ReindexSerializer)
    def post(self, request):
        return Response(ReindexSerializer(knowledge.reindex_organization()).data)
