"""Administration sans code des types de documents et des obligations (Document 10, V1 ; Document 8).

Garde-fous : un code ne change jamais après création (il sert de référence aux critères, obligations, livrables) ;
un type de document utilisé par une obligation active ne peut pas être désactivé ; une obligation réglementaire est
adossée à une règle du registre et n'est active que si cette règle est VÉRIFIÉE (RM-08). Les modifications valent
pour les prochaines échéances générées ; les échéances existantes ne changent pas. Tout est tracé (avant/après).
"""

from __future__ import annotations

import re

from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core import jsonlogic
from pme360.core.exceptions import BusinessError
from pme360.documents.models import DocumentCategory, DocumentType

from .models import ObligationTemplate, RegulatoryRule

CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{2,40}$")

DOCUMENT_TYPE_FIELDS = (
    "name",
    "description",
    "guidance",
    "period_kind",
    "validity_days",
    "freshness_days",
    "evidence_level",
    "sensitive",
    "order",
    "is_active",
)
OBLIGATION_FIELDS = (
    "name",
    "description",
    "nature",
    "frequency",
    "frequency_rule",
    "due_days_after_period_end",
    "applicability",
    "reminder_offsets",
    "is_critical",
)


def _require(access) -> None:
    if not access.has("org.configure") or access.is_pme_user:
        raise PermissionDenied()


def _snapshot(instance, fields) -> dict:
    data = {}
    for name in fields:
        value = getattr(instance, name)
        data[name] = getattr(value, "code", value)
    return data


# --- Types de documents -----------------------------------------------------------------------------------------


def save_document_type(access, data: dict, instance: DocumentType | None = None) -> DocumentType:
    _require(access)
    creating = instance is None
    if creating:
        code = (data.get("code") or "").strip().upper()
        if not CODE_PATTERN.match(code):
            raise ValidationError({"code": ["Code en majuscules, chiffres, - et _ (2 à 40 caractères)."]})
        if DocumentType.objects.filter(code=code).exists():
            raise ValidationError({"code": ["Ce code existe déjà."]})
        instance = DocumentType(code=code)
    elif "code" in data and data["code"] != instance.code:
        raise ValidationError({"code": ["Le code d'un type de document ne peut pas être modifié."]})
    before = {} if creating else _snapshot(instance, (*DOCUMENT_TYPE_FIELDS, "category"))
    if "category" in data:
        category = DocumentCategory.objects.filter(code=data["category"]).first()
        if category is None:
            raise ValidationError({"category": ["Catégorie inconnue."]})
        instance.category = category
    elif creating:
        raise ValidationError({"category": ["Catégorie obligatoire."]})
    for name in DOCUMENT_TYPE_FIELDS:
        if name in data:
            setattr(instance, name, data[name])
    if not (instance.name or "").strip():
        raise ValidationError({"name": ["Libellé obligatoire."]})
    if instance.evidence_level is not None and not 0 <= instance.evidence_level <= 4:
        raise ValidationError({"evidence_level": ["Niveau de preuve entre 0 et 4."]})
    if not creating and not instance.is_active:
        used = list(
            ObligationTemplate.objects.filter(document_type=instance, is_active=True).values_list("name", flat=True)
        )
        if used:
            raise BusinessError(
                "Ce type de document est exigé par des obligations actives : désactivez-les d'abord ("
                + ", ".join(used)
                + ").",
                code="document_type_in_use",
            )
    instance.save()
    audit.record(
        "document_type.created" if creating else "document_type.updated",
        instance=instance,
        before=before,
        after=_snapshot(instance, (*DOCUMENT_TYPE_FIELDS, "category")),
    )
    return instance


def document_type_usage(document_type: DocumentType) -> dict:
    from pme360.diagnostic.models import Criterion, FrameworkVersion

    published = FrameworkVersion.objects.filter(status=FrameworkVersion.Status.PUBLISHED).first()
    criteria = (
        list(
            Criterion.objects.filter(
                framework_version=published, evidence_document_types__contains=[document_type.code]
            ).values_list("code", flat=True)
        )
        if published
        else []
    )
    return {
        "documents": document_type.documents.filter(deleted_at__isnull=True).count(),
        "obligations": list(
            ObligationTemplate.objects.filter(document_type=document_type).values_list("code", flat=True)
        ),
        "criteria": criteria,
    }


# --- Obligations ------------------------------------------------------------------------------------------------


def _validate_logic(field: str, value, expect_frequency: bool = False) -> None:
    if value in (None, {}):
        return
    if not isinstance(value, dict) or len(value) != 1:
        raise ValidationError({field: ["Règle JSON Logic attendue (un objet à un seul opérateur)."]})
    try:
        result = jsonlogic.evaluate(value, {"headcount": 10, "size_category": "PETITE", "sector": "COMMERCE"})
    except jsonlogic.JsonLogicError as exc:
        raise ValidationError({field: [str(exc)]}) from exc
    if expect_frequency and result not in ObligationTemplate.Frequency.values:
        raise ValidationError({field: ["La règle doit renvoyer une périodicité (MENSUELLE, TRIMESTRIELLE…)."]})


