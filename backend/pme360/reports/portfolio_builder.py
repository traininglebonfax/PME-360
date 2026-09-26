"""Données figées du rapport trimestriel de portefeuille (Document 9, § 7) — direction GUDE-PME et bailleurs.

Contenu : PME accompagnées, évolution des scores, principaux problèmes, besoins, actions réalisées ou en retard,
progression par secteur et par région, recommandations de pilotage. Règles de présentation (Document 9, § 6.2) :
« évolutions observées », effectifs et part de données vérifiées affichés, cellules masquées si n < 5, aucune
attribution causale (RM-09). Par défaut, aucun nom de PME n'apparaît.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import mean

from django.utils import timezone

from pme360.core.exceptions import BusinessError

TEMPLATE_VERSION = "1.0.0"
MIN_CELL = 5

SECTIONS = [
    "Synthèse",
    "Activité du trimestre",
    "Évolution des scores",
    "Principaux problèmes",
    "Besoins d'accompagnement",
    "Actions réalisées et en retard",
    "Progression par secteur et par région",
    "Conformité documentaire",
    "PME nécessitant un accompagnement renforcé",
    "Recommandations de pilotage",
    "Méthodologie et définitions",
]


@dataclass
class ReportScope:
    """Périmètre figé d'un rapport : l'objet se comporte comme un contexte d'accès restreint à ces PME."""

    organization_id: object
    pme_ids: list[str]
    is_pme_user: bool = False

    def pme_queryset(self, queryset):
        return queryset.filter(pk__in=self.pme_ids)


def parse_period(value: str | None, today: date | None = None) -> tuple[str, date, date]:
    """« 2026-T3 » → (libellé, début, fin). Sans valeur : le trimestre écoulé."""
    today = today or timezone.localdate()
    if not value:
        quarter = (today.month - 1) // 3  # trimestre précédent (0 = T4 de l'année d'avant)
        year = today.year if quarter else today.year - 1
        quarter = quarter or 4
    else:
        match = re.fullmatch(r"(\d{4})-T([1-4])", value.strip().upper())
        if not match:
            raise BusinessError("Période attendue au format AAAA-Tn (ex. 2026-T3).", code="invalid_period")
        year, quarter = int(match.group(1)), int(match.group(2))
    start = date(year, 3 * quarter - 2, 1)
    end = (date(year + 1, 1, 1) if quarter == 4 else date(year, 3 * quarter + 1, 1)) - timedelta(days=1)
    if start > today:
        raise BusinessError("Ce trimestre n'a pas encore commencé.", code="future_period")
    return f"{year}-T{quarter}", start, end


def scope_pmes(access, programme_id=None, cohort_id=None):
    from pme360.pmes.models import Pme

    pmes = access.pme_queryset(Pme.objects.all())
    if cohort_id:
        pmes = pmes.filter(enrollments__cohort_id=cohort_id, enrollments__exited_at__isnull=True)
    elif programme_id:
        pmes = pmes.filter(enrollments__cohort__programme_id=programme_id, enrollments__exited_at__isnull=True)
    return pmes.distinct()


def _mean(values: list[float], digits: int = 1) -> float | None:
    return round(mean(values), digits) if values else None


def _score_at(snapshots: list, day: date):
    """Dernier score figé dont la date de référence est au plus ``day``."""
    candidates = [s for s in snapshots if s.reference_date <= day and s.global_score is not None]
    return float(candidates[-1].global_score) if candidates else None


