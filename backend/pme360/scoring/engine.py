"""Moteur de scoring GUDE-360 (Document 6). FONCTION PURE : aucune base de données, aucune horloge.

Entrées : ``FrameworkSpec`` (référentiel) + ``DiagnosticInput`` (profil, niveaux déclarés, données, revues, preuves).
Sortie : dictionnaire JSON entièrement dérivé des entrées ; mêmes entrées + même version du référentiel + même
version du moteur ⇒ même résultat (tests de non-régression).

Aucune valeur métier n'est codée ici : poids, seuils, bandes, niveaux, portes et règles de priorité viennent de
``FrameworkSpec.settings`` et du contenu du référentiel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from pme360.core import expressions, jsonlogic

ENGINE_VERSION = "1.0.0"

STATUS_EVALUATED = "EVALUE"
STATUS_NOT_EVALUATED = "NON_EVALUE"
STATUS_NOT_APPLICABLE = "NON_APPLICABLE"
DIM_EVALUATED = "EVALUE"
DIM_PROVISIONAL = "PROVISOIRE"
DIM_NOT_EVALUABLE = "NON_EVALUABLE"
DIM_EXCLUDED = "EXCLUE"


# --- Entrées --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSpec:
    code: str
    name: str
    criterion: str | None
    formula: str
    formula_label: str
    unit: str
    bands: list
    weight: float


@dataclass(frozen=True)
class CriterionSpec:
    code: str
    name: str
    dimension: str
    lens: str
    weight: float
    is_critical: bool
    declarative_cap_level: int
    applicability: dict | None
    evidence_policy: str
    sector_module: str
    metrics: tuple[MetricSpec, ...] = ()


@dataclass(frozen=True)
class DimensionSpec:
    code: str
    name: str
    short_name: str
    pillar: str
    weight: float


@dataclass(frozen=True)
class FrameworkSpec:
    version_id: str
    version: str
    pillars: dict[str, str]
    dimensions: tuple[DimensionSpec, ...]
    criteria: tuple[CriterionSpec, ...]
    metrics: tuple[MetricSpec, ...]
    settings: dict


@dataclass(frozen=True)
class Declared:
    """Niveau déclaré d'un critère (issu des réponses) et sa provenance."""

    level: int
    source: str  # DECLARATIF | DECLARATIF_CORROBORE | INFERE
    answered_on: date


@dataclass(frozen=True)
class InputValue:
    value: float
    source: str
    answered_on: date


@dataclass(frozen=True)
class Review:
    status: str  # VALIDE | MODIFIE | NON_APPLICABLE
    level_final: int | None
    corroborated: bool = False


@dataclass(frozen=True)
class Evidence:
    """Preuve documentaire d'un critère (alimentée à partir de la phase 3)."""

    verified: bool
    level: int | None
    source: str  # DOCUMENT_VERIFIE | DOCUMENT_IA
    dated: date


@dataclass
class DiagnosticInput:
    reference_date: date
    profile: dict
    declared: dict[str, Declared] = field(default_factory=dict)
    inputs: dict[str, InputValue] = field(default_factory=dict)
    reviews: dict[str, Review] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    # Contexte pour les règles de priorité (alertes, actions : phases 3 à 5 ; historique des snapshots).
    context: dict = field(default_factory=dict)


# --- Calculs élémentaires -------------------------------------------------------------------------------------


def _freshness(answered_on: date, reference: date, validity_days: int) -> float:
    """1,0 dans la durée de validité, puis décroissance linéaire jusqu'à 0,5 à 2× la durée (Document 6, § 5.1)."""
    age = (reference - answered_on).days
    if age <= validity_days:
        return 1.0
    if age >= 2 * validity_days:
        return 0.5
    return 1.0 - 0.5 * (age - validity_days) / validity_days


def _band(value: float, bands: list) -> dict | None:
    for band in bands:
        if band["upto"] is None or value < band["upto"]:
            return band
    return None


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value + 0.0, digits)


