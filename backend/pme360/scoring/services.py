"""Chargement des entrées du moteur depuis la base, gel des snapshots, comparaison (Document 6, § 3.5 et § 8)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from pme360.audit import services as audit
from pme360.core import events
from pme360.diagnostic.models import (
    Answer,
    Criterion,
    CriterionAssessment,
    Diagnostic,
    Dimension,
    FrameworkVersion,
    MetricDefinition,
    Pillar,
    Question,
)

from . import engine
from .models import MetricValue, ScoreItem, ScoreSnapshot

ANSWER_SOURCE_TO_CONFIDENCE = {
    Answer.Source.PME: "DECLARATIF",
    Answer.Source.REPRISE: "DECLARATIF",
    Answer.Source.CONSEILLER: "DECLARATIF_CORROBORE",
    Answer.Source.IA_PREREMPLI: "INFERE",
}


@dataclass(frozen=True)
class QuestionMeta:
    code: str
    criterion: str | None
    type: str
    feeds: str
    levels: dict[str, int]


_spec_cache: dict[str, tuple[engine.FrameworkSpec, dict[str, QuestionMeta]]] = {}


def load_framework(version: FrameworkVersion) -> tuple[engine.FrameworkSpec, dict[str, QuestionMeta]]:
    """Référentiel sous forme de structures immuables ; mis en cache pour les versions publiées (immuables)."""
    key = str(version.pk)
    if version.status != FrameworkVersion.Status.DRAFT and key in _spec_cache:
        return _spec_cache[key]
    metrics = [
        engine.MetricSpec(
            code=m.code,
            name=m.name,
            criterion=m.criterion.code if m.criterion_id else None,
            formula=m.formula,
            formula_label=m.formula_label,
            unit=m.unit,
            bands=m.bands,
            weight=float(m.weight),
        )
        for m in MetricDefinition.objects.filter(framework_version=version)
        .select_related("criterion")
        .order_by("order")
    ]
    by_criterion: dict[str, list[engine.MetricSpec]] = {}
    for metric in metrics:
        if metric.criterion and metric.weight > 0:
            by_criterion.setdefault(metric.criterion, []).append(metric)
    criteria = tuple(
        engine.CriterionSpec(
            code=c.code,
            name=c.name,
            dimension=c.dimension.code,
            lens=c.lens,
            weight=float(c.weight),
            is_critical=c.is_critical,
            declarative_cap_level=c.declarative_cap_level,
            applicability=c.applicability,
            evidence_policy=c.evidence_policy,
            sector_module=c.sector_module,
            metrics=tuple(by_criterion.get(c.code, ())),
        )
        for c in Criterion.objects.filter(framework_version=version).select_related("dimension").order_by("order")
    )
    dimensions = tuple(
        engine.DimensionSpec(
            code=d.code, name=d.name, short_name=d.short_name, pillar=d.pillar.code, weight=float(d.weight)
        )
        for d in Dimension.objects.filter(framework_version=version).select_related("pillar").order_by("order")
    )
    pillars = {p.code: p.name for p in Pillar.objects.filter(framework_version=version).order_by("order")}
    spec = engine.FrameworkSpec(
        version_id=key,
        version=version.version,
        pillars=pillars,
        dimensions=dimensions,
        criteria=criteria,
        metrics=tuple(metrics),
        settings=version.settings,
    )
    questions = {
        q.code: QuestionMeta(
            code=q.code,
            criterion=q.criterion.code if q.criterion_id else None,
            type=q.type,
            feeds=q.feeds,
            levels={str(o["value"]): int(o["level"]) for o in q.options if "level" in o},
        )
        for q in Question.objects.filter(framework_version=version).select_related("criterion")
    }
    if version.status != FrameworkVersion.Status.DRAFT:
        _spec_cache[key] = (spec, questions)
    return spec, questions


def base_profile(pme, reference_date: date) -> dict:
    age = None
    if pme.creation_date:
        age = math.floor((reference_date - pme.creation_date).days / 365.25 * 10) / 10
    return {
        "sector": pme.sector.code if pme.sector_id else None,
        "size_category": pme.size_category,
        "headcount": pme.headcount,
        "is_company": pme.legal_form.is_company if pme.legal_form_id else None,
        "company_age_years": age,
        "region": pme.region.code if pme.region_id else None,
        "has_stock": None,
        "has_production": None,
        "is_family_business": None,
    }


def answers_by_code(diagnostic: Diagnostic) -> dict[str, Answer]:
    return {
        a.question.code: a
        for a in Answer.objects.filter(diagnostic=diagnostic).select_related("question").order_by("answered_at")
    }


def build_profile(diagnostic: Diagnostic, answers: dict[str, Answer], questions: dict[str, QuestionMeta]) -> dict:
    profile = base_profile(diagnostic.pme, diagnostic.reference_date)
    for code, answer in answers.items():
        meta = questions.get(code)
        if meta and meta.feeds.startswith("profile.") and answer.value is not None:
            profile[meta.feeds.split(".", 1)[1]] = answer.value
    return profile


_criteria_documents_cache: dict[str, dict[str, list[str]]] = {}


def criteria_documents(version: FrameworkVersion) -> dict[str, list[str]]:
    """Critère → types de documents qui le prouvent (``criterion.evidence_document_types``)."""
    key = str(version.pk)
    if version.status == FrameworkVersion.Status.DRAFT or key not in _criteria_documents_cache:
        _criteria_documents_cache[key] = {
            code: list(types)
            for code, types in Criterion.objects.filter(framework_version=version).values_list(
                "code", "evidence_document_types"
            )
            if types
        }
    return _criteria_documents_cache[key]


def build_input(
    diagnostic: Diagnostic,
    version: FrameworkVersion | None = None,
    context: dict | None = None,
    evidence_as_of: date | None = None,
):
    """Entrées du moteur pour ``diagnostic`` évalué avec ``version`` (par défaut, la sienne).

    Les réponses et revues sont rapprochées par CODE de question et de critère : un diagnostic peut ainsi être
    « re-projeté » sur une autre version du référentiel pour comparer ce qui est comparable (Document 6, § 8).
    """
    version = version or diagnostic.framework_version
    spec, questions = load_framework(version)
    answers = answers_by_code(diagnostic)
    profile = build_profile(diagnostic, answers, questions)

    levels: dict[str, list[tuple[int, Answer]]] = {}
    inputs: dict[str, engine.InputValue] = {}
    for code, answer in answers.items():
        meta = questions.get(code)
        if meta is None or answer.value is None:
            continue
        if meta.criterion and str(answer.value) in meta.levels:
            levels.setdefault(meta.criterion, []).append((meta.levels[str(answer.value)], answer))
        elif meta.feeds.startswith("input.") and isinstance(answer.value, int | float):
            inputs[meta.feeds.split(".", 1)[1]] = engine.InputValue(
                value=float(answer.value),
                source=ANSWER_SOURCE_TO_CONFIDENCE[answer.source],
                answered_on=timezone.localtime(answer.answered_at).date(),
            )
    declared = {}
    for criterion, items in levels.items():
        sources = {ANSWER_SOURCE_TO_CONFIDENCE[a.source] for _, a in items}
        declared[criterion] = engine.Declared(
            level=math.floor(sum(level for level, _ in items) / len(items)),
            source="DECLARATIF_CORROBORE" if sources == {"DECLARATIF_CORROBORE"} else sorted(sources)[0],
            answered_on=max(timezone.localtime(a.answered_at).date() for _, a in items),
        )
    from pme360.documents.evidence import evidence_for, verified_documents

    evidence = evidence_for(criteria_documents(version), verified_documents(diagnostic.pme, evidence_as_of))
    reviews = {
        a.criterion.code: engine.Review(status=a.status, level_final=a.level_final, corroborated=a.corroborated)
        for a in CriterionAssessment.objects.filter(diagnostic=diagnostic).select_related("criterion")
    }
    data = engine.DiagnosticInput(
        reference_date=diagnostic.reference_date,
        profile=profile,
        declared=declared,
        inputs=inputs,
        reviews=reviews,
        evidence=evidence,
        context=context if context is not None else priority_context(diagnostic),
    )
    return spec, data


def priority_context(diagnostic: Diagnostic) -> dict:
    """Variables historiques utilisées par les règles de priorité (écarts depuis les snapshots figés)."""
    previous = (
        ScoreSnapshot.objects.filter(pme=diagnostic.pme, is_frozen=True, reference_date__lte=diagnostic.reference_date)
        .exclude(diagnostic=diagnostic)
        .order_by("-reference_date")
    )
    last = previous.first()
    baseline = previous.filter(kind=ScoreSnapshot.Kind.BASELINE).order_by("reference_date").first()
    from pme360.alerts.models import Alert

    open_alerts = Alert.objects.filter(pme=diagnostic.pme, status__in=Alert.OPEN)
    context = {
        "previous_imo": _float(last.imo) if last else None,
        "baseline_global": None,
        "months_since_baseline": None,
        "open_critical_alerts": open_alerts.filter(severity="CRITIQUE").count(),
        "open_high_alerts": open_alerts.filter(severity__in=["ELEVEE", "CRITIQUE"]).count(),
    }
    if baseline:
        context["baseline_global"] = _float(baseline.global_score)
        context["months_since_baseline"] = round((diagnostic.reference_date - baseline.reference_date).days / 30.44, 1)
    return context


def _float(value) -> float | None:
    return None if value is None else float(value)


def compute(
    diagnostic: Diagnostic, version: FrameworkVersion | None = None, evidence_as_of: date | None = None
) -> dict:
    evidence_as_of = evidence_as_of or timezone.localdate()
    spec, data = build_input(diagnostic, version, evidence_as_of=evidence_as_of)
    result = engine.compute(spec, data)
    # Écarts historiques pour les règles de priorité, calculés sur le résultat courant.
    context = data.context
    extra = {}
    if context.get("previous_imo") is not None and result["imo"] is not None:
        extra["delta_imo"] = result["imo"] - context["previous_imo"]
    if context.get("baseline_global") is not None and result["global_score"] is not None:
        extra["delta_global_since_baseline"] = result["global_score"] - context["baseline_global"]
    if extra:
        data.context = {**context, **extra}
        result = engine.compute(spec, data)
    result["evidence_as_of"] = evidence_as_of.isoformat()
    return result


def _decimal(value, places: str = "0.1") -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(Decimal(places))


def snapshot_kind(diagnostic: Diagnostic) -> str:
    if diagnostic.type == Diagnostic.Type.CLOTURE:
        return ScoreSnapshot.Kind.CLOTURE
    has_baseline = ScoreSnapshot.objects.filter(pme=diagnostic.pme, kind=ScoreSnapshot.Kind.BASELINE).exists()
    if diagnostic.type == Diagnostic.Type.INITIAL and not has_baseline:
        return ScoreSnapshot.Kind.BASELINE
    return ScoreSnapshot.Kind.FOLLOW_UP


def freeze(diagnostic: Diagnostic) -> ScoreSnapshot:
    """Calcule et fige le snapshot d'un diagnostic validé (RM-04 : immuable, lié à la version du référentiel)."""
    result = compute(diagnostic, evidence_as_of=timezone.localdate())
    snapshot = ScoreSnapshot.objects.create(
        pme=diagnostic.pme,
        diagnostic=diagnostic,
        framework_version=diagnostic.framework_version,
        kind=snapshot_kind(diagnostic),
        reference_date=diagnostic.reference_date,
        computed_at=timezone.now(),
        engine_version=result["engine_version"],
        global_score=_decimal(result["global_score"]),
        imo=_decimal(result["imo"]),
        ipe=_decimal(result["ipe"]),
        risk_index=_decimal(result["risk_index"]),
        digital_index=_decimal(result["digital"]["index"]),
        confidence=_decimal(result["confidence"], "0.001"),
        maturity_level=result["maturity"]["level"],
        maturity_level_uncapped=result["maturity"]["level_uncapped"],
        gates_failed=result["maturity"]["gates_failed"],
        intervention_priority=result["priority"]["priority"],
        quadrant=result["quadrant"],
        is_frozen=True,
        result=result,
    )
    items = [
        ScoreItem(
            snapshot=snapshot,
            scope=ScoreItem.Scope.DIMENSION,
            ref_code=d["code"],
            score=_decimal(d["score"]),
            confidence=_decimal(d["confidence"], "0.001"),
            status=d["status"],
            details={"coverage": d["coverage"], "weight": d["weight"]},
        )
        for d in result["dimensions"]
    ]
    items += [
        ScoreItem(
            snapshot=snapshot,
            scope=ScoreItem.Scope.CRITERION,
            ref_code=c["code"],
            score=_decimal(c["score"]),
            confidence=_decimal(c["confidence"], "0.001"),
            status=c["status"],
            details={"level": c["level"], "capped": c["capped"], "source": c["source"]},
        )
        for c in result["criteria"]
    ]
    items += [
        ScoreItem(
            snapshot=snapshot,
            scope=ScoreItem.Scope.PILLAR,
            ref_code=p["code"],
            score=_decimal(p["score"]),
            status="EVALUE" if p["score"] is not None else "NON_EVALUABLE",
        )
        for p in result["pillars"]
    ]
    items += [
        ScoreItem(
            snapshot=snapshot,
            scope=ScoreItem.Scope.LENS,
            ref_code=lens,
            score=_decimal(score),
            status="EVALUE" if score is not None else "NON_EVALUABLE",
        )
        for lens, score in result["lenses"].items()
    ]
    ScoreItem.objects.bulk_create(items)
    MetricValue.objects.bulk_create(
        [
            MetricValue(
                snapshot=snapshot,
                metric_code=m["code"],
                value=_decimal(m["value"], "0.000001"),
                points=m["points"],
                band_label=m["band"] or "",
                inputs_used=m["inputs"],
                sources=m["sources"],
            )
            for m in result["metrics"]
        ]
    )
    audit.record(
        "score.snapshot_frozen",
        instance=snapshot,
        pme_id=diagnostic.pme_id,
        after={
            "kind": snapshot.kind,
            "global_score": result["global_score"],
            "maturity_level": snapshot.maturity_level,
            "confidence": result["confidence"],
            "framework_version": result["framework_version"],
        },
    )
    events.emit("score.changed", pme_id=str(diagnostic.pme_id), snapshot_id=str(snapshot.pk))
    return snapshot


