"""API de l'accompagnement : recommandations, plans, actions, catalogue et règles (Document 7)."""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.diagnostic.views import scoped_pme
from pme360.pmes.models import Pme

from . import services
from .models import Action, ActionPlan, DeliverableTemplate, Recommendation, RecommendationRule, SupportOffer
from .serializers import (
    ActionDetailSerializer,
    ActionSerializer,
    ActionTransitionRequestSerializer,
    ActionUpdateSerializer,
    DeliverableTemplateSerializer,
    DependencyRequestSerializer,
    ManualRecommendationSerializer,
    PlanDetailSerializer,
    PlanGenerateSerializer,
    PlanReasonSerializer,
    PlanSerializer,
    PlanTransitionSerializer,
    RecommendationDecisionSerializer,
    RecommendationSerializer,
    RuleSerializer,
    RuleTestResultSerializer,
    RuleWriteSerializer,
    SupportOfferSerializer,
)


def _staff(request) -> None:
    if get_access(request).is_pme_user:
        raise PermissionDenied("Réservé aux équipes d'accompagnement.")


def _context(request) -> dict:
    return {"today": timezone.localdate(), "access": get_access(request)}


def scoped_actions(request):
    access = get_access(request)
    pmes = access.pme_queryset(Pme.objects.all())
    queryset = Action.objects.filter(pme__in=pmes).select_related("plan", "pme", "offer", "advisor_user", "owner_user")
    if access.is_pme_user:
        queryset = queryset.exclude(plan__status__in=[ActionPlan.Status.BROUILLON]).exclude(
            plan__status=ActionPlan.Status.EN_VALIDATION, plan__validated_at__isnull=True
        )
    return queryset


def scoped_plan(request, plan_id) -> ActionPlan:
    access = get_access(request)
    plan = get_object_or_404(
        ActionPlan.objects.filter(pme__in=access.pme_queryset(Pme.objects.all())).select_related("pme"), pk=plan_id
    )
    if access.is_pme_user and not services.plan_visible_to_pme(plan):
        raise NotFound()
    return plan


# --- Recommandations ---------------------------------------------------------------------------------------------


class PmeRecommendationsView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=RecommendationSerializer(many=True))
    def get(self, request, pme_id):
        _staff(request)
        pme = scoped_pme(request, pme_id)
        diagnostic = services.reference_diagnostic(pme)
        queryset = Recommendation.objects.filter(diagnostic=diagnostic).select_related("offer", "decided_by")
        return Response(RecommendationSerializer(queryset, many=True).data)

    @extend_schema(request=None, responses=RecommendationSerializer(many=True))
    def post(self, request, pme_id):
        """(Re)génère les recommandations à partir des règles actives et du score courant."""
        _staff(request)
        if not get_access(request).has("plan.edit"):
            raise PermissionDenied()
        pme = scoped_pme(request, pme_id)
        diagnostic = services.reference_diagnostic(pme)
        recommendations = services.generate_recommendations(diagnostic, request.user)
        return Response(RecommendationSerializer(recommendations, many=True).data)


class ManualRecommendationView(APIView):
    required_permissions = "plan.edit"

    @extend_schema(request=ManualRecommendationSerializer, responses={201: RecommendationSerializer})
    def post(self, request, pme_id):
        _staff(request)
        pme = scoped_pme(request, pme_id)
        serializer = ManualRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.ensure_catalog(services.pme_organization(pme))
        offer = get_object_or_404(SupportOffer.objects.filter(is_active=True), code=data["offer_code"])
        recommendation = services.add_recommendation(
            services.reference_diagnostic(pme),
            get_access(request),
            offer=offer,
            problem=data["problem"],
            rationale=data["rationale"],
        )
        return Response(RecommendationSerializer(recommendation).data, status=status.HTTP_201_CREATED)


class RecommendationDecisionView(APIView):
    required_permissions = "plan.edit"

    @extend_schema(request=RecommendationDecisionSerializer, responses=RecommendationSerializer)
    def post(self, request, recommendation_id):
        _staff(request)
        access = get_access(request)
        recommendation = get_object_or_404(
            Recommendation.objects.filter(pme__in=access.pme_queryset(Pme.objects.all())).select_related(
                "offer", "pme"
            ),
            pk=recommendation_id,
        )
        serializer = RecommendationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        recommendation = services.decide_recommendation(
            recommendation,
            access,
            status=data["status"],
            reason=data["reason"],
            axes={k: data.get(k) for k in ("impact", "urgency", "risk", "effort")},
            priority_reason=data["priority_reason"],
        )
        return Response(RecommendationSerializer(recommendation).data)


