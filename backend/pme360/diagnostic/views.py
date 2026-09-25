from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.pmes.models import Pme
from pme360.scoring import services as scoring

from . import referential, services
from .models import Answer, Criterion, CriterionAssessment, Diagnostic, FrameworkVersion
from .serializers import (
    AcceptResultSerializer,
    AnswerBatchResultSerializer,
    AnswerBatchSerializer,
    AssessmentSerializer,
    CloneSerializer,
    DiagnosticSerializer,
    FrameworkVersionDetailSerializer,
    FrameworkVersionSerializer,
    QuestionnaireSerializer,
    ReasonSerializer,
    ReviewPayloadSerializer,
    ReviewSerializer,
    StartDiagnosticSerializer,
)


def _with_ref(diagnostic: Diagnostic) -> Diagnostic:
    diagnostic.pme_ref = {"id": diagnostic.pme_id, "name": diagnostic.pme.legal_name}
    return diagnostic


def serialize(diagnostic: Diagnostic) -> dict:
    return DiagnosticSerializer(_with_ref(diagnostic)).data


def scoped_pme(request, pme_id) -> Pme:
    return get_object_or_404(get_access(request).pme_queryset(Pme.objects.all()), pk=pme_id)


def scoped_diagnostic(request, diagnostic_id) -> Diagnostic:
    pmes = get_access(request).pme_queryset(Pme.objects.all())
    return get_object_or_404(
        Diagnostic.objects.select_related("pme", "framework_version", "validated_by", "lead_advisor").filter(
            pme__in=pmes
        ),
        pk=diagnostic_id,
    )


# --- Référentiel ----------------------------------------------------------------------------------------------


class FrameworkVersionListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=FrameworkVersionSerializer(many=True))
    def get(self, request):
        versions = FrameworkVersion.objects.select_related("framework", "published_by")
        return Response(FrameworkVersionSerializer(versions, many=True).data)


class FrameworkVersionDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=FrameworkVersionDetailSerializer)
    def get(self, request, version_id):
        version = get_object_or_404(FrameworkVersion.objects.select_related("framework", "published_by"), pk=version_id)
        return Response(FrameworkVersionDetailSerializer(version).data)


class FrameworkVersionCloneView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=CloneSerializer, responses={201: FrameworkVersionSerializer})
    def post(self, request, version_id):
        source = get_object_or_404(FrameworkVersion, pk=version_id)
        serializer = CloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = referential.clone_version(source, serializer.validated_data["version"], request.user)
        return Response(FrameworkVersionSerializer(draft).data, status=status.HTTP_201_CREATED)


class FrameworkVersionPublishView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=None, responses=FrameworkVersionSerializer)
    def post(self, request, version_id):
        version = get_object_or_404(FrameworkVersion, pk=version_id)
        return Response(FrameworkVersionSerializer(referential.publish_version(version, request.user)).data)


# --- Diagnostics ----------------------------------------------------------------------------------------------


class PmeDiagnosticsView(APIView):
    required_permissions = {"GET": "pme.view", "POST": "diagnostic.validate"}

    @extend_schema(responses=DiagnosticSerializer(many=True))
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        diagnostics = Diagnostic.objects.filter(pme=pme).select_related(
            "pme", "framework_version", "validated_by", "lead_advisor"
        )
        return Response([serialize(d) for d in diagnostics])

    @extend_schema(request=StartDiagnosticSerializer, responses={201: DiagnosticSerializer})
    def post(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        serializer = StartDiagnosticSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        diagnostic = services.start_diagnostic(
            get_access(request), pme, serializer.validated_data["type"], serializer.validated_data.get("reference_date")
        )
        return Response(serialize(diagnostic), status=status.HTTP_201_CREATED)


class DiagnosticDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=DiagnosticSerializer)
    def get(self, request, diagnostic_id):
        return Response(serialize(scoped_diagnostic(request, diagnostic_id)))


