from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.audit import services as audit
from pme360.core.permissions import IsPlatformAdmin, get_access
from pme360.core.tenancy import system_context

from .models import Organization, Programme
from .serializers import (
    CohortSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
    PlatformOrganizationSerializer,
    ProgrammeSerializer,
)
from .services import create_organization

AUDITED_ORG_FIELDS = ["name", "branding", "settings", "ai_external_allowed"]


class CurrentOrganizationView(APIView):
    """Organisation active de l'utilisateur."""

    required_permissions = {"GET": None, "PATCH": "org.configure"}

    def get_object(self) -> Organization:
        return get_object_or_404(Organization, pk=self.request.organization_id)

    @extend_schema(responses=OrganizationSerializer)
    def get(self, request):
        return Response(OrganizationSerializer(self.get_object()).data)

    @extend_schema(request=OrganizationUpdateSerializer, responses=OrganizationSerializer)
    def patch(self, request):
        organization = self.get_object()
        before = audit.snapshot(organization, AUDITED_ORG_FIELDS)
        serializer = OrganizationUpdateSerializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        changed_before, changed_after = audit.diff(before, audit.snapshot(organization, AUDITED_ORG_FIELDS))
        audit.record("organization.updated", instance=organization, before=changed_before, after=changed_after)
        return Response(OrganizationSerializer(organization).data)


class ProgrammeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProgrammeSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch"]
    lookup_value_converter = "uuid"
    required_permissions = {
        "list": None,
        "retrieve": None,
        "create": "programme.manage",
        "partial_update": "programme.manage",
        "cohorts": None,
    }

    def get_queryset(self):
        return Programme.objects.prefetch_related("cohorts")

    def perform_create(self, serializer):
        programme = serializer.save(created_by=self.request.user)
        audit.record("programme.created", instance=programme, after=serializer.data)

    def perform_update(self, serializer):
        programme = serializer.save(updated_by=self.request.user)
        audit.record("programme.updated", instance=programme, after=serializer.data)

    @extend_schema(request=CohortSerializer, responses=CohortSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def cohorts(self, request, pk=None):
        programme = self.get_object()
        if request.method == "GET":
            return Response(CohortSerializer(programme.cohorts.all(), many=True).data)
        if not get_access(request).has("programme.manage"):
            self.permission_denied(request)
        serializer = CohortSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cohort = serializer.save(programme=programme, created_by=request.user)
        audit.record("cohort.created", instance=cohort, after=serializer.data)
        return Response(CohortSerializer(cohort).data, status=status.HTTP_201_CREATED)


class PlatformOrganizationViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Administration plateforme (SUPER_ADMIN) : création des tenants, sans accès aux contenus métier."""

    serializer_class = PlatformOrganizationSerializer
    permission_classes = [IsPlatformAdmin]
    requires_organization = False
    pagination_class = None

    def list(self, request, *args, **kwargs):
        with system_context():
            data = PlatformOrganizationSerializer(Organization.objects.order_by("name"), many=True).data
        return Response(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = create_organization(
            name=data["name"],
            slug=data["slug"],
            type=data["type"],
            admin_email=data["admin_email"],
            admin_full_name=data["admin_full_name"],
            created_by=request.user,
        )
        with system_context():
            body = PlatformOrganizationSerializer(organization).data
        return Response(body, status=status.HTTP_201_CREATED)


# --- Chiffrement des fichiers par organisation (V1) ------------------------------------------------------------


class KeyVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    retired_at = serializers.DateTimeField(allow_null=True)


class EncryptionStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    algorithm = serializers.CharField()
    active_version = serializers.IntegerField(allow_null=True)
    versions = KeyVersionSerializer(many=True)
    can_rotate = serializers.BooleanField()


def _encryption_payload(request) -> dict:
    from django.conf import settings

    from .models import OrganizationKey

    access = get_access(request)
    versions = list(OrganizationKey.objects.order_by("-version"))
    active = next((k for k in versions if k.status == OrganizationKey.Status.ACTIVE), None)
    return {
        "enabled": settings.PME360_STORAGE_ENCRYPTION,
        "algorithm": "AES-256-GCM, clé propre à l'organisation enveloppée par la clé maîtresse de la plateforme",
        "active_version": active.version if active else None,
        "versions": [
            {"version": k.version, "status": k.status, "created_at": k.created_at, "retired_at": k.retired_at}
            for k in versions
        ],
        "can_rotate": access.has("org.configure") and not access.is_pme_user,
    }


class EncryptionStatusView(APIView):
    """État du chiffrement des fichiers de l'organisation (sans jamais exposer de clé) ; rotation par l'admin."""

    required_permissions = {"GET": None, "POST": "org.configure"}

    @extend_schema(responses=EncryptionStatusSerializer)
    def get(self, request):
        from rest_framework.exceptions import PermissionDenied

        access = get_access(request)
        if not (access.has("audit.view") or access.has("org.configure")) or access.is_pme_user:
            raise PermissionDenied()
        return Response(EncryptionStatusSerializer(_encryption_payload(request)).data)

    @extend_schema(request=None, responses=EncryptionStatusSerializer)
    def post(self, request):
        from rest_framework.exceptions import PermissionDenied

        from . import keys

        access = get_access(request)
        if access.is_pme_user:
            raise PermissionDenied()
        key = keys.create_key(request.organization_id)
        audit.record(
            "organization.key_rotated", entity_type="organization_key", entity_id=key.pk, after={"version": key.version}
        )
        return Response(EncryptionStatusSerializer(_encryption_payload(request)).data)


# --- Identité visuelle (marque blanche, V1) ---------------------------------------------------------------------


class BrandIdentitySerializer(serializers.Serializer):
    product_name = serializers.CharField()
    short_name = serializers.CharField()
    primary_color = serializers.CharField()
    logo = serializers.CharField(allow_null=True)
    tagline = serializers.CharField(allow_blank=True)


class BrandWriteSerializer(serializers.Serializer):
    product_name = serializers.CharField(required=False, allow_blank=True, max_length=40)
    short_name = serializers.CharField(required=False, allow_blank=True, max_length=40)
    tagline = serializers.CharField(required=False, allow_blank=True, max_length=80)
    primary_color = serializers.CharField(required=False, max_length=7)
    logo = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PublicBrandView(APIView):
    """Identité affichée sur la page de connexion (``?org=<slug>``) ; identité neutre si inconnue ou suspendue."""

    permission_classes = [AllowAny]
    requires_organization = False

    @extend_schema(parameters=[OpenApiParameter("org", str)], responses=BrandIdentitySerializer)
    def get(self, request):
        from .branding import DEFAULT_COLOR, DEFAULT_PRODUCT, brand

        slug = (request.query_params.get("org") or "").strip()[:80]
        organization = None
        if slug:
            with system_context():
                organization = Organization.objects.filter(slug=slug, status=Organization.Status.ACTIVE).first()
        if organization is None:
            data = {
                "product_name": DEFAULT_PRODUCT,
                "short_name": "",
                "primary_color": DEFAULT_COLOR,
                "logo": None,
                "tagline": "Connaître · Accompagner · Mesurer",
            }
        else:
            data = brand(organization)
        return Response(BrandIdentitySerializer(data).data)


class BrandingView(APIView):
    """Identité de l'organisation : nom du produit, nom court, couleur, logo (administrateur)."""

    required_permissions = {"GET": None, "PUT": "org.configure"}

    @extend_schema(responses=BrandIdentitySerializer)
    def get(self, request):
        from .branding import brand

        return Response(
            BrandIdentitySerializer(brand(get_object_or_404(Organization, pk=request.organization_id))).data
        )

    @extend_schema(request=BrandWriteSerializer, responses=BrandIdentitySerializer)
    def put(self, request):
        from .branding import brand, validate

        organization = get_object_or_404(Organization, pk=request.organization_id)
        serializer = BrandWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = dict(organization.branding or {})
        organization.branding = validate(serializer.validated_data, before)
        organization.save(update_fields=["branding", "updated_at"])

        def loggable(data: dict) -> dict:  # le logo n'est pas recopié dans le journal (taille)
            return {k: ("(image)" if k == "logo" and v else v) for k, v in data.items()}

        audit.record(
            "organization.branding_updated",
            instance=organization,
            before=loggable(before),
            after=loggable(organization.branding),
        )
        return Response(BrandIdentitySerializer(brand(organization)).data)
