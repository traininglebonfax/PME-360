"""Évaluateur JSON Logic (sous-ensemble) pour les règles métier stockées en base (ADR-005).

Opérateurs pris en charge : ``var``, ``missing``, ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=`` (y compris la forme
« entre » à trois arguments), ``and``, ``or``, ``!``, ``!!``, ``if``, ``in``,
``+``, ``-``, ``*``, ``/``, ``min``, ``max``.
Aucune exécution de code arbitraire : une règle est une donnée.
"""

from __future__ import annotations

from typing import Any


class JsonLogicError(ValueError):
    pass


def _var(data: Any, path: Any, default: Any = None) -> Any:
    if path in (None, ""):
        return data
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    return current


def _truthy(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _compare(op: str, a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False  # une donnée absente ne satisfait jamais une comparaison numérique
    try:
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a >= b
    except TypeError:
        return False


def evaluate(rule: Any, data: dict | None = None) -> Any:
    data = data or {}
    if isinstance(rule, list):
        return [evaluate(item, data) for item in rule]
    if not isinstance(rule, dict) or len(rule) != 1:
        return rule
    op, raw_args = next(iter(rule.items()))
    args = raw_args if isinstance(raw_args, list) else [raw_args]

    # Opérateurs paresseux
    if op == "and":
        result: Any = True
        for arg in args:
            result = evaluate(arg, data)
            if not _truthy(result):
                return result
        return result
    if op == "or":
        result = False
        for arg in args:
            result = evaluate(arg, data)
            if _truthy(result):
                return result
        return result
    if op == "if":
        for index in range(0, len(args) - 1, 2):
            if _truthy(evaluate(args[index], data)):
                return evaluate(args[index + 1], data)
        return evaluate(args[-1], data) if len(args) % 2 == 1 else None

    values = [evaluate(arg, data) for arg in args]
    if op == "var":
        return _var(data, values[0] if values else None, values[1] if len(values) > 1 else None)
    if op == "missing":
        return [key for key in values if _var(data, key) in (None, "")]
    if op == "==":
        return values[0] == values[1]
    if op == "!=":
        return values[0] != values[1]
    if op in ("<", "<=", ">", ">="):
        if len(values) == 3:  # forme « entre » : a < b < c
            return _compare(op, values[0], values[1]) and _compare(op, values[1], values[2])
        return _compare(op, values[0], values[1])
    if op == "!":
        return not _truthy(values[0])
    if op == "!!":
        return _truthy(values[0])
    if op == "in":
        container = values[1]
        return container is not None and values[0] in container
    if op in ("+", "*", "min", "max"):
        numbers = [v for v in values if v is not None]
        if len(numbers) != len(values):
            return None
        if op == "+":
            return sum(numbers)
        if op == "*":
            product = 1
            for number in numbers:
                product *= number
            return product
        return min(numbers) if op == "min" else max(numbers)
    if op == "-":
        if any(v is None for v in values):
            return None
        return -values[0] if len(values) == 1 else values[0] - values[1]
    if op == "/":
        if values[0] is None or not values[1]:
            return None
        return values[0] / values[1]
    raise JsonLogicError(f"Opérateur JSON Logic non pris en charge : {op}")


def validate(rule: Any) -> None:
    """Vérifie qu'une règle n'utilise que des opérateurs connus (appelé avant enregistrement)."""
    known = {
        "var",
        "missing",
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "and",
        "or",
        "!",
        "!!",
        "if",
        "in",
        "+",
        "-",
        "*",
        "/",
        "min",
        "max",
    }
    if isinstance(rule, list):
        for item in rule:
            validate(item)
    elif isinstance(rule, dict):
        if len(rule) != 1:
            raise JsonLogicError("Chaque nœud de règle doit avoir exactement un opérateur.")
        op, args = next(iter(rule.items()))
        if op not in known:
            raise JsonLogicError(f"Opérateur JSON Logic non pris en charge : {op}")
        validate(args)
