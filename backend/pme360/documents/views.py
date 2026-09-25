from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.audit import services as audit
from pme360.compliance.models import Deadline
from pme360.core.exceptions import BusinessError, problem_response
from pme360.core.permissions import get_access
from pme360.diagnostic.views import scoped_pme
from pme360.pmes.models import Pme

from . import services
from .models import Document, DocumentType, DocumentVersion
from .serializers import (
    DocumentDetailSerializer,
    DocumentSerializer,
    DocumentTypeSerializer,
    DownloadUrlSerializer,
    UploadSerializer,
    VerifySerializer,
)
from .storage import get_storage


def scoped_documents(request):
    pmes = get_access(request).pme_queryset(Pme.objects.all())
    return Document.objects.filter(pme__in=pmes, deleted_at__isnull=True).select_related(
        "pme", "document_type__category", "deadline", "verified_by", "uploaded_by"
    )


class DocumentTypeListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=DocumentTypeSerializer(many=True))
    def get(self, request):
        types = DocumentType.objects.filter(is_active=True).select_related("category")
        return Response(DocumentTypeSerializer(types, many=True).data)


class PmeDocumentsView(APIView):
    """Dépôt (multipart) et liste des documents d'une PME."""

    required_permissions = {"GET": "pme.view", "POST": "document.upload"}
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        parameters=[OpenApiParameter("type", str), OpenApiParameter("status", str)],
        responses=DocumentSerializer(many=True),
    )
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        documents = scoped_documents(request).filter(pme=pme)
        if type_code := request.query_params.get("type"):
            documents = documents.filter(document_type__code=type_code)
        return Response(DocumentSerializer(documents, many=True).data)

    @extend_schema(request={"multipart/form-data": UploadSerializer}, responses={201: DocumentDetailSerializer})
    def post(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        uploaded = data["file"]
        if uploaded.size > settings.PME360_MAX_UPLOAD_BYTES:
            limit = settings.PME360_MAX_UPLOAD_BYTES // (1024 * 1024)
            return problem_response(400, "file_too_large", f"Le fichier dépasse {limit} Mo.", request)
        document = None
        if data.get("document_id"):
            document = get_object_or_404(Document.objects.filter(pme=pme), pk=data["document_id"])
        deadline = (
            get_object_or_404(Deadline.objects.filter(pme=pme), pk=data["deadline_id"])
            if data.get("deadline_id")
            else None
        )
        document_type = None
        if data.get("document_type"):
            document_type = get_object_or_404(DocumentType.objects.filter(is_active=True), code=data["document_type"])
        try:
            result = services.upload(
                get_access(request),
                pme,
                filename=uploaded.name,
                content=uploaded.read(),
                document_type=document_type,
                document=document,
                deadline=deadline,
                title=data.get("title", ""),
                period_start=data.get("period_start"),
                period_end=data.get("period_end"),
                issued_at=data.get("issued_at"),
                expires_at=data.get("expires_at"),
            )
        except BusinessError as refused:
            # Réponse sans exception : l'entrée d'audit du refus est conservée (rien d'autre n'a été écrit).
            return problem_response(refused.status_code, refused.code, str(refused.detail), request)
        if result.infected:
            # Réponse sans exception : la trace de l'incident (document, version, audit, alerte) est conservée.
            return problem_response(
                422,
                "infected_file",
                "Ce fichier a été bloqué par l'antivirus et n'a pas été enregistré. Votre conseiller est prévenu.",
                request,
                document_id=str(result.document.pk),
            )
        document = scoped_documents(request).prefetch_related("versions__checks").get(pk=result.document.pk)
        return Response(DocumentDetailSerializer(document).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=DocumentDetailSerializer)
    def get(self, request, document_id):
        document = get_object_or_404(
            scoped_documents(request).prefetch_related("versions__checks", "versions__uploaded_by"), pk=document_id
        )
        return Response(DocumentDetailSerializer(document).data)


class DocumentVerifyView(APIView):
    required_permissions = "document.verify"

    @extend_schema(request=VerifySerializer, responses=DocumentSerializer)
    def post(self, request, document_id):
        document = get_object_or_404(scoped_documents(request), pk=document_id)
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify(get_access(request), document, **serializer.validated_data)
        return Response(DocumentSerializer(scoped_documents(request).get(pk=document_id)).data)


class VerificationQueueView(APIView):
    """File de vérification du conseiller : documents du périmètre en attente, les plus anciens d'abord."""

    required_permissions = "document.verify"

    @extend_schema(responses=DocumentSerializer(many=True))
    def get(self, request):
        documents = (
            scoped_documents(request)
            .filter(verification_status=Document.Verification.VERIF_HUMAINE_REQUISE)
            .order_by("updated_at")
        )
        return Response(DocumentSerializer(documents, many=True).data)


class DownloadUrlView(APIView):
    """URL signée de 5 minutes, délivrée après contrôle d'accès (Document 2, § 8.2)."""

    required_permissions = "pme.view"

    @extend_schema(responses=DownloadUrlSerializer)
    def get(self, request, document_id, version_no):
        document = get_object_or_404(scoped_documents(request), pk=document_id)
        version = get_object_or_404(
            DocumentVersion.objects.filter(document=document, av_status=DocumentVersion.Antivirus.SAIN).exclude(
                storage_key=""
            ),
            version_no=version_no,
        )
        token = services.download_token(version, request.user)
        return Response({"url": f"/api/v1/files/{token}", "expires_in": settings.PME360_DOWNLOAD_URL_TTL})


class FileDownloadView(APIView):
    """Sert le fichier d'une URL signée ; l'accès (consultation) est journalisé."""

    permission_classes = [IsAuthenticated]

    @extend_schema(exclude=True)
    def get(self, request, token):
        try:
            claims = services.read_token(token, settings.PME360_DOWNLOAD_URL_TTL)
        except signing.BadSignature as exc:
            raise Http404("Lien expiré ou invalide.") from exc
        # Lien personnel, valable uniquement dans l'organisation active de la session (pas de bascule de tenant).
        if claims["u"] != str(request.user.pk) or claims["o"] != str(request.organization_id):
            raise Http404("Lien expiré ou invalide.")
        version = DocumentVersion.objects.select_related("document").filter(pk=claims["v"]).first()
        if version is None or not version.storage_key:
            raise Http404()
        content = get_storage().get(version.storage_key)
        audit.record(
            "document.downloaded",
            instance=version.document,
            pme_id=version.document.pme_id,
            after={"version": version.version_no},
        )
        inline = version.extension in (".pdf", ".jpg", ".jpeg", ".png")
        response = HttpResponse(content, content_type=version.mime_detected)
        disposition = "inline" if inline else "attachment"
        safe_name = version.original_filename.replace('"', "").replace("\\", "")
        response["Content-Disposition"] = f'{disposition}; filename="{safe_name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        response["Cache-Control"] = "private, no-store"
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response
