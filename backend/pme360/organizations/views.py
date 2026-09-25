from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
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
