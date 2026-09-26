"""Analyse financière (Document 4, fonction D) : ratios DÉTERMINISTES + commentaire rédigé, relu avant publication.

Les états financiers extraits alimentent les données d'indicateurs du moteur de scoring (``ca_n``,
``resultat_net``…) avec la source DOCUMENT_VERIFIE (après revue humaine) ou DOCUMENT_IA (extraction provisoire),
à la place des montants déclarés au questionnaire. Les ratios restent calculés par le moteur.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from pme360.scoring import engine

from .models import FinancialStatement

MAX_AGE_DAYS = 548  # exercice clos depuis moins de 18 mois à la date de référence


def _as_of_status(statement: FinancialStatement, as_of: date) -> str | None:
    if statement.status == FinancialStatement.Status.VERIFIE and statement.verified_at:
        if timezone.localtime(statement.verified_at).date() <= as_of:
            return "DOCUMENT_VERIFIE"
    if timezone.localtime(statement.created_at).date() <= as_of:
        return "DOCUMENT_IA"
    return None


def statement_inputs(pme, reference_date: date, as_of: date | None = None) -> tuple[dict, FinancialStatement | None]:
    """Données d'indicateurs issues des derniers états financiers connus à ``as_of`` (reproductible)."""
    as_of = as_of or timezone.localdate()
    candidates = (
        FinancialStatement.objects.filter(
            pme=pme,
            fiscal_year_end__lte=reference_date,
            fiscal_year_end__gte=reference_date - timedelta(days=MAX_AGE_DAYS),
        )
        .exclude(status=FinancialStatement.Status.ECARTE)
        .order_by("-fiscal_year_end")
    )
    for statement in candidates:
        source = _as_of_status(statement, as_of)
        if source is None:
            continue
        inputs = {
            key: engine.InputValue(value=float(value), source=source, answered_on=statement.fiscal_year_end)
            for key, value in statement.values.items()
            if isinstance(value, int | float)
        }
        if "ca_n1" not in inputs:
            previous = (
                FinancialStatement.objects.filter(pme=pme, fiscal_year_end__lt=statement.fiscal_year_end)
                .exclude(status=FinancialStatement.Status.ECARTE)
                .order_by("-fiscal_year_end")
                .first()
            )
            previous_source = _as_of_status(previous, as_of) if previous else None
            if previous_source and isinstance(previous.values.get("ca_n"), int | float):
                inputs["ca_n1"] = engine.InputValue(
                    value=float(previous.values["ca_n"]), source=previous_source, answered_on=previous.fiscal_year_end
                )
        return inputs, statement
    return {}, None


def display(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "PERCENT":
        return f"{value * 100:.1f} %".replace(".", ",")
    if unit == "DAYS":
        return f"{value:.0f} jours"
    if unit == "YEARS":
        return f"{value:.1f} ans".replace(".", ",")
    if unit == "AMOUNT":
        return f"{value:,.0f} FCFA".replace(",", " ")
    return f"{value:.2f}".replace(".", ",")


def metrics_for(pme) -> dict:
    """Indicateurs financiers de la PME à ce jour : déclaratifs du dernier diagnostic, remplacés par les comptes."""
    from pme360.diagnostic.models import Diagnostic
    from pme360.diagnostic.services import published_version
    from pme360.scoring import services as scoring

    today = timezone.localdate()
    diagnostic = (
        Diagnostic.objects.filter(pme=pme).exclude(status=Diagnostic.Status.ANNULE).order_by("-reference_date").first()
    )
    version = diagnostic.framework_version if diagnostic else published_version()
    spec, _ = scoring.load_framework(version)
    if diagnostic:
        _, data = scoring.build_input(diagnostic, context={}, evidence_as_of=today)
        data.reference_date = today
    else:
        data = engine.DiagnosticInput(reference_date=today, profile={})
        data.inputs, _ = statement_inputs(pme, today, today)
    settings = spec.settings
    metrics = []
    for metric in spec.metrics:
        result = engine.evaluate_metric(
            metric, data, settings["confidence"]["sources"], settings["engine"]["declarative_validity_days"]
        )
        result["display"] = display(result["value"], metric.unit)
        metrics.append(result)
    statements = list(
        FinancialStatement.objects.filter(pme=pme)
        .exclude(status=FinancialStatement.Status.ECARTE)
        .select_related("source_version__document")
        .order_by("-fiscal_year_end")
    )
    return {"metrics": metrics, "statements": statements, "diagnostic": diagnostic, "as_of": today}
