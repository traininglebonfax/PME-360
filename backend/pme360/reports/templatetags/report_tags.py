"""Filtres d'affichage des rapports (formats français)."""

from datetime import date, datetime

from django import template

register = template.Library()


@register.filter
def frdate(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    return str(value)


@register.filter
def score(value) -> str:
    return "—" if value is None else f"{float(value):.0f}"


@register.filter
def decimal1(value) -> str:
    return "—" if value is None else f"{float(value):.1f}".replace(".", ",")


@register.filter
def pct(value) -> str:
    return "—" if value is None else f"{float(value) * 100:.0f} %"


@register.filter
def bar(value) -> int:
    """Largeur (en %) d'une barre de 0 à 100, jamais nulle pour rester visible."""
    return 1 if value is None else max(1, min(100, round(float(value))))


@register.filter
def rest(value) -> int:
    return 100 - bar(value)


@register.filter
def tone(value) -> str:
    """Couleur d'un score : < 50 fragile, 50–69 intermédiaire, ≥ 70 solide."""
    if value is None:
        return "#c9ced6"
    value = float(value)
    return "#c2410c" if value < 50 else "#b7791f" if value < 70 else "#0f7a55"
