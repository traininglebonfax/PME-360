from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access

from . import defaults, services
from .models import WorkflowDefinition


class WorkflowStateSerializer(serializers.Serializer):
    label = serializers.CharField(allow_blank=True, max_length=60)
    pme_label = serializers.CharField(allow_blank=True, max_length=60)


class WorkflowTransitionSerializer(serializers.Serializer):
    # « from » est un mot réservé en Python : champ déclaré dynamiquement.
    to = serializers.CharField()
    actors = serializers.ListField(child=serializers.ChoiceField(choices=["STAFF", "PME"]))
    reason_required = serializers.BooleanField()
    button = serializers.CharField(allow_blank=True)
    pme_button = serializers.CharField(allow_blank=True, required=False, default="")

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = serializers.CharField()
        return fields


class WorkflowSystemTransitionSerializer(serializers.Serializer):
    to = serializers.CharField()
    trigger = serializers.CharField()

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = serializers.CharField()
        return fields


class ActiveWorkflowSerializer(serializers.Serializer):
    version = serializers.IntegerField(help_text="0 : workflow par défaut.")
    states = serializers.DictField(child=WorkflowStateSerializer())
    transitions = WorkflowTransitionSerializer(many=True)


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    states = serializers.DictField(child=WorkflowStateSerializer())
    transitions = WorkflowTransitionSerializer(many=True)
    activated_by_name = serializers.CharField(source="activated_by.full_name", default=None, read_only=True)

    class Meta:
        model = WorkflowDefinition
        fields = [
            "id",
            "version",
            "status",
            "states",
            "transitions",
            "notes",
            "activated_at",
            "activated_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class HistoryItemSerializer(serializers.ModelSerializer):
    activated_by_name = serializers.CharField(source="activated_by.full_name", default=None, read_only=True)

    class Meta:
        model = WorkflowDefinition
        fields = ["id", "version", "status", "notes", "activated_at", "activated_by_name"]
        read_only_fields = fields


class WorkflowIssuesSerializer(serializers.Serializer):
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())


class WorkflowRulesSerializer(serializers.Serializer):
    terminal = serializers.ListField(child=serializers.CharField())
    system_only_targets = serializers.ListField(child=serializers.CharField())
    pme_targets = serializers.ListField(child=serializers.CharField())
    mandatory_target = serializers.CharField()


class WorkflowAdminSerializer(serializers.Serializer):
    active = ActiveWorkflowSerializer()
    draft = WorkflowDefinitionSerializer(allow_null=True)
    issues = WorkflowIssuesSerializer(allow_null=True)
    history = HistoryItemSerializer(many=True)
    system_transitions = WorkflowSystemTransitionSerializer(many=True)
    rules = WorkflowRulesSerializer()


class DraftWriteSerializer(serializers.Serializer):
    states = serializers.DictField(child=WorkflowStateSerializer(), required=False)
    transitions = WorkflowTransitionSerializer(many=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)


def _target(target: str) -> str:
    if target.upper() != WorkflowDefinition.TargetType.ACTION:
        raise NotFound()
    return target.upper()


def _admin_payload() -> dict:
    active = services.action_workflow()
    draft = services.current_draft()
    issues = None
    if draft is not None:
        errors, warnings = services.check(draft.states, draft.transitions)
        issues = {"errors": errors, "warnings": warnings}
    return {
        "active": {"version": active.version, "states": active.states, "transitions": active.transitions},
        "draft": WorkflowDefinitionSerializer(draft).data if draft else None,
        "issues": issues,
        "history": HistoryItemSerializer(
            WorkflowDefinition.objects.exclude(status=WorkflowDefinition.Status.DRAFT).select_related("activated_by"),
            many=True,
        ).data,
        "system_transitions": defaults.SYSTEM_TRANSITIONS,
        "rules": {
            "terminal": sorted(defaults.TERMINAL),
            "system_only_targets": sorted(defaults.SYSTEM_ONLY_TARGETS),
            "pme_targets": sorted(defaults.PME_TARGETS),
            "mandatory_target": defaults.ABANDON,
        },
    }


class ActiveWorkflowView(APIView):
    """Workflow en vigueur (libellés des états, transitions) : lu par les écrans des actions, PME comprises."""

    @extend_schema(responses=ActiveWorkflowSerializer)
    def get(self, request, target):
        _target(target)
        workflow = services.action_workflow()
        return Response({"version": workflow.version, "states": workflow.states, "transitions": workflow.transitions})


class WorkflowAdminView(APIView):
    required_permissions = "org.configure"

    @extend_schema(responses=WorkflowAdminSerializer)
    def get(self, request, target):
        _target(target)
        return Response(WorkflowAdminSerializer(_admin_payload()).data)


class WorkflowDraftView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=None, responses={201: WorkflowAdminSerializer})
    def post(self, request, target):
        _target(target)
        services.create_draft(get_access(request))
        return Response(WorkflowAdminSerializer(_admin_payload()).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DraftWriteSerializer, responses=WorkflowAdminSerializer)
    def patch(self, request, target):
        _target(target)
        draft = services.current_draft()
        if draft is None:
            raise NotFound("Aucun brouillon.")
        serializer = DraftWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_draft(get_access(request), draft, serializer.validated_data)
        return Response(WorkflowAdminSerializer(_admin_payload()).data)

    @extend_schema(responses={200: WorkflowAdminSerializer})
    def delete(self, request, target):
        _target(target)
        draft = services.current_draft()
        if draft is None:
            raise NotFound("Aucun brouillon.")
        services.delete_draft(get_access(request), draft)
        return Response(WorkflowAdminSerializer(_admin_payload()).data)


class WorkflowActivateView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=None, responses=WorkflowAdminSerializer)
    def post(self, request, target):
        _target(target)
        draft = services.current_draft()
        if draft is None:
            raise NotFound("Aucun brouillon.")
        services.activate(get_access(request), draft)
        return Response(WorkflowAdminSerializer(_admin_payload()).data)
