"""Moteur de scoring (Document 6) : tests unitaires purs, sans base de données."""

import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from pme360.core import expressions, jsonlogic
from pme360.diagnostic import gude360_v1
from pme360.scoring import engine
from pme360.scoring.engine import (
    CriterionSpec,
    Declared,
    DiagnosticInput,
    DimensionSpec,
    Evidence,
    FrameworkSpec,
    InputValue,
    MetricSpec,
    Review,
)

REF = date(2026, 3, 15)
SETTINGS = deepcopy(gude360_v1.SETTINGS)
SETTINGS["digital_index"] = {
    "dimension": "D2",
    "extra_criteria": [],
    "levels": gude360_v1.SETTINGS["digital_index"]["levels"],
}

MARGE = MetricSpec(
    code="MARGE",
    name="Marge nette",
    criterion="P1",
    formula="resultat / ca",
    formula_label="Résultat / CA",
    unit="PERCENT",
    bands=[
        {"upto": 0, "points": 0, "label": "Critique"},
        {"upto": 0.05, "points": 50, "label": "Acceptable"},
        {"upto": None, "points": 100, "label": "Excellent"},
    ],
    weight=1,
)


def crit(code, dimension, lens, weight, **extra) -> CriterionSpec:
    defaults = dict(
        is_critical=False,
        declarative_cap_level=2,
        applicability=None,
        evidence_policy="NONE",
        sector_module="",
        metrics=(),
    )
    return CriterionSpec(code=code, name=code, dimension=dimension, lens=lens, weight=weight, **{**defaults, **extra})


def spec(**overrides) -> FrameworkSpec:
    criteria = overrides.pop(
        "criteria",
        (
            crit("C1", "D1", "C", 50, is_critical=True, evidence_policy="REQUIRED"),
            crit("O1", "D1", "O", 30),
            crit("R1", "D1", "R", 20),
            crit("P1", "D2", "P", 60, metrics=(MARGE,)),
            crit("O2", "D2", "O", 40, applicability={">=": [{"var": "headcount"}, 1]}),
        ),
    )
    return FrameworkSpec(
        version_id="v1",
        version="1.0.0",
        pillars={"A": "Conformité", "B": "Performance"},
        dimensions=(
            DimensionSpec("D1", "Dimension 1", "D1", "A", 60),
            DimensionSpec("D2", "Dimension 2", "D2", "B", 40),
        ),
        criteria=criteria,
        metrics=(MARGE,),
        settings=overrides.pop("settings", SETTINGS),
    )


def declared(level, source="DECLARATIF", days_ago=0):
    return Declared(level=level, source=source, answered_on=REF - timedelta(days=days_ago))


def data(levels=None, inputs=None, **extra) -> DiagnosticInput:
    levels = levels if levels is not None else {"C1": 4, "O1": 3, "R1": 2, "O2": 1}
    return DiagnosticInput(
        reference_date=REF,
        profile=extra.pop("profile", {"headcount": 5, "sector": "COMMERCE"}),
        declared={code: declared(level) for code, level in levels.items()},
        inputs=inputs
        if inputs is not None
        else {"resultat": InputValue(8, "DECLARATIF", REF), "ca": InputValue(100, "DECLARATIF", REF)},
        **extra,
    )


def by_code(items, code):
    return next(item for item in items if item["code"] == code)


# --- Critères -------------------------------------------------------------------------------------------------


def test_grid_score_and_declarative_cap_without_evidence():
    result = engine.compute(spec(), data())
    c1 = by_code(result["criteria"], "C1")
    assert c1["level_uncapped"] == 4 and c1["level"] == 2 and c1["capped"] and c1["score"] == 50  # RM-01
    assert by_code(result["criteria"], "O1")["score"] == 75  # pas de plafond sans politique REQUIRED


def test_verified_evidence_lifts_cap_and_proves():
    evidence = {"C1": Evidence(verified=True, level=4, source="DOCUMENT_VERIFIE", dated=REF)}
    c1 = by_code(engine.compute(spec(), data(evidence=evidence))["criteria"], "C1")
    assert c1["score"] == 100 and c1["proven"] and not c1["capped"] and c1["confidence"] == 1.0