def _weighted(items: list[tuple[float, float]]) -> float | None:
    total = sum(weight for weight, _ in items)
    return sum(weight * value for weight, value in items) / total if total else None


def evaluate_metric(metric: MetricSpec, data: DiagnosticInput, source_factors: dict, validity: int) -> dict:
    variables = sorted(expressions.variables(metric.formula))
    used = {name: data.inputs[name] for name in variables if name in data.inputs}
    result = {
        "code": metric.code,
        "name": metric.name,
        "criterion": metric.criterion,
        "formula": metric.formula_label,
        "unit": metric.unit,
        "inputs": {name: used[name].value if name in used else None for name in variables},
        "sources": sorted({used[name].source for name in used}),
        "value": None,
        "points": None,
        "band": None,
        "confidence": 0.0,
        "status": STATUS_NOT_EVALUATED,
    }
    try:
        value = expressions.evaluate(metric.formula, {name: item.value for name, item in used.items()})
    except expressions.MissingInput as missing:
        result["missing"] = str(missing)
        return result
    result["value"] = round(value, 6)
    result["status"] = STATUS_EVALUATED
    result["confidence"] = (
        min(
            source_factors[item.source] * _freshness(item.answered_on, data.reference_date, validity)
            for item in used.values()
        )
        if used
        else 0.0
    )
    band = _band(value, metric.bands) if metric.bands else None
    if band:
        result["points"] = band["points"]
        result["band"] = band["label"]
    return result


def evaluate_criterion(criterion: CriterionSpec, data: DiagnosticInput, settings: dict) -> dict:
    conf = settings["confidence"]["sources"]
    validity = settings["engine"]["declarative_validity_days"]
    review = data.reviews.get(criterion.code)
    result = {
        "code": criterion.code,
        "name": criterion.name,
        "dimension": criterion.dimension,
        "lens": criterion.lens,
        "weight": criterion.weight,
        "is_critical": criterion.is_critical,
        "sector_module": criterion.sector_module,
        "status": STATUS_NOT_EVALUATED,
        "score": None,
        "level": None,
        "level_uncapped": None,
        "capped": False,
        "proven": False,
        "source": None,
        "confidence": 0.0,
        "reviewed": review is not None,
    }
    if criterion.sector_module and criterion.sector_module != data.profile.get("sector"):
        result["status"] = STATUS_NOT_APPLICABLE
        result["reason"] = "Module sectoriel d'un autre secteur"
        return result
    if criterion.applicability and not jsonlogic.evaluate(criterion.applicability, data.profile):
        result["status"] = STATUS_NOT_APPLICABLE
        result["reason"] = "Règle d'applicabilité"
        return result
    if review and review.status == "NON_APPLICABLE":
        result["status"] = STATUS_NOT_APPLICABLE
        result["reason"] = "Décision justifiée du conseiller"
        return result

    if criterion.metrics:
        metrics = [evaluate_metric(m, data, conf, validity) for m in criterion.metrics]
        scored = [
            (m, spec.weight) for m, spec in zip(metrics, criterion.metrics, strict=True) if m["points"] is not None
        ]
        result["metrics"] = [m["code"] for m in metrics]
        if scored:
            result["status"] = STATUS_EVALUATED
            result["score"] = _weighted([(weight, m["points"]) for m, weight in scored])
            result["confidence"] = _weighted([(weight, m["confidence"]) for m, weight in scored])
            result["source"] = "INDICATEURS"
        return result

    declared = data.declared.get(criterion.code)
    evidence = data.evidence.get(criterion.code)
    if review and review.status in ("VALIDE", "MODIFIE") and review.level_final is not None:
        level = review.level_final
    elif declared is not None:
        level = declared.level
    elif evidence and evidence.verified and evidence.level is not None:
        level = evidence.level  # la preuve vérifiée suffit, même sans déclaration
    else:
        return result
    source = declared.source if declared else "DECLARATIF"
    answered_on = declared.answered_on if declared else data.reference_date
    if review and review.corroborated and source == "DECLARATIF":
        source = "DECLARATIF_CORROBORE"
    proven = bool(evidence and evidence.verified and evidence.level is not None and evidence.level >= level)
    if evidence and evidence.verified:
        source, answered_on = evidence.source, evidence.dated
    result["level_uncapped"] = level
    if criterion.evidence_policy == "REQUIRED" and not proven and level > criterion.declarative_cap_level:
        level = criterion.declarative_cap_level  # RM-01 : pas de conformité sans preuve vérifiée
        result["capped"] = True
    result.update(
        status=STATUS_EVALUATED,
        level=level,
        score=level * 25.0,
        proven=proven,
        source=source,
        confidence=conf[source] * _freshness(answered_on, data.reference_date, validity),
    )
    return result