# --- Plans -------------------------------------------------------------------------------------------------------


class PmePlanView(APIView):
    """Plan courant de la PME (le plan ouvert, sinon le dernier clos) ; 204 s'il n'y en a pas."""

    required_permissions = "pme.view"

    @extend_schema(responses={200: PlanDetailSerializer, 204: None})
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        access = get_access(request)
        plans = ActionPlan.objects.filter(pme=pme).select_related("pme", "validated_by", "accepted_by")
        plan = plans.filter(status__in=services.OPEN_PLAN).first() or plans.order_by("-version").first()
        if plan is None or (access.is_pme_user and not services.plan_visible_to_pme(plan)):
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(PlanDetailSerializer(plan, context=_context(request)).data)


class PmePlanHistoryView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=PlanSerializer(many=True))
    def get(self, request, pme_id):
        pme = scoped_pme(request, pme_id)
        plans = [
            p
            for p in ActionPlan.objects.filter(pme=pme).order_by("-version")
            if not get_access(request).is_pme_user or services.plan_visible_to_pme(p)
        ]
        return Response(PlanSerializer(plans, many=True).data)


class PlanGenerateView(APIView):
    required_permissions = "plan.edit"

    @extend_schema(request=PlanGenerateSerializer, responses={201: PlanDetailSerializer})
    def post(self, request, pme_id):
        _staff(request)
        pme = scoped_pme(request, pme_id)
        serializer = PlanGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = services.generate_plan(
            pme,
            get_access(request),
            horizon_start=serializer.validated_data.get("horizon_start"),
            title=serializer.validated_data["title"],
        )
        return Response(PlanDetailSerializer(plan, context=_context(request)).data, status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=PlanDetailSerializer)
    def get(self, request, plan_id):
        return Response(PlanDetailSerializer(scoped_plan(request, plan_id), context=_context(request)).data)


class PlanTransitionView(APIView):
    required_permissions = "pme.view"

    @extend_schema(request=PlanTransitionSerializer, responses=PlanDetailSerializer)
    def post(self, request, plan_id):
        plan = scoped_plan(request, plan_id)
        serializer = PlanTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = services.transition_plan(
            plan, get_access(request), serializer.validated_data["action"], serializer.validated_data["reason"]
        )
        return Response(PlanDetailSerializer(plan, context=_context(request)).data)


class PlanNewVersionView(APIView):
    required_permissions = "plan.edit"

    @extend_schema(request=PlanReasonSerializer, responses={201: PlanDetailSerializer})
    def post(self, request, plan_id):
        _staff(request)
        plan = scoped_plan(request, plan_id)
        serializer = PlanReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new = services.new_version(plan, get_access(request), reason=serializer.validated_data["reason"])
        return Response(PlanDetailSerializer(new, context=_context(request)).data, status=status.HTTP_201_CREATED)


# --- Actions -----------------------------------------------------------------------------------------------------


class ActionListView(APIView):
    """Actions du périmètre (« Ma journée » du conseiller, suivi PME) ; filtres : pme, status, overdue."""

    required_permissions = "pme.view"

    @extend_schema(
        parameters=[
            OpenApiParameter("pme", str, required=False),
            OpenApiParameter("status", str, required=False, description="Statuts séparés par des virgules."),
            OpenApiParameter("overdue", bool, required=False),
        ],
        responses=ActionSerializer(many=True),
    )
    def get(self, request):
        queryset = (
            scoped_actions(request)
            .filter(plan__status__in=services.OPEN_PLAN)
            .prefetch_related("deliverables", "dependency_links__depends_on_action")
        )
        if pme := request.query_params.get("pme"):
            queryset = queryset.filter(pme_id=pme)
        if statuses := request.query_params.get("status"):
            queryset = queryset.filter(status__in=statuses.split(","))
        if request.query_params.get("overdue") in ("1", "true"):
            queryset = queryset.filter(due_date__lt=timezone.localdate()).exclude(
                status__in=[*Action.TERMINAL, Action.Status.BLOQUE]
            )
        return Response(
            ActionSerializer(queryset.order_by("due_date")[:200], many=True, context=_context(request)).data
        )