def test_metric_criterion_uses_bands_and_reports_formula():
    result = engine.compute(spec(), data())
    p1 = by_code(result["criteria"], "P1")
    assert p1["score"] == 100 and p1["source"] == "INDICATEURS"
    metric = by_code(result["metrics"], "MARGE")
    assert (
        metric["value"] == 0.08 and metric["band"] == "Excellent" and metric["inputs"] == {"ca": 100.0, "resultat": 8.0}
    )


@pytest.mark.parametrize(
    "inputs", [{}, {"resultat": InputValue(5, "DECLARATIF", REF), "ca": InputValue(0, "DECLARATIF", REF)}]
)
def test_missing_or_invalid_metric_input_is_not_evaluated(inputs):
    result = engine.compute(spec(), data(inputs=inputs))
    assert by_code(result["criteria"], "P1")["status"] == engine.STATUS_NOT_EVALUATED
    assert result["ipe"] is None and result["quadrant"] == "NON_DETERMINE"


def test_review_overrides_declared_level_and_can_exclude_criterion():
    reviews = {"O1": Review(status="MODIFIE", level_final=1), "R1": Review(status="NON_APPLICABLE", level_final=None)}
    result = engine.compute(spec(), data(reviews=reviews))
    assert by_code(result["criteria"], "O1")["score"] == 25
    assert by_code(result["criteria"], "R1")["status"] == engine.STATUS_NOT_APPLICABLE
    assert result["risk_index"] is None


def test_applicability_rule_removes_criterion_and_renormalises_weights():
    result = engine.compute(spec(), data(profile={"headcount": 0}))
    o2 = by_code(result["criteria"], "O2")
    assert o2["status"] == engine.STATUS_NOT_APPLICABLE and o2["effective_weight"] == 0
    assert by_code(result["criteria"], "P1")["effective_weight"] == 1.0
    assert by_code(result["dimensions"], "D2")["score"] == 100


# --- Confiance ------------------------------------------------------------------------------------------------


def test_confidence_by_source_and_freshness():
    levels = {
        "C1": declared(2),
        "O1": declared(2, "DECLARATIF_CORROBORE"),
        "R1": declared(2, days_ago=365 + 182),
        "O2": declared(2, days_ago=900),
    }
    result = engine.compute(spec(), DiagnosticInput(reference_date=REF, profile={"headcount": 5}, declared=levels))
    assert by_code(result["criteria"], "C1")["confidence"] == 0.45
    assert by_code(result["criteria"], "O1")["confidence"] == 0.6
    assert by_code(result["criteria"], "R1")["confidence"] == pytest.approx(0.45 * 0.7507, abs=1e-3)
    assert by_code(result["criteria"], "O2")["confidence"] == pytest.approx(0.225)


def test_corroborated_review_raises_confidence():
    reviews = {"C1": Review(status="VALIDE", level_final=2, corroborated=True)}
    assert by_code(engine.compute(spec(), data(reviews=reviews))["criteria"], "C1")["confidence"] == 0.6


def test_unanswered_criterion_counts_as_zero_confidence():
    result = engine.compute(spec(), data(levels={"C1": 2, "O1": 2}))
    d1 = by_code(result["dimensions"], "D1")
    assert d1["coverage"] == 0.8 and d1["confidence"] == pytest.approx(0.8 * 0.45)


# --- Agrégation ---------------------------------------------------------------------------------------------


def test_global_score_is_weighted_mean_of_dimensions():
    result = engine.compute(spec(), data())
    d1 = by_code(result["dimensions"], "D1")["score"]  # 0,5×50 + 0,3×75 + 0,2×50 = 57,5
    d2 = by_code(result["dimensions"], "D2")["score"]  # 0,6×100 + 0,4×25 = 70
    assert (d1, d2) == (57.5, 70)
    assert result["global_score"] == pytest.approx((60 * 57.5 + 40 * 70) / 100, abs=0.01)