# --- Agrégation -----------------------------------------------------------------------------------------------


def _effective_weights(criteria: list[dict]) -> None:
    """Poids effectif (fraction) de chaque critère applicable dans sa dimension ; somme = 1."""
    applicable = [c for c in criteria if c["status"] != STATUS_NOT_APPLICABLE]
    total = sum(c["weight"] for c in applicable)
    for criterion in criteria:
        criterion["effective_weight"] = (
            criterion["weight"] / total if total and criterion["status"] != STATUS_NOT_APPLICABLE else 0.0
        )


def aggregate_dimension(dimension: DimensionSpec, criteria: list[dict], settings: dict) -> dict:
    engine = settings["engine"]
    _effective_weights(criteria)
    relevant = [c for c in criteria if not c["sector_module"] or c["status"] != STATUS_NOT_APPLICABLE]
    total_weight = sum(c["weight"] for c in relevant)
    na_weight = sum(c["weight"] for c in relevant if c["status"] == STATUS_NOT_APPLICABLE)
    evaluated = [c for c in criteria if c["status"] == STATUS_EVALUATED]
    coverage = sum(c["effective_weight"] for c in evaluated)
    score = _weighted([(c["effective_weight"], c["score"]) for c in evaluated])
    confidence = sum(c["effective_weight"] * c["confidence"] for c in criteria)
    if total_weight and na_weight / total_weight > engine["not_applicable_exclusion"]:
        status = DIM_EXCLUDED
    elif coverage < engine["non_evaluable_coverage"]:
        status = DIM_NOT_EVALUABLE
    elif coverage < engine["provisional_coverage"]:
        status = DIM_PROVISIONAL
    else:
        status = DIM_EVALUATED
    return {
        "code": dimension.code,
        "name": dimension.name,
        "short_name": dimension.short_name,
        "pillar": dimension.pillar,
        "weight": dimension.weight,
        "status": status,
        "coverage": round(coverage, 4),
        "score": score if status in (DIM_EVALUATED, DIM_PROVISIONAL) else None,
        "raw_score": score,
        "confidence": round(confidence, 4) if status != DIM_EXCLUDED else None,
        "not_applicable_share": round(na_weight / total_weight, 4) if total_weight else 0.0,
    }


def _index(criteria: list[dict], dimensions: dict[str, dict], lenses: set[str]) -> float | None:
    items = [
        (c["effective_weight"] * dimensions[c["dimension"]]["weight"], c["score"])
        for c in criteria
        if c["status"] == STATUS_EVALUATED
        and c["lens"] in lenses
        and dimensions[c["dimension"]]["status"] != DIM_EXCLUDED
    ]
    return _weighted(items)


def _level_label(levels: list[dict], score: float | None) -> dict | None:
    if score is None:
        return None
    return max((lvl for lvl in levels if score >= lvl["min"]), key=lambda lvl: lvl["min"])