def compare(before: ScoreSnapshot, after: ScoreSnapshot) -> dict:
    """Explique l'écart entre deux snapshots ; re-projette le premier si le référentiel a changé."""
    before_result = before.result
    reprojected = False
    if before.framework_version_id != after.framework_version_id and before.diagnostic_id:
        as_of = before.result.get("evidence_as_of")
        spec, data = build_input(
            before.diagnostic,
            after.framework_version,
            context={},
            evidence_as_of=date.fromisoformat(as_of) if as_of else before.reference_date,
        )
        before_result = engine.compute(spec, data)
        reprojected = True
    explanation = engine.explain_change(before_result, after.result)
    explanation["reprojected_baseline"] = reprojected
    if reprojected:
        explanation["before"]["original_global_score"] = before.result["global_score"]
    return explanation


def latest_validated(pme) -> Diagnostic | None:
    return Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date").first()


def refresh_live(pme) -> ScoreSnapshot | None:
    """Score courant (Document 7, § 6) : dernier diagnostic validé + preuves vérifiées à ce jour. Non figé."""
    ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE).delete()
    diagnostic = latest_validated(pme)
    if diagnostic is None:
        return None
    result = compute(diagnostic)
    result["source_diagnostic"] = str(diagnostic.pk)
    return ScoreSnapshot.objects.create(
        pme=pme,
        diagnostic=None,
        framework_version=diagnostic.framework_version,
        kind=ScoreSnapshot.Kind.LIVE,
        reference_date=timezone.localdate(),
        computed_at=timezone.now(),
        engine_version=result["engine_version"],
        global_score=_decimal(result["global_score"]),
        imo=_decimal(result["imo"]),
        ipe=_decimal(result["ipe"]),
        risk_index=_decimal(result["risk_index"]),
        digital_index=_decimal(result["digital"]["index"]),
        confidence=_decimal(result["confidence"], "0.001"),
        maturity_level=result["maturity"]["level"],
        maturity_level_uncapped=result["maturity"]["level_uncapped"],
        gates_failed=result["maturity"]["gates_failed"],
        intervention_priority=result["priority"]["priority"],
        quadrant=result["quadrant"],
        is_frozen=False,
        result=result,
    )
