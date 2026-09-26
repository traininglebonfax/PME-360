"""Moteur de recommandations « sans code » (Document 7, § 3) : variables, évaluation JSON Logic, justifications.

Une règle est une donnée (JSON Logic) : aucune exécution de code arbitraire. Les variables décrivent l'état de la
PME au moment de l'évaluation (score courant, profil, conformité, alertes, échéances).
"""

from __future__ import annotations

import re
from datetime import date

from django.utils import timezone

from pme360.core import jsonlogic

TEMPLATE_VAR = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")


def variables(pme, result: dict, today: date | None = None) -> dict:
    """Variables disponibles dans les conditions (Document 7, § 3.2)."""
    from pme360.alerts.models import Alert
    from pme360.compliance import services as compliance
    from pme360.compliance.models import Deadline

    today = today or timezone.localdate()
    criteria = {}
    for c in result.get("criteria", []):
        applicable = c["status"] != "NON_APPLICABLE"
        criteria[c["code"]] = {
            "level": c.get("level") if applicable else None,
            "score": c.get("score"),
            "evidenced": bool(c.get("proven")),
            "capped": bool(c.get("capped")),
            "applicable": applicable,
            "critical": bool(c.get("is_critical")),
        }
    open_alerts: dict[str, int] = {}
    for kind in Alert.objects.filter(pme=pme, status__in=Alert.OPEN).values_list("rule__kind", flat=True):
        open_alerts[kind] = open_alerts.get(kind, 0) + 1
    return {
        "pme": result.get("profile", {}),
        "dimension": {
            d["code"]: {"score": d.get("score"), "confidence": d.get("confidence"), "coverage": d.get("coverage")}
            for d in result.get("dimensions", [])
        },
        "criterion": criteria,
        "metric": {m["code"]: {"value": m.get("value"), "band": m.get("band")} for m in result.get("metrics", [])},
        "lens": result.get("lenses", {}),
        "global": {"score": result.get("global_score")},
        "global_score": result.get("global_score"),
        "imo": result.get("imo"),
        "ipe": result.get("ipe"),
        "risk_index": result.get("risk_index"),
        "maturity_level": result.get("maturity", {}).get("level"),
        "compliance_rate": compliance.compliance_rate(pme, today)["rate"],
        "alerts": {"open": open_alerts},
        "deadlines": {"overdue": {"count": Deadline.objects.filter(pme=pme, status=Deadline.Status.EN_RETARD).count()}},
    }


def matches(condition: dict, data: dict) -> bool:
    try:
        return bool(jsonlogic.evaluate(condition, data))
    except jsonlogic.JsonLogicError:
        return False


def _format(value) -> str:
    if value is None:
        return "non renseigné"
    if isinstance(value, float):
        return f"{value:.0f}" if value == int(value) else f"{value:.1f}".replace(".", ",")
    return str(value)


def render(template: str, data: dict) -> str:
    """Remplace les ``{{variable}}`` d'un gabarit de justification (valeurs absentes : « non renseigné »)."""
    return TEMPLATE_VAR.sub(lambda m: _format(jsonlogic.evaluate({"var": m.group(1)}, data)), template)


def referenced_criteria(condition) -> set[str]:
    """Critères cités par une condition (preuves de la recommandation)."""
    found: set[str] = set()
    if isinstance(condition, dict):
        for op, args in condition.items():
            if op == "var" and isinstance(args, str) and args.startswith("criterion."):
                found.add(args.split(".")[1])
            else:
                found |= referenced_criteria(args)
    elif isinstance(condition, list):
        for item in condition:
            found |= referenced_criteria(item)
    return found


def validate_condition(condition) -> None:
    """Refuse une condition mal formée (opérateur inconnu) avant enregistrement."""
    from rest_framework.exceptions import ValidationError

    if not isinstance(condition, dict) or len(condition) != 1:
        raise ValidationError({"condition": ["Une condition JSON Logic est un objet à un seul opérateur."]})
    try:
        jsonlogic.evaluate(condition, {})
    except jsonlogic.JsonLogicError as exc:
        raise ValidationError({"condition": [str(exc)]}) from exc