def _check_gate(level: int, rules: dict, result: dict) -> list[dict]:
    """Renvoie les manquements à la porte du niveau ``level`` (liste vide = porte franchie)."""
    failures = []
    criteria = [c for c in result["criteria"] if c["status"] != STATUS_NOT_APPLICABLE]
    critical = [c for c in criteria if c["is_critical"]]
    dimensions = [d for d in result["dimensions"] if d["status"] in (DIM_EVALUATED, DIM_PROVISIONAL)]

    def below(items, minimum):
        return [c["code"] for c in items if c["level"] is None or c["level"] < minimum]

    if rule := rules.get("critical_pillar_min_level"):
        pillar_dims = {d["code"] for d in result["dimensions"] if d["pillar"] == rule["pillar"]}
        if codes := below([c for c in critical if c["dimension"] in pillar_dims], rule["level"]):
            failures.append(
                {
                    "rule": "critical_pillar_min_level",
                    "criteria": codes,
                    "message": f"Critères critiques du pilier {rule['pillar']} sous le niveau {rule['level']}",
                }
            )
    if (minimum := rules.get("critical_min_level")) is not None and (codes := below(critical, minimum)):
        failures.append(
            {"rule": "critical_min_level", "criteria": codes, "message": f"Critères critiques sous le niveau {minimum}"}
        )
    if rules.get("critical_proven") and (codes := [c["code"] for c in critical if not c["proven"]]):
        failures.append({"rule": "critical_proven", "criteria": codes, "message": "Critères critiques non prouvés"})
    if rule := rules.get("pillar_dimension_min"):
        codes = [d["code"] for d in dimensions if d["pillar"] == rule["pillar"] and d["score"] < rule["score"]]
        if codes:
            failures.append(
                {
                    "rule": "pillar_dimension_min",
                    "dimensions": codes,
                    "message": f"Dimensions du pilier {rule['pillar']} sous {rule['score']}/100",
                }
            )
    if (minimum := rules.get("dimension_min")) is not None:
        if codes := [d["code"] for d in dimensions if d["score"] < minimum]:
            failures.append({"rule": "dimension_min", "dimensions": codes, "message": f"Dimensions sous {minimum}/100"})
    if (minimum := rules.get("confidence_min")) is not None and result["confidence"] < minimum:
        failures.append(
            {"rule": "confidence_min", "message": f"Confiance globale inférieure à {round(minimum * 100)} %"}
        )
    if (minimum := rules.get("ipe_min")) is not None and (result["ipe"] is None or result["ipe"] < minimum):
        failures.append({"rule": "ipe_min", "message": f"Indice de performance inférieur à {minimum}"})
    if rules.get("no_critical_alert") and result["context"].get("open_critical_alerts", 0) > 0:
        failures.append({"rule": "no_critical_alert", "message": "Alerte critique ouverte"})
    return failures


def _priority(settings: dict, variables: dict) -> dict:
    for rule in settings["priority_rules"]:
        if jsonlogic.evaluate(rule["condition"], variables):
            return {"priority": rule["priority"], "label": rule["label"]}
    return dict(settings["default_priority"])


