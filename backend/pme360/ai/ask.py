"""Ask AI — Copilot du conseiller (Document 4, § 9).

- Contexte : une PME ou le portefeuille de l'utilisateur ; outils en LECTURE SEULE (``ai.tools``).
- Avec un fournisseur externe autorisé : boucle agentique limitée à ``PME360_AI_MAX_TOOL_CALLS`` appels d'outils.
- Sinon : moteur local par intention (les mêmes outils, des réponses rédigées par gabarits).
- Format imposé : réponse, « Sur quoi repose cette réponse » (sources datées), niveau de confiance, limites.
- Réponses diffusées en flux (SSE) ; conversations conservées et auditables.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator

import jsonschema
from django.conf import settings

from pme360.audit import services as audit

from . import gateway, prompts, tools
from .models import AiAnalysis, Conversation, ConversationMessage
from .pseudonymize import Pseudonymizer, for_pme
from .rules import fold
from .schemas import ANSWER_SCHEMA

ANSWER_TOOL = "repondre"
HISTORY = 8


def _event(kind: str, **payload) -> dict:
    return {"type": kind, **payload}


def _chunks(text: str) -> Iterator[str]:
    for match in re.finditer(r"\S+\s*", text):
        yield match.group(0)


def _use_external(organization) -> tuple[object | None, list[str]]:
    provider = gateway.external_provider()
    if provider is None:
        return None, ["IA externe non configurée : réponse par le moteur local"]
    reasons = []
    if not organization.ai_external_allowed:
        reasons.append("IA externe non autorisée par l'organisation : réponse par le moteur local")
    if gateway.breaker_open(provider.name):
        reasons.append("fournisseur indisponible : réponse par le moteur local")
    quota = organization.setting("ai_monthly_token_quota")
    if quota and gateway.month_usage(organization.pk)["tokens"] >= quota:
        reasons.append("budget mensuel de jetons épuisé : réponse par le moteur local")
    if not hasattr(provider, "chat"):
        reasons.append("fournisseur sans mode conversationnel")
    return (None, reasons) if reasons else (provider, [])


def ask(conversation: Conversation, question: str, access) -> Iterator[dict]:
    """Pose une question ; produit des événements (status, delta, done). Le message final est enregistré."""
    question = question.strip()[:2000]
    ConversationMessage.objects.create(conversation=conversation, role=ConversationMessage.Role.USER, content=question)
    ctx = tools.ToolContext(access=access, pme=conversation.pme)
    organization = gateway._organization()
    provider, notes = _use_external(organization)
    started = time.monotonic()
    if provider is not None:
        final, calls, usage = yield from _external(provider, conversation, question, ctx)
    else:
        final, calls = yield from _local(question, ctx)
        usage = None
    final["limits"] = list(dict.fromkeys([*final.get("limits", [])]))
    try:
        jsonschema.validate(final, ANSWER_SCHEMA)
    except jsonschema.ValidationError:
        final = {
            "answer": "La réponse produite n'a pas le format attendu : reformulez la question ou consultez les écrans.",
            "sources": [],
            "confidence": "FAIBLE",
            "limits": ["Sortie de l'assistant invalide."],
        }
    analysis = gateway.record(
        task=AiAnalysis.Task.ASK_AI,
        prompt_code="copilot.ask",
        provider=provider.name if provider else "local",
        model=usage["model"] if usage else prompts.LOCAL_ENGINE_VERSION,
        output=final,
        tokens_in=usage["tokens_in"] if usage else 0,
        tokens_out=usage["tokens_out"] if usage else 0,
        latency_ms=int((time.monotonic() - started) * 1000),
        pme=conversation.pme,
        input_refs={"conversation": str(conversation.pk), "question": question, "tools": calls, "routing": notes},
        user=access.user,
        pseudonymized=bool(usage and usage.get("pseudonymized")),
    )
    message = ConversationMessage.objects.create(
        conversation=conversation,
        role=ConversationMessage.Role.ASSISTANT,
        content=final["answer"],
        sources=final["sources"],
        confidence=final["confidence"],
        limits=final["limits"],
        tool_calls=calls,
        analysis=analysis,
    )
    conversation.save(update_fields=["updated_at"])
    audit.record(
        "ai.question_answered",
        instance=conversation,
        pme_id=conversation.pme_id,
        after={"question": question, "tools": [c["tool"] for c in calls], "provider": analysis.provider},
    )
    for piece in _chunks(final["answer"]):
        yield _event("delta", text=piece)
    yield _event(
        "done",
        message={
            "id": str(message.pk),
            "content": message.content,
            "sources": message.sources,
            "confidence": message.confidence,
            "limits": message.limits,
            "analysis_id": str(analysis.pk),
            "provider": analysis.provider,
        },
    )


# --- Fournisseur externe : boucle agentique bornée -----------------------------------------------------------------

TOOL_STATUS = {
    "get_pme_profile": "Lecture de la fiche PME…",
    "get_scores": "Consultation des scores…",
    "compare_snapshots": "Comparaison des diagnostics…",
    "get_financial_metrics": "Lecture des indicateurs financiers…",
    "list_documents": "Lecture du dossier de conformité…",
    "list_deadlines": "Lecture des échéances…",
    "list_actions": "Lecture des actions…",
    "list_alerts": "Lecture des alertes…",
    "portfolio_query": "Analyse du portefeuille…",
    "search_knowledge": "Recherche dans la base de connaissances…",
    "draft_report": "Préparation du brouillon…",
}


def _external(provider, conversation: Conversation, question: str, ctx: tools.ToolContext):
    pseudonymizer: Pseudonymizer = for_pme(conversation.pme)
    history = list(conversation.messages.order_by("-created_at")[1 : HISTORY + 1])[::-1]
    messages = [
        {
            "role": "user" if m.role == ConversationMessage.Role.USER else "assistant",
            "content": pseudonymizer.text(m.content),
        }
        for m in history
    ]
    scope = (
        f"PME : {conversation.pme.legal_name} (id {conversation.pme.pk})"
        if conversation.pme
        else "Portefeuille de l'utilisateur"
    )
    messages.append({"role": "user", "content": f"Contexte — {scope}.\nQuestion : {pseudonymizer.text(question)}"})
    # Deux messages consécutifs du même rôle ne sont pas admis : on fusionne.
    merged: list[dict] = []
    for message in messages:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"] += "\n\n" + message["content"]
        else:
            merged.append(message)
    messages = merged if merged[0]["role"] == "user" else merged[1:]
    definitions = tools.definitions() + [
        {"name": ANSWER_TOOL, "description": "Réponse finale structurée.", "input_schema": ANSWER_SCHEMA}
    ]
    model = gateway.model_for("ASK_AI")
    usage = {"model": model, "tokens_in": 0, "tokens_out": 0, "pseudonymized": True}
    calls: list[dict] = []
    final = None
    for _ in range(settings.PME360_AI_MAX_TOOL_CALLS + 2):
        force = len(calls) >= settings.PME360_AI_MAX_TOOL_CALLS
        try:
            response = provider.chat(
                model=model,
                system=prompts.get("copilot.ask").system,
                messages=messages,
                tools=[d for d in definitions if not force or d["name"] == ANSWER_TOOL],
            )
        except Exception as exc:  # fournisseur indisponible : on repasse en local sans perdre la question
            gateway._breaker_failure(getattr(provider, "name", "externe"))
            yield _event("status", text="Fournisseur indisponible : réponse par le moteur local…")
            final, local_calls = yield from _local(question, ctx)
            final["limits"] = [*final.get("limits", []), f"Réponse du moteur local ({type(exc).__name__})."]
            return final, calls + local_calls, None
        usage["model"] = response.model
        usage["tokens_in"] += response.usage.input_tokens
        usage["tokens_out"] += response.usage.output_tokens
        messages.append(
            {"role": "assistant", "content": [block.model_dump(exclude_none=True) for block in response.content]}
        )
        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            final = {
                "answer": text or "Je n'ai pas pu formuler de réponse.",
                "sources": _sources(calls),
                "confidence": "MOYENNE",
                "limits": [],
            }
            break
        results = []
        for block in uses:
            if block.name == ANSWER_TOOL:
                final = pseudonymizer.restore(dict(block.input))
                break
            yield _event("status", text=TOOL_STATUS.get(block.name, "Consultation des données…"))
            try:
                output = tools.call(ctx, block.name, dict(block.input))
                calls.append({"tool": block.name, "arguments": dict(block.input), "sources": output.get("sources", [])})
                content = pseudonymizer.text(json.dumps(output, ensure_ascii=False, default=str))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
            except tools.ToolError as exc:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(exc), "is_error": True})
        if final is not None:
            break
        messages.append({"role": "user", "content": results})
    if final is None:
        final = {
            "answer": "Je n'ai pas pu conclure dans le nombre d'étapes autorisé.",
            "sources": _sources(calls),
            "confidence": "FAIBLE",
            "limits": ["Question trop large : précisez-la."],
        }
    gateway._breaker_success(getattr(provider, "name", "externe"))
    return final, calls, usage


def _sources(calls: list[dict]) -> list[dict]:
    seen, sources = set(), []
    for call in calls:
        for source in call.get("sources", []):
            key = (source["label"], source.get("detail", ""))
            if key not in seen:
                seen.add(key)
                sources.append(source)
    return sources


# --- Moteur local : intentions → outils → réponse rédigée ---------------------------------------------------------

INTENTS = [
    ("documents", r"document|piece|justificatif|manqu|dossier|conformite"),
    ("echeances", r"echeance|delai|date limite|obligation|relance"),
    ("evolution", r"evolu|progress|depuis|compar|initial|dernier diagnostic|avance"),
    ("finances", r"ratio|financ|rentab|marge|endettement|tresorerie|chiffre d'affaires|\bca\b|ebe"),
    ("alertes", r"alerte|risque|urgent|intervention|inquiet"),
    ("priorites", r"priorit|que faire|quoi faire|actions?|plan|recommand|ameliorer"),
    ("frequents", r"frequent|recurrent|commun|le plus souvent|principaux problemes des"),
    ("rapport", r"rapport"),
    ("score", r"score|faible|point faible|probleme|pourquoi|niveau|force|faiblesse|diagnostic|situation"),
]
SUPPORTED = (
    "les problèmes principaux et les raisons d'un score, les documents manquants, les échéances, les priorités, "
    "l'évolution depuis le dernier diagnostic ou le diagnostic initial, les ratios financiers, les alertes ; "
    "pour le portefeuille : les PME à intervention urgente, les problèmes fréquents, la progression et la stagnation"
)


def _intents(question: str) -> list[str]:
    folded = fold(question)
    return [name for name, pattern in INTENTS if re.search(pattern, folded)]


def _call(ctx, calls, name, **arguments) -> dict | None:
    try:
        output = tools.call(ctx, name, arguments)
    except tools.ToolError as exc:
        calls.append({"tool": name, "arguments": arguments, "error": str(exc), "sources": []})
        return None
    calls.append({"tool": name, "arguments": arguments, "sources": output.get("sources", [])})
    return output


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f} %"


def _local(question: str, ctx: tools.ToolContext):
    calls: list[dict] = []
    parts: list[str] = []
    limits: list[str] = []
    intents = _intents(question)
    on_pme = ctx.pme is not None
    if not on_pme and (
        "alertes" in intents
        or "frequents" in intents
        or "evolution" in intents
        or "rapport" in intents
        or "score" in intents
        or not intents
    ):
        yield _event("status", text="Analyse du portefeuille…")
        if "frequents" in intents or "score" in intents:
            out = _call(ctx, calls, "portfolio_query", query="problemes_frequents")
            if out and out["data"]:
                items = "; ".join(
                    f"{w['dimension']} ({_pct(w['part_des_pme_sous_le_seuil'])} des PME sous le seuil)"
                    for w in out["data"][:5]
                )
                parts.append(f"Problèmes les plus fréquents du portefeuille : {items}.")
                limits += out.get("limits", [])
        if "alertes" in intents or not intents:
            out = _call(ctx, calls, "portfolio_query", query="pme_urgentes")
            if out is not None:
                urgent = out["data"]
                parts.append(
                    "PME en priorité d'intervention P1 : "
                    + (
                        "; ".join(
                            f"{u['pme_name']} (score {u['global_score']}, risque {u['risk_index']})" for u in urgent
                        )
                        if urgent
                        else "aucune."
                    )
                )
        if "evolution" in intents:
            out = _call(ctx, calls, "portfolio_query", query="progression")
            if out is not None and out["data"]:
                parts.append(
                    "Plus fortes progressions : "
                    + "; ".join(f"{p['pme_name']} (+{p['delta']} pts en {p['months']} mois)" for p in out["data"])
                    + "."
                )
            out = _call(ctx, calls, "portfolio_query", query="stagnation")
            if out is not None:
                parts.append(
                    "PME qui stagnent depuis 6 mois ou plus : "
                    + ("; ".join(p["pme_name"] for p in out["data"]) or "aucune")
                    + "."
                )
        if "rapport" in intents:
            limits.append("La génération du rapport trimestriel arrive en phase 6 ; voici les éléments disponibles.")
            out = _call(ctx, calls, "portfolio_query", query="indicateurs_cles")
            if out is not None:
                k = out["data"]
                parts.append(
                    f"Portefeuille : {k['pmes_total']} PME, {k['pmes_diagnosed']} diagnostiquées, "
                    f"score moyen {k['average_score']}, progression moyenne {k['average_progress']} pts, "
                    f"{k['pmes_urgent']} en priorité P1."
                )
    elif on_pme:
        name = ctx.pme.legal_name
        if "score" in intents or "priorites" in intents or not intents:
            yield _event("status", text="Consultation des scores…")
            out = _call(ctx, calls, "get_scores")
            if out and out["data"]:
                d = out["data"]
                weakest = ", ".join(
                    f"{x['dimension']} ({x['score']:.0f})" for x in d["dimensions_du_plus_faible_au_plus_fort"][:3]
                )
                parts.append(
                    f"{name} : score global {d['score_global']}/100 ({d['nature']} du {d['date']}), "
                    f"niveau « {d['niveau']} », priorité {d['priorite']}, confiance {_pct(d['confiance'])}. "
                    f"Dimensions les plus faibles : {weakest}."
                )
                if d["portes_non_franchies"]:
                    parts.append(
                        "Le niveau est plafonné : " + "; ".join(str(g) for g in d["portes_non_franchies"] if g) + "."
                    )
                gaps = d["ecarts_a_plus_fort_impact"][:4]
                if gaps:
                    parts.append(
                        (
                            "Priorités (écarts à plus fort impact) : "
                            if "priorites" in intents
                            else "Principaux écarts : "
                        )
                        + "; ".join(
                            f"{g['critere']} ({g['dimension']}, score {g['score']:.0f}"
                            + (", critère critique" if g["critique"] else "")
                            + (", plafonné faute de preuve" if g["plafonne_faute_de_preuve"] else "")
                            + ")"
                            for g in gaps
                        )
                        + "."
                    )
                if "priorites" in intents:
                    limits.append(
                        "Le plan d'accompagnement priorisé (Impact × Urgence × Risque × Effort) arrive en phase 5."
                    )
            elif out:
                limits += out.get("limits", [])
        if "documents" in intents:
            yield _event("status", text="Lecture du dossier de conformité…")
            out = _call(ctx, calls, "list_documents")
            if out:
                d = out["data"]
                parts.append(
                    f"Dossier complet à {_pct(d['taux_de_conformite'])}. "
                    + (f"Manquants : {', '.join(d['manquants'])}. " if d["manquants"] else "Aucun document manquant. ")
                    + (f"Expirés : {', '.join(d['expires'])}. " if d["expires"] else "")
                    + (f"Refusés : {', '.join(d['non_conformes'])}. " if d["non_conformes"] else "")
                    + (f"En vérification : {', '.join(d['en_verification'])}." if d["en_verification"] else "")
                )
        if "echeances" in intents:
            yield _event("status", text="Lecture des échéances…")
            out = _call(ctx, calls, "list_deadlines", days=60)
            if out:
                items = out["data"]["echeances"]
                parts.append(
                    "Échéances des 60 prochains jours : "
                    + (
                        "; ".join(
                            f"{e['obligation']} ({e['periode']}) pour le {e['echeance']}"
                            + (f", en retard de {e['en_retard_de_jours']} j" if e["en_retard_de_jours"] else "")
                            for e in items
                        )
                        if items
                        else "aucune."
                    )
                )
        if "evolution" in intents:
            yield _event("status", text="Comparaison des diagnostics…")
            reference = "initial" if "initial" in fold(question) else "precedent"
            out = _call(ctx, calls, "compare_snapshots", reference=reference)
            if out and out["data"]:
                d = out["data"]
                top = "; ".join(
                    f"{c['dimension']} ({c['contribution_points']:+.1f} pt)" for c in d["contributions"][:4]
                )
                parts.append(
                    f"Du {d['de']} au {d['a']} : {d['score_avant']} → {d['score_apres']} ({d['ecart']:+.1f} pts, "
                    f"dont {d['dont_gain_de_preuve']:+.1f} de gain de preuve). Contributions principales : {top}."
                )
            elif out:
                limits += out.get("limits", [])
        if "finances" in intents:
            yield _event("status", text="Lecture des indicateurs financiers…")
            out = _call(ctx, calls, "get_financial_metrics")
            if out:
                items = out["data"]["indicateurs"]
                parts.append(
                    "Indicateurs financiers : "
                    + (
                        "; ".join(
                            f"{m['indicateur']} {m['valeur']}"
                            + (f" ({m['appreciation']})" if m["appreciation"] else "")
                            for m in items
                        )
                        if items
                        else "aucun calculable."
                    )
                    + "."
                )
                limits += out.get("limits", [])
                if any("DOCUMENT_IA" in m["sources"] for m in items):
                    limits.append("Certains montants viennent d'une extraction d'états financiers non encore vérifiée.")
                if items and all(set(m["sources"]) <= {"DECLARATIF"} for m in items):
                    limits.append("Montants déclarés au questionnaire, sans états financiers vérifiés.")
        if "alertes" in intents:
            out = _call(ctx, calls, "list_alerts")
            if out:
                items = out["data"]["alertes_ouvertes"]
                parts.append(
                    "Alertes ouvertes : "
                    + ("; ".join(f"{a['titre']} ({a['gravite']})" for a in items) if items else "aucune.")
                )
        if "rapport" in intents:
            limits.append("La génération de rapports arrive en phase 6.")
    if not parts:
        out = _call(ctx, calls, "search_knowledge", query=question)
        fragments = out["data"]["fragments"] if out else []
        if fragments:
            parts.append(
                "Éléments trouvés dans la base de connaissances :\n"
                + "\n".join(f"- {f['source']} : {f['texte'][:300]}" for f in fragments[:3])
            )
            limits.append("Réponse limitée à des extraits : le moteur local ne rédige pas de synthèse libre.")
        else:
            parts.append("Je ne dispose pas des données nécessaires pour répondre à cette question.")
            limits.append(f"Questions prises en charge par le moteur local : {SUPPORTED}.")
    sources = _sources(calls)
    confidence = "FAIBLE" if not sources else "MOYENNE" if limits else "ELEVEE"
    return {"answer": "\n\n".join(parts), "sources": sources, "confidence": confidence, "limits": limits}, calls