def test_health_check_example_of_document_6():
    """Vérification du calcul publié au Document 6, § 10 (Boutik Plus) : 51,8."""
    weights = [10, 10, 10, 15, 7, 8, 8, 7, 5, 8, 6, 6]
    scores = [60, 55, 40, 58, 45, 78, 62, 35, 42, 30, 50, 55]
    assert round(engine._weighted(list(zip(weights, scores, strict=True))), 1) == 51.8


def test_coverage_thresholds_provisional_and_non_evaluable():
    provisional = engine.compute(spec(), data(levels={"C1": 2, "O1": 2, "O2": 2}))  # D1 couvert à 80 %
    assert by_code(provisional["dimensions"], "D1")["status"] == engine.DIM_EVALUATED
    partial = engine.compute(spec(), data(levels={"C1": 2}))  # D1 couvert à 50 %
    assert by_code(partial["dimensions"], "D1")["status"] == engine.DIM_PROVISIONAL
    scarce = engine.compute(spec(), data(levels={"R1": 2}))  # D1 couvert à 20 %
    d1 = by_code(scarce["dimensions"], "D1")
    assert d1["status"] == engine.DIM_NOT_EVALUABLE and d1["score"] is None
    assert scarce["global_score"] == by_code(scarce["dimensions"], "D2")["score"]  # poids renormalisés


def test_dimension_excluded_when_mostly_not_applicable():
    reviews = {code: Review(status="NON_APPLICABLE", level_final=None) for code in ("C1", "O1")}
    d1 = by_code(engine.compute(spec(), data(reviews=reviews))["dimensions"], "D1")
    assert d1["status"] == engine.DIM_EXCLUDED and d1["confidence"] is None


def test_sector_module_only_for_matching_sector():
    criteria = (
        crit("C1", "D1", "C", 85),
        crit("MOD-A", "D1", "O", 15, sector_module="AGRO"),
        crit("MOD-B", "D1", "O", 15, sector_module="BTP"),
        crit("P1", "D2", "P", 100, metrics=(MARGE,)),
    )
    levels = {"C1": 2, "MOD-A": 4, "MOD-B": 0}
    agro = engine.compute(spec(criteria=criteria), data(levels=levels, profile={"sector": "AGRO"}))
    assert by_code(agro["criteria"], "MOD-B")["status"] == engine.STATUS_NOT_APPLICABLE
    assert by_code(agro["dimensions"], "D1")["score"] == pytest.approx(0.85 * 50 + 0.15 * 100)
    other = engine.compute(spec(criteria=criteria), data(levels=levels, profile={"sector": "TECH"}))
    d1 = by_code(other["dimensions"], "D1")
    assert d1["score"] == 50 and d1["status"] == engine.DIM_EVALUATED and d1["not_applicable_share"] == 0


def test_indices_separate_maturity_and_performance():
    result = engine.compute(spec(), data())
    assert result["ipe"] == 100  # seule la lentille P
    expected_imo = engine._weighted([(0.5 * 60, 50), (0.3 * 60, 75), (0.2 * 60, 50), (0.4 * 40, 25)])
    assert result["imo"] == pytest.approx(expected_imo, abs=0.01)
    assert result["risk_index"] == 50
    assert result["quadrant"] == "STRUCTUREE_A_DEVELOPPER" if result["imo"] >= 55 else "PERFORMANTE_FRAGILE"


# --- Niveaux, portes, priorité ------------------------------------------------------------------------------


def test_level_is_capped_by_gates_with_explanation():
    all_top = {"C1": 4, "O1": 4, "R1": 4, "O2": 4}
    result = engine.compute(spec(), data(levels=all_top))
    maturity = result["maturity"]
    # IMO élevé, mais le critère critique C1 n'est pas prouvé : la porte du niveau 4 bloque.
    assert maturity["level_uncapped"] >= 4 and maturity["level"] == 3 and maturity["capped"]
    rules = {g["rule"] for g in maturity["gates_failed"]}
    assert "critical_proven" in rules


