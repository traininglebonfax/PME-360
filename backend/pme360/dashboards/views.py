"""Tableaux de bord — squelette de la phase 1 (Document 9).

Seuls les indicateurs calculables avec les données de la phase 1 sont produits. Les autres blocs sont renvoyés
avec ``available_in_phase`` pour que l'interface affiche un emplacement explicite plutôt qu'un chiffre inventé
(principe « aucune valeur codée en dur », Document 9, § 1).
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.core.permissions import get_access
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme, PmeAssignment

PENDING = {
    "documents_to_verify": 3,
    "alerts_open": 3,
    "diagnostics_to_validate": 2,
    "actions_overdue": 5,
    "deadlines_this_week": 3,
}


def _inactive_q(days: int) -> Q:
    threshold = timezone.now() - timedelta(days=days)
    return Q(last_activity_at__lt=threshold) | Q(last_activity_at__isnull=True, created_at__lt=threshold)


def _breakdown(queryset, field: str, label_field: str | None = None) -> list[dict]:
    values = [field] + ([label_field] if label_field else [])
    rows = queryset.values(*values).annotate(count=Count("id")).order_by("-count")
    return [
        {"key": row[field], "label": row[label_field] if label_field else row[field], "count": row["count"]}
        for row in rows
    ]


def _placeholders() -> dict:
    return {key: {"value": None, "available_in_phase": phase} for key, phase in PENDING.items()}


class AdvisorDashboardView(APIView):
    """« Ma journée » du conseiller : son portefeuille (périmètre) et sa file de travail."""

    required_permissions = "pme.view"

    @extend_schema(responses=dict)
    def get(self, request):
        access = get_access(request)
        organization = Organization.objects.get(pk=access.organization_id)
        inactivity_days = organization.setting("inactivity_days")
        pmes = access.pme_queryset(Pme.objects.all())
        month_start = timezone.localdate().replace(day=1)
        recent = (
            pmes.select_related("sector")
            .order_by("-last_activity_at")[:8]
            .values("id", "legal_name", "lifecycle_status", "sector__name", "last_activity_at")
        )
        return Response(
            {
                "kpis": {
                    "pmes_followed": pmes.count(),
                    "pmes_inactive": pmes.filter(_inactive_q(inactivity_days)).count(),
                    "pmes_onboarded_this_month": pmes.filter(onboarding_started_at__date__gte=month_start).count(),
                    **_placeholders(),
                },
                "by_lifecycle": _breakdown(pmes, "lifecycle_status"),
                "recent_pmes": list(recent),
                "work_queue": {"items": [], "available_in_phase": 3},
                "inactivity_days": inactivity_days,
            }
        )


class PortfolioDashboardView(APIView):
    """Vue d'ensemble programme / direction (Document 9, § 4.1) — indicateurs disponibles en phase 1."""

    required_permissions = "dashboard.portfolio"

    @extend_schema(responses=dict)
    def get(self, request):
        access = get_access(request)
        organization = Organization.objects.get(pk=access.organization_id)
        inactivity_days = organization.setting("inactivity_days")
        pmes = access.pme_queryset(Pme.objects.all())
        month_start = timezone.localdate().replace(day=1)
        accompanied = pmes.filter(lifecycle_status=Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF)
        return Response(
            {
                "kpis": {
                    "pmes_total": pmes.count(),
                    "pmes_new_this_month": pmes.filter(onboarding_started_at__date__gte=month_start).count(),
                    # Provisoire : défini par le plan VALIDÉ/EN_COURS à partir de la phase 5 (Document 9, § 4.1).
                    "pmes_accompanied": accompanied.count(),
                    "pmes_active": pmes.exclude(_inactive_q(inactivity_days)).count(),
                    "pmes_inactive": pmes.filter(_inactive_q(inactivity_days)).count(),
                    "pmes_without_advisor": pmes.exclude(
                        pk__in=PmeAssignment.objects.filter(
                            end_date__isnull=True, role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL
                        ).values("pme_id")
                    ).count(),
                    "average_score": {"value": None, "available_in_phase": 2},
                    "average_progress": {"value": None, "available_in_phase": 2},
                    "average_compliance": {"value": None, "available_in_phase": 3},
                    "pmes_at_risk": {"value": None, "available_in_phase": 2},
                    "pmes_urgent": {"value": None, "available_in_phase": 2},
                },
                "by_lifecycle": _breakdown(pmes, "lifecycle_status"),
                "by_sector": _breakdown(pmes, "sector__code", "sector__name"),
                "by_region": _breakdown(pmes, "region__code", "region__name"),
                "by_size": _breakdown(pmes, "size_category"),
                "inactivity_days": inactivity_days,
            }
        )


class PmeDashboardView(APIView):
    """Accueil du portail PME (Document 9, § 2) : les 4 questions, avec les données disponibles en phase 1."""

    required_permissions = "pme.view"

    @extend_schema(responses=dict)
    def get(self, request, pme_id):
        access = get_access(request)
        pme = get_object_or_404(access.pme_queryset(Pme.objects.select_related("sector", "region")), pk=pme_id)
        principal = (
            PmeAssignment.objects.filter(
                pme=pme, end_date__isnull=True, role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL
            )
            .select_related("user")
            .first()
        )
        return Response(
            {
                "pme": {
                    "id": pme.id,
                    "legal_name": pme.legal_name,
                    "trade_name": pme.trade_name,
                    "lifecycle_status": pme.lifecycle_status,
                    "sector": pme.sector.name if pme.sector else None,
                },
                "advisor": (
                    {
                        "full_name": principal.user.full_name,
                        "email": principal.user.email,
                        "phone": principal.user.phone,
                    }
                    if principal
                    else None
                ),
                "score": {"value": None, "available_in_phase": 2},
                "next_actions": {"items": [], "available_in_phase": 5},
                "compliance": {"value": None, "available_in_phase": 3},
                "feedback": {"items": [], "available_in_phase": 3},
                "deadlines": {"items": [], "available_in_phase": 3},
            }
        )