def portfolio_report_data(
    access, period: str | None = None, *, programme=None, cohort=None, include_names: bool = False, generated_by=None
) -> dict:
    from pme360.analytics import portfolio
    from pme360.analytics import services as analytics
    from pme360.compliance.models import Deadline
    from pme360.diagnostic.models import Diagnostic
    from pme360.plans.models import Action, ActionPlan
    from pme360.scoring.models import ScoreSnapshot

    label, start, end = parse_period(period)
    today = timezone.localdate()
    as_of = min(end, today)
    pmes = scope_pmes(access, getattr(programme, "pk", None), getattr(cohort, "pk", None))
    ids = [str(pk) for pk in pmes.values_list("pk", flat=True)]
    if not ids:
        raise BusinessError("Aucune PME dans ce périmètre.", code="empty_scope")
    scope = ReportScope(organization_id=access.organization_id, pme_ids=ids)
    names = dict(pmes.values_list("pk", "legal_name"))

    def name(pme_id) -> str | None:
        return names.get(pme_id) if include_names else None

    period_start = timezone.make_aware(datetime.combine(start, time.min))
    period_end = timezone.make_aware(datetime.combine(end, time.max))

    kpis = portfolio.overview(scope)
    states = analytics.current_states(scope)
    trajectories = portfolio.trajectories(scope)
    problems = portfolio.frequent_problems(scope)
    demanded = portfolio.demanded_offers(scope)
    reinforced = portfolio.reinforced_support(scope)

    # Activité du trimestre.
    diagnostics = Diagnostic.objects.filter(pme_id__in=ids, validated_at__range=(period_start, period_end))
    new_pmes = pmes.filter(onboarding_started_at__range=(period_start, period_end)).count()
    plans_validated = ActionPlan.objects.filter(pme_id__in=ids, accepted_at__range=(period_start, period_end)).count()
    completed = Action.objects.filter(pme_id__in=ids, completed_at__range=(period_start, period_end)).select_related(
        "offer"
    )
    by_offer: dict[str, int] = {}
    for action in completed:
        key = action.offer.title if action.offer_id else action.title
        by_offer[key] = by_offer.get(key, 0) + 1
    live_actions = Action.objects.filter(pme_id__in=ids, plan__status__in=["VALIDE", "EN_COURS"])
    overdue = live_actions.filter(due_date__lt=today).exclude(status__in=["TERMINE", "ABANDONNE", "BLOQUE"])

    # Évolution des scores sur le trimestre (scores figés au début et à la fin de la période).
    snapshots: dict = {}
    for snapshot in ScoreSnapshot.objects.filter(pme_id__in=ids, is_frozen=True).order_by(
        "reference_date", "computed_at"
    ):
        snapshots.setdefault(snapshot.pme_id, []).append(snapshot)
    quarter_deltas = []
    for items in snapshots.values():
        before, after = _score_at(items, start - timedelta(days=1)), _score_at(items, as_of)
        if before is not None and after is not None:
            quarter_deltas.append(after - before)
    evaluated = proven = 0
    for state in states:
        if state["current_snapshot_id"] is None:
            continue
        result = ScoreSnapshot.objects.get(pk=state["current_snapshot_id"]).result
        for criterion in result.get("criteria", []):
            if criterion.get("status") == "EVALUE" and criterion.get("source") != "INDICATEURS":
                evaluated += 1
                proven += bool(criterion.get("proven"))

    # Progression par secteur et par région (baseline → aujourd'hui), cellules masquées si n < 5.
    deltas = {str(t["pme_id"]): t for t in analytics.trajectories(scope)}

    def group(key: str, label_key: str) -> list[dict]:
        buckets: dict = {}
        for state in states:
            bucket = buckets.setdefault(
                state[key] or "—", {"label": state[label_key] or "Non renseigné", "scores": [], "deltas": [], "pmes": 0}
            )
            bucket["pmes"] += 1
            if state["current_score"] is not None:
                bucket["scores"].append(float(state["current_score"]))
            trajectory = deltas.get(str(state["pme_id"]))
            if (
                trajectory
                and trajectory["delta_current"] is not None
                and trajectory["baseline_id"] != state["current_snapshot_id"]
            ):
                bucket["deltas"].append(float(trajectory["delta_current"]))
        rows = []
        for bucket in buckets.values():
            n = len(bucket["scores"])
            rows.append(
                {
                    "label": bucket["label"],
                    "pmes": bucket["pmes"],
                    "n": n,
                    "score": _mean(bucket["scores"]) if n >= MIN_CELL else None,
                    "delta": _mean(bucket["deltas"]) if len(bucket["deltas"]) >= MIN_CELL else None,
                    "delta_n": len(bucket["deltas"]),
                }
            )
        return sorted(rows, key=lambda r: (-r["pmes"], r["label"]))

    overdue_obligations = Deadline.objects.filter(pme_id__in=ids, status=Deadline.Status.EN_RETARD).count()
    data = {
        "sections": SECTIONS,
        "template_version": TEMPLATE_VERSION,
        "generated_at": timezone.now().isoformat(),
        "generated_by": getattr(generated_by, "full_name", None),
        "period": {
            "label": label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "as_of": as_of.isoformat(),
            "partial": end > today,
        },
        "scope": {
            "label": f"Cohorte {cohort.name}"
            if cohort
            else f"Programme {programme.name}"
            if programme
            else "Toute l'organisation",
            "programme_id": str(programme.pk) if programme else None,
            "cohort_id": str(cohort.pk) if cohort else None,
            "pme_ids": ids,
            "include_names": include_names,
        },
        "kpis": kpis,
        "activity": {
            "new_pmes": new_pmes,
            "diagnostics_validated": diagnostics.count(),
            "plans_accepted": plans_validated,
            "actions_completed": sum(by_offer.values()),
            "actions_completed_by_offer": sorted(
                ({"offer": k, "count": v} for k, v in by_offer.items()), key=lambda i: -i["count"]
            ),
        },
        "scores": {
            "quarter_delta": _mean(quarter_deltas),
            "quarter_n": len(quarter_deltas),
            "evidence_share": round(proven / evaluated, 3) if evaluated else None,
            "criteria_evaluated": evaluated,
            "distribution": trajectories["distribution"],
            "measured": trajectories["measured"],
            "top": [{**t, "pme_name": name(t["pme_id"]), "pme_id": None} for t in trajectories["top"]],
            "stagnating": len(trajectories["stagnating"]),
            "stagnating_names": [n for n in (name(t["pme_id"]) for t in trajectories["stagnating"]) if n],
        },
        "problems": problems,
        "needs": demanded,
        "actions": {
            "overdue": overdue.count(),
            "overdue_waiting_pme": overdue.filter(waiting_on="PME").count(),
            "overdue_waiting_gude": overdue.filter(waiting_on="GUDE").count(),
            "open": live_actions.exclude(status__in=["TERMINE", "ABANDONNE"]).count(),
        },
        "by_sector": group("sector_code", "sector_name"),
        "by_region": group("region_code", "region_name"),
        "compliance": {"average": kpis["average_compliance"], "obligations_overdue": overdue_obligations},
        "reinforced": {
            "p1": sum(1 for r in reinforced if r["priority"] == "P1"),
            "p2": sum(1 for r in reinforced if r["priority"] == "P2"),
            "items": [
                {"pme_name": name(r["pme_id"]), "priority": r["priority"], "reason": r["reason"]} for r in reinforced
            ]
            if include_names
            else [],
            "reasons": sorted({r["reason"] for r in reinforced if r["reason"]}),
        },
        "definitions": {k: v for k, v in portfolio.DEFINITIONS.items() if k != "pmes_new_this_month"},
        "notice": portfolio.RM09,
        "min_cell": MIN_CELL,
    }
    data["recommendations"] = steering_recommendations(data)
    return data


