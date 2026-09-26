"""Tableaux de bord (Document 9) — indicateurs des phases 1 et 2.

Les indicateurs qui dépendent des phases suivantes sont renvoyés avec ``available_in_phase`` pour que l'interface
affiche un emplacement explicite plutôt qu'un chiffre inventé (Document 9, § 1 : « aucune valeur codée en dur »).
Les agrégats de scores portent sur le DERNIER snapshot figé de chaque PME ; ils affichent aussi la confiance
moyenne et la part de PME à confiance faible (Document 9, § 1.5).
"""

from datetime import timedelta
from statistics import mean

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.alerts.models import Alert
from pme360.compliance import services as compliance
from pme360.compliance.models import Deadline
from pme360.core.permissions import get_access
from pme360.diagnostic.models import Diagnostic
from pme360.documents.models import Document
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme, PmeAssignment
from pme360.scoring.models import ScoreSnapshot

PENDING: dict[str, int] = {}  # tous les indicateurs des phases 1 à 5 sont disponibles
WEAKNESS_THRESHOLD = 50  # « problème » = dimension sous 50/100 (paramètre d'affichage, Document 9, § 4.2)
STAGNATION_POINTS = 2  # < +2 points en 6 mois (Document 6, § 6)
MIN_CELL = 5  # cellules masquées si n < 5 (Document 9, § 4.2)


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


def next_actions(pme) -> dict:
    """Plan de la PME : prochaines actions ouvertes (échéance la plus proche d'abord) et plan à accepter."""
    from pme360.plans.models import Action, ActionPlan
    from pme360.plans.services import OPEN_PLAN, plan_visible_to_pme

    plan = ActionPlan.objects.filter(pme=pme, status__in=OPEN_PLAN).first()
    if plan is None or not plan_visible_to_pme(plan):
        return {"plan": None, "items": []}
    today = timezone.localdate()
    actions = plan.actions.exclude(status__in=Action.TERMINAL).order_by("due_date")[:5]
    statuses = list(plan.actions.values_list("status", flat=True))
    return {
        "plan": {
            "id": plan.pk,
            "status": plan.status,
            "to_accept": plan.status == ActionPlan.Status.EN_VALIDATION,
            "done": statuses.count(Action.Status.TERMINE),
            "in_progress": sum(1 for status in statuses if status not in (*Action.TERMINAL, Action.Status.BLOQUE)),
            "overdue": plan.actions.filter(due_date__lt=today)
            .exclude(status__in=[*Action.TERMINAL, Action.Status.BLOQUE])
            .count(),
            "total": len(statuses),
        },
        "items": [
            {
                "id": a.pk,
                "human_ref": a.human_ref,
                "title": a.title,
                "status": a.status,
                "due_date": a.due_date,
                "overdue": a.due_date < today and a.status != Action.Status.BLOQUE,
            }
            for a in actions
        ],
    }


def evolution(baseline, current) -> list[dict]:
    """« Mon évolution » : score de chaque dimension au diagnostic initial et aujourd'hui (Document 9, § 2)."""
    if baseline is None or current is None:
        return []
    initial = {d["code"]: d.get("score") for d in baseline.result.get("dimensions", [])}
    return [
        {
            "code": d["code"],
            "name": d.get("short_name") or d["name"],
            "initial": initial.get(d["code"]),
            "current": d.get("score"),
        }
        for d in current.result.get("dimensions", [])
    ]


def quadrant_thresholds() -> dict:
    """Seuils IMO / IPE des quadrants maturité × performance du référentiel publié (Document 6, § 4)."""
    from pme360.diagnostic.models import FrameworkVersion

    version = FrameworkVersion.objects.filter(status=FrameworkVersion.Status.PUBLISHED).first()
    return (version.settings if version else {}).get("quadrants", {"imo_threshold": 55, "ipe_threshold": 60})


def latest_snapshots(pmes) -> dict:
    """Dernier snapshot figé de chaque PME du périmètre (DISTINCT ON PostgreSQL)."""
    snapshots = (
        ScoreSnapshot.objects.filter(pme__in=pmes, is_frozen=True)
        .order_by("pme_id", "-reference_date", "-computed_at")
        .distinct("pme_id")
    )
    return {s.pme_id: s for s in snapshots}


def baselines(pmes) -> dict:
    return {
        s.pme_id: s
        for s in ScoreSnapshot.objects.filter(pme__in=pmes, kind=ScoreSnapshot.Kind.BASELINE, is_frozen=True)
    }


def _f(value) -> float | None:
    return None if value is None else float(value)


def average_compliance(pmes) -> dict:
    rates = [r for r in (compliance.compliance_rate(p)["rate"] for p in pmes) if r is not None]
    return {"value": round(mean(rates), 3) if rates else None, "pmes": len(rates)}


