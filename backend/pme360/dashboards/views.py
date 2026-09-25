"""Tableaux de bord (Document 9) — indicateurs des phases 1 et 2.

Les indicateurs qui dépendent des phases suivantes sont renvoyés avec ``available_in_phase`` pour que l'interface
affiche un emplacement explicite plutôt qu'un chiffre inventé (Document 9, § 1 : « aucune valeur codée en dur »).
Les agrégats de scores portent sur le DERNIER snapshot figé de chaque PME ; ils affichent aussi la confiance
moyenne et la part de PME à confiance faible (Document 9, § 1.5).
"""

from datetime import timedelta
from statistics import mean, median

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

PENDING = {"actions_overdue": 5}
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
                    ],
                    "available_in_phase": 5,  # les actions en retard rejoignent la file en phase 5
                },
                "inactivity_days": inactivity_days,
            }
        )


class PortfolioDashboardView(APIView):
    """Vue d'ensemble programme / direction (Document 9, § 4.1) et analyses de portefeuille (§ 4.2)."""

    required_permissions = "dashboard.portfolio"

    @extend_schema(responses=dict)
    def get(self, request):
        access = get_access(request)
        organization = Organization.objects.get(pk=access.organization_id)
        inactivity_days = organization.setting("inactivity_days")
        pmes = access.pme_queryset(Pme.objects.all())
        month_start = timezone.localdate().replace(day=1)
        accompanied = pmes.filter(lifecycle_status=Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF)
        latest = latest_snapshots(pmes)
        starts = baselines(pmes)
        names = dict(pmes.values_list("id", "legal_name"))
        scored = [s for s in latest.values() if s.global_score is not None]
        scores = [float(s.global_score) for s in scored]
        progress = []
        for pme_id, snapshot in latest.items():
            baseline = starts.get(pme_id)
            if baseline and baseline.pk != snapshot.pk and snapshot.global_score is not None:
                months = (snapshot.reference_date - baseline.reference_date).days / 30.44
                progress.append(
                    {
                        "pme_id": pme_id,
                        "pme_name": names.get(pme_id),
                        "delta": round(float(snapshot.global_score - baseline.global_score), 1),
                        "months": round(months, 1),
                        "from": _f(baseline.global_score),
                        "to": _f(snapshot.global_score),
                    }
                )
        # Problèmes les plus fréquents : part des PME dont la dimension est sous le seuil (dernier snapshot).
        weaknesses: dict[str, dict] = {}
        for snapshot in scored:
            for dimension in snapshot.result.get("dimensions", []):
                if dimension["score"] is None:
                    continue
                entry = weaknesses.setdefault(
                    dimension["code"],
                    {"code": dimension["code"], "name": dimension["short_name"], "weak": 0, "evaluated": 0},
                )
                entry["evaluated"] += 1
                entry["weak"] += dimension["score"] < WEAKNESS_THRESHOLD
        weakness_list = sorted(
            ({**w, "share": round(w["weak"] / w["evaluated"], 3)} for w in weaknesses.values()),
            key=lambda w: -w["share"],
        )
        confidences = [float(s.confidence) for s in scored]
        levels = {}
        for snapshot in scored:
            label = snapshot.result.get("maturity", {}).get("label") or "Non déterminé"
            levels.setdefault(snapshot.maturity_level, {"key": snapshot.maturity_level, "label": label, "count": 0})
            levels[snapshot.maturity_level]["count"] += 1
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
                    "pmes_diagnosed": len(scored),
                    "average_score": round(mean(scores), 1) if scores else None,
                    "median_score": round(median(scores), 1) if scores else None,
                    "average_progress": round(mean(p["delta"] for p in progress), 1) if progress else None,
                    "average_confidence": round(mean(confidences), 3) if confidences else None,
                    "low_confidence_share": round(sum(c < 0.5 for c in confidences) / len(confidences), 3)
                    if confidences
                    else None,
                    "pmes_at_risk": sum(1 for s in scored if s.risk_index is not None and s.risk_index >= 50),
                    "pmes_urgent": sum(1 for s in scored if s.intervention_priority == "P1"),
                    "average_compliance": average_compliance(pmes),
                },
                "by_lifecycle": _breakdown(pmes, "lifecycle_status"),
                "by_sector": _breakdown(pmes, "sector__code", "sector__name"),
                "by_region": _breakdown(pmes, "region__code", "region__name"),
                "by_size": _breakdown(pmes, "size_category"),
                "by_maturity": sorted(levels.values(), key=lambda item: item["key"] or 0),
                "by_priority": [
                    {"key": p, "label": p, "count": sum(1 for s in scored if s.intervention_priority == p)}
                    for p in ("P1", "P2", "P3", "P4")
                ],
                "weaknesses": weakness_list,
                "weakness_threshold": WEAKNESS_THRESHOLD,
                "progress": {
                    "top": sorted(progress, key=lambda p: -p["delta"])[:5],
                    "stagnating": [p for p in progress if p["months"] >= 6 and p["delta"] < STAGNATION_POINTS],
                },
                "urgent": [
                    {
                        "pme_id": s.pme_id,
                        "pme_name": names.get(s.pme_id),
                        "global_score": _f(s.global_score),
                        "risk_index": _f(s.risk_index),
                    }
                    for s in scored
                    if s.intervention_priority == "P1"
                ],
                "inactivity_days": inactivity_days,
                "min_cell": MIN_CELL,
            }
        )


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
                "next_actions": {"items": [], "available_in_phase": 5},
                "compliance": compliance.compliance_rate(pme),
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
