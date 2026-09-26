"""Données figées du rapport de diagnostic (Document 9, § 7 : les 16 sections).

Chaque phrase du rapport est dérivée des données (aucun texte inventé) ; les évolutions sont décrites sans
attribution causale (RM-09). Le résultat est stocké tel quel dans ``Report.data_snapshot``.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

TEMPLATE_VERSION = "1.0.0"

SECTIONS = [
    "Présentation de l'entreprise",
    "Méthodologie",
    "Score global",
    "Scores par dimension",
    "Forces",
    "Faiblesses",
    "Risques",
    "Anomalies",
    "Documents manquants",
    "Priorités",
    "Recommandations",
    "Plan d'accompagnement",
    "Calendrier",
    "Indicateurs de suivi",
    "Conclusion",
    "Annexes",
]

QUADRANTS = {
    "CHAMPIONNE_STRUCTUREE": "Championne structurée",
    "STRUCTUREE_A_DEVELOPPER": "Structurée, à développer",
    "PERFORMANTE_FRAGILE": "Performante mais fragile",
    "A_CONSOLIDER": "À consolider",
    "NON_DETERMINE": "Non déterminé",
}
PRIORITIES = {"P1": "Intervention urgente", "P2": "Renforcée", "P3": "Standard", "P4": "Veille"}
SOURCES = {
    "DECLARATIF": "Déclaratif",
    "DECLARATIF_CORROBORE": "Déclaratif corroboré",
    "DOCUMENT_VERIFIE": "Document vérifié",
    "DOCUMENT_IA": "Document analysé (IA)",
    "INFERE": "Inféré",
    "INDICATEURS": "Indicateurs calculés",
}
DIAGNOSTIC_TYPES = {
    "INITIAL": "Diagnostic initial",
    "SUIVI": "Diagnostic de suivi",
    "REEVALUATION": "Réévaluation",
    "CLOTURE": "Diagnostic de clôture",
}
FOLDER_STATES = {"MANQUANT": "Manquant", "EXPIRE": "Expiré", "NON_CONFORME": "Non conforme"}
JOURNAL_LABELS = {
    "diagnostic.started": "Diagnostic ouvert",
    "diagnostic.submitted": "Questionnaire soumis",
    "diagnostic.reopened": "Renvoyé en collecte",
    "diagnostic.bulk_accepted": "Niveaux déclarés acceptés en lot (avec confirmation)",
    "diagnostic.validated": "Diagnostic validé, score figé",
    "plan.recommendations_generated": "Recommandations calculées",
}
STRONG_SCORE = 70
WEAK_SCORE = 50


def _f(value):
    return None if value is None else float(value)


def format_metric(value, unit: str) -> str:
    if value is None:
        return "Non évaluable"
    if unit == "PERCENT":
        return f"{value * 100:.1f} %".replace(".", ",")
    if unit == "DAYS":
        return f"{value:.0f} jours"
    if unit == "YEARS":
        return f"{value:.1f} ans".replace(".", ",")
    if unit == "AMOUNT":
        return f"{value:,.0f} FCFA".replace(",", " ")
    return f"{value:.2f}".replace(".", ",")


def diagnostic_report_data(diagnostic, generated_by=None) -> dict:
    """Assemble les 16 sections à partir du snapshot figé du diagnostic et de l'état de la PME à date."""
    from pme360.alerts.models import Alert
    from pme360.audit.models import AuditLog
    from pme360.compliance import services as compliance
    from pme360.compliance.models import Deadline
    from pme360.diagnostic.models import CriterionAssessment
    from pme360.notifications.services import advisors
    from pme360.plans.models import ActionPlan, Recommendation
    from pme360.scoring.models import ScoreSnapshot

    pme = diagnostic.pme
    today = timezone.localdate()
    snapshot = ScoreSnapshot.objects.get(diagnostic=diagnostic, is_frozen=True)
    result = snapshot.result
    live = ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE).first()
    current = live.result if live and live.result.get("source_diagnostic") == str(diagnostic.pk) else None
    previous = (
        ScoreSnapshot.objects.filter(pme=pme, is_frozen=True, reference_date__lt=snapshot.reference_date)
        .order_by("-reference_date")
        .first()
    )
    advisor = next(iter(advisors(pme)), None)

    dimensions = [
        {
            "code": d["code"],
            "name": d["name"],
            "short_name": d.get("short_name") or d["name"],
            "score": _f(d.get("score")),
            "confidence": _f(d.get("confidence")),
            "status": d["status"],
            "weight": _f(d.get("weight")),
        }
        for d in result["dimensions"]
    ]
    scored_dims = [d for d in dimensions if d["score"] is not None]
    criteria = [c for c in result["criteria"] if c["status"] == "EVALUE"]
    dim_names = {d["code"]: d["short_name"] for d in dimensions}

    strengths = {
        "dimensions": [d for d in sorted(scored_dims, key=lambda d: -d["score"]) if d["score"] >= STRONG_SCORE][:5],
        "criteria": [
            {**_criterion(c, dim_names)}
            for c in sorted(criteria, key=lambda c: (-(c.get("level") or 0), c["code"]))
            if (c.get("level") or 0) >= 3
        ][:8],
    }
    weaknesses = {
        "dimensions": [d for d in sorted(scored_dims, key=lambda d: d["score"]) if d["score"] < WEAK_SCORE],
        "criteria": [
            _criterion(c, dim_names)
            for c in sorted(criteria, key=lambda c: (not c["is_critical"], c.get("level") or 0, c["code"]))
            if c.get("level") is not None and c["level"] <= 1
        ][:10],
        "capped": [_criterion(c, dim_names) for c in criteria if c.get("capped")],
    }
    alerts = list(
        Alert.objects.filter(pme=pme, status__in=Alert.OPEN).select_related("rule").order_by("-created_at")[:30]
    )
    risk_criteria = [_criterion(c, dim_names) for c in criteria if c["lens"] == "R" and (c.get("level") or 0) <= 1]
    risks = {
        "risk_index": _f(result.get("risk_index")),
        "criteria": risk_criteria,
        "alerts": [
            {"title": a.title, "severity": a.get_severity_display(), "message": a.message}
            for a in alerts
            if a.severity in ("ELEVEE", "CRITIQUE") and a.rule.kind not in ("INCOHERENCE", "ANOMALIE_DOC")
        ],
    }
    anomalies = [
        {"title": a.title, "severity": a.get_severity_display(), "message": a.message}
        for a in alerts
        if a.rule.kind in ("INCOHERENCE", "ANOMALIE_DOC")
    ]
    folder = compliance.compliance_folder(pme)
    missing = [
        {
            "category": category["name"],
            "name": item["document_type"]["name"],
            "state": FOLDER_STATES[item["state"]],
            "criteria": item["criteria"],
        }
        for category in folder
        for item in category["items"]
        if item["required"] and item["state"] in FOLDER_STATES
    ]
    rate = compliance.compliance_rate(pme, today)

    recommendations = [
        {
            "offer": r.offer.title,
            "dimension": dim_names.get(r.offer.dimension_code, r.offer.dimension_code),
            "problem": r.problem,
            "rationale": r.rationale,
            "axes": f"I{r.impact} U{r.urgency} R{r.risk} E{r.effort}",
            "priority": float(r.priority_final),
            "status": r.get_status_display(),
        }
        for r in Recommendation.objects.filter(diagnostic=diagnostic)
        .exclude(status=Recommendation.Status.REJETEE)
        .select_related("offer")
        .order_by("-priority_final")
    ]
    plan = ActionPlan.objects.filter(pme=pme).exclude(status=ActionPlan.Status.BROUILLON).order_by("-version").first()
    actions = []
    if plan:
        for a in plan.actions.select_related("offer").prefetch_related("deliverables").order_by("position", "due_date"):
            actions.append(
                {
                    "ref": a.human_ref,
                    "title": a.title,
                    "dimension": dim_names.get(a.dimension_code, a.dimension_code),
                    "phase": a.get_phase_display(),
                    "status": a.get_status_display(),
                    "start": a.start_date.isoformat() if a.start_date else None,
                    "due": a.due_date.isoformat(),
                    "priority": float(a.priority_score),
                    "indicator": a.success_indicator,
                    "deliverables": [d.title for d in a.deliverables.all()],
                }
            )
    deadlines = [
        {"label": d.pme_obligation.template.name, "period": d.period_label, "due": d.due_date.isoformat()}
        for d in Deadline.objects.filter(pme=pme, status__in=Deadline.OPEN, due_date__lte=today + timedelta(days=90))
        .select_related("pme_obligation__template")
        .order_by("due_date")[:15]
    ]
    calendar = sorted(
        [{"date": a["due"], "label": f"{a['ref']} — {a['title']}", "kind": "Action"} for a in actions]
        + [{"date": d["due"], "label": f"{d['label']} ({d['period']})", "kind": "Obligation"} for d in deadlines],
        key=lambda item: item["date"],
    )

    metrics = [
        {
            "code": m["code"],
            "name": m["name"],
            "formula": m["formula"],
            "value": format_metric(m.get("value"), m.get("unit", "")),
            "band": m.get("band"),
            "sources": ", ".join(SOURCES.get(s, s) for s in m.get("sources", [])) or "—",
        }
        for m in result.get("metrics", [])
    ]
    assessments = [
        {
            "criterion": a.criterion.code,
            "name": a.criterion.name,
            "status": a.get_status_display(),
            "declared": a.level_declared,
            "final": a.level_final,
            "comment": a.comment,
            "reviewer": a.reviewer.full_name,
            "at": a.reviewed_at.isoformat(),
        }
        for a in CriterionAssessment.objects.filter(diagnostic=diagnostic)
        .exclude(status="VALIDE")
        .select_related("criterion", "reviewer")
        .order_by("criterion__code")
    ]
    journal = [
        {
            "action": JOURNAL_LABELS.get(e.action, e.action),
            "at": e.at.isoformat(),
            "actor": e.actor.full_name if e.actor else "Système",
        }
        for e in AuditLog.objects.filter(entity_type="diagnostic", entity_id=str(diagnostic.pk))
        .select_related("actor")
        .order_by("id")[:40]
    ]

    global_score = _f(result.get("global_score"))
    delta = None
    if previous and previous.global_score is not None and global_score is not None:
        delta = round(global_score - float(previous.global_score), 1)
    return {
        "sections": SECTIONS,
        "template_version": TEMPLATE_VERSION,
        "generated_at": timezone.now().isoformat(),
        "generated_by": getattr(generated_by, "full_name", None),
        "pme": {
            "legal_name": pme.legal_name,
            "trade_name": pme.trade_name,
            "legal_form": pme.legal_form.name if pme.legal_form_id else None,
            "sector": pme.sector.name if pme.sector_id else None,
            "region": pme.region.name if pme.region_id else None,
            "commune": pme.commune,
            "creation_date": pme.creation_date.isoformat() if pme.creation_date else None,
            "headcount": pme.headcount,
            "size": pme.get_size_category_display() if pme.size_category else None,
            "rccm": pme.rccm_number,
            "advisor": advisor.full_name if advisor else None,
        },
        "diagnostic": {
            "type": DIAGNOSTIC_TYPES.get(diagnostic.type, diagnostic.type),
            "reference_date": diagnostic.reference_date.isoformat(),
            "validated_at": diagnostic.validated_at.isoformat() if diagnostic.validated_at else None,
            "validated_by": diagnostic.validated_by.full_name if diagnostic.validated_by_id else None,
            "framework_version": result.get("framework_version"),
            "framework_name": diagnostic.framework_version.framework.name,
            "engine_version": result.get("engine_version"),
            "evidence_as_of": result.get("evidence_as_of"),
            "criteria_evaluated": len(criteria),
            "criteria_total": len(result["criteria"]),
        },
        "score": {
            "global": global_score,
            "confidence": _f(result.get("confidence")),
            "confidence_label": result.get("confidence_label"),
            "maturity_level": result["maturity"].get("level"),
            "maturity_label": result["maturity"].get("label"),
            "maturity_message": result["maturity"].get("message"),
            "gates_failed": [g.get("message") for g in result["maturity"].get("gates_failed", [])],
            "imo": _f(result.get("imo")),
            "ipe": _f(result.get("ipe")),
            "quadrant": QUADRANTS.get(result.get("quadrant"), result.get("quadrant")),
            "priority": result["priority"]["priority"],
            "priority_label": PRIORITIES.get(result["priority"]["priority"], result["priority"]["label"]),
            "digital_index": _f(result.get("digital", {}).get("index")),
            "previous": _f(previous.global_score) if previous else None,
            "previous_date": previous.reference_date.isoformat() if previous else None,
            "delta": delta,
            "current": _f(current.get("global_score")) if current else None,
        },
        "dimensions": dimensions,
        "pillars": [
            {"code": p["code"], "name": p["name"], "score": _f(p.get("score"))} for p in result.get("pillars", [])
        ],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "risks": risks,
        "anomalies": anomalies,
        "missing_documents": missing,
        "compliance": {"rate": rate["rate"], "eligible": rate.get("eligible")},
        "priorities": [
            {
                "criterion": g["criterion"],
                "name": g["name"],
                "dimension": dim_names.get(g["dimension"], g["dimension"]),
                "gain": _f(g["potential_gain"]),
                "critical": g["is_critical"],
            }
            for g in result.get("gaps", [])
        ],
        "recommendations": recommendations,
        "plan": {
            "title": plan.title if plan else None,
            "version": plan.version if plan else None,
            "status": plan.get_status_display() if plan else None,
            "horizon_start": plan.horizon_start.isoformat() if plan else None,
            "actions": actions,
        },
        "calendar": calendar,
        "indicators": [
            {"label": "Score global 360", "baseline": global_score, "unit": "/100"},
            {"label": "Conformité documentaire", "baseline": rate["rate"], "unit": "%"},
            *[{"label": a["indicator"], "action": a["ref"]} for a in actions if a["indicator"]],
        ],
        "conclusion": _conclusion(global_score, result, weaknesses, actions, delta),
        "annexes": {"metrics": metrics, "assessments": assessments, "journal": journal},
    }