class QuestionnaireView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=QuestionnaireSerializer)
    def get(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        payload = services.questionnaire(diagnostic, get_access(request))
        payload["diagnostic"] = _with_ref(diagnostic)
        return Response(QuestionnaireSerializer(payload).data)


class AnswersView(APIView):
    required_permissions = "diagnostic.answer"

    @extend_schema(request=AnswerBatchSerializer, responses=AnswerBatchResultSerializer)
    def put(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        serializer = AnswerBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access = get_access(request)
        changed = services.save_answers(diagnostic, access, serializer.validated_data["answers"])
        progress = services.questionnaire(diagnostic, access)["progress"]
        return Response({"changed": changed, "progress": progress})


class SubmitView(APIView):
    required_permissions = "diagnostic.answer"

    @extend_schema(request=None, responses=DiagnosticSerializer)
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        return Response(serialize(services.submit(diagnostic, get_access(request))))


class ReopenView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(request=ReasonSerializer, responses=DiagnosticSerializer)
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            serialize(services.reopen(diagnostic, get_access(request), serializer.validated_data["reason"]))
        )


class CancelView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(request=ReasonSerializer, responses=DiagnosticSerializer)
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serialize(services.cancel(diagnostic, serializer.validated_data["reason"])))


class ReviewView(APIView):
    """Écran de revue : critères par dimension avec réponses, grille, résultat provisoire et revue existante."""

    required_permissions = "diagnostic.validate"

    @extend_schema(responses=ReviewPayloadSerializer)
    def get(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        result = scoring.compute(diagnostic)
        criteria = {
            c.code: c
            for c in Criterion.objects.filter(framework_version=diagnostic.framework_version).select_related(
                "dimension"
            )
        }
        assessments = {
            a.criterion.code: a
            for a in CriterionAssessment.objects.filter(diagnostic=diagnostic).select_related("criterion", "reviewer")
        }
        answers: dict[str, list[dict]] = {}
        for answer in Answer.objects.filter(diagnostic=diagnostic).select_related("question__criterion"):
            question = answer.question
            if not question.criterion_id:
                continue
            label = next((o["label"] for o in question.options if str(o["value"]) == str(answer.value)), answer.value)
            answers.setdefault(question.criterion.code, []).append(
                {"question": question.text, "answer": label, "source": answer.source, "answered_at": answer.answered_at}
            )
        results = {c["code"]: c for c in result["criteria"]}
        dimensions = []
        for dimension in result["dimensions"]:
            items = [
                {
                    "code": code,
                    "name": crit.name,
                    "dimension": dimension["code"],
                    "lens": crit.lens,
                    "is_critical": crit.is_critical,
                    "evidence_policy": crit.evidence_policy,
                    "rubric": crit.rubric,
                    "result": results[code],
                    "answers": answers.get(code, []),
                    "assessment": AssessmentSerializer(assessments[code]).data if code in assessments else None,
                }
                for code, crit in criteria.items()
                if crit.dimension.code == dimension["code"]
                and (results[code]["status"] != "NON_APPLICABLE" or code in assessments)
            ]
            if items:
                dimensions.append(
                    {"code": dimension["code"], "name": dimension["name"], "result": dimension, "criteria": items}
                )
        payload = {
            "diagnostic": _with_ref(diagnostic),
            "preview": {k: v for k, v in result.items() if k != "criteria"},
            "pending": services.review_status(diagnostic, result)["pending"],
            "dimensions": dimensions,
        }
        return Response(ReviewPayloadSerializer(payload).data)


class ReviewCriterionView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(request=ReviewSerializer, responses=AssessmentSerializer)
    def post(self, request, diagnostic_id, criterion_code):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assessment = services.review_criterion(
            diagnostic,
            get_access(request),
            criterion_code,
            status=data["status"],
            level_final=data.get("level_final"),
            comment=data["comment"],
            corroborated=data["corroborated"],
        )
        return Response(AssessmentSerializer(assessment).data)


class AcceptRemainingView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(request=None, responses=AcceptResultSerializer)
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        return Response({"accepted": services.accept_remaining(diagnostic, get_access(request))})


class ValidateView(APIView):
    required_permissions = "diagnostic.validate"

    @extend_schema(request=None, responses=DiagnosticSerializer)
    def post(self, request, diagnostic_id):
        diagnostic = scoped_diagnostic(request, diagnostic_id)
        services.validate(diagnostic, get_access(request))
        return Response(serialize(scoped_diagnostic(request, diagnostic_id)))
