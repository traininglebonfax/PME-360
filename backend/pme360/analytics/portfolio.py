"""Indicateurs et analyses de portefeuille (Document 9, § 4) calculés à partir des vues analytiques.

Chaque KPI suit la définition exacte du Document 9, § 4.1. Les analyses d'évolution décrivent des évolutions
observées et n'attribuent aucune cause (RM-09).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median

from django.db.models import Count
from django.utils import timezone

from . import services

WEAKNESS_THRESHOLD = 50  # « problème » = score < 50/100 (paramètre d'affichage, Document 9, § 4.2)
WEAK_LEVEL = 1  # critères au niveau ≤ 1
STAGNATION_POINTS = 2  # < +2 points en 6 mois (Document 6, § 6)
STAGNATION_MONTHS = 6
PROGRESS_MIN_MONTHS = 3  # progression moyenne : PME accompagnées depuis ≥ 3 mois
RISK_THRESHOLD = 50
MIN_CELL = 5  # cellules masquées si n < 5 (Document 9, § 4.2)

RM09 = (
    "Évolutions observées chez les PME accompagnées : elles ne prouvent pas, à elles seules, l'effet de "
    "l'accompagnement (sélection des PME, gain de preuve, conjoncture)."
)

# Définitions affichées en info-bulle (Document 9, § 1.2 : aucun chiffre sans définition).
DEFINITIONS = {
    "pmes_total": "PME non supprimées du périmètre (organisation, programme ou portefeuille).",
    "pmes_new_this_month": "PME dont l'intégration a commencé ce mois-ci.",
    "pmes_accompanied": "PME ayant un plan d'accompagnement validé ou en cours.",
    "pmes_active": "PME avec une activité significative depuis moins de N jours (60 par défaut).",
    "average_score": "Moyenne du score global courant (preuves vérifiées incluses) des PME diagnostiquées ; "
    "la médiane est aussi indiquée.",
    "average_progress": "Moyenne de (score courant − score initial) des PME accompagnées depuis au moins 3 mois.",
    "average_compliance": "Moyenne des taux de conformité documentaire.",
    "pmes_at_risk": f"PME dont l'exposition au risque est d'au moins {RISK_THRESHOLD}/100.",
    "pmes_urgent": "PME en priorité d'intervention P1.",
    "pmes_without_advisor": "PME sans conseiller principal assigné.",
    "pmes_late": "PME ayant au moins une action ou une obligation en retard.",
    "actions_done": "Actions terminées dans les plans validés, en cours ou clos.",
    "actions_overdue": "Actions dont l'échéance est dépassée et qui ne sont ni terminées ni abandonnées.",
    "average_confidence": "Confiance moyenne des scores ; la part à confiance faible (< 50 %) est indiquée.",
}


def _f(value) -> float | None:
    return None if value is None else float(value)


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def overview(access, today: date | None = None) -> dict:
    """KPI de la vue d'ensemble (Document 9, § 4.1)."""
    from pme360.compliance import services as compliance
    from pme360.compliance.models import Deadline
    from pme360.organizations.models import Organization
    from pme360.pmes.models import Pme, PmeAssignment

    today = today or timezone.localdate()
    organization = Organization.objects.get(pk=access.organization_id)
    inactivity_days = organization.setting("inactivity_days")
    states = services.current_states(access)
    scored = [s for s in states if s["current_score"] is not None]
    scores = [float(s["current_score"]) for s in scored]
    confidences = [float(s["confidence"]) for s in scored if s["confidence"] is not None]
    trajectories = {str(t["pme_id"]): t for t in services.trajectories(access)}
    progress = [
        float(t["delta_current"])
        for s in states
        if s["accompanied"]
        and (t := trajectories.get(str(s["pme_id"])))
        and t["delta_current"] is not None
        and (today - t["baseline_date"]).days / 30.44 >= PROGRESS_MIN_MONTHS
    ]
    threshold = timezone.now() - timedelta(days=inactivity_days)

    def inactive(state) -> bool:
        return state["last_activity_at"] is None or state["last_activity_at"] < threshold

    late_obligations = set(
        Deadline.objects.filter(pme_id__in=[s["pme_id"] for s in states], status=Deadline.Status.EN_RETARD)
        .values_list("pme_id", flat=True)
        .distinct()
    )
    rates = [
        r
        for r in (compliance.compliance_rate(p, today)["rate"] for p in access.pme_queryset(Pme.objects.all()))
        if r is not None
    ]
    month_start = today.replace(day=1)
    return {
        "pmes_total": len(states),
        "pmes_new_this_month": sum(
            1 for s in states if s["onboarding_started_at"] and s["onboarding_started_at"].date() >= month_start
        ),
        "pmes_accompanied": sum(1 for s in states if s["accompanied"]),
        "pmes_active": sum(1 for s in states if not inactive(s)),
        "pmes_inactive": sum(1 for s in states if inactive(s)),
        "pmes_without_advisor": access.pme_queryset(Pme.objects.all())
        .exclude(
            pk__in=PmeAssignment.objects.filter(
                end_date__isnull=True, role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL
            ).values("pme_id")
        )
        .count(),
        "pmes_diagnosed": len(scored),
        "average_score": _round(mean(scores)) if scores else None,
        "median_score": _round(median(scores)) if scores else None,
        "average_progress": _round(mean(progress)) if progress else None,
        "progress_pmes": len(progress),
        "average_confidence": _round(mean(confidences), 3) if confidences else None,
        "low_confidence_share": _round(sum(c < 0.5 for c in confidences) / len(confidences), 3)
        if confidences
        else None,
        "pmes_at_risk": sum(1 for s in scored if s["risk_index"] is not None and s["risk_index"] >= RISK_THRESHOLD),
        "pmes_urgent": sum(1 for s in scored if s["intervention_priority"] == "P1"),
        "pmes_late": sum(1 for s in states if s["actions_overdue"] or s["pme_id"] in late_obligations),
        "actions_done": sum(s["actions_done"] for s in states),
        "actions_overdue": sum(s["actions_overdue"] for s in states),
        "average_compliance": {"value": _round(mean(rates), 3) if rates else None, "pmes": len(rates)},
    }


