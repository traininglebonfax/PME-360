"""Éditeur sans code du référentiel (Document 10, V1 ; Document 6, § 11 ; ADR-004).

On n'édite qu'un BROUILLON (clone d'une version) : une version publiée est immuable (trigger PostgreSQL). Les
modifications sont enregistrées une à une, même si les pondérations sont provisoirement déséquilibrées ; l'état
de publication (anomalies bloquantes et avertissements) est recalculé à chaque lecture et la publication reste
refusée tant qu'une anomalie subsiste (``referential.validate_version``). Tout est tracé au journal d'audit.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core import jsonlogic
from pme360.core.exceptions import BusinessError

from . import referential
from .models import Criterion, Dimension, FrameworkVersion, MetricDefinition, Pillar, Question

CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{2,40}$")
LENSES = {choice for choice, _ in Criterion.Lens.choices}


def _require(access, version: FrameworkVersion) -> None:
    if not access.has("org.configure") or access.is_pme_user:
        raise PermissionDenied()
    if version.status != FrameworkVersion.Status.DRAFT:
        raise BusinessError(
            "Une version publiée ou retirée ne se modifie pas : créez un brouillon à partir de celle-ci.",
            code="version_not_draft",
        )


def _snapshot(instance, fields) -> dict:
    data = {}
    for name in fields:
        value = getattr(instance, name)
        value = getattr(value, "code", value)
        data[name] = str(value) if isinstance(value, Decimal) else value
    return data


def _weight(value, field: str = "weight", allow_zero: bool = False) -> Decimal:
    try:
        weight = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({field: ["Nombre attendu."]}) from exc
    if weight < 0 or weight > 100 or (weight == 0 and not allow_zero):
        raise ValidationError({field: ["Entre 0 et 100." if allow_zero else "Supérieur à 0 et au plus 100."]})
    return weight


def _code(version: FrameworkVersion, model, value) -> str:
    code = (value or "").strip().upper()
    if not CODE_PATTERN.match(code):
        raise ValidationError({"code": ["Code en majuscules, chiffres, - et _ (2 à 40 caractères)."]})
    if model.objects.filter(framework_version=version, code=code).exists():
        raise ValidationError({"code": ["Ce code existe déjà dans cette version."]})
    return code


def _text(data: dict, field: str, label: str, required: bool = True, max_length: int | None = None) -> str | None:
    if field not in data:
        return None
    value = (data[field] or "").strip()
    if required and not value:
        raise ValidationError({field: [f"{label} obligatoire."]})
    if max_length and len(value) > max_length:
        raise ValidationError({field: [f"{max_length} caractères au plus."]})
    return value


def _logic(field: str, value):
    if value in (None, {}):
        return None
    try:
        jsonlogic.validate(value)
    except jsonlogic.JsonLogicError as exc:
        raise ValidationError({field: [str(exc)]}) from exc
    return value


def _record(action: str, version: FrameworkVersion, instance, before: dict, after: dict) -> None:
    audit.record(
        f"framework.{action}",
        instance=instance,
        before=before,
        after={**after, "version": version.version},
    )


# --- Piliers et dimensions -----------------------------------------------------------------------------------

PILLAR_FIELDS = ("name", "weight")
DIMENSION_FIELDS = ("name", "short_name", "description", "weight", "sector_module_share", "pillar", "order")


def update_pillar(access, version: FrameworkVersion, pillar: Pillar, data: dict) -> Pillar:
    _require(access, version)
    before = _snapshot(pillar, PILLAR_FIELDS)
    if (name := _text(data, "name", "Libellé", max_length=200)) is not None:
        pillar.name = name
    if "weight" in data:
        pillar.weight = _weight(data["weight"])
    pillar.save()
    _record("pillar_updated", version, pillar, before, _snapshot(pillar, PILLAR_FIELDS))
    return pillar


def save_dimension(access, version: FrameworkVersion, data: dict, dimension: Dimension | None = None) -> Dimension:
    _require(access, version)
    creating = dimension is None
    if creating:
        dimension = Dimension(framework_version=version, code=_code(version, Dimension, data.get("code")))
        last = Dimension.objects.filter(framework_version=version).order_by("-order").first()
        dimension.order = (last.order + 1) if last else 0
        for field in ("name", "weight", "pillar"):
            if field not in data:
                raise ValidationError({field: ["Champ obligatoire."]})
    before = {} if creating else _snapshot(dimension, DIMENSION_FIELDS)
    if (name := _text(data, "name", "Libellé", max_length=200)) is not None:
        dimension.name = name
    if (short := _text(data, "short_name", "Nom court", required=False, max_length=60)) is not None:
        dimension.short_name = short
    if (description := _text(data, "description", "Description", required=False)) is not None:
        dimension.description = description
    if "weight" in data:
        dimension.weight = _weight(data["weight"])
    if "sector_module_share" in data:
        dimension.sector_module_share = _weight(data["sector_module_share"], "sector_module_share", allow_zero=True)
    if "pillar" in data:
        pillar = Pillar.objects.filter(framework_version=version, code=data["pillar"]).first()
        if pillar is None:
            raise ValidationError({"pillar": ["Pilier inconnu dans cette version."]})
        dimension.pillar = pillar
    if "order" in data:
        dimension.order = int(data["order"])
    if not dimension.short_name:
        dimension.short_name = dimension.name[:60]
    dimension.save()
    _record(
        "dimension_created" if creating else "dimension_updated",
        version,
        dimension,
        before,
        _snapshot(dimension, DIMENSION_FIELDS),
    )
    return dimension


def delete_dimension(access, version: FrameworkVersion, dimension: Dimension) -> None:
    _require(access, version)
    if dimension.criteria.exists() or dimension.questions.exists():
        raise BusinessError(
            "Cette dimension contient encore des critères ou des questions : déplacez-les ou supprimez-les d'abord.",
            code="dimension_not_empty",
        )
    before = _snapshot(dimension, DIMENSION_FIELDS)
    _record("dimension_deleted", version, dimension, before, {"code": dimension.code})
    dimension.delete()


# --- Critères ------------------------------------------------------------------------------------------------

CRITERION_FIELDS = (
    "name",
    "dimension",
    "lens",
    "weight",
    "is_critical",
    "rubric",
    "declarative_cap_level",
    "applicability",
    "evidence_policy",
    "evidence_document_types",
    "sector_module",
    "order",
)


def _sync_rubric_question(criterion: Criterion) -> None:
    """Les libellés des options de la question principale suivent la grille du critère (niveaux 0 à 4)."""
    question = Question.objects.filter(
        framework_version=criterion.framework_version, criterion=criterion, type=Question.Type.SINGLE
    ).first()
    if question and all(str(o.get("value")) == str(o.get("level")) for o in question.options):
        question.options = [
            {"value": str(level), "label": label, "level": level} for level, label in enumerate(criterion.rubric)
        ]
        question.save(update_fields=["options", "updated_at"])


@transaction.atomic
def save_criterion(access, version: FrameworkVersion, data: dict, criterion: Criterion | None = None) -> Criterion:
    from pme360.documents.models import DocumentType
    from pme360.pmes.models import Sector

    _require(access, version)
    creating = criterion is None
    if creating:
        criterion = Criterion(framework_version=version, code=_code(version, Criterion, data.get("code")))
        for field in ("name", "dimension", "lens", "weight", "rubric"):
            if field not in data:
                raise ValidationError({field: ["Champ obligatoire."]})
    elif "code" in data and data["code"] != criterion.code:
        raise ValidationError({"code": ["Le code d'un critère ne se modifie pas (il est référencé par les règles)."]})
    before = {} if creating else _snapshot(criterion, CRITERION_FIELDS)
    rubric_changed = False
    if (name := _text(data, "name", "Libellé", max_length=300)) is not None:
        criterion.name = name
    if "dimension" in data:
        dimension = Dimension.objects.filter(framework_version=version, code=data["dimension"]).first()
        if dimension is None:
            raise ValidationError({"dimension": ["Dimension inconnue dans cette version."]})
        criterion.dimension = dimension
    if "lens" in data:
        if data["lens"] not in LENSES:
            raise ValidationError({"lens": ["Lentille inconnue."]})
        criterion.lens = data["lens"]
    if "weight" in data:
        criterion.weight = _weight(data["weight"])
    if "is_critical" in data:
        criterion.is_critical = bool(data["is_critical"])
    if "rubric" in data:
        rubric = [str(item).strip() for item in (data["rubric"] or [])]
        if len(rubric) != 5 or not all(rubric):
            raise ValidationError({"rubric": ["Décrivez les cinq niveaux, de 0 à 4."]})
        rubric_changed = rubric != criterion.rubric
        criterion.rubric = rubric
    if "declarative_cap_level" in data:
        cap = int(data["declarative_cap_level"])
        if not 0 <= cap <= 4:
            raise ValidationError({"declarative_cap_level": ["Niveau entre 0 et 4."]})
        criterion.declarative_cap_level = cap
    if "applicability" in data:
        criterion.applicability = _logic("applicability", data["applicability"])
    if "evidence_policy" in data:
        if data["evidence_policy"] not in Criterion.EvidencePolicy.values:
            raise ValidationError({"evidence_policy": ["Valeur inconnue."]})
        criterion.evidence_policy = data["evidence_policy"]
    if "evidence_document_types" in data:
        codes = list(dict.fromkeys(data["evidence_document_types"] or []))
        unknown = set(codes) - set(DocumentType.objects.filter(code__in=codes).values_list("code", flat=True))
        if unknown:
            raise ValidationError(
                {"evidence_document_types": [f"Types de documents inconnus : {', '.join(sorted(unknown))}."]}
            )
        criterion.evidence_document_types = codes
    if "sector_module" in data:
        module = (data["sector_module"] or "").strip()
        if module and not Sector.objects.filter(code=module).exists():
            raise ValidationError({"sector_module": ["Secteur inconnu."]})
        criterion.sector_module = module
    if "order" in data:
        criterion.order = int(data["order"])
    elif creating:
        last = Criterion.objects.filter(framework_version=version).order_by("-order").first()
        criterion.order = (last.order + 1) if last else 0
    criterion.save()
    if creating and (text := (data.get("question") or "").strip()):
        Question.objects.create(
            framework_version=version,
            criterion=criterion,
            code=f"Q-{criterion.code}",
            text=text[:500],
            type=Question.Type.SINGLE,
            options=[
                {"value": str(level), "label": label, "level": level} for level, label in enumerate(criterion.rubric)
            ],
            order=100 + criterion.order,
        )
    elif rubric_changed:
        _sync_rubric_question(criterion)
    _record(
        "criterion_created" if creating else "criterion_updated",
        version,
        criterion,
        before,
        _snapshot(criterion, CRITERION_FIELDS),
    )
    return criterion


@transaction.atomic
def delete_criterion(access, version: FrameworkVersion, criterion: Criterion) -> None:
    _require(access, version)
    before = _snapshot(criterion, CRITERION_FIELDS)
    _record("criterion_deleted", version, criterion, before, {"code": criterion.code})
    MetricDefinition.objects.filter(criterion=criterion).delete()
    Question.objects.filter(criterion=criterion).delete()
    criterion.delete()


# --- Questions -----------------------------------------------------------------------------------------------

QUESTION_FIELDS = (
    "text",
    "help_text",
    "why_text",
    "type",
    "options",
    "visibility",
    "target_audience",
    "is_required",
    "evidence_hint",
    "order",
)


def _options(value, qtype: str) -> list[dict]:
    if qtype != Question.Type.SINGLE:
        return []
    options = []
    for index, item in enumerate(value or []):
        label = str(item.get("label", "")).strip()
        try:
            level = int(item.get("level"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"options": [f"Option {index + 1} : niveau attendu (0 à 4)."]}) from exc
        if not label or not 0 <= level <= 4:
            raise ValidationError({"options": [f"Option {index + 1} : libellé et niveau entre 0 et 4."]})
        options.append({"value": str(item.get("value") or level), "label": label, "level": level})
    if len(options) < 2:
        raise ValidationError({"options": ["Au moins deux réponses possibles."]})
    if len({o["value"] for o in options}) != len(options):
        raise ValidationError({"options": ["Deux réponses ont la même valeur."]})
    return options


@transaction.atomic
def save_question(access, version: FrameworkVersion, data: dict, question: Question | None = None) -> Question:
    _require(access, version)
    creating = question is None
    if creating:
        question = Question(framework_version=version, code=_code(version, Question, data.get("code")))
        parent = data.get("criterion") or data.get("dimension")
        if data.get("criterion"):
            question.criterion = Criterion.objects.filter(framework_version=version, code=data["criterion"]).first()
        elif data.get("dimension"):
            question.dimension = Dimension.objects.filter(framework_version=version, code=data["dimension"]).first()
        if not parent or (question.criterion_id is None and question.dimension_id is None):
            raise ValidationError({"criterion": ["Critère ou dimension de rattachement inconnu."]})
        for field in ("text", "type"):
            if field not in data:
                raise ValidationError({field: ["Champ obligatoire."]})
        siblings = Question.objects.filter(framework_version=version).order_by("-order").first()
        question.order = (siblings.order + 1) if siblings else 0
    before = {} if creating else _snapshot(question, QUESTION_FIELDS)
    if (text := _text(data, "text", "Question", max_length=500)) is not None:
        question.text = text
    for field, label in (("help_text", "Aide"), ("why_text", "Pourquoi")):
        if (value := _text(data, field, label, required=False)) is not None:
            setattr(question, field, value)
    if (hint := _text(data, "evidence_hint", "Preuve", required=False, max_length=300)) is not None:
        question.evidence_hint = hint
    if "type" in data:
        if data["type"] not in Question.Type.values:
            raise ValidationError({"type": ["Type inconnu."]})
        if not creating and data["type"] != question.type and question.feeds:
            raise ValidationError({"type": ["Cette question alimente le moteur : son type ne change pas."]})
        question.type = data["type"]
    if "options" in data or "type" in data:
        question.options = _options(data.get("options", question.options), question.type)
    if "visibility" in data:
        question.visibility = _logic("visibility", data["visibility"])
    if "target_audience" in data:
        if data["target_audience"] not in Question.Audience.values:
            raise ValidationError({"target_audience": ["Public inconnu."]})
        question.target_audience = data["target_audience"]
    if "is_required" in data:
        question.is_required = bool(data["is_required"])
    if "order" in data:
        question.order = int(data["order"])
    question.save()
    _record(
        "question_created" if creating else "question_updated",
        version,
        question,
        before,
        _snapshot(question, QUESTION_FIELDS),
    )
    return question


def delete_question(access, version: FrameworkVersion, question: Question) -> None:
    _require(access, version)
    if question.feeds:
        raise BusinessError(
            f"Cette question alimente le moteur ({question.feeds}) : elle ne peut pas être supprimée.",
            code="question_feeds_engine",
        )
    _record("question_deleted", version, question, _snapshot(question, QUESTION_FIELDS), {"code": question.code})
    question.delete()


# --- Version -------------------------------------------------------------------------------------------------


def update_notes(access, version: FrameworkVersion, notes: str) -> FrameworkVersion:
    _require(access, version)
    before = {"notes": version.notes}
    version.notes = (notes or "").strip()
    version.save(update_fields=["notes", "updated_at"])
    _record("version_updated", version, version, before, {"notes": version.notes})
    return version


def delete_draft(access, version: FrameworkVersion) -> None:
    _require(access, version)
    with transaction.atomic():
        audit.record("framework.draft_deleted", instance=version, before={"version": version.version})
        for model in (MetricDefinition, Question, Criterion, Dimension, Pillar):
            model.objects.filter(framework_version=version).delete()
        version.delete()


def issues(version: FrameworkVersion) -> dict:
    """État de publication : anomalies bloquantes, avertissements et équilibre des poids."""
    errors: list[str] = []
    try:
        referential.validate_version(version)
    except ValidationError as exc:
        errors = [str(e) for e in exc.detail.get("framework_version", [])]
    warnings: list[str] = []
    codes = set(Criterion.objects.filter(framework_version=version).values_list("code", flat=True))
    published = FrameworkVersion.objects.filter(
        framework=version.framework, status=FrameworkVersion.Status.PUBLISHED
    ).first()
    if published and published.pk != version.pk:
        removed = set(Criterion.objects.filter(framework_version=published).values_list("code", flat=True)) - codes
        if removed:
            from pme360.plans.models import RecommendationRule, SupportOffer

            used = defaultdict(list)
            for offer in SupportOffer.objects.filter(is_active=True):
                for code in removed & set(offer.target_criteria):
                    used[code].append(f"offre {offer.code}")
            for rule in RecommendationRule.objects.filter(status=RecommendationRule.Status.ACTIVE):
                text = json.dumps(rule.condition)
                for code in removed:
                    if re.search(rf"(?<![A-Z0-9-]){re.escape(code)}(?![A-Z0-9-])", text):
                        used[code].append(f"règle {rule.code}")
            for code in sorted(used):
                warnings.append(
                    f"{code} n'existe plus dans ce brouillon mais reste utilisé ({', '.join(used[code])}) : "
                    "mettez à jour l'accompagnement."
                )
    for criterion in Criterion.objects.filter(framework_version=version):
        if not Question.objects.filter(criterion=criterion).exists() and not criterion.metrics.exists():
            warnings.append(f"{criterion.code} : aucune question ni indicateur ; il ne pourra pas être évalué.")
    return {"errors": errors, "warnings": warnings, "balance": balance(version)}


def balance(version: FrameworkVersion) -> dict:
    """Sommes de poids attendues et constatées, pour l'affichage en direct dans l'éditeur."""
    pillars = list(Pillar.objects.filter(framework_version=version).order_by("order"))
    dimensions = list(Dimension.objects.filter(framework_version=version).select_related("pillar").order_by("order"))
    criteria = list(Criterion.objects.filter(framework_version=version).select_related("dimension"))
    common = defaultdict(Decimal)
    modules: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for criterion in criteria:
        if criterion.sector_module:
            modules[criterion.dimension.code][criterion.sector_module] += criterion.weight
        else:
            common[criterion.dimension.code] += criterion.weight
    by_pillar = defaultdict(Decimal)
    for dimension in dimensions:
        by_pillar[dimension.pillar.code] += dimension.weight
    return {
        "pillars_total": str(sum((p.weight for p in pillars), Decimal(0))),
        "pillars": [{"code": p.code, "expected": str(p.weight), "actual": str(by_pillar[p.code])} for p in pillars],
        "dimensions": [
            {
                "code": d.code,
                "expected": str(100 - d.sector_module_share),
                "actual": str(common[d.code]),
                "modules": [
                    {"sector": sector, "expected": str(d.sector_module_share), "actual": str(total)}
                    for sector, total in sorted(modules[d.code].items())
                ],
            }
            for d in dimensions
        ],
    }