def _action(request, action_id) -> Action:
    return get_object_or_404(
        scoped_actions(request).prefetch_related(
            "deliverables__template",
            "deliverables__document",
            "transitions__actor",
            "dependency_links__depends_on_action",
            "dependent_links__action",
        ),
        pk=action_id,
    )


class ActionDetailView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=ActionDetailSerializer)
    def get(self, request, action_id):
        return Response(ActionDetailSerializer(_action(request, action_id), context=_context(request)).data)

    @extend_schema(request=ActionUpdateSerializer, responses=ActionDetailSerializer)
    def patch(self, request, action_id):
        action = _action(request, action_id)
        serializer = ActionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_action(action, get_access(request), **serializer.validated_data)
        return Response(ActionDetailSerializer(_action(request, action_id), context=_context(request)).data)


class ActionTransitionView(APIView):
    required_permissions = "task.update"

    @extend_schema(request=ActionTransitionRequestSerializer, responses=ActionDetailSerializer)
    def post(self, request, action_id):
        action = _action(request, action_id)
        serializer = ActionTransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.transition_action(
            action, get_access(request), serializer.validated_data["to"], serializer.validated_data["reason"]
        )
        return Response(ActionDetailSerializer(_action(request, action_id), context=_context(request)).data)


class ActionDependencyView(APIView):
    required_permissions = "plan.edit"

    @extend_schema(request=DependencyRequestSerializer, responses=ActionDetailSerializer)
    def post(self, request, action_id):
        _staff(request)
        action = _action(request, action_id)
        serializer = DependencyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        other = get_object_or_404(scoped_actions(request), pk=serializer.validated_data["depends_on"])
        services.add_dependency(action, other, get_access(request))
        return Response(ActionDetailSerializer(_action(request, action_id), context=_context(request)).data)


# --- Catalogue et règles -------------------------------------------------------------------------------------------


class SupportOfferListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=SupportOfferSerializer(many=True))
    def get(self, request):
        _staff(request)
        services.ensure_catalog(services.pme_organization_for(get_access(request)))
        return Response(SupportOfferSerializer(SupportOffer.objects.all(), many=True).data)


class DeliverableTemplateListView(APIView):
    required_permissions = "pme.view"

    @extend_schema(responses=DeliverableTemplateSerializer(many=True))
    def get(self, request):
        return Response(
            DeliverableTemplateSerializer(DeliverableTemplate.objects.filter(is_active=True), many=True).data
        )


class RuleListView(APIView):
    required_permissions = "org.configure"

    @extend_schema(responses=RuleSerializer(many=True))
    def get(self, request):
        return Response(RuleSerializer(RecommendationRule.objects.select_related("offer"), many=True).data)

    @extend_schema(request=RuleWriteSerializer, responses={201: RuleSerializer})
    def post(self, request):
        serializer = RuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = services.save_rule(get_access(request), serializer.validated_data)
        return Response(RuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class RuleTestView(APIView):
    required_permissions = "org.configure"

    @extend_schema(request=None, responses=RuleTestResultSerializer)
    def post(self, request, rule_id):
        rule = get_object_or_404(RecommendationRule.objects.all(), pk=rule_id)
        return Response(RuleTestResultSerializer(services.test_rule(rule, get_access(request))).data)


class RuleStatusView(APIView):
    required_permissions = "org.configure"
    target = ""

    @extend_schema(request=None, responses=RuleSerializer)
    def post(self, request, rule_id):
        target = self.target
        rule = get_object_or_404(RecommendationRule.objects.select_related("offer"), pk=rule_id)
        status_value = {
            "activate": RecommendationRule.Status.ACTIVE,
            "deactivate": RecommendationRule.Status.INACTIVE,
        }.get(target)
        if status_value is None:
            raise NotFound()
        return Response(RuleSerializer(services.set_rule_status(rule, get_access(request), status_value)).data)