def breakdowns(access) -> dict:
    states = services.current_states(access)
    scored = [s for s in states if s["current_score"] is not None]

    def count(items, key, label=None):
        result: dict = {}
        for item in items:
            k = item[key]
            entry = result.setdefault(k, {"key": k, "label": item[label] if label else k, "count": 0})
            entry["count"] += 1
        return sorted(result.values(), key=lambda e: -e["count"])

    levels: dict = {}
    for s in scored:
        entry = levels.setdefault(
            s["maturity_level"],
            {"key": s["maturity_level"], "label": s["maturity_label"] or "Non déterminé", "count": 0},
        )
        entry["count"] += 1
    accompanied = [s for s in states if s["accompanied"]]
    return {
        "by_lifecycle": count(states, "lifecycle_status"),
        "by_sector": count(states, "sector_code", "sector_name"),
        "by_region": count(states, "region_code", "region_name"),
        "by_size": count(states, "size_category"),
        "by_maturity": sorted(levels.values(), key=lambda e: e["key"] or 0),
        "by_priority": [
            {"key": p, "label": p, "count": sum(1 for s in scored if s["intervention_priority"] == p)}
            for p in ("P1", "P2", "P3", "P4")
        ],
        "accompanied_by_sector": count(accompanied, "sector_code", "sector_name"),
        "accompanied_by_region": count(accompanied, "region_code", "region_name"),
        "accompanied_by_size": count(accompanied, "size_category"),
    }


