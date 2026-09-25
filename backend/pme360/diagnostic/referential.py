"""Gestion du référentiel : installation, validation, clonage et publication (Document 6, § 11 ; ADR-004)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from pme360.audit import services as audit
from pme360.core import expressions, jsonlogic

from . import gude360_v1 as spec
from .models import Criterion, Dimension, Framework, FrameworkVersion, MetricDefinition, Pillar, Question

CONTENT_MODELS = (Pillar, Dimension, Criterion, Question, MetricDefinition)


def _anchor_options(anchors: list[str]) -> list[dict]:
    return [{"value": str(level), "label": label, "level": level} for level, label in enumerate(anchors)]


@transaction.atomic
def install_gude360(organization, published_by=None) -> FrameworkVersion:
    """Installe le référentiel GUDE-360 v1 publié dans ``organization`` (idempotent)."""
    framework, _ = Framework.objects.get_or_create(
        organization=organization, code=spec.FRAMEWORK_CODE, defaults={"name": spec.FRAMEWORK_NAME}
    )
    existing = FrameworkVersion.objects.filter(framework=framework, version=spec.VERSION).first()
    if existing:
        return existing
    version = FrameworkVersion.objects.create(
        organization=organization,
        framework=framework,
        version=spec.VERSION,
        settings=spec.SETTINGS,
        notes="Proposition initiale (Documents 5 et 6) — à valider en atelier (décision D-04).",
    )
    common = {"organization": organization, "framework_version": version}
    pillars = {
        code: Pillar.objects.create(**common, code=code, name=name, weight=weight, order=index)
        for index, (code, name, weight) in enumerate(spec.PILLARS)
    }
    dimensions = {}
    for index, (code, pillar, short, name, weight, module_share, description) in enumerate(spec.DIMENSIONS):
        dimensions[code] = Dimension.objects.create(
            **common,
            pillar=pillars[pillar],
            code=code,
            name=name,
            short_name=short,
            weight=weight,
            sector_module_share=module_share,
            description=description,
            order=index,
        )
    order = 0
    for index, item in enumerate(spec.PROFILE_QUESTIONS):
        Question.objects.create(
            **common,
            dimension=dimensions["D01"],
            code=item["code"],
            text=item["q"],
            why_text=item["why"],
            type=item["type"],
            target_audience=item["audience"],
            feeds=item["feeds"],
            order=index,
        )
    criteria = {}
    for index, item in enumerate(spec.CRITERIA):
        lens = item["lens"]
        anchors = item.get("anchors") or spec.GENERIC_ANCHORS[lens]
        criterion = Criterion.objects.create(
            **common,
            dimension=dimensions[item["dim"]],
            code=item["code"],
            name=item["name"],
            lens=lens,
            weight=item["weight"],
            is_critical=item.get("critical", False),
            rubric=anchors,
            applicability=item.get("when"),
            evidence_policy=item.get("evidence", "NONE"),
            evidence_document_types=item.get("docs", []),
            sector_module=item.get("module", ""),
            order=index,
        )
        criteria[item["code"]] = criterion
        if item.get("q"):
            order += 1
            Question.objects.create(
                **common,
                criterion=criterion,
                code=f"Q-{item['code']}",
                text=item["q"],
                why_text=item.get("why", ""),
                type=Question.Type.SINGLE,
                options=_anchor_options(anchors),
                target_audience=item.get("audience", "LES_DEUX"),
                evidence_hint=item.get("hint", ""),
                order=100 + index,
            )
    for index, (key, qtype, label) in enumerate(spec.FINANCIAL_INPUTS):
        Question.objects.create(
            **common,
            dimension=dimensions["D04"],
            code=f"FIN-IN-{key}",
            text=label,
            type=qtype,
            feeds=f"input.{key}",
            is_required=False,
            order=500 + index,
            help_text="Reportez le montant de vos derniers états financiers ; "
            "laissez vide si vous ne le connaissez pas.",
        )
    for index, (code, criterion_code, name, formula, label, unit, bands, weight) in enumerate(spec.METRICS):
        MetricDefinition.objects.create(
            **common,
            criterion=criteria.get(criterion_code),
            code=code,
            name=name,
            formula=formula,
            formula_label=label,
            unit=unit,
            bands=bands,
            weight=weight,
            order=index,
        )
    validate_version(version)
    publish_version(version, published_by, record=False)
    return version


def validate_version(version: FrameworkVersion) -> None:
    """Contrôles de publication (Document 3, § 5.2) ; lève ``ValidationError`` avec la liste des anomalies."""
    errors: list[str] = []
    pillars = list(Pillar.objects.filter(framework_version=version))
    dimensions = list(Dimension.objects.filter(framework_version=version).select_related("pillar"))
    criteria = list(Criterion.objects.filter(framework_version=version).select_related("dimension"))
    questions = list(Question.objects.filter(framework_version=version))
    metrics = list(MetricDefinition.objects.filter(framework_version=version))

    if sum(p.weight for p in pillars) != 100:
        errors.append("La somme des poids des piliers doit être égale à 100.")
    by_pillar = defaultdict(Decimal)
    for dimension in dimensions:
        by_pillar[dimension.pillar.code] += dimension.weight
    for pillar in pillars:
        if by_pillar[pillar.code] != pillar.weight:
            errors.append(
                f"Pilier {pillar.code} : la somme des poids des dimensions ({by_pillar[pillar.code]}) "
                f"doit être égale au poids du pilier ({pillar.weight})."
            )
    common = defaultdict(Decimal)
    modules = defaultdict(Decimal)
    for criterion in criteria:
        if criterion.sector_module:
            modules[(criterion.dimension.code, criterion.sector_module)] += criterion.weight
        else:
            common[criterion.dimension.code] += criterion.weight
        if criterion.is_critical and not criterion.evidence_document_types:
            errors.append(f"{criterion.code} : un critère critique doit définir au moins une preuve.")
        if len(criterion.rubric) != 5:
            errors.append(f"{criterion.code} : la grille doit décrire les niveaux 0 à 4.")
        try:
            jsonlogic.validate(criterion.applicability)
        except jsonlogic.JsonLogicError as exc:
            errors.append(f"{criterion.code} : règle d'applicabilité invalide ({exc}).")
    for dimension in dimensions:
        expected = 100 - dimension.sector_module_share
        if common[dimension.code] != expected:
            errors.append(
                f"{dimension.code} : la somme des poids du tronc commun ({common[dimension.code]}) "
                f"doit être égale à {expected}."
            )
    for (dimension_code, module), total in modules.items():
        share = next(d.sector_module_share for d in dimensions if d.code == dimension_code)
        if total != share:
            errors.append(
                f"{dimension_code} / module {module} : la somme des poids ({total}) doit être égale à {share}."
            )
    for question in questions:
        for option in question.options:
            if not 0 <= int(option.get("level", 0)) <= 4:
                errors.append(f"{question.code} : niveau d'option hors de l'échelle 0 à 4.")
        try:
            jsonlogic.validate(question.visibility)
        except jsonlogic.JsonLogicError as exc:
            errors.append(f"{question.code} : règle de visibilité invalide ({exc}).")
    input_keys = {q.feeds.split(".", 1)[1] for q in questions if q.feeds.startswith("input.")}
    for metric in metrics:
        try:
            missing = expressions.variables(metric.formula) - input_keys
        except expressions.ExpressionError as exc:
            errors.append(f"{metric.code} : {exc}")
            continue
        if missing:
            errors.append(f"{metric.code} : données inconnues dans la formule ({', '.join(sorted(missing))}).")
        thresholds = [band["upto"] for band in metric.bands if band["upto"] is not None]
        if thresholds != sorted(thresholds) or (metric.bands and metric.bands[-1]["upto"] is not None):
            errors.append(f"{metric.code} : bandes non ordonnées ou dernière bande non ouverte.")
    if errors:
        raise ValidationError({"framework_version": errors})


@transaction.atomic
def publish_version(version: FrameworkVersion, user, record: bool = True) -> FrameworkVersion:
    if version.status != FrameworkVersion.Status.DRAFT:
        raise ValidationError({"status": ["Seule une version en brouillon peut être publiée."]})
    validate_version(version)
    previous = FrameworkVersion.objects.filter(framework=version.framework, status=FrameworkVersion.Status.PUBLISHED)
    for old in previous:
        old.status = FrameworkVersion.Status.RETIRED
        old.save(update_fields=["status", "updated_at"])
    version.status = FrameworkVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.published_by = user
    version.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    if record:
        audit.record("framework.published", instance=version, after={"version": version.version})
    return version


@transaction.atomic
def clone_version(source: FrameworkVersion, new_version: str, user) -> FrameworkVersion:
    """Crée un brouillon modifiable à partir d'une version (publiée ou non)."""
    if FrameworkVersion.objects.filter(framework=source.framework, version=new_version).exists():
        raise ValidationError({"version": ["Ce numéro de version existe déjà."]})
    draft = FrameworkVersion.objects.create(
        framework=source.framework,
        version=new_version,
        settings=source.settings,
        created_by=user,
        notes=f"Brouillon créé à partir de la version {source.version}.",
    )
    mapping: dict[type, dict] = defaultdict(dict)
    for model in CONTENT_MODELS:
        for item in model.objects.filter(framework_version=source).order_by("order"):
            old_id = item.pk
            item.pk = None
            item.id = None
            item._state.adding = True
            item.framework_version = draft
            for field, target in (("pillar", Pillar), ("dimension", Dimension), ("criterion", Criterion)):
                if hasattr(item, f"{field}_id") and getattr(item, f"{field}_id"):
                    setattr(item, f"{field}_id", mapping[target][getattr(item, f"{field}_id")])
            item.save()
            mapping[model][old_id] = item.pk
    audit.record("framework.cloned", instance=draft, after={"from": source.version, "version": new_version})
    return draft
