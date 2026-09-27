"""Données figées des rapports de suivi, annuel et de conformité d'une PME (Document 9, § 7).

- Suivi : évolution depuis le dernier rapport de suivi (ou le dernier diagnostic validé), actions, conformité.
- Annuel : trajectoire sur 12 mois et explication des écarts de score.
- Conformité : état du dossier, échéances, anomalies, ce qu'il reste à fournir.

Comme pour le rapport de diagnostic, chaque phrase est dérivée des données et les évolutions sont décrites sans
attribution causale (RM-09). Le résultat est stocké tel quel dans ``Report.data_snapshot``.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from .builders import PRIORITIES, _f

TEMPLATE_VERSION = "1.0.0"

FOLLOW_UP_DAYS = 90
ANNUAL_DAYS = 365
UPCOMING_DAYS = 90
EXPIRING_DAYS = 60

FOLLOW_UP_SECTIONS = [
    "Synthèse",
    "Évolution du score",
    "Explication des écarts",
    "Actions du plan",
    "Progrès vérifiés",
    "Conformité et échéances",
    "Points d'attention",
    "Prochaines étapes",
]
ANNUAL_SECTIONS = [
    "Synthèse",
    "Trajectoire sur 12 mois",
    "Évolution du score",
    "Explication des écarts",
    "Actions du plan",
    "Progrès vérifiés",
    "Conformité et échéances",
    "Points d'attention",
    "Prochaines étapes",
]
COMPLIANCE_SECTIONS = [
    "Synthèse",
    "Ce qu'il reste à faire",
    "Dossier par catégorie",
    "Échéances",
    "Documents arrivant à expiration",
    "Anomalies",
]

STATES = {
    "CONFORME": "Conforme",
    "CONFORME_SOUS_RESERVE": "Conforme sous réserve",
    "EN_VERIFICATION": "En vérification",
    "MANQUANT": "Manquant",
    "EXPIRE": "Expiré",
    "NON_CONFORME": "Non conforme",
}
TODO_STATES = ("MANQUANT", "EXPIRE", "NON_CONFORME")
NATURES = {"PROGRES": "Progrès", "RECUL": "Recul", "GAIN_DE_PREUVE": "Gain de preuve"}
SNAPSHOT_KINDS = {"BASELINE": "Diagnostic initial", "FOLLOW_UP": "Suivi", "CLOTURE": "Clôture", "LIVE": "Score courant"}
HONORED = ("CONFORME", "CONFORME_SOUS_RESERVE", "DISPENSE")
UNDER_REVIEW = ("RECU", "EN_ANALYSE", "VERIF_HUMAINE_REQUISE", "EN_ATTENTE")


# --- Période ------------------------------------------------------------------------------------------------------


def follow_up_period(pme, annual: bool, today: date | None = None) -> tuple[date, date]:
    """Suivi : depuis la fin du dernier rapport de suivi, sinon la validation du dernier diagnostic, sinon 90 jours.

    Rééditer un rapport le jour même reprend la période du précédent (nouvelle version, même période).
    """
    from pme360.diagnostic.models import Diagnostic

    from .models import Report

    today = today or timezone.localdate()
    if annual:
        return today - timedelta(days=ANNUAL_DAYS - 1), today
    last = Report.objects.filter(pme=pme, type=Report.Type.SUIVI).order_by("-generated_at").first()
    if last:
        start, end = (date.fromisoformat(value) for value in last.period.split("_"))
        return (start, end) if end == today else (end + timedelta(days=1), today)
    validated = (
        Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE, validated_at__isnull=False)
        .order_by("-validated_at")
        .values_list("validated_at", flat=True)
        .first()
    )
    if validated and timezone.localdate(validated) < today:
        return timezone.localdate(validated) + timedelta(days=1), today
    return today - timedelta(days=FOLLOW_UP_DAYS - 1), today


def period_label(start: date, end: date) -> str:
    return f"{start.isoformat()}_{end.isoformat()}"


# --- Suivi et annuel ----------------------------------------------------------------------------------------------


def follow_up_report_data(pme, *, annual: bool, start: date, end: date, generated_by=None) -> dict:
    from pme360.alerts.models import Alert
    from pme360.plans.models import Action, ActionPlan, CriterionProgress
    from pme360.plans.services import overdue_actions
    from pme360.scoring import services as scoring
    from pme360.scoring.models import ScoreSnapshot

    from .models import Report

    frozen = list(ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("reference_date", "computed_at"))
    live = ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE).first()
    current = live or (frozen[-1] if frozen else None)
    reference = next((s for s in reversed(frozen) if s.reference_date < start), frozen[0] if frozen else None)
    baseline = next((s for s in frozen if s.kind == ScoreSnapshot.Kind.BASELINE), frozen[0] if frozen else None)

    names = {c["code"]: c["name"] for c in (current.result.get("criteria", []) if current else [])}
    dim_names = {
        d["code"]: d.get("short_name") or d["name"] for d in (current.result.get("dimensions", []) if current else [])
    }

    score = None
    explanation = None
    if current:
        before = {d["code"]: _f(d.get("score")) for d in reference.result.get("dimensions", [])} if reference else {}
        first = {d["code"]: _f(d.get("score")) for d in baseline.result.get("dimensions", [])} if baseline else {}
        score = {
            "current": _f(current.global_score),
            "current_date": current.reference_date.isoformat(),
            "current_is_live": current.kind == ScoreSnapshot.Kind.LIVE,
            "reference": _f(reference.global_score) if reference else None,
            "reference_date": reference.reference_date.isoformat() if reference else None,
            "baseline": _f(baseline.global_score) if baseline else None,
            "baseline_date": baseline.reference_date.isoformat() if baseline else None,
            "delta": _delta(current.global_score, reference.global_score if reference else None),
            "delta_baseline": _delta(current.global_score, baseline.global_score if baseline else None),
            "confidence": _f(current.confidence),
            "maturity_level": current.maturity_level,
            "maturity_label": current.result.get("maturity", {}).get("label"),
            "priority": current.intervention_priority,
            "priority_label": PRIORITIES.get(current.intervention_priority, ""),
            "dimensions": [
                {
                    "code": d["code"],
                    "name": d.get("short_name") or d["name"],
                    "baseline": first.get(d["code"]),
                    "reference": before.get(d["code"]),
                    "current": _f(d.get("score")),
                    "delta": _delta(d.get("score"), before.get(d["code"])),
                }
                for d in current.result.get("dimensions", [])
            ],
        }
        if reference and reference.pk != current.pk:
            raw = scoring.compare(reference, current)
            explanation = {
                "delta": raw.get("delta_global"),
                "other": raw.get("other"),
                "proof_gain": raw.get("proof_gain"),
                "reprojected": raw.get("reprojected_baseline", False),
                "dimensions": [
                    {
                        "name": c["name"],
                        "before": c["before"],
                        "after": c["after"],
                        "contribution": c["contribution"],
                        "criteria": [
                            {
                                "code": d["criterion"],
                                "name": d["name"],
                                "nature": NATURES.get(d["nature"], d["nature"]),
                                "contribution": d["contribution"],
                            }
                            for d in c["criteria"][:4]
                        ],
                    }
                    for c in raw.get("contributions", [])
                    if c["contribution"]
                ][:8],
            }

    trajectory = [
        {
            "date": s.reference_date.isoformat(),
            "kind": SNAPSHOT_KINDS.get(s.kind, s.kind),
            "score": _f(s.global_score),
            "maturity": s.maturity_level,
            "confidence": _f(s.confidence),
        }
        for s in [*frozen, *([live] if live else [])]
        if s.reference_date >= start or s is reference
    ]

    plan = ActionPlan.objects.filter(pme=pme).exclude(status=ActionPlan.Status.BROUILLON).order_by("-version").first()
    actions = Action.objects.filter(pme=pme).select_related("offer")
    completed = [
        _action(a, dim_names)
        for a in actions.filter(status=Action.Status.TERMINE, completed_at__date__range=(start, end)).order_by(
            "completed_at"
        )
    ]
    abandoned = [
        {**_action(a, dim_names), "reason": a.abandon_reason}
        for a in actions.filter(status=Action.Status.ABANDONNE, status_changed_at__date__range=(start, end))
    ]
    overdue = [
        {**_action(a, dim_names), "days_late": (end - a.due_date).days, "waiting_on": _waiting(a.waiting_on)}
        for a in overdue_actions(pme, end).order_by("due_date")
    ]
    overdue_ids = {a["ref"] for a in overdue}
    open_actions = actions.filter(plan=plan).exclude(status__in=[*Action.TERMINAL]).order_by("due_date") if plan else []
    in_progress = [_action(a, dim_names) for a in open_actions if a.human_ref not in overdue_ids]
    upcoming = [a for a in in_progress if a["due"] <= (end + timedelta(days=UPCOMING_DAYS)).isoformat()]
    plan_total = actions.filter(plan=plan).exclude(status=Action.Status.ABANDONNE).count() if plan else 0
    plan_done = actions.filter(plan=plan, status=Action.Status.TERMINE).count() if plan else 0

    progress = [
        {
            "criterion": p.criterion_code,
            "name": names.get(p.criterion_code, p.criterion_code),
            "level": p.level,
            "action": p.action.human_ref,
            "at": p.achieved_at.isoformat(),
        }
        for p in CriterionProgress.objects.filter(pme=pme, achieved_at__date__range=(start, end))
        .select_related("action")
        .order_by("achieved_at")
    ]

    compliance = _period_compliance(pme, start, end)
    previous = (
        Report.objects.filter(pme=pme, type=Report.Type.SUIVI, generated_at__date__lt=start)
        .order_by("-generated_at")
        .first()
    )
    compliance["previous_rate"] = (previous.data_snapshot.get("compliance") or {}).get("rate") if previous else None

    alerts = Alert.objects.filter(pme=pme)
    attention = {
        "open": [
            {"title": a.title, "severity": a.get_severity_display(), "message": a.message}
            for a in alerts.filter(status__in=Alert.OPEN, severity__in=("ELEVEE", "CRITIQUE")).order_by("-created_at")[
                :10
            ]
        ],
        "open_count": alerts.filter(status__in=Alert.OPEN).count(),
        "raised": alerts.filter(created_at__date__range=(start, end)).count(),
        "resolved": alerts.filter(resolved_at__date__range=(start, end)).count(),
    }

    data = {
        "kind": "ANNUEL" if annual else "SUIVI",
        "sections": ANNUAL_SECTIONS if annual else FOLLOW_UP_SECTIONS,
        "template_version": TEMPLATE_VERSION,
        "generated_at": timezone.now().isoformat(),
        "generated_by": getattr(generated_by, "full_name", None),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1},
        "pme": _pme(pme),
        "score": score,
        "explanation": explanation,
        "trajectory": trajectory,
        "plan": {
            "title": plan.title if plan else None,
            "version": plan.version if plan else None,
            "status": plan.get_status_display() if plan else None,
            "total": plan_total,
            "done": plan_done,
            "completion": round(plan_done / plan_total, 3) if plan_total else None,
        },
        "actions": {
            "completed": completed,
            "abandoned": abandoned,
            "overdue": overdue,
            "in_progress": in_progress,
            "upcoming": upcoming[:10],
        },
        "progress": progress,
        "compliance": compliance,
        "attention": attention,
    }
    data["summary"] = _follow_up_summary(data)
    data["next_steps"] = _next_steps(data)
    return data


def _period_compliance(pme, start: date, end: date) -> dict:
    from pme360.compliance import services as compliance
    from pme360.compliance.models import Deadline
    from pme360.documents.models import Document

    rate = compliance.compliance_rate(pme, end)
    due = Deadline.objects.filter(pme=pme, due_date__range=(start, end))
    honored = due.filter(status__in=HONORED).count()
    reviewing = due.filter(status__in=UNDER_REVIEW).count()
    verified = Document.objects.filter(pme=pme, deleted_at__isnull=True, verified_at__date__range=(start, end))
    return {
        "rate": rate["rate"],
        "eligible": rate["eligible"],
        "deadlines_due": due.count(),
        "deadlines_honored": honored,
        "deadlines_reviewing": reviewing,
        "deadlines_missed": due.count() - honored - reviewing,
        "documents_verified": verified.count(),
        "documents_conform": verified.filter(conformity_status__in=("CONFORME", "CONFORME_SOUS_RESERVE")).count(),
        "upcoming": _deadlines(
            Deadline.objects.filter(
                pme=pme, status__in=Deadline.OPEN, due_date__range=(end, end + timedelta(days=UPCOMING_DAYS))
            ),
            end,
        ),
        "overdue": _deadlines(Deadline.objects.filter(pme=pme, status__in=Deadline.OPEN, due_date__lt=end), end),
    }


def _follow_up_summary(data: dict) -> list[str]:
    """Synthèse descriptive (aucune attribution causale, RM-09)."""
    period = data["period"]
    days = f"{period['days']} jour{'s' if period['days'] > 1 else ''}"
    lines = [f"Période couverte : du {_fr(period['start'])} au {_fr(period['end'])} ({days})."]
    score = data["score"]
    if score is None:
        lines.append("Aucun diagnostic validé : le score n'est pas encore disponible.")
    elif score["current"] is not None:
        line = f"Score global à date : {score['current']:.0f}/100"
        if score["delta"] is not None and score["reference_date"]:
            line += f", {_direction(score['delta'])} par rapport au {_fr(score['reference_date'])}"
        if score["delta_baseline"] is not None and score["baseline_date"] != score["reference_date"]:
            line += f" ({_signed(score['delta_baseline'])} depuis le diagnostic initial)"
        lines.append(line + ".")
    actions = data["actions"]
    lines.append(
        f"{len(actions['completed'])} action(s) terminée(s) sur la période ; {len(actions['overdue'])} en retard et "
        f"{len(actions['in_progress'])} en cours à la date d'édition."
    )
    if data["progress"]:
        lines.append(f"{len(data['progress'])} critère(s) relevé(s) par une preuve vérifiée.")
    compliance = data["compliance"]
    if compliance["rate"] is not None:
        deadlines = (
            f"{compliance['deadlines_honored']} échéance(s) honorée(s) sur {compliance['deadlines_due']} tombée(s) "
            "pendant la période"
            if compliance["deadlines_due"]
            else "aucune échéance n'est tombée pendant la période"
        )
        lines.append(f"Conformité documentaire : {compliance['rate'] * 100:.0f} % ; {deadlines}.")
    lines.append(
        "Ces évolutions sont observées sur la période ; elles ne sont pas attribuées à une cause unique "
        "(conjoncture, preuves nouvellement fournies, actions menées)."
    )
    return lines


def _next_steps(data: dict) -> list[str]:
    steps = [
        f"Rattraper « {a['title']} » ({a['ref']}, échue le {_fr(a['due'])})" for a in data["actions"]["overdue"][:3]
    ]
    steps += [
        f"Fournir « {d['label']} » ({d['period']}, attendu le {_fr(d['due'])})"
        for d in data["compliance"]["overdue"][:3]
    ]
    steps += [f"Poursuivre « {a['title']} » (échéance le {_fr(a['due'])})" for a in data["actions"]["upcoming"][:3]]
    steps += [
        f"Préparer « {d['label']} » ({d['period']}, pour le {_fr(d['due'])})"
        for d in data["compliance"]["upcoming"][:3]
    ]
    return steps[:10]


# --- Conformité ---------------------------------------------------------------------------------------------------


def compliance_report_data(pme, *, today: date | None = None, generated_by=None) -> dict:
    from pme360.alerts.models import Alert
    from pme360.compliance import services as compliance
    from pme360.compliance.models import Deadline
    from pme360.documents.models import Document

    today = today or timezone.localdate()
    rate = compliance.compliance_rate(pme, today)
    categories = []
    todo = []
    for category in compliance.compliance_folder(pme):
        items = []
        for item in category["items"]:
            latest = item["documents"][0] if item["documents"] else None
            row = {
                "name": item["document_type"]["name"],
                "required": item["required"],
                "obligation": item["obligation"],
                "state": item["state"],
                "state_label": STATES.get(item["state"], item["state"]),
                "document": latest.title if latest else None,
                "issued_at": latest.issued_at.isoformat() if latest and latest.issued_at else None,
                "expires_at": latest.expires_at.isoformat() if latest and latest.expires_at else None,
                "reason": latest.decision_reason if latest and item["state"] == "NON_CONFORME" else "",
                "guidance": item["document_type"]["guidance"],
            }
            items.append(row)
            if item["required"] and item["state"] in TODO_STATES:
                todo.append({**row, "category": category["name"]})
        categories.append({"name": category["name"], "items": items})

    open_deadlines = Deadline.objects.filter(pme=pme, status__in=Deadline.OPEN)
    year = Deadline.objects.filter(pme=pme, due_date__range=(today - timedelta(days=364), today))
    history = {
        "due": year.exclude(status="DISPENSE").count(),
        "honored": year.filter(status__in=("CONFORME", "CONFORME_SOUS_RESERVE")).count(),
        "reviewing": year.filter(status__in=UNDER_REVIEW).count(),
        "exempted": year.filter(status="DISPENSE").count(),
    }
    history["missed"] = history["due"] - history["honored"] - history["reviewing"]

    expiring = [
        {
            "name": d.document_type.name,
            "title": d.title,
            "expires_at": d.expires_at.isoformat(),
            "days": (d.expires_at - today).days,
        }
        for d in Document.objects.filter(
            pme=pme,
            deleted_at__isnull=True,
            conformity_status__in=("CONFORME", "CONFORME_SOUS_RESERVE"),
            expires_at__range=(today, today + timedelta(days=EXPIRING_DAYS)),
        )
        .select_related("document_type")
        .order_by("expires_at")
    ]
    anomalies = [
        {"title": a.title, "severity": a.get_severity_display(), "message": a.message, "at": a.created_at.isoformat()}
        for a in Alert.objects.filter(
            pme=pme, status__in=Alert.OPEN, rule__kind__in=("INCOHERENCE", "ANOMALIE_DOC")
        ).order_by("-created_at")[:20]
    ]
    rejected = [
        {
            "name": d.document_type.name,
            "title": d.title,
            "status": "Incohérent" if d.conformity_status == "INCOHERENT" else "Non conforme",
            "reason": d.decision_reason,
            "at": d.verified_at.isoformat() if d.verified_at else None,
        }
        for d in Document.objects.filter(
            pme=pme, deleted_at__isnull=True, conformity_status__in=("NON_CONFORME", "INCOHERENT")
        )
        .select_related("document_type")
        .order_by("-verified_at")[:20]
    ]
    overdue = _deadlines(open_deadlines.filter(due_date__lt=today), today)
    data = {
        "kind": "CONFORMITE",
        "sections": COMPLIANCE_SECTIONS,
        "template_version": TEMPLATE_VERSION,
        "generated_at": timezone.now().isoformat(),
        "generated_by": getattr(generated_by, "full_name", None),
        "date": today.isoformat(),
        "pme": _pme(pme),
        "rate": {
            "rate": rate["rate"],
            "eligible": rate["eligible"],
            "points": rate["points"],
            "counts": {STATES[k]: v for k, v in rate["counts"].items()},
        },
        "todo": todo,
        "categories": categories,
        "deadlines": {
            "overdue": overdue,
            "upcoming": _deadlines(
                open_deadlines.filter(due_date__range=(today, today + timedelta(days=UPCOMING_DAYS))), today
            ),
            "history": history,
        },
        "expiring": expiring,
        "anomalies": anomalies,
        "rejected": rejected,
    }
    summary = []
    if rate["rate"] is not None:
        summary.append(
            f"Au {_fr(today.isoformat())}, le taux de conformité documentaire est de {rate['rate'] * 100:.0f} % "
            f"({rate['points']:g} point(s) sur {rate['eligible']} élément(s) exigible(s))."
        )
    else:
        summary.append(f"Au {_fr(today.isoformat())}, aucun document ni aucune échéance n'est encore exigible.")
    summary.append(
        f"{len(todo)} document(s) exigé(s) à fournir ou à remplacer, {len(overdue)} échéance(s) en retard, "
        f"{len(expiring)} document(s) expirant dans les {EXPIRING_DAYS} jours."
    )
    if history["due"]:
        summary.append(f"Sur les 12 derniers mois : {history['honored']} échéance(s) honorée(s) sur {history['due']}.")
    summary.append(
        "Ce rapport décrit l'état du dossier à la date d'édition ; il ne vaut pas attestation de régularité auprès "
        "des administrations."
    )
    data["summary"] = summary
    return data


# --- Outils -------------------------------------------------------------------------------------------------------


def _pme(pme) -> dict:
    from pme360.notifications.services import advisors

    advisor = next(iter(advisors(pme)), None)
    return {
        "legal_name": pme.legal_name,
        "trade_name": pme.trade_name,
        "sector": pme.sector.name if pme.sector_id else None,
        "region": pme.region.name if pme.region_id else None,
        "headcount": pme.headcount,
        "rccm": pme.rccm_number,
        "advisor": advisor.full_name if advisor else None,
    }


def _action(action, dim_names: dict) -> dict:
    return {
        "ref": action.human_ref,
        "title": action.title,
        "dimension": dim_names.get(action.dimension_code, action.dimension_code),
        "status": action.get_status_display(),
        "due": action.due_date.isoformat(),
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
    }


def _deadlines(queryset, today: date) -> list[dict]:
    return [
        {
            "label": d.pme_obligation.template.name,
            "period": d.period_label,
            "due": d.due_date.isoformat(),
            "status": d.get_status_display(),
            "days": (d.due_date - today).days,
            "late": max(0, (today - d.due_date).days),
        }
        for d in queryset.select_related("pme_obligation__template").order_by("due_date")[:20]
    ]


def _waiting(value: str) -> str:
    return {"PME": "l'entreprise", "GUDE": "l'accompagnateur"}.get(value, "")


def _delta(after, before):
    if after is None or before is None:
        return None
    return round(float(after) - float(before), 1)


def _signed(value: float) -> str:
    return f"{value:+.1f} point(s)".replace(".", ",")


def _direction(delta: float) -> str:
    if delta > 0:
        return f"en hausse de {delta:.1f} point(s)".replace(".", ",")
    if delta < 0:
        return f"en baisse de {-delta:.1f} point(s)".replace(".", ",")
    return "stable"


def _fr(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