def test_gate_level_2_requires_critical_pillar_a():
    result = engine.compute(spec(), data(levels={"C1": 0, "O1": 4, "R1": 4, "O2": 4}))
    assert result["maturity"]["level"] == 1
    assert result["maturity"]["gates_failed"][0]["criteria"] == ["C1"]


def test_full_evidence_reaches_top_levels():
    evidence = {"C1": Evidence(True, 4, "DOCUMENT_VERIFIE", REF)}
    levels = {code: declared(4, "DECLARATIF_CORROBORE") for code in ("O1", "R1", "O2")}
    reviews = {code: Review("VALIDE", 4, corroborated=True) for code in ("O1", "R1", "O2")}
    settings = deepcopy(SETTINGS)
    settings["confidence"]["sources"]["DECLARATIF_CORROBORE"] = 0.9
    payload = DiagnosticInput(
        REF,
        {"headcount": 3},
        declared=levels,
        reviews=reviews,
        evidence=evidence,
        inputs={"resultat": InputValue(20, "DOCUMENT_VERIFIE", REF), "ca": InputValue(100, "DOCUMENT_VERIFIE", REF)},
    )
    result = engine.compute(spec(settings=settings), payload)
    assert result["maturity"]["level"] == 5 and not result["maturity"]["gates_failed"]
    assert result["priority"]["priority"] == "P4"
    assert result["confidence_label"] == "Élevée"


@pytest.mark.parametrize(
    ("levels", "context", "expected"),
    [
        ({"C1": 1, "O1": 1, "R1": 0, "O2": 0}, {}, "P1"),  # exposition au risque ≥ 70
        ({"C1": 2, "O1": 2, "R1": 2, "O2": 2}, {}, "P2"),  # IMO < 55
        ({"C1": 4, "O1": 4, "R1": 4, "O2": 4}, {"open_critical_alerts": 1}, "P1"),
        ({"C1": 4, "O1": 4, "R1": 3, "O2": 4}, {}, "P3"),
    ],
)
def test_intervention_priority_rules(levels, context, expected):
    assert engine.compute(spec(), data(levels=levels, context=context))["priority"]["priority"] == expected


def test_priority_rules_are_configuration_not_code():
    settings = deepcopy(SETTINGS)
    settings["priority_rules"] = [{"priority": "P1", "label": "Tout", "condition": {"==": [1, 1]}}]
    assert engine.compute(spec(settings=settings), data())["priority"]["priority"] == "P1"


def test_gaps_rank_critical_then_potential_gain():
    gaps = engine.compute(spec(), data())["gaps"]
    assert gaps[0]["criterion"] == "C1" and gaps[0]["capped"]
    assert all(g["potential_gain"] > 0 for g in gaps)


# --- Reproductibilité et explications -----------------------------------------------------------------------


def test_engine_is_pure_and_serialisable():
    first, second = engine.compute(spec(), data()), engine.compute(spec(), data())
    assert first == second
    assert json.loads(json.dumps(first)) == first
    assert first["engine_version"] == engine.ENGINE_VERSION


def test_explain_change_contributions_and_proof_gain():
    before = engine.compute(spec(), data(levels={"C1": 4, "O1": 1, "R1": 2, "O2": 1}))
    evidence = {"C1": Evidence(True, 4, "DOCUMENT_VERIFIE", REF)}
    after = engine.compute(spec(), data(levels={"C1": 4, "O1": 3, "R1": 2, "O2": 1}, evidence=evidence))
    explanation = engine.explain_change(before, after)
    assert explanation["delta_global"] == pytest.approx(after["global_score"] - before["global_score"], abs=0.02)
    assert explanation["other"] == pytest.approx(0, abs=0.05)
    d1 = next(c for c in explanation["contributions"] if c["dimension"] == "D1")
    natures = {d["criterion"]: d["nature"] for d in d1["criteria"]}
    assert natures == {"C1": "GAIN_DE_PREUVE", "O1": "PROGRES"}
    assert explanation["proof_gain"] > 0