def score_summary(snapshot: ScoreSnapshot | None, baseline: ScoreSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    delta = None
    if (
        baseline
        and baseline.pk != snapshot.pk
        and snapshot.global_score is not None
        and baseline.global_score is not None
    ):
        delta = round(float(snapshot.global_score - baseline.global_score), 1)
    return {
        "global_score": _f(snapshot.global_score),
        "maturity_level": snapshot.maturity_level,
        "maturity_label": snapshot.result.get("maturity", {}).get("label"),
        "confidence": _f(snapshot.confidence),
        "confidence_label": snapshot.result.get("confidence_label"),
        "priority": snapshot.intervention_priority,
        "reference_date": snapshot.reference_date,
        "delta_since_baseline": delta,
        "baseline_date": baseline.reference_date if baseline else None,
    }


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
        latest = latest_snapshots(pmes)
        recent = list(
            pmes.select_related("sector")
            .order_by("-last_activity_at")[:8]
            .values("id", "legal_name", "lifecycle_status", "sector__name", "last_activity_at")
        )
        for row in recent:
            snapshot = latest.get(row["id"])
            row["global_score"] = _f(snapshot.global_score) if snapshot else None
            row["priority"] = snapshot.intervention_priority if snapshot else None
        diagnostics = Diagnostic.objects.filter(pme__in=pmes)
        today = timezone.localdate()
        documents_to_verify = list(
            Document.objects.filter(pme__in=pmes, verification_status=Document.Verification.VERIF_HUMAINE_REQUISE)
            .order_by("updated_at")
            .values("id", "pme_id", "pme__legal_name", "title", "updated_at")
        )
        open_alerts = Alert.objects.filter(pme__in=pmes, status__in=Alert.OPEN)
        overdue = list(
            Deadline.objects.filter(pme__in=pmes, status=Deadline.Status.EN_RETARD)
            .order_by("due_date")
            .values("id", "pme_id", "pme__legal_name", "period_label", "due_date", "pme_obligation__template__name")[
                :20
            ]
        )
        from pme360.plans.models import Action, ActionPlan

        live_actions = Action.objects.filter(
            pme__in=pmes, plan__status__in=[ActionPlan.Status.VALIDE, ActionPlan.Status.EN_COURS]
        )
        overdue_actions = list(
            live_actions.filter(due_date__lt=today)
            .exclude(status__in=[*Action.TERMINAL, Action.Status.BLOQUE])
            .order_by("due_date")
            .values("id", "pme_id", "pme__legal_name", "human_ref", "title", "due_date")[:20]
        )
        to_validate = list(
            diagnostics.filter(status=Diagnostic.Status.EN_REVUE)
            .select_related("pme")
            .order_by("submitted_at")
            .values("id", "pme_id", "pme__legal_name", "type", "submitted_at")
        )
        return Response(
            {
                "kpis": {
                    "pmes_followed": pmes.count(),
                    "pmes_inactive": pmes.filter(_inactive_q(inactivity_days)).count(),
                    "pmes_onboarded_this_month": pmes.filter(onboarding_started_at__date__gte=month_start).count(),
                    "diagnostics_to_validate": len(to_validate),
                    "diagnostics_in_progress": diagnostics.filter(status=Diagnostic.Status.EN_COLLECTE).count(),
                    "pmes_urgent": sum(1 for s in latest.values() if s.intervention_priority == "P1"),
                    "documents_to_verify": len(documents_to_verify),
                    "alerts_open": open_alerts.count(),
                    "alerts_critical": open_alerts.filter(severity__in=["ELEVEE", "CRITIQUE"]).count(),
                    "deadlines_this_week": Deadline.objects.filter(
                        pme__in=pmes,
                        status__in=Deadline.OPEN,
                        due_date__gte=today,
                        due_date__lte=today + timedelta(days=7),
                    ).count(),
                    "deadlines_overdue": Deadline.objects.filter(
                        pme__in=pmes, status=Deadline.Status.EN_RETARD
                    ).count(),
                    "actions_overdue": live_actions.filter(due_date__lt=today)
                    .exclude(status__in=[*Action.TERMINAL, Action.Status.BLOQUE])
                    .count(),
                    "actions_to_verify": live_actions.filter(status=Action.Status.A_VERIFIER).count(),
                    **_placeholders(),
                },
                "by_lifecycle": _breakdown(pmes, "lifecycle_status"),
                "recent_pmes": recent,
                "work_queue": {
                    # Tri par urgence (Document 9, § 3) : alertes graves, documents, diagnostics, retards.
                    "items": [
                        *[
                            {
                                "kind": "ALERTE",
                                "id": a.pk,
                                "pme_id": a.pme_id,
                                "pme_name": a.pme.legal_name,
                                "label": a.title,
                                "severity": a.severity,
                                "since": a.created_at,
                            }
                            for a in open_alerts.filter(
                                severity__in=["ELEVEE", "CRITIQUE"], status=Alert.Status.OUVERTE
                            )
                            .select_related("pme")
                            .order_by("created_at")[:20]
                        ],
                        *[
                            {
                                "kind": "DOCUMENT_A_VERIFIER",
                                "id": d["id"],
                                "pme_id": d["pme_id"],
                                "pme_name": d["pme__legal_name"],
                                "label": d["title"],
                                "since": d["updated_at"],
                            }
                            for d in documents_to_verify
                        ],
                        *[
                            {
                                "kind": "DIAGNOSTIC_A_VALIDER",
                                "id": d["id"],
                                "pme_id": d["pme_id"],
                                "pme_name": d["pme__legal_name"],
                                "label": d["type"],
                                "since": d["submitted_at"],
                            }
                            for d in to_validate
                        ],
                        *[
                            {
                                "kind": "ECHEANCE_EN_RETARD",
                                "id": d["id"],
                                "pme_id": d["pme_id"],
                                "pme_name": d["pme__legal_name"],
                                "label": f"{d['pme_obligation__template__name']} ({d['period_label']})",
                                "since": d["due_date"],
                            }
                            for d in overdue
                        ],
                        *[
                            {
                                "kind": "ACTION_EN_RETARD",
                                "id": a["id"],
                                "pme_id": a["pme_id"],
                                "pme_name": a["pme__legal_name"],
                                "label": f"{a['human_ref']} — {a['title']}",
                                "since": a["due_date"],
                            }
                            for a in overdue_actions
                        ],
                    ],
                },
                "inactivity_days": inactivity_days,
            }
        )


class PortfolioDashboardView(APIView):
    """Vue d'ensemble programme / direction (Document 9, § 4.1) et analyses de portefeuille (§ 4.2)."""

    required_permissions = "dashboard.portfolio"

    @extend_schema(responses=dict)
    def get(self, request):
        return Response(portfolio_overview(get_access(request)))


def portfolio_overview(access) -> dict:
    """Indicateurs et analyses du portefeuille visible par ``access`` (tableau de bord, Copilot).

    Tous les chiffres viennent des vues analytiques (Document 9, § 1.4) via ``pme360.analytics.portfolio``.
    """
    from pme360.analytics import portfolio, services

    organization = Organization.objects.get(pk=access.organization_id)
    problems = portfolio.frequent_problems(access)
    trajectories = portfolio.trajectories(access)
    return {
        "kpis": portfolio.overview(access),
        **portfolio.breakdowns(access),
        "weaknesses": problems["dimensions"],
        "weakness_threshold": problems["threshold"],
        "progress": {"top": trajectories["top"], "stagnating": trajectories["stagnating"]},
        "urgent": [
            {
                "pme_id": item["pme_id"],
                "pme_name": item["pme_name"],
                "global_score": item["global_score"],
                "risk_index": item["risk_index"],
            }
            for item in portfolio.reinforced_support(access)
            if item["priority"] == "P1"
        ],
        "definitions": portfolio.DEFINITIONS,
        "quadrant_thresholds": quadrant_thresholds(),
        "refreshed_at": services.freshness(),
        "inactivity_days": organization.setting("inactivity_days"),
        "min_cell": MIN_CELL,
    }


class PortfolioAnalysesView(APIView):
    """Analyses de portefeuille (Document 9, § 4.2) : problèmes fréquents, besoins, secteurs, trajectoires."""

    required_permissions = "dashboard.portfolio"

    @extend_schema(responses=dict)
    def get(self, request):
        from pme360.analytics import portfolio, services

        access = get_access(request)
        return Response(
            {
                "frequent_problems": portfolio.frequent_problems(access),
                "demanded_offers": portfolio.demanded_offers(access),
                "sector_heatmap": portfolio.sector_heatmap(access),
                "trajectories": portfolio.trajectories(access),
                "reinforced_support": portfolio.reinforced_support(access),
                "offer_effectiveness": portfolio.offer_effectiveness(access),
                "refreshed_at": services.freshness(),
            }
        )


PORTFOLIO_COLUMNS = [
    ("legal_name", "PME"),
    ("sector_name", "Secteur"),
    ("region_name", "Région"),
    ("maturity_level", "Niveau"),
    ("current_score", "Score"),
    ("trend_6m", "Tendance 6 mois"),
    ("confidence", "Confiance"),
    ("compliance_rate", "Conformité"),
    ("risk_index", "Risque"),
    ("intervention_priority", "Priorité"),
    ("actions_overdue", "Actions en retard"),
    ("last_activity_at", "Dernière activité"),
]


def portfolio_rows(access) -> list[dict]:
    """Tableau du portefeuille (Document 9, § 3) : une ligne par PME du périmètre."""
    from pme360.analytics import services

    today = timezone.localdate()
    since = today - timedelta(days=183)
    history: dict = {}
    pmes = access.pme_queryset(Pme.objects.all())
    for pme_id, score in (
        ScoreSnapshot.objects.filter(pme__in=pmes, is_frozen=True, reference_date__lte=since)
        .order_by("pme_id", "-reference_date")
        .values_list("pme_id", "global_score")
    ):
        history.setdefault(pme_id, score)
    by_id = {p.pk: p for p in pmes}
    rows = []
    for state in services.current_states(access):
        score = _f(state["current_score"])
        past = history.get(state["pme_id"])
        pme = by_id.get(state["pme_id"])
        rows.append(
            {
                "pme_id": state["pme_id"],
                "legal_name": state["legal_name"],
                "sector_name": state["sector_name"],
                "region_name": state["region_name"],
                "size_category": state["size_category"],
                "lifecycle_status": state["lifecycle_status"],
                "maturity_level": state["maturity_level"],
                "maturity_label": state["maturity_label"],
                "current_score": score,
                "trend_6m": round(score - float(past), 1) if score is not None and past is not None else None,
                "imo": _f(state["imo"]),
                "ipe": _f(state["ipe"]),
                "quadrant": state["quadrant"],
                "confidence": _f(state["confidence"]),
                "compliance_rate": compliance.compliance_rate(pme, today)["rate"] if pme else None,
                "risk_index": _f(state["risk_index"]),
                "intervention_priority": state["intervention_priority"],
                "actions_overdue": state["actions_overdue"],
                "alerts_high": state["alerts_high"],
                "last_activity_at": state["last_activity_at"],
            }
        )
    return rows


class PortfolioPmesView(APIView):
    """Tableau du portefeuille, filtrable côté interface ; ``?format=csv`` pour l'export."""

    required_permissions = "pme.view"

    @extend_schema(responses=dict)
    def get(self, request):
        import csv
        import io

        from django.http import HttpResponse

        access = get_access(request)
        if access.is_pme_user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied()
        rows = portfolio_rows(access)
        if request.query_params.get("export") == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter=";")
            writer.writerow([label for _, label in PORTFOLIO_COLUMNS])
            for row in rows:
                writer.writerow(["" if row[key] is None else row[key] for key, _ in PORTFOLIO_COLUMNS])
            response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="portefeuille-{timezone.localdate()}.csv"'
            return response
        return Response(rows)