def save_obligation(access, data: dict, instance: ObligationTemplate | None = None) -> ObligationTemplate:
    _require(access)
    creating = instance is None
    if creating:
        code = (data.get("code") or "").strip().upper()
        if not CODE_PATTERN.match(code):
            raise ValidationError({"code": ["Code en majuscules, chiffres, - et _ (2 à 40 caractères)."]})
        if ObligationTemplate.objects.filter(code=code).exists():
            raise ValidationError({"code": ["Ce code existe déjà."]})
        instance = ObligationTemplate(code=code, is_active=False, reminder_offsets=[-30, -15, -7, 0, 7, 15, 30])
    elif "code" in data and data["code"] != instance.code:
        raise ValidationError({"code": ["Le code d'une obligation ne peut pas être modifié."]})
    before = (
        {} if creating else _snapshot(instance, (*OBLIGATION_FIELDS, "document_type", "regulatory_rule", "is_active"))
    )
    for name in OBLIGATION_FIELDS:
        if name in data:
            setattr(instance, name, data[name])
    if "document_type" in data:
        document_type = DocumentType.objects.filter(code=data["document_type"], is_active=True).first()
        if document_type is None:
            raise ValidationError({"document_type": ["Type de document inconnu ou inactif."]})
        instance.document_type = document_type
    elif creating:
        raise ValidationError({"document_type": ["Type de document obligatoire."]})
    if "regulatory_rule" in data:
        code = data["regulatory_rule"]
        instance.regulatory_rule = RegulatoryRule.objects.filter(code=code).first() if code else None
        if code and instance.regulatory_rule is None:
            raise ValidationError({"regulatory_rule": ["Règle inconnue dans le registre."]})
    if not (instance.name or "").strip():
        raise ValidationError({"name": ["Libellé obligatoire."]})
    if instance.nature == ObligationTemplate.Nature.REGLEMENTAIRE and instance.regulatory_rule is None:
        raise ValidationError(
            {"regulatory_rule": ["Une obligation réglementaire s'appuie sur une règle sourcée du registre (RM-08)."]}
        )
    if not 0 <= instance.due_days_after_period_end <= 365:
        raise ValidationError({"due_days_after_period_end": ["Entre 0 et 365 jours."]})
    offsets = instance.reminder_offsets or []
    if not all(isinstance(o, int) and -120 <= o <= 120 for o in offsets):
        raise ValidationError({"reminder_offsets": ["Relances en jours, entre -120 et +120."]})
    instance.reminder_offsets = sorted(set(offsets))
    _validate_logic("applicability", instance.applicability)
    _validate_logic("frequency_rule", instance.frequency_rule, expect_frequency=True)
    instance.applicability = instance.applicability or None
    instance.frequency_rule = instance.frequency_rule or None
    rule = instance.regulatory_rule
    if instance.is_active and rule is not None and rule.status != RegulatoryRule.Status.VERIFIE:
        raise BusinessError(
            f"La règle {rule.code} n'est pas vérifiée : une obligation active ne peut pas s'y rattacher (RM-08).",
            code="rule_not_verified",
        )
    instance.save()
    audit.record(
        "obligation.created" if creating else "obligation.updated",
        instance=instance,
        before=before,
        after=_snapshot(instance, (*OBLIGATION_FIELDS, "document_type", "regulatory_rule", "is_active")),
    )
    return instance


# --- Lecture en français ------------------------------------------------------------------------------------------

PROFILE_LABELS = {
    "headcount": "Effectif",
    "size_category": "Taille",
    "sector": "Secteur",
    "is_company": "Société (personne morale)",
    "lifecycle_status": "Statut de la PME",
}
OPERATORS = {
    ">=": "au moins",
    "<=": "au plus",
    ">": "supérieur à",
    "<": "inférieur à",
    "==": "égal à",
    "!=": "différent de",
}


def value_labels() -> dict[str, dict[str, str]]:
    from pme360.pmes.models import Pme, Sector

    return {
        "size_category": dict(Pme.SizeCategory.choices),
        "lifecycle_status": dict(Pme.LifecycleStatus.choices),
        "sector": dict(Sector.objects.values_list("code", "name")),
        "frequency": dict(ObligationTemplate.Frequency.choices),
    }


def describe_logic(condition, labels: dict | None = None) -> str:
    """Règle de profil → phrase française (« Effectif au moins 1 ET Taille parmi Petite, Moyenne »)."""
    labels = labels if labels is not None else value_labels()
    if condition in (None, {}):
        return "Toutes les PME"
    if not isinstance(condition, dict) or len(condition) != 1:
        return str(labels["frequency"].get(condition, condition))
    op, args = next(iter(condition.items()))
    args = args if isinstance(args, list) else [args]
    if op in ("and", "or"):
        return (" ET " if op == "and" else " OU ").join(describe_logic(a, labels) for a in args)
    if op == "!":
        return f"NON ({describe_logic(args[0], labels)})"
    if op == "if" and len(args) == 3:
        return (
            f"{describe_logic(args[1], labels)} si {describe_logic(args[0], labels)}, "
            f"sinon {describe_logic(args[2], labels)}"
        ).capitalize()
    if len(args) == 2 and isinstance(args[0], dict) and "var" in args[0]:
        key = args[0]["var"]
        name = PROFILE_LABELS.get(key, key)
        values = labels.get(key, {})
        if op == "in" and isinstance(args[1], list):
            return f"{name} parmi " + ", ".join(str(values.get(v, v)) for v in args[1])
        if op in OPERATORS:
            right = args[1]
            shown = "oui" if right is True else "non" if right is False else values.get(right, right)
            return f"{name} {OPERATORS[op]} {shown}"
    return str(condition)
