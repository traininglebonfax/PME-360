"""Présentation métier des règles de recommandation (Document 7, § 3.3).

Une règle est stockée en JSON Logic ; l'utilisateur la lit et la construit en français : « SI Portefeuille clients
(COM-01) au plus niveau 2 OU … ». Les libellés viennent du référentiel publié de l'organisation.
"""

from __future__ import annotations

import re

from .rules import TEMPLATE_VAR

OPERATORS = {
    "<=": "au plus",
    "<": "inférieur à",
    ">=": "au moins",
    ">": "supérieur à",
    "==": "égal à",
    "!=": "différent de",
}

GENERAL_VARIABLES = [
    ("global_score", "Score global (0 à 100)", "score"),
    ("risk_index", "Exposition au risque (0 à 100)", "score"),
    ("imo", "Indice de maturité organisationnelle (IMO)", "score"),
    ("ipe", "Indice de performance économique (IPE)", "score"),
    ("maturity_level", "Niveau de maturité (N1 à N5)", "maturity"),
    ("compliance_rate", "Taux de conformité documentaire (0 à 1)", "rate"),
    ("deadlines.overdue.count", "Nombre d'obligations en retard", "count"),
]


def variables_catalog() -> list[dict]:
    """Variables utilisables dans une condition, avec libellé et type de valeur attendu."""
    from pme360.diagnostic.models import Criterion, Dimension, FrameworkVersion

    version = FrameworkVersion.objects.filter(status=FrameworkVersion.Status.PUBLISHED).first()
    catalog = [
        {"key": key, "label": label, "type": kind, "group": "Indicateurs généraux"}
        for key, label, kind in GENERAL_VARIABLES
    ]
    if version is None:
        return catalog
    dimensions = Dimension.objects.filter(framework_version=version).order_by("code")
    for dimension in dimensions:
        catalog.append(
            {
                "key": f"dimension.{dimension.code}.score",
                "label": f"Score {dimension.short_name} ({dimension.code})",
                "type": "score",
                "group": "Dimensions",
            }
        )
    for criterion in Criterion.objects.filter(framework_version=version).select_related("dimension").order_by("code"):
        group = f"Critères · {criterion.dimension.short_name}"
        catalog.append(
            {
                "key": f"criterion.{criterion.code}.level",
                "label": f"{criterion.name} ({criterion.code}) — niveau",
                "type": "level",
                "group": group,
            }
        )
        catalog.append(
            {
                "key": f"criterion.{criterion.code}.capped",
                "label": f"{criterion.name} ({criterion.code}) plafonné faute de preuve",
                "type": "boolean",
                "group": group,
            }
        )
    return catalog


def labels() -> dict[str, str]:
    return {item["key"]: item["label"] for item in variables_catalog()}


def _value(value) -> str:
    if value is True:
        return "oui"
    if value is False:
        return "non"
    return str(value).replace(".", ",") if isinstance(value, float) else str(value)


def describe(condition, names: dict[str, str]) -> str:
    """Condition JSON Logic → phrase française (sans le « SI » initial)."""
    if not isinstance(condition, dict) or len(condition) != 1:
        return _value(condition)
    op, args = next(iter(condition.items()))
    args = args if isinstance(args, list) else [args]
    if op in ("and", "or"):
        joiner = " ET " if op == "and" else " OU "
        parts = [describe(arg, names) for arg in args]
        nested = [
            f"({p})" if isinstance(a, dict) and next(iter(a)) in ("and", "or") else p
            for a, p in zip(args, parts, strict=True)
        ]
        return joiner.join(nested)
    if op == "!":
        return f"NON ({describe(args[0], names)})"
    if op == "var":
        return names.get(args[0], args[0])
    if op in OPERATORS and len(args) == 2:
        left, right = args
        if isinstance(left, dict) and "var" in left:
            key = left["var"]
            label = names.get(key, key)
            if right is True and op == "==":
                return label
            return f"{label} {OPERATORS[op]} {_value(right)}"
        return f"{describe(left, names)} {OPERATORS[op]} {describe(right, names)}"
    return str(condition)


SHORT_GENERAL = {
    "global_score": "score global",
    "risk_index": "exposition au risque",
    "imo": "IMO",
    "ipe": "IPE",
    "maturity_level": "niveau de maturité",
    "compliance_rate": "taux de conformité",
    "deadlines.overdue.count": "obligations en retard",
}


def short_label(key: str, names: dict[str, str]) -> str:
    """Libellé court d'une variable dans une justification : « niveau COM-01 », « score Finance »…"""
    if key in SHORT_GENERAL:
        return SHORT_GENERAL[key]
    parts = key.split(".")
    if len(parts) == 3 and parts[0] == "criterion":
        return f"niveau {parts[1]}" if parts[2] == "level" else f"{parts[1]} plafonné"
    if len(parts) == 3 and parts[0] == "dimension":
        label = names.get(key, "")
        match = re.match(r"Score (.+) \(D\d{2}\)", label)
        return f"score {match.group(1)}" if match else f"score {parts[1]}"
    return names.get(key, key)


def readable_template(template: str, names: dict[str, str]) -> str:
    """Remplace les ``{{variable}}`` d'un gabarit par « [libellé court] » pour la lecture."""
    return TEMPLATE_VAR.sub(lambda m: f"[{short_label(m.group(1), names)}]", template)


def is_simple(condition) -> bool:
    """Condition éditable par le constructeur visuel : comparaisons simples, reliées par un seul ET ou OU."""

    def comparison(node) -> bool:
        return (
            isinstance(node, dict)
            and len(node) == 1
            and next(iter(node)) in OPERATORS
            and isinstance(next(iter(node.values())), list)
            and len(next(iter(node.values()))) == 2
            and isinstance(next(iter(node.values()))[0], dict)
            and "var" in next(iter(node.values()))[0]
            and not isinstance(next(iter(node.values()))[1], dict | list)
        )

    if comparison(condition):
        return True
    if isinstance(condition, dict) and len(condition) == 1 and next(iter(condition)) in ("and", "or"):
        return all(comparison(item) for item in next(iter(condition.values())))
    return False
