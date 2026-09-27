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


@register.filter
def pct_width(value) -> int:
    """Proportion (0 à 1) → largeur de barre en %, jamais nulle pour rester visible."""
    return bar(None if value is None else float(value) * 100)


@register.filter
def pct_rest(value) -> int:
    return 100 - pct_width(value)


KPI_LABELS = {
    "pmes_total": "PME au total",
    "pmes_new_this_month": "Nouvelles PME",
    "pmes_accompanied": "PME accompagnées",
    "pmes_active": "PME actives",
    "average_score": "Score moyen",
    "average_progress": "Progression moyenne",
    "average_compliance": "Conformité moyenne",
    "pmes_at_risk": "PME à risque",
    "pmes_urgent": "Intervention urgente",
    "pmes_without_advisor": "PME sans conseiller",
    "pmes_late": "PME en retard",
    "actions_done": "Actions réalisées",
    "actions_overdue": "Actions en retard",
    "average_confidence": "Confiance moyenne",
}


@register.filter
def kpi_label(key: str) -> str:
    return KPI_LABELS.get(key, key)


@register.filter
def signed(value) -> str:
    """Écart signé à une décimale (« +3,5 », « −2,0 », « 0,0 »)."""
    if value is None:
        return "—"
    value = float(value)
    return f"{'+' if value > 0 else ''}{value:.1f}".replace(".", ",")


@register.filter
def period_fr(value) -> str:
    """Période « AAAA-MM-JJ_AAAA-MM-JJ » → « du JJ/MM/AAAA au JJ/MM/AAAA »."""
    if not value or "_" not in str(value):
        return frdate(value)
    start, end = str(value).split("_", 1)
    return f"du {frdate(start)} au {frdate(end)}"
