"""Évaluation sûre des formules d'indicateurs (``metric_definition.formula``), par analyse de l'AST Python.

Seuls les nombres, les variables fournies, les opérateurs + - * / ** et les fonctions ``abs``, ``min``, ``max`` sont
admis. Toute autre construction est refusée : une formule configurée en base ne peut pas exécuter de code.
"""

from __future__ import annotations

import ast
import operator
from decimal import Decimal, DivisionByZero, InvalidOperation

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCTIONS = {"abs": abs, "min": min, "max": max}


class ExpressionError(ValueError):
    pass


class MissingInput(ExpressionError):
    """Une donnée nécessaire au calcul est absente : l'indicateur est « non évaluable »."""


def parse(formula: str) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Formule invalide : {formula}") from exc
    for node in ast.walk(tree):
        allowed = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Constant,
            ast.Name,
            ast.Load,
            ast.Call,
            *tuple(_BINARY),
            *tuple(_UNARY),
        )
        if not isinstance(node, allowed):
            raise ExpressionError(f"Construction interdite dans la formule : {type(node).__name__}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS):
            raise ExpressionError("Seules les fonctions abs, min et max sont autorisées.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            raise ExpressionError("Seules les constantes numériques sont autorisées.")
    return tree


def variables(formula: str) -> set[str]:
    return {node.id for node in ast.walk(parse(formula)) if isinstance(node, ast.Name) and node.id not in _FUNCTIONS}


def evaluate(formula: str, values: dict[str, float | Decimal | None]) -> float:
    tree = parse(formula)

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            value = values.get(node.id)
            if value is None:
                raise MissingInput(node.id)
            return float(value)
        if isinstance(node, ast.UnaryOp):
            return _UNARY[type(node.op)](visit(node.operand))
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            try:
                return _BINARY[type(node.op)](left, right)
            except (ZeroDivisionError, DivisionByZero, InvalidOperation, OverflowError) as exc:
                raise MissingInput("division par zéro") from exc
        if isinstance(node, ast.Call):
            return _FUNCTIONS[node.func.id](*[visit(arg) for arg in node.args])
        raise ExpressionError(type(node).__name__)

    result = visit(tree)
    if isinstance(result, complex):
        raise MissingInput("résultat non réel")
    return float(result)