def frequent_problems(access, threshold: float = WEAKNESS_THRESHOLD) -> dict:
    """Analyse 1 — problèmes les plus fréquents : % des PME sous le seuil par dimension ; critères au niveau ≤ 1."""
    dims: dict[str, dict] = {}
    for row in services.weaknesses(access, "DIMENSION"):
        entry = dims.setdefault(row["code"], {"code": row["code"], "name": row["name"], "weak": 0, "evaluated": 0})
        entry["evaluated"] += 1
        entry["weak"] += float(row["score"]) < threshold
    criteria: dict[str, dict] = {}
    for row in services.weaknesses(access, "CRITERE"):
        entry = criteria.setdefault(row["code"], {"code": row["code"], "name": row["name"], "weak": 0, "evaluated": 0})
        entry["evaluated"] += 1
        entry["weak"] += row["level"] is not None and row["level"] <= WEAK_LEVEL
    for entry in [*dims.values(), *criteria.values()]:
        entry["share"] = round(entry["weak"] / entry["evaluated"], 3)
    return {
        "threshold": threshold,
        "weak_level": WEAK_LEVEL,
        "dimensions": sorted(dims.values(), key=lambda e: (-e["share"], e["code"])),
        "criteria": sorted(
            (c for c in criteria.values() if c["weak"]), key=lambda e: (-e["weak"], -e["share"], e["code"])
        )[:10],
    }


def demanded_offers(access) -> list[dict]:
    """Analyse 2 — accompagnements les plus demandés : recommandations acceptées (ou au plan) par offre."""
    from pme360.plans.models import Recommendation
    from pme360.pmes.models import Pme

    rows = (
        Recommendation.objects.filter(
            pme__in=access.pme_queryset(Pme.objects.all()),
            status__in=[Recommendation.Status.ACCEPTEE, Recommendation.Status.CONVERTIE],
        )
        .values("offer__code", "offer__title", "offer__dimension_code")
        .annotate(count=Count("pme", distinct=True))
        .order_by("-count", "offer__code")
    )
    return [
        {
            "code": r["offer__code"],
            "title": r["offer__title"],
            "dimension": r["offer__dimension_code"],
            "pmes": r["count"],
        }
        for r in rows
    ]


def sector_heatmap(access, min_cell: int = MIN_CELL) -> dict:
    """Analyse 3 — secteurs en difficulté : score moyen secteur × dimension, cellules masquées si n < min_cell."""
    cells: dict[tuple, list[float]] = defaultdict(list)
    sectors: dict[str, str] = {}
    dimensions: dict[str, str] = {}
    for row in services.weaknesses(access, "DIMENSION"):
        sector = row["sector_code"] or "NON_RENSEIGNE"
        sectors[sector] = row["sector_name"] or "Secteur non renseigné"
        dimensions[row["code"]] = row["name"]
        cells[(sector, row["code"])].append(float(row["score"]))
    return {
        "min_cell": min_cell,
        "sectors": [{"code": code, "name": name} for code, name in sorted(sectors.items(), key=lambda i: i[1])],
        "dimensions": [{"code": code, "name": name} for code, name in sorted(dimensions.items())],
        "cells": [
            {
                "sector": sector,
                "dimension": dimension,
                "n": len(values),
                "average": round(mean(values), 1) if len(values) >= min_cell else None,
            }
            for (sector, dimension), values in sorted(cells.items())
        ],
    }


def trajectories(access, today: date | None = None) -> dict:
    """PME qui progressent / stagnent (Document 9, § 4.2) : écarts entre le diagnostic initial et le dernier."""
    rows = services.trajectories(access)
    moved = [r for r in rows if r["delta"] is not None]
    items = [
        {
            "pme_id": r["pme_id"],
            "pme_name": r["pme_name"],
            "delta": round(float(r["delta"]), 1),
            "months": _f(r["months"]),
            "from": _f(r["baseline_score"]),
            "to": _f(r["last_score"]),
            "current": _f(r["current_score"]),
        }
        for r in moved
    ]
    buckets = [
        (-100, -5, "Recul de plus de 5 points"),
        (-5, 2, "Stable (moins de +2)"),
        (2, 10, "+2 à +10"),
        (10, 101, "Plus de +10"),
    ]
    return {
        "top": sorted(items, key=lambda i: -i["delta"])[:5],
        "stagnating": [i for i in items if (i["months"] or 0) >= STAGNATION_MONTHS and i["delta"] < STAGNATION_POINTS],
        "distribution": [
            {"label": label, "count": sum(1 for i in items if low <= i["delta"] < high)} for low, high, label in buckets
        ],
        "measured": len(items),
        "notice": RM09,
    }