class PmeDashboardView(APIView):
    """Accueil du portail PME (Document 9, § 2) : où j'en suis, que faire, retours, échéances."""

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
        live = ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE).first()
        snapshot = latest_snapshots(Pme.objects.filter(pk=pme.pk)).get(pme.pk)
        if live and snapshot and live.result.get("source_diagnostic") == str(snapshot.diagnostic_id):
            snapshot = live  # score courant : tient compte des preuves vérifiées depuis la validation
        baseline = baselines(Pme.objects.filter(pk=pme.pk)).get(pme.pk)
        open_diagnostic = (
            Diagnostic.objects.filter(pme=pme)
            .exclude(status__in=[Diagnostic.Status.VALIDE, Diagnostic.Status.ANNULE])
            .values("id", "type", "status", "reference_date")
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
                "score": score_summary(snapshot, baseline),
                "open_diagnostic": open_diagnostic,
                "next_actions": next_actions(pme),
                "compliance": compliance.compliance_rate(pme),
                "evolution": evolution(baseline, snapshot),
                "feedback": [
                    {
                        "id": d.pk,
                        "title": d.title,
                        "status": d.status_display,
                        "reason": d.decision_reason,
                        "decided_at": d.verified_at,
                    }
                    for d in Document.objects.filter(pme=pme, verified_at__isnull=False).order_by("-verified_at")[:5]
                ],
                "deadlines": [
                    {
                        "id": d.pk,
                        "label": d.pme_obligation.template.document_type.name,
                        "period": d.period_label,
                        "due_date": d.due_date,
                        "status": d.status,
                        "document_type": d.pme_obligation.template.document_type.code,
                    }
                    for d in Deadline.objects.filter(pme=pme, status__in=Deadline.OPEN)
                    .select_related("pme_obligation__template__document_type")
                    .order_by("due_date")[:10]
                ],
            }
        )
