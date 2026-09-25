from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.audit.labels import label_for
from pme360.audit.models import AuditLog
from pme360.core.permissions import get_access

from . import services
from .models import LegalForm, Pme, PmeAssignment, PmePerson, Region, Sector
from .serializers import (
    AssignmentCreateSerializer,
    AssignmentSerializer,
    DuplicateQuerySerializer,
    DuplicateSerializer,
    PersonSerializer,
    PmeCreateSerializer,
    PmeListSerializer,
    PmeSerializer,
    RefItemSerializer,
    TimelineEntrySerializer,
    TransitionSerializer,
)

WRITE_FIELDS_EXCLUDED = {"primary_person", "advisor_id", "cohort_id", "confirm_duplicates", "start_onboarding"}


class PmeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """PME du périmètre de l'utilisateur (rôle + périmètre, Document 1, § 6)."""

    http_method_names = ["get", "post", "patch"]
    lookup_value_converter = "uuid"
    filter_backends = [OrderingFilter]
    ordering_fields = ["legal_name", "created_at", "last_activity_at"]
    ordering = ["-created_at"]
    required_permissions = {
        "list": "pme.view",
        "retrieve": "pme.view",
        "create": "pme.create",
        "partial_update": "pme.view",  # pme.update ou pme.update_identity, contrôlé par le service
        "transition": "pme.lifecycle",
        "assignments": "pme.assign",
        "end_assignment": "pme.assign",
        "duplicates": "pme.create",
        "timeline": "pme.view",
    }

    def get_serializer_class(self):
        if self.action == "list":
            return PmeListSerializer
        if self.action == "create":
            return PmeCreateSerializer
        return PmeSerializer

    def get_queryset(self):
        access = get_access(self.request)
        queryset = Pme.objects.select_related("sector", "region", "legal_form").prefetch_related(
            Prefetch(
                "assignments",
                queryset=PmeAssignment.objects.filter(
                    end_date__isnull=True, role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL
                ).select_related("user"),
                to_attr="active_principal",
            )
        )
        queryset = access.pme_queryset(queryset)
        if self.action == "list":
            queryset = self._filter(queryset)
        return queryset

    def _filter(self, queryset):
        params = self.request.query_params
        if q := params.get("q", "").strip():
            queryset = queryset.filter(
                Q(legal_name__icontains=q)
                | Q(trade_name__icontains=q)
                | Q(rccm_number__icontains=q)
                | Q(ncc__icontains=q)
            )
        for param, lookup in (("sector", "sector__code"), ("region", "region__code")):
            if value := params.get(param):
                queryset = queryset.filter(**{lookup: value})
        for param in ("lifecycle_status", "size_category"):
            if value := params.get(param):
                queryset = queryset.filter(**{param: value})
        if advisor := params.get("advisor"):
            advisor_id = self.request.user.pk if advisor == "me" else advisor
            queryset = queryset.filter(
                pk__in=PmeAssignment.objects.filter(user_id=advisor_id, end_date__isnull=True).values("pme_id")
            )
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Recherche : raison sociale, sigle, RCCM, NCC"),
            OpenApiParameter("sector", str, description="Code secteur"),
            OpenApiParameter("region", str, description="Code région"),
            OpenApiParameter("lifecycle_status", str),
            OpenApiParameter("size_category", str),
            OpenApiParameter("advisor", str, description="« me » ou identifiant d'un conseiller"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=PmeCreateSerializer, responses={201: PmeSerializer})
    def create(self, request, *args, **kwargs):
        serializer = PmeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        extras = {key: data.pop(key) for key in list(data) if key in WRITE_FIELDS_EXCLUDED}
        pme = services.create_pme(get_access(request), data, **extras)
        return Response(PmeSerializer(self.get_queryset().get(pk=pme.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=PmeSerializer, responses=PmeSerializer)
    def partial_update(self, request, *args, **kwargs):
        pme = self.get_object()
        serializer = PmeSerializer(pme, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_pme(get_access(request), pme, dict(serializer.validated_data))
        return Response(PmeSerializer(self.get_queryset().get(pk=pme.pk)).data)

    @extend_schema(request=TransitionSerializer, responses=PmeSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        pme = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.transition(pme, data["to"], request.user, reason=data["reason"], exit_reason=data["exit_reason"])
        return Response(PmeSerializer(self.get_queryset().get(pk=pme.pk)).data)

    @extend_schema(request=AssignmentCreateSerializer, responses={201: AssignmentSerializer})
    @action(detail=True, methods=["post"])
    def assignments(self, request, pk=None):
        pme = self.get_object()
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = services.assign_by_id(pme, **serializer.validated_data, user=request.user)
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=AssignmentSerializer)
    @action(detail=True, methods=["post"], url_path="assignments/<uuid:assignment_id>/end")
    def end_assignment(self, request, pk=None, assignment_id=None):
        pme = self.get_object()
        assignment = get_object_or_404(PmeAssignment.objects.select_related("user"), pk=assignment_id, pme=pme)
        services.end_assignment(assignment, request.user)
        return Response(AssignmentSerializer(assignment).data)

    @extend_schema(parameters=[DuplicateQuerySerializer], responses=DuplicateSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def duplicates(self, request):
        query = DuplicateQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(
            DuplicateSerializer(
                services.find_duplicates(**query.validated_data, access=get_access(request)), many=True
            ).data
        )

    @extend_schema(responses=TimelineEntrySerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def timeline(self, request, pk=None):
        pme = self.get_object()
        entries = AuditLog.objects.filter(pme_id=pme.pk).select_related("actor").order_by("-id")[:200]
        data = [
            {
                "id": entry.id,
                "at": entry.at,
                "action": entry.action,
                "label": label_for(entry.action),
                "actor": entry.actor.full_name
                if entry.actor
                else ("Système" if entry.actor_type == "SYSTEM" else None),
                "before": entry.before,
                "after": entry.after,
            }
            for entry in entries
        ]
        return Response(TimelineEntrySerializer(data, many=True).data)


class PmePersonViewSet(viewsets.ModelViewSet):
    """Dirigeants, associés et contacts d'une PME."""

    serializer_class = PersonSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]
    lookup_value_converter = "uuid"
    required_permissions = {"list": "pme.view", "retrieve": "pme.view"}

    def get_pme(self) -> Pme:
        if not hasattr(self, "_pme"):
            access = get_access(self.request)
            self._pme = get_object_or_404(access.pme_queryset(Pme.objects.all()), pk=self.kwargs["pme_pk"])
        return self._pme

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action not in ("list", "retrieve"):
            access = get_access(request)
            if not (access.has("pme.update") or access.has("pme.update_identity")):
                self.permission_denied(request)

    def get_queryset(self):
        return PmePerson.objects.filter(pme=self.get_pme())

    def perform_create(self, serializer):
        serializer.instance = services.add_person(self.get_pme(), dict(serializer.validated_data), self.request.user)

    def perform_update(self, serializer):
        serializer.instance = services.update_person(
            serializer.instance, dict(serializer.validated_data), self.request.user
        )

    def perform_destroy(self, instance):
        services.remove_person(instance)


class ReferenceListView(APIView):
    """Nomenclatures de l'organisation (secteurs, formes juridiques, régions)."""

    models = {"sectors": Sector, "legal-forms": LegalForm, "regions": Region}

    @extend_schema(responses=RefItemSerializer(many=True))
    def get(self, request, kind: str):
        model = self.models.get(kind)
        if model is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(RefItemSerializer(model.objects.filter(is_active=True), many=True).data)
