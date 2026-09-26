"""Priorisation des actions (Document 6, § 9) : notation proposée automatiquement, puis modifiable avec motif.

PS = 20 × (0,40 × Impact + 0,30 × Urgence + 0,30 × Risque) × facteur_effort, entre 13 et 100.
Les coefficients, bornes et seuils d'horizon viennent de ``organization.settings["plan_priority"]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .defaults import PRIORITY_SETTINGS

LEGAL_DIMENSIONS = {"D01", "D02", "D03"}  # pilier A : conformité légale
PHASE_ORDER = ["J1_30", "J31_60", "J61_90", "M6", "M12"]
PHASE_START_DAYS = {"J1_30": 0, "J31_60": 30, "J61_90": 60, "M6": 90, "M12": 180}
PHASE_END_DAYS = {"J1_30": 30, "J31_60": 60, "J61_90": 90, "M6": 180, "M12": 365}


def settings_for(organization) -> dict:
    custom = (organization.settings or {}).get("plan_priority") or {}
    return {**PRIORITY_SETTINGS, **custom}


@dataclass
class Scoring:
    impact: int
    urgency: int
    risk: int
    effort: int
    score: float
    details: dict = field(default_factory=dict)


def priority_score(impact: int, urgency: int, risk: int, effort: int, settings: dict) -> float:
    weights = settings["weights"]
    factor = settings["effort_factor"][str(effort)]
    raw = 20 * (weights["impact"] * impact + weights["urgency"] * urgency + weights["risk"] * risk) * factor
    return round(raw, 1)


def potential_gain(result: dict, criteria: list[str], target_level: int) -> float:
    """Points de score global gagnables si les critères atteignent ``target_level`` (Document 6, § 9.1)."""
    dims = {d["code"]: d for d in result.get("dimensions", []) if d.get("score") is not None}
    total = sum(d["weight"] for d in dims.values()) or 1
    gain = 0.0
    for criterion in result.get("criteria", []):
        if criterion["code"] not in criteria or criterion["status"] != "EVALUE" or criterion["dimension"] not in dims:
            continue
        missing = max(target_level * 25.0 - (criterion["score"] or 0.0), 0.0)
        gain += dims[criterion["dimension"]]["weight"] * criterion.get("effective_weight", 0) * missing / total
    return round(gain, 2)


def _quintile(value: float, bounds: list[float]) -> int:
    return 1 + sum(value >= bound for bound in bounds)


def score_offer(offer, result: dict, data: dict, settings: dict, overrides: dict | None = None) -> Scoring:
    """Note Impact / Urgence / Risque / Effort d'une offre pour la PME ; ``overrides`` : valeurs fixées par la règle."""
    overrides = {k: v for k, v in (overrides or {}).items() if v}
    targets = [c for c in result.get("criteria", []) if c["code"] in offer.target_criteria]
    details: dict = {}

    gain = potential_gain(result, offer.target_criteria, offer.target_level)
    impact = _quintile(gain, settings["impact_bounds"])
    details["impact"] = f"{gain:.1f} point(s) de score global gagnable(s)".replace(".", ",")

    legal_gap = any(
        c["dimension"] in LEGAL_DIMENSIONS and c["status"] == "EVALUE" and ((c["level"] or 0) <= 2 or c.get("capped"))
        for c in targets
    )
    critical = any(c.get("is_critical") and c["status"] == "EVALUE" for c in targets)
    overdue = data.get("deadlines", {}).get("overdue", {}).get("count", 0)
    if legal_gap and (critical or overdue):
        urgency, details["urgency"] = 5, "Obligation légale non remplie ou non prouvée"
    elif critical:
        urgency, details["urgency"] = 4, "Critère critique concerné"
    elif offer.code in settings.get("_prerequisites", set()):
        urgency, details["urgency"] = 3, "Prérequis d'autres actions"
    else:
        urgency, details["urgency"] = 2, "Pas d'échéance imposée"

    risk_index = data.get("risk_index")
    lens_r = any(c.get("lens") == "R" for c in targets)
    dimension_score = data.get("dimension", {}).get(offer.dimension_code, {}).get("score")
    if lens_r and risk_index is not None and risk_index >= 70:
        risk, details["risk"] = 5, f"Exposition au risque élevée ({risk_index:.0f}/100)"
    elif lens_r or legal_gap:
        risk, details["risk"] = 4, "Risque de sanction, de fraude ou de perte"
    elif dimension_score is not None and dimension_score < 40:
        risk, details["risk"] = 3, f"Dimension fragile ({dimension_score:.0f}/100)"
    else:
        risk, details["risk"] = 2, "Risque limité"

    effort = offer.effort
    details["effort"] = f"{offer.typical_duration_days} jours, {offer.get_provider_type_display().lower()}"

    impact = overrides.get("impact", impact)
    urgency = overrides.get("urgency", urgency)
    risk = overrides.get("risk", risk)
    for axis in ("impact", "urgency", "risk"):
        if axis in overrides:
            details[axis] = "Fixé par la règle"
    return Scoring(impact, urgency, risk, effort, priority_score(impact, urgency, risk, effort, settings), details)


def base_phase(ps: float, impact: int, urgency: int, effort: int, is_growth: bool, settings: dict) -> str:
    """Horizon proposé (Document 6, § 9.3), avant dépendances et capacité."""
    if is_growth:
        return "M12"
    horizons = settings["horizons"]
    if urgency == 5 or ps >= horizons["urgent"] or (impact >= 3 and effort <= 2):
        return "J1_30"
    if effort == 5:
        return "M6"
    if ps >= horizons["structuring"]:
        return "J31_60"
    if ps >= horizons["consolidation"]:
        return "J61_90"
    return "M6"


def later(phase: str, other: str) -> str:
    return phase if PHASE_ORDER.index(phase) >= PHASE_ORDER.index(other) else other


def next_phase(phase: str) -> str:
    index = PHASE_ORDER.index(phase)
    return PHASE_ORDER[min(index + 1, len(PHASE_ORDER) - 1)]


def assign_phases(items: list[dict], capacity: int) -> None:
    """Affecte les horizons en respectant dépendances et capacité ; ``items`` triés par priorité décroissante.

    Chaque item : {"key", "phase" (proposé), "depends" (clés), ...} ; « phase » est mis à jour sur place.
    """
    placed: dict[str, str] = {}
    load: dict[str, int] = {p: 0 for p in PHASE_ORDER}
    pending = list(items)
    # Les prérequis sont placés avant leurs dépendants (ordre topologique stable, priorité conservée).
    for _ in range(len(items) + 1):
        progressed = False
        for item in list(pending):
            deps = [d for d in item["depends"] if d in {i["key"] for i in items}]
            if any(d not in placed for d in deps):
                continue
            phase = item["phase"]
            for dep in deps:
                # Un dépendant démarre après son prérequis : horizon suivant celui du prérequis.
                phase = later(phase, next_phase(placed[dep]))
            while phase not in ("M6", "M12") and load[phase] >= capacity:
                phase = next_phase(phase)
            item["phase"] = phase
            placed[item["key"]] = phase
            load[phase] += 1
            pending.remove(item)
            progressed = True
        if not pending or not progressed:
            break
    for item in pending:  # cycle éventuel : placé sans contrainte (l'application refuse les cycles)
        placed[item["key"]] = item["phase"]
