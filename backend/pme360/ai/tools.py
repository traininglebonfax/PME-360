"""Outils du Copilot (Document 4, § 8.3) : lecture seule, avec les droits et le périmètre de l'utilisateur.

Les chiffres, scores, échéances et alertes viennent de ces outils (données de la plateforme), jamais de la
recherche vectorielle ni du modèle. Chaque résultat porte ses sources (donnée + date).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from pme360.pmes.models import Pme


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    access: object
    pme: Pme | None = None


def _pme(ctx: ToolContext, pme_id: str | None) -> Pme:
    pme_id = pme_id or (str(ctx.pme.pk) if ctx.pme else None)
    if not pme_id:
        raise ToolError("Précisez la PME concernée.")
    pme = ctx.access.pme_queryset(Pme.objects.all()).filter(pk=pme_id).first()
    if pme is None:
        raise ToolError("PME introuvable dans votre périmètre.")
    return pme


def _src(label: str, detail: str = "") -> dict:
    return {"label": label, "detail": detail}


def _current_snapshot(pme):
    from pme360.scoring.models import ScoreSnapshot

    frozen = ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("-reference_date").first()
    live = ScoreSnapshot.objects.filter(pme=pme, kind=ScoreSnapshot.Kind.LIVE).first()
    if live and frozen and live.result.get("source_diagnostic") == str(frozen.diagnostic_id):
        return live, frozen
    return frozen, frozen


def get_pme_profile(ctx: ToolContext, pme_id: str | None = None) -> dict:
    pme = _pme(ctx, pme_id)
    advisor = (
        pme.assignments.filter(end_date__isnull=True, role_in_pme="CONSEILLER_PRINCIPAL").select_related("user").first()
    )
    return {
        "data": {
            "pme_id": str(pme.pk),
            "raison_sociale": pme.legal_name,
            "secteur": pme.sector.name if pme.sector_id else None,
            "region": pme.region.name if pme.region_id else None,
            "effectif": pme.headcount,
            "taille": pme.get_size_category_display() if pme.size_category else None,
            "cycle_de_vie": pme.get_lifecycle_status_display(),
            "date_creation": pme.creation_date.isoformat() if pme.creation_date else None,
            "conseiller_principal": advisor.user.full_name if advisor else None,
        },
        "sources": [
            _src(f"Fiche PME — {pme.legal_name}", f"mise à jour le {timezone.localtime(pme.updated_at):%d/%m/%Y}")
        ],
    }


def get_scores(ctx: ToolContext, pme_id: str | None = None) -> dict:
    pme = _pme(ctx, pme_id)
    current, frozen = _current_snapshot(pme)
    if current is None:
        return {"data": None, "sources": [], "limits": ["Aucun diagnostic validé pour cette PME."]}
    result = current.result
    dimensions = sorted(
        (
            {"dimension": d["short_name"], "score": round(d["score"], 1), "statut": d["status"]}
            for d in result["dimensions"]
            if d.get("score") is not None
        ),
        key=lambda d: d["score"],
    )
    names = {d["code"]: d["short_name"] for d in result["dimensions"]}
    gaps = [
        {
            "critere": g["name"],
            "dimension": names.get(g["dimension"], g["dimension"]),
            "score": g["score"],
            "gain_potentiel": round(g["potential_gain"], 2),
            "critique": g["is_critical"],
            "plafonne_faute_de_preuve": g["capped"],
        }
        for g in result.get("gaps", [])[:6]
    ]
    kind = "score courant (preuves vérifiées à ce jour)" if current.kind == "LIVE" else "snapshot figé"
    return {
        "data": {
            "date": current.reference_date.isoformat(),
            "nature": kind,
            "score_global": result["global_score"],
            "imo": result["imo"],
            "ipe": result["ipe"],
            "niveau": result["maturity"]["label"],
            "portes_non_franchies": [
                f.get("label") or f.get("message") for f in result["maturity"].get("gates_failed", [])
            ],
            "confiance": result["confidence"],
            "priorite": result["priority"]["priority"],
            "quadrant": result.get("quadrant"),
            "dimensions_du_plus_faible_au_plus_fort": dimensions,
            "ecarts_a_plus_fort_impact": gaps,
        },
        "sources": [
            _src(
                f"Diagnostic validé du {frozen.reference_date:%d/%m/%Y}" if frozen else "Diagnostic",
                f"{kind}, calculé le {timezone.localtime(current.computed_at):%d/%m/%Y}",
            )
        ],
    }


def compare_snapshots(ctx: ToolContext, pme_id: str | None = None, reference: str = "precedent") -> dict:
    from pme360.scoring import services as scoring
    from pme360.scoring.models import ScoreSnapshot

    pme = _pme(ctx, pme_id)
    frozen = list(ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("reference_date"))
    if len(frozen) < 2:
        return {
            "data": None,
            "sources": [],
            "limits": ["Un seul diagnostic validé : pas encore d'évolution mesurable."],
        }
    after = frozen[-1]
    before = frozen[0] if reference == "initial" else frozen[-2]
    explanation = scoring.compare(before, after)
    contributions = [
        {
            "dimension": c["name"],
            "avant": c["before"],
            "apres": c["after"],
            "contribution_points": c["contribution"],
            "criteres": [
                {"critere": d["name"], "nature": d["nature"], "contribution": d["contribution"]}
                for d in c["criteria"][:3]
            ],
        }
        for c in explanation["contributions"][:6]
    ]
    return {
        "data": {
            "de": before.reference_date.isoformat(),
            "a": after.reference_date.isoformat(),
            "score_avant": explanation["before"]["global_score"],
            "score_apres": explanation["after"]["global_score"],
            "ecart": explanation["delta_global"],
            "dont_gain_de_preuve": explanation["proof_gain"],
            "contributions": contributions,
            "referentiel_reprojete": explanation["reprojected_baseline"],
        },
        "sources": [
            _src(f"Snapshot du {before.reference_date:%d/%m/%Y}", before.get_kind_display()),
            _src(f"Snapshot du {after.reference_date:%d/%m/%Y}", after.get_kind_display()),
        ],
    }


def get_financial_metrics(ctx: ToolContext, pme_id: str | None = None) -> dict:
    from .financials import metrics_for

    pme = _pme(ctx, pme_id)
    analysis = metrics_for(pme)
    metrics = [
        {
            "indicateur": m["name"],
            "valeur": m["display"],
            "appreciation": m["band"],
            "formule": m["formula"],
            "sources": m["sources"],
        }
        for m in analysis["metrics"]
        if m["value"] is not None
    ]
    missing = [m["name"] for m in analysis["metrics"] if m["value"] is None]
    sources = [
        _src(f"États financiers — exercice clos le {s.fiscal_year_end:%d/%m/%Y}", s.get_status_display())
        for s in analysis["statements"][:2]
    ]
    if analysis["diagnostic"]:
        sources.append(
            _src(
                f"Questionnaire du diagnostic du {analysis['diagnostic'].reference_date:%d/%m/%Y}", "données déclarées"
            )
        )
    return {
        "data": {"indicateurs": metrics, "non_calculables": missing},
        "sources": sources,
        "limits": ["Indicateurs non calculables : " + ", ".join(missing)] if missing else [],
    }


def list_documents(ctx: ToolContext, pme_id: str | None = None) -> dict:
    from pme360.compliance import services as compliance

    pme = _pme(ctx, pme_id)
    folder = compliance.compliance_folder(pme)
    rate = compliance.compliance_rate(pme)
    by_state: dict[str, list[str]] = {}
    for category in folder:
        for item in category["items"]:
            by_state.setdefault(item["state"], []).append(item["document_type"]["name"])
    return {
        "data": {
            "taux_de_conformite": rate.get("rate"),
            "manquants": by_state.get("MANQUANT", []),
            "expires": by_state.get("EXPIRE", []),
            "non_conformes": by_state.get("NON_CONFORME", []),
            "en_verification": by_state.get("EN_VERIFICATION", []),
            "conformes": by_state.get("CONFORME", []) + by_state.get("CONFORME_SOUS_RESERVE", []),
        },
        "sources": [_src(f"Dossier de conformité — {pme.legal_name}", f"état au {timezone.localdate():%d/%m/%Y}")],
    }


def list_deadlines(ctx: ToolContext, pme_id: str | None = None, days: int = 60) -> dict:
    from pme360.compliance.models import Deadline

    pme = _pme(ctx, pme_id)
    today = timezone.localdate()
    deadlines = (
        Deadline.objects.filter(pme=pme, status__in=Deadline.OPEN, due_date__lte=today + timedelta(days=days))
        .select_related("pme_obligation__template")
        .order_by("due_date")
    )
    items = [
        {
            "obligation": d.pme_obligation.template.name,
            "periode": d.period_label,
            "echeance": d.due_date.isoformat(),
            "statut": d.get_status_display(),
            "en_retard_de_jours": (today - d.due_date).days if d.due_date < today else 0,
        }
        for d in deadlines[:20]
    ]
    return {
        "data": {"echeances": items},
        "sources": [_src("Échéancier de conformité", f"au {today:%d/%m/%Y}, horizon {days} jours")],
    }


def list_alerts(ctx: ToolContext, pme_id: str | None = None, severity: str | None = None) -> dict:
    from pme360.alerts.models import Alert

    alerts = Alert.objects.filter(status__in=Alert.OPEN).select_related("pme")
    if pme_id or ctx.pme:
        alerts = alerts.filter(pme=_pme(ctx, pme_id))
    else:
        alerts = alerts.filter(pme__in=ctx.access.pme_queryset(Pme.objects.all()).values("pk"))
    if severity:
        alerts = alerts.filter(severity=severity)
    items = [
        {
            "pme": a.pme.legal_name,
            "gravite": a.get_severity_display(),
            "titre": a.title,
            "depuis": timezone.localtime(a.created_at).date().isoformat(),
        }
        for a in alerts.order_by("-created_at")[:20]
    ]
    return {
        "data": {"alertes_ouvertes": items, "total": alerts.count()},
        "sources": [_src("Alertes ouvertes", f"au {timezone.localdate():%d/%m/%Y}")],
    }


PORTFOLIO_QUERIES = (
    "pme_urgentes",
    "problemes_frequents",
    "progression",
    "stagnation",
    "indicateurs_cles",
    "repartition_niveaux",
)


def portfolio_query(ctx: ToolContext, query: str) -> dict:
    from pme360.dashboards.views import portfolio_overview

    if not ctx.access.has("dashboard.portfolio"):
        raise ToolError("Vous n'avez pas accès aux analyses de portefeuille.")
    if query not in PORTFOLIO_QUERIES:
        raise ToolError(f"Requête inconnue. Requêtes possibles : {', '.join(PORTFOLIO_QUERIES)}.")
    overview = portfolio_overview(ctx.access)
    data = {
        "pme_urgentes": overview["urgent"],
        "problemes_frequents": [
            {"dimension": w["name"], "part_des_pme_sous_le_seuil": w["share"], "pme_evaluees": w["evaluated"]}
            for w in overview["weaknesses"][:6]
        ],
        "progression": overview["progress"]["top"],
        "stagnation": overview["progress"]["stagnating"],
        "indicateurs_cles": overview["kpis"],
        "repartition_niveaux": overview["by_maturity"],
    }[query]
    return {
        "data": data,
        "sources": [
            _src("Tableau de bord de portefeuille", f"périmètre de l'utilisateur, au {timezone.localdate():%d/%m/%Y}")
        ],
        "limits": [f"Seuil de faiblesse : {overview['weakness_threshold']}/100."]
        if query == "problemes_frequents"
        else [],
    }


def search_knowledge(ctx: ToolContext, query: str, pme_id: str | None = None) -> dict:
    from .knowledge import search

    pme = _pme(ctx, pme_id) if (pme_id or ctx.pme) else None
    results = search(ctx.access, query, pme=pme, limit=6)
    return {
        "data": {"fragments": [{"source": r["source_label"], "page": r["page"], "texte": r["text"]} for r in results]},
        "sources": [_src(r["source_label"], f"page {r['page']}" if r["page"] else (r["date"] or "")) for r in results],
    }


def list_actions(ctx: ToolContext, pme_id: str | None = None) -> dict:
    return {"data": None, "sources": [], "limits": ["Les plans et actions d'accompagnement arrivent en phase 5."]}


def draft_report(ctx: ToolContext, report_type: str = "diagnostic") -> dict:
    return {"data": None, "sources": [], "limits": ["La génération de rapports arrive en phase 6."]}


_PME = {
    "pme_id": {
        "type": "string",
        "description": "Identifiant de la PME (facultatif si la conversation porte sur une PME).",
    }
}

TOOLS = {
    "get_pme_profile": (get_pme_profile, "Fiche synthétique de la PME.", _PME),
    "get_scores": (get_scores, "Scores, niveau de maturité, confiance, dimensions et écarts à plus fort impact.", _PME),
    "compare_snapshots": (
        compare_snapshots,
        "Évolution entre deux diagnostics validés et contributions par dimension et critère.",
        {**_PME, "reference": {"type": "string", "enum": ["precedent", "initial"]}},
    ),
    "get_financial_metrics": (get_financial_metrics, "Ratios financiers calculés (formule, valeur, source).", _PME),
    "list_documents": (list_documents, "Dossier de conformité : documents manquants, expirés, refusés.", _PME),
    "list_deadlines": (
        list_deadlines,
        "Échéances ouvertes de la PME.",
        {**_PME, "days": {"type": "integer", "minimum": 1, "maximum": 365}},
    ),
    "list_actions": (list_actions, "Actions du plan d'accompagnement (phase 5).", _PME),
    "list_alerts": (
        list_alerts,
        "Alertes ouvertes d'une PME ou du portefeuille.",
        {**_PME, "severity": {"type": "string", "enum": ["INFO", "MOYENNE", "ELEVEE", "CRITIQUE"]}},
    ),
    "portfolio_query": (
        portfolio_query,
        "Analyses prédéfinies du portefeuille de l'utilisateur (pas de requête libre).",
        {"query": {"type": "string", "enum": list(PORTFOLIO_QUERIES)}},
    ),
    "search_knowledge": (
        search_knowledge,
        "Recherche dans le référentiel, les règles vérifiées, les documents vérifiés et l'historique.",
        {"query": {"type": "string"}, **_PME},
    ),
    "draft_report": (draft_report, "Brouillon de rapport (phase 6).", {"report_type": {"type": "string"}}),
}


def definitions() -> list[dict]:
    required = {"portfolio_query": ["query"], "search_knowledge": ["query"]}
    return [
        {
            "name": name,
            "description": description,
            "input_schema": {"type": "object", "properties": props, "required": required.get(name, [])},
        }
        for name, (_, description, props) in TOOLS.items()
    ]


def call(ctx: ToolContext, name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        raise ToolError(f"Outil inconnu : {name}.")
    handler, _, props = TOOLS[name]
    kwargs = {key: value for key, value in (arguments or {}).items() if key in props}
    return handler(ctx, **kwargs)