def reinforced_support(access) -> list[dict]:
    """PME nécessitant un accompagnement renforcé (P1 / P2) avec le motif de la règle de priorité."""
    from pme360.scoring.models import ScoreSnapshot

    states = [s for s in services.current_states(access) if s["intervention_priority"] in ("P1", "P2")]
    reasons = {
        str(pk): result.get("priority", {}).get("label")
        for pk, result in ScoreSnapshot.objects.filter(pk__in=[s["current_snapshot_id"] for s in states]).values_list(
            "pk", "result"
        )
    }
    return [
        {
            "pme_id": s["pme_id"],
            "pme_name": s["legal_name"],
            "priority": s["intervention_priority"],
            "reason": reasons.get(str(s["current_snapshot_id"])),
            "global_score": _f(s["current_score"]),
            "risk_index": _f(s["risk_index"]),
            "actions_overdue": s["actions_overdue"],
            "alerts_high": s["alerts_high"],
        }
        for s in sorted(states, key=lambda s: (s["intervention_priority"], -(s["risk_index"] or 0)))
    ]


def offer_effectiveness(access) -> dict:
    """Évolution des critères ciblés : PME ayant terminé l'offre vs PME éligibles ne l'ayant pas suivie (RM-09)."""
    from pme360.plans.models import Action, SupportOffer
    from pme360.pmes.models import Pme
    from pme360.scoring.models import ScoreSnapshot

    pmes = access.pme_queryset(Pme.objects.all())
    current = defaultdict(dict)
    for row in services.weaknesses(access, "CRITERE"):
        current[str(row["pme_id"])][row["code"]] = row["level"]
    baseline = defaultdict(dict)
    for pme_id, result in ScoreSnapshot.objects.filter(
        pme__in=pmes, is_frozen=True, kind=ScoreSnapshot.Kind.BASELINE
    ).values_list("pme_id", "result"):
        for criterion in result.get("criteria", []):
            if criterion.get("status") == "EVALUE" and criterion.get("level") is not None:
                baseline[str(pme_id)][criterion["code"]] = criterion["level"]
    done = defaultdict(set)
    for pme_id, offer_id in Action.objects.filter(pme__in=pmes, status=Action.Status.TERMINE).values_list(
        "pme_id", "offer_id"
    ):
        done[offer_id].add(str(pme_id))

    def delta(pme_id: str, criteria: list[str]) -> float | None:
        values = [
            current[pme_id][c] - baseline[pme_id][c]
            for c in criteria
            if current[pme_id].get(c) is not None and baseline[pme_id].get(c) is not None
        ]
        return mean(values) if values else None

    offers = []
    for offer in SupportOffer.objects.filter(pk__in=list(done)):
        treated = [d for p in done[offer.pk] if (d := delta(p, offer.target_criteria)) is not None]
        eligible = [
            p
            for p in baseline
            if p not in done[offer.pk]
            and any((baseline[p].get(c) or 0) < offer.target_level for c in offer.target_criteria)
        ]
        compared = [d for p in eligible if (d := delta(p, offer.target_criteria)) is not None]
        offers.append(
            {
                "code": offer.code,
                "title": offer.title,
                "criteria": offer.target_criteria,
                "treated_n": len(treated),
                "treated_delta": _round(mean(treated), 2) if treated else None,
                "compared_n": len(compared),
                "compared_delta": _round(mean(compared), 2) if compared else None,
            }
        )
    return {"offers": offers, "unit": "niveaux de critère (0 à 4)", "notice": RM09}