def steering_recommendations(data: dict) -> list[dict]:
    """Recommandations de pilotage dérivées des chiffres du rapport (chacune cite sa base factuelle)."""
    items = []
    kpis = data["kpis"]
    weak = [d for d in data["problems"]["dimensions"] if d["evaluated"] and d["share"] >= 0.5]
    if weak:
        top = sorted(weak, key=lambda d: (-d["share"], d["code"]))[:3]
        listed = ", ".join(f"{d['name']} ({round(d['share'] * 100)} %)" for d in top)
        items.append(
            {
                "topic": "Concentrer l'offre d'accompagnement sur les dimensions les plus fragiles",
                "basis": f"{len(weak)} dimension(s) sous {data['problems']['threshold']}/100 pour au moins la moitié "
                f"des PME diagnostiquées ; les plus touchées : {listed}.",
            }
        )
    actions = data["actions"]
    if actions["overdue"]:
        items.append(
            {
                "topic": "Traiter les actions en retard",
                "basis": f"{actions['overdue']} action(s) en retard, dont {actions['overdue_waiting_gude']} "
                f"en attente de GUDE-PME et {actions['overdue_waiting_pme']} en attente des PME : "
                "vérifier la charge des conseillers.",
            }
        )
    share = kpis.get("low_confidence_share")
    evidence = data["scores"]["evidence_share"]
    if (share is not None and share >= 0.3) or (evidence is not None and evidence < 0.3):
        items.append(
            {
                "topic": "Fiabiliser les scores par les justificatifs",
                "basis": f"Seulement {round((evidence or 0) * 100)} % des critères évalués sont prouvés par un "
                "document vérifié"
                + (f" ; {round(share * 100)} % des scores ont une confiance faible." if share is not None else "."),
            }
        )
    if kpis.get("pmes_without_advisor"):
        items.append(
            {
                "topic": "Assigner un conseiller",
                "basis": f"{kpis['pmes_without_advisor']} PME n'ont pas de conseiller principal.",
            }
        )
    if data["scores"]["stagnating"]:
        items.append(
            {
                "topic": "Réexaminer les plans des PME qui stagnent",
                "basis": f"{data['scores']['stagnating']} PME gagnent moins de 2 points en 6 mois d'accompagnement.",
            }
        )
    if kpis.get("pmes_inactive"):
        items.append(
            {
                "topic": "Relancer les PME inactives",
                "basis": f"{kpis['pmes_inactive']} PME sans activité significative récente.",
            }
        )
    if data["reinforced"]["p1"]:
        items.append(
            {
                "topic": "Prioriser les interventions urgentes",
                "basis": f"{data['reinforced']['p1']} PME en priorité P1 (intervention urgente).",
            }
        )
    if data["compliance"]["obligations_overdue"]:
        items.append(
            {
                "topic": "Suivre les obligations en retard",
                "basis": f"{data['compliance']['obligations_overdue']} obligation(s) documentaire(s) en retard.",
            }
        )
    return items