def compute(framework: FrameworkSpec, data: DiagnosticInput) -> dict:
    """Calcule le résultat complet d'un diagnostic (Document 6, § 3.5)."""
    settings = framework.settings
    dimension_specs = {d.code: d for d in framework.dimensions}
    criteria = [evaluate_criterion(c, data, settings) for c in framework.criteria]
    by_dimension: dict[str, list[dict]] = {code: [] for code in dimension_specs}
    for criterion in criteria:
        by_dimension[criterion["dimension"]].append(criterion)
    dimensions = [aggregate_dimension(d, by_dimension[d.code], settings) for d in framework.dimensions]
    dims = {d["code"]: d for d in dimensions}

    scored = [d for d in dimensions if d["status"] in (DIM_EVALUATED, DIM_PROVISIONAL)]
    global_score = _weighted([(d["weight"], d["score"]) for d in scored])
    counted = [d for d in dimensions if d["status"] != DIM_EXCLUDED]
    confidence = _weighted([(d["weight"], d["confidence"]) for d in counted]) or 0.0

    lenses = {lens: _index(criteria, dims, {lens}) for lens in ("C", "O", "P", "R")}
    imo = _index(criteria, dims, {"C", "O", "R"})
    ipe = lenses["P"]
    risk_index = None if lenses["R"] is None else 100 - lenses["R"]

    pillars = []
    for code, name in framework.pillars.items():
        members = [d for d in scored if d["pillar"] == code]
        pillars.append({"code": code, "name": name, "score": _weighted([(d["weight"], d["score"]) for d in members])})

    digital = settings["digital_index"]
    digital_items = [
        (c["weight"], c["score"])
        for c in criteria
        if c["status"] == STATUS_EVALUATED
        and (c["dimension"] == digital["dimension"] or c["code"] in digital["extra_criteria"])
    ]
    digital_index = _weighted(digital_items)

    result = {
        "engine_version": ENGINE_VERSION,
        "framework_version": framework.version,
        "reference_date": data.reference_date.isoformat(),
        "profile": data.profile,
        "context": data.context,
        "criteria": criteria,
        "dimensions": dimensions,
        "pillars": pillars,
        "lenses": lenses,
        "global_score": global_score,
        "imo": imo,
        "ipe": ipe,
        "risk_index": risk_index,
        "confidence": confidence,
        "metrics": [
            evaluate_metric(m, data, settings["confidence"]["sources"], settings["engine"]["declarative_validity_days"])
            for m in framework.metrics
        ],
    }

    # Niveau de maturité : plage d'IMO puis portes cumulatives (Document 6, § 4).
    levels = settings["maturity_levels"]
    raw = _level_label(levels, imo)
    level = raw["level"] if raw else None
    gates_failed = []
    if raw:
        for candidate in range(2, raw["level"] + 1):
            failures = _check_gate(candidate, settings["gates"].get(str(candidate), {}), result)
            if failures:
                level = candidate - 1
                gates_failed = [{"level": candidate, **failure} for failure in failures]
                break
    result["maturity"] = {
        "level": level,
        "level_uncapped": raw["level"] if raw else None,
        "label": next((lvl["label"] for lvl in levels if lvl["level"] == level), None),
        "message": next((lvl["message"] for lvl in levels if lvl["level"] == level), None),
        "capped": bool(raw and level != raw["level"]),
        "gates_failed": gates_failed,
    }

    quadrants = settings["quadrants"]
    if imo is None or ipe is None:
        quadrant = "NON_DETERMINE"
    elif imo >= quadrants["imo_threshold"]:
        quadrant = "CHAMPIONNE_STRUCTUREE" if ipe >= quadrants["ipe_threshold"] else "STRUCTUREE_A_DEVELOPPER"
    else:
        quadrant = "PERFORMANTE_FRAGILE" if ipe >= quadrants["ipe_threshold"] else "A_CONSOLIDER"
    result["quadrant"] = quadrant

    digital_level = _level_label(digital["levels"], digital_index)
    result["digital"] = {"index": digital_index, "label": digital_level["label"] if digital_level else None}

    confidence_band = next(b for b in settings["confidence"]["bands"] if confidence >= b["min"])
    result["confidence_label"] = confidence_band["label"]

    variables = {
        "imo": imo,
        "ipe": ipe,
        "risk_index": risk_index,
        "global_score": global_score,
        "maturity_level": level,
        "confidence": confidence,
        "open_critical_alerts": 0,
        "open_high_alerts": 0,
        "overdue_critical_actions": 0,
        **data.context,
    }
    result["priority"] = _priority(settings, variables)
    result["gaps"] = priority_gaps(result)
    return _rounded(result)


def priority_gaps(result: dict, limit: int = 5) -> list[dict]:
    """Écarts à plus fort impact : points de score global gagnables en portant le critère au niveau 4.

    Composante « Impact » de la matrice de priorisation (Document 6, § 9.1) ; le score complet
    Impact × Urgence × Risque × Effort est produit par le moteur de recommandations (phase 5).
    """
    dims = {d["code"]: d for d in result["dimensions"] if d["status"] in (DIM_EVALUATED, DIM_PROVISIONAL)}
    total = sum(d["weight"] for d in dims.values())
    gaps = []
    for criterion in result["criteria"]:
        if criterion["status"] != STATUS_EVALUATED or criterion["dimension"] not in dims or criterion["score"] >= 100:
            continue
        gain = (
            dims[criterion["dimension"]]["weight"] * criterion["effective_weight"] * (100 - criterion["score"]) / total
        )
        gaps.append(
            {
                "criterion": criterion["code"],
                "name": criterion["name"],
                "dimension": criterion["dimension"],
                "score": criterion["score"],
                "potential_gain": gain,
                "is_critical": criterion["is_critical"],
                "capped": criterion["capped"],
            }
        )
    gaps.sort(key=lambda g: (-g["is_critical"], -g["potential_gain"]))
    return gaps[:limit]