def _criterion(criterion: dict, dim_names: dict) -> dict:
    return {
        "code": criterion["code"],
        "name": criterion["name"],
        "dimension": dim_names.get(criterion["dimension"], criterion["dimension"]),
        "level": criterion.get("level"),
        "critical": criterion.get("is_critical", False),
        "source": SOURCES.get(criterion.get("source"), criterion.get("source")),
        "proven": criterion.get("proven", False),
    }


def _conclusion(score, result, weaknesses, actions, delta) -> list[str]:
    """Synthèse descriptive (aucune attribution causale, RM-09)."""
    maturity = result["maturity"]
    lines = []
    if score is not None:
        lines.append(
            f"Au {result['reference_date'][8:10]}/{result['reference_date'][5:7]}/{result['reference_date'][:4]}, "
            f"l'entreprise obtient un score global de {score:.0f}/100 (niveau {maturity.get('level')} — "
            f"{maturity.get('label')}), avec une confiance {str(result.get('confidence_label', '')).lower()}."
        )
    if delta is not None:
        direction = "en hausse" if delta > 0 else "en baisse" if delta < 0 else "stable"
        lines.append(f"Le score est {direction} de {abs(delta):.1f} point(s) par rapport au diagnostic précédent.")
    if weaknesses["dimensions"]:
        names = ", ".join(d["short_name"] for d in weaknesses["dimensions"][:3])
        lines.append(f"Les marges de progression principales portent sur : {names}.")
    if weaknesses["capped"]:
        lines.append(
            f"{len(weaknesses['capped'])} critère(s) restent plafonnés faute de preuve vérifiée : déposer les "
            "justificatifs correspondants améliorera la fiabilité et le score."
        )
    if actions:
        lines.append(
            f"Le plan d'accompagnement comporte {len(actions)} action(s), à réaliser selon le calendrier ci-dessus."
        )
    lines.append(
        "Ce rapport décrit la situation observée à la date du diagnostic ; il ne constitue ni une certification ni "
        "une évaluation de solvabilité."
    )
    return lines