def test_gude360_settings_are_consistent():
    levels = [lvl["min"] for lvl in gude360_v1.SETTINGS["maturity_levels"]]
    assert levels == sorted(levels) and levels[0] == 0
    for rule in gude360_v1.SETTINGS["priority_rules"]:
        jsonlogic.validate(rule["condition"])


# --- Règles et formules -------------------------------------------------------------------------------------


def test_jsonlogic_operators():
    payload = {"a": 5, "b": {"c": [1, 2]}, "flag": True}
    assert jsonlogic.evaluate({"and": [{">=": [{"var": "a"}, 5]}, {"in": [2, {"var": "b.c"}]}]}, payload)
    assert jsonlogic.evaluate({"<": [1, {"var": "a"}, 10]}, payload)
    assert jsonlogic.evaluate({"if": [{"var": "flag"}, "oui", "non"]}, payload) == "oui"
    assert jsonlogic.evaluate({"missing": ["a", "z"]}, payload) == ["z"]
    assert jsonlogic.evaluate({"<": [{"var": "absent"}, 3]}, payload) is False
    assert jsonlogic.evaluate({"/": [{"var": "a"}, 0]}, payload) is None
    with pytest.raises(jsonlogic.JsonLogicError):
        jsonlogic.validate({"eval": ["import os"]})


@pytest.mark.parametrize(
    "formula", ["__import__('os')", "a.b", "[1, 2]", "a if b else c", "open('x')", "'texte'", "lambda: 1"]
)
def test_formulas_reject_arbitrary_code(formula):
    with pytest.raises(expressions.ExpressionError):
        expressions.evaluate(formula, {"a": 1, "b": 2, "c": 3})


def test_formula_evaluation():
    assert expressions.evaluate("(a - b) / b", {"a": 120, "b": 100}) == pytest.approx(0.2)
    assert expressions.evaluate("max(a, 0) + abs(-b)", {"a": -3, "b": 2}) == 2
    with pytest.raises(expressions.MissingInput):
        expressions.evaluate("a / b", {"a": 1, "b": 0})
    with pytest.raises(expressions.MissingInput):
        expressions.evaluate("a + b", {"a": 1})
    assert expressions.variables("dettes / (resultat + dotations)") == {"dettes", "resultat", "dotations"}


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"==": [1, 1]}, True),
        ({"!=": [1, 2]}, True),
        ({"!": [False]}, True),
        ({"!!": [[1]]}, True),
        ({"or": [False, 0, "x"]}, "x"),
        ({"or": [False, 0]}, 0),
        ({"and": [1, 0, 2]}, 0),
        ({"+": [1, 2, 3]}, 6),
        ({"*": [2, 3]}, 6),
        ({"-": [5, 2]}, 3),
        ({"-": [4]}, -4),
        ({"/": [9, 3]}, 3),
        ({"min": [3, 1]}, 1),
        ({"max": [3, 1]}, 3),
        ({"+": [1, None]}, None),
        ({"-": [None, 1]}, None),
        ({"<=": [1, 1]}, True),
        ({">": [2, 1]}, True),
        ({"<": ["a", 1]}, False),
        ({"if": [False, "a", True, "b", "c"]}, "b"),
        ({"if": [False, "a"]}, None),
        ({"var": ["liste.1"]}, 20),
        ({"var": ["absent", "défaut"]}, "défaut"),
        ({"var": [""]}, "WHOLE"),
        ({"in": ["x", None]}, False),
        ([{"var": "n"}, 2], [7, 2]),
        (5, 5),
    ],
)
def test_jsonlogic_table(rule, expected):
    payload = {"liste": [10, 20], "n": 7}
    result = jsonlogic.evaluate(rule, payload)
    assert (result is payload) if expected == "WHOLE" else result == expected


def test_jsonlogic_rejects_unknown_operators():
    with pytest.raises(jsonlogic.JsonLogicError):
        jsonlogic.evaluate({"exec": [1]}, {})
    with pytest.raises(jsonlogic.JsonLogicError):
        jsonlogic.validate({"==": [1, 1], "or": []})