def _rounded(value):
    """Arrondi final pour l'affichage et la comparaison (1 décimale pour les scores, 4 pour les fractions)."""
    if isinstance(value, dict):
        return {key: _round_field(key, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


_FRACTIONS = {"confidence", "coverage", "effective_weight", "not_applicable_share"}


def _round_field(key: str, value):
    if isinstance(value, float):
        return round(value, 4) if key in _FRACTIONS else round(value, 2)
    return _rounded(value)


# --- Explication des évolutions (Document 6, § 8) ------------------------------------------------------------


def explain_change(before: dict, after: dict) -> dict:
    """Contributions de chaque dimension et critère à l'écart de score global entre deux résultats."""
    dims_after = {d["code"]: d for d in after["dimensions"]}
    dims_before = {d["code"]: d for d in before["dimensions"]}
    comparable = [
        code
        for code, d in dims_after.items()
        if d["score"] is not None and dims_before.get(code, {}).get("score") is not None
    ]
    total = sum(dims_after[code]["weight"] for code in comparable)
    crit_before = {c["code"]: c for c in before["criteria"]}
    contributions = []
    for code in comparable:
        d_after, d_before = dims_after[code], dims_before[code]
        contribution = d_after["weight"] * (d_after["score"] - d_before["score"]) / total if total else 0
        details = []
        for criterion in (c for c in after["criteria"] if c["dimension"] == code):
            previous = crit_before.get(criterion["code"])
            if not previous or criterion["score"] is None or previous["score"] is None:
                continue
            delta = criterion["score"] - previous["score"]
            if not delta:
                continue
            if (
                delta > 0
                and previous["capped"]
                and not criterion["capped"]
                and (criterion["level_uncapped"] == previous["level_uncapped"])
            ):
                nature = "GAIN_DE_PREUVE"
            else:
                nature = "PROGRES" if delta > 0 else "RECUL"
            details.append(
                {
                    "criterion": criterion["code"],
                    "name": criterion["name"],
                    "before": previous["score"],
                    "after": criterion["score"],
                    "nature": nature,
                    "contribution": round(d_after["weight"] * criterion["effective_weight"] * delta / total, 2)
                    if total
                    else 0,
                }
            )
        contributions.append(
            {
                "dimension": code,
                "name": d_after["short_name"],
                "before": d_before["score"],
                "after": d_after["score"],
                "contribution": round(contribution, 2),
                "criteria": sorted(details, key=lambda item: -abs(item["contribution"])),
            }
        )
    contributions.sort(key=lambda item: -abs(item["contribution"]))
    delta_global = None
    if before["global_score"] is not None and after["global_score"] is not None:
        delta_global = round(after["global_score"] - before["global_score"], 2)
    explained = round(sum(c["contribution"] for c in contributions), 2)
    proof_gain = round(
        sum(d["contribution"] for c in contributions for d in c["criteria"] if d["nature"] == "GAIN_DE_PREUVE"), 2
    )
    return {
        "before": {
            "global_score": before["global_score"],
            "reference_date": before["reference_date"],
            "framework_version": before["framework_version"],
        },
        "after": {
            "global_score": after["global_score"],
            "reference_date": after["reference_date"],
            "framework_version": after["framework_version"],
        },
        "delta_global": delta_global,
        "contributions": contributions,
        "other": round(delta_global - explained, 2) if delta_global is not None else None,
        "proof_gain": proof_gain,
    }
