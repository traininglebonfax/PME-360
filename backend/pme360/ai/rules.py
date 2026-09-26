"""Moteur de règles local : classification, extraction, pré-diagnostic et commentaire sans IA externe.

C'est le « mode dégradé local » du Document 4 (§ 3.1 et § 13) : aucune donnée ne quitte l'infrastructure. Il lit
les documents à texte natif dont les libellés sont usuels (formulaires administratifs, liasses SYSCOHADA) ; ce qu'il
ne trouve pas avec certitude reste vide, avec une confiance basse, et part en vérification humaine.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from .schemas import AUTRE, CLASSIFIABLE_TYPES, ExtractionSchema

# --- Normalisation ---------------------------------------------------------------------------------------------


def _fold(char: str) -> str:
    base = unicodedata.normalize("NFD", char)[0].lower()
    return {" ": " ", " ": " ", "’": "'", "‘": "'", "–": "-", "—": "-"}.get(char, base)


def fold(text: str) -> str:
    """Minuscules sans accents, MÊME LONGUEUR que le texte d'origine (les positions restent alignées)."""
    return "".join(_fold(c) for c in text)


# --- Classification --------------------------------------------------------------------------------------------

# (expression, poids) ; les expressions « titre » (poids 5) caractérisent le type.
KEYWORDS: dict[str, tuple[tuple[str, int], ...]] = {
    "RCCM": (
        ("registre du commerce et du credit mobilier", 5),
        ("extrait du registre du commerce", 5),
        ("rccm", 2),
        ("immatriculation", 1),
        ("greffe", 2),
        ("tribunal de commerce", 1),
    ),
    "STATUTS": (
        ("statuts", 4),
        ("objet social", 2),
        ("capital social", 1),
        ("article 1", 2),
        ("associes", 1),
        ("assemblee generale", 1),
    ),
    "DFE": (
        ("declaration fiscale d'existence", 6),
        ("compte contribuable", 2),
        ("regime d'imposition", 2),
        ("centre des impots", 1),
        ("direction generale des impots", 1),
    ),
    "ATTEST_REGUL_FISC": (
        ("attestation de regularite fiscale", 6),
        ("obligations fiscales", 2),
        ("direction generale des impots", 1),
        ("regularite fiscale", 2),
    ),
    "ATTEST_CNPS": (
        ("attestation de situation cotisante", 5),
        ("attestation de regularite cnps", 5),
        ("prevoyance sociale", 2),
        ("cnps", 1),
        ("a jour de ses cotisations", 2),
        ("employeur", 1),
    ),
    "DECL_CNPS_PERIODIQUE": (
        ("declaration de cotisations sociales", 5),
        ("declaration individuelle des salaires", 5),
        ("masse salariale", 2),
        ("prevoyance sociale", 1),
        ("cotisations dues", 2),
    ),
    "ETATS_FIN_SYSCOHADA": (
        ("etats financiers", 4),
        ("compte de resultat", 2),
        ("bilan", 1),
        ("syscohada", 2),
        ("total actif", 1),
        ("capitaux propres", 1),
        ("chiffre d'affaires", 1),
    ),
    "TABLEAU_TRESORERIE": (
        ("tableau de tresorerie", 5),
        ("plan de tresorerie", 5),
        ("encaissements", 2),
        ("decaissements", 2),
        ("solde de tresorerie", 1),
    ),
    "ATTEST_ASSURANCE": (
        ("attestation d'assurance", 6),
        ("police n", 2),
        ("assure", 1),
        ("garanties", 1),
        ("assureur", 1),
    ),
    "ATTEST_BANCAIRE": (
        ("attestation bancaire", 6),
        ("titulaire du compte", 2),
        ("relation bancaire", 2),
        ("banque", 1),
    ),
}


def classify(text: str) -> dict:
    folded = fold(text)
    scores = {code: sum(weight for phrase, weight in phrases if phrase in folded) for code, phrases in KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    (best, top), (_, second) = ranked[0], ranked[1]
    if top < 3:
        return {
            "document_type": AUTRE,
            "confidence": 0.3,
            "entity_name": None,
            "period": None,
            "rationale": "Aucun marqueur caractéristique d'un type connu.",
        }
    strength = min(1.0, top / 8)
    margin = (top - second) / top
    confidence = round(0.4 + 0.6 * strength * (0.5 + 0.5 * margin), 3)
    matched = [phrase for phrase, _ in KEYWORDS[best] if phrase in folded]
    return {
        "document_type": best,
        "confidence": confidence,
        "entity_name": None,
        "period": None,
        "rationale": f"{CLASSIFIABLE_TYPES[best]} : marqueurs trouvés ({', '.join(matched)}).",
    }


# --- Valeurs ---------------------------------------------------------------------------------------------------

MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}
DATE_PATTERN = (
    r"(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2}|(?:1er|\d{1,2})\s+(?:" + "|".join(MONTHS) + r")\s+\d{4})"
)
AMOUNT_PATTERN = r"(?:-\s?)?\(?\d{1,3}(?:[ .]\d{3})+\)?|(?:-\s?)?\(?\d+\)?"
# Entre un libellé et sa valeur : ponctuation, points de conduite, code de rubrique. Un « - » suivi d'un chiffre
# n'en fait pas partie : c'est le signe d'un montant négatif.
GAP = r"(?:[\s.:_…|]|-(?!\s?[\d(])|\([a-z]{1,3}\)|\(fcfa\)|fcfa|en francs cfa)*"
COLUMN = r"(?:\s*\|\s*|\s+)"
IDENTIFIERS = {"numero_rccm", "rccm", "ncc", "numero_employeur", "numero_police"}


def parse_date(raw: str) -> date | None:
    raw = fold(raw).strip()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", raw):
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.fullmatch(r"(1er|\d{1,2})\s+([a-z]+)\s+(\d{4})", raw):
            day = 1 if m[1] == "1er" else int(m[1])
            return date(int(m[3]), MONTHS[m[2]], day)
    except (ValueError, KeyError):
        return None
    return None


def parse_amount(raw: str) -> float | None:
    raw = raw.strip()
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")"))
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    value = float(digits)
    return -value if negative else value


# --- Extraction --------------------------------------------------------------------------------------------------

# Libellés par champ : (expression normalisée, confiance). Les plus spécifiques d'abord.
LABELS: dict[str, tuple[tuple[str, float], ...]] = {
    "numero_rccm": (("numero rccm", 0.95), ("n° rccm", 0.95), ("rccm n°", 0.95), ("rccm", 0.85)),
    "raison_sociale": (
        ("raison sociale", 0.95),
        ("denomination sociale", 0.95),
        ("denomination", 0.9),
        ("nom de l'entreprise", 0.9),
        ("assure", 0.85),
        ("souscripteur", 0.8),
        ("titulaire", 0.75),
    ),
    "forme_juridique": (("forme juridique", 0.95),),
    "date_immatriculation": (("date d'immatriculation", 0.95), ("immatricule le", 0.9)),
    "siege": (("siege social", 0.95), ("siege", 0.85), ("adresse", 0.7)),
    "ncc": (
        ("numero de compte contribuable", 0.95),
        ("n° de compte contribuable", 0.95),
        ("compte contribuable", 0.9),
        ("ncc", 0.9),
    ),
    "rccm": (("n° rccm", 0.95), ("rccm", 0.9)),
    "regime_fiscal": (("regime d'imposition", 0.95), ("regime fiscal", 0.95), ("regime", 0.75)),
    "centre_impots": (("centre des impots", 0.95), ("centre de rattachement", 0.9)),
    "date_delivrance": (
        ("date de delivrance", 0.95),
        ("delivree le", 0.95),
        ("delivre le", 0.95),
        ("fait a abidjan le", 0.85),
        ("fait le", 0.8),
        ("date d'emission", 0.9),
    ),
    "date_validite": (
        ("valable jusqu'au", 0.95),
        ("date de validite", 0.95),
        ("valide jusqu'au", 0.95),
        ("date d'expiration", 0.95),
        ("expire le", 0.9),
    ),
    "numero_employeur": (("numero employeur", 0.95), ("n° employeur", 0.95), ("matricule employeur", 0.9)),
    "effectif_declare": (("effectif declare", 0.95), ("nombre de salaries", 0.9), ("effectif", 0.8)),
    "emetteur": (("emetteur", 0.9), ("service emetteur", 0.9)),
    "assureur": (("assureur", 0.95), ("compagnie d'assurance", 0.9), ("compagnie", 0.75)),
    "numero_police": (("numero de police", 0.95), ("police n°", 0.95), ("n° de police", 0.95), ("contrat n°", 0.8)),
    "garanties": (("garanties", 0.9), ("garantie", 0.85)),
    "date_debut": (("date d'effet", 0.95), ("prise d'effet", 0.9), ("du", 0.5)),
    "date_fin": (("date d'echeance", 0.95), ("date de fin", 0.95), ("echeance", 0.9), ("expire le", 0.9)),
    "systeme": (("systeme", 0.9),),
    "chiffre_affaires": (("chiffre d'affaires", 0.95), ("ca net", 0.85)),
    "marge_commerciale": (("marge commerciale", 0.95),),
    "valeur_ajoutee": (("valeur ajoutee", 0.95),),
    "ebe": (("excedent brut d'exploitation", 0.95), ("ebe", 0.9)),
    "resultat_exploitation": (("resultat d'exploitation", 0.95),),
    "resultat_financier": (("resultat financier", 0.95),),
    "resultat_net": (("resultat net de l'exercice", 0.95), ("resultat net", 0.95)),
    "charges_personnel": (("charges de personnel", 0.95),),
    "dotations_amortissements": (
        ("dotations aux amortissements et provisions", 0.95),
        ("dotations aux amortissements", 0.95),
    ),
    "frais_financiers": (("frais financiers", 0.95),),
    "actif_immobilise_net": (
        ("actif immobilise net", 0.95),
        ("total actif immobilise", 0.9),
        ("actif immobilise", 0.85),
    ),
    "stocks": (("stocks et encours", 0.95), ("stocks", 0.95)),
    "creances_clients": (("creances clients", 0.95), ("clients", 0.8)),
    "autres_creances": (("autres creances", 0.95),),
    "tresorerie_actif": (("tresorerie actif", 0.95), ("tresorerie - actif", 0.95), ("disponibilites", 0.85)),
    "total_actif": (("total actif", 0.95), ("total general actif", 0.95), ("total bilan actif", 0.95)),
    "capitaux_propres": (("total capitaux propres", 0.95), ("capitaux propres", 0.95)),
    "dettes_financieres": (("dettes financieres", 0.95), ("emprunts et dettes financieres", 0.95)),
    "fournisseurs": (("fournisseurs d'exploitation", 0.95), ("dettes fournisseurs", 0.95), ("fournisseurs", 0.9)),
    "dettes_fiscales_sociales": (("dettes fiscales et sociales", 0.95),),
    "autres_dettes": (("autres dettes", 0.95),),
    "tresorerie_passif": (("tresorerie passif", 0.95), ("tresorerie - passif", 0.95)),
    "total_passif": (("total passif", 0.95), ("total general passif", 0.95), ("total bilan passif", 0.95)),
}

PERIOD = re.compile(rf"du\s+({DATE_PATTERN})\s+au\s+({DATE_PATTERN})")


def _find(folded: str, original: str, label: str, value_pattern: str) -> tuple[str, str] | None:
    """Première valeur après ``label`` sur la même ligne ; renvoie (texte normalisé, texte d'origine)."""
    pattern = rf"(?<![a-z]){re.escape(label)}(?![a-z]){GAP}({value_pattern})"
    match = re.search(pattern, folded)
    if not match:
        return None
    return match.group(1), original[match.start(1) : match.end(1)]


def _line_value(folded: str, original: str, label: str) -> str | None:
    match = re.search(rf"(?<![a-z]){re.escape(label)}(?![a-z])\s*(?:\([^)\n]*\))?\s*[:\-]\s*([^\n]+)", folded)
    if not match:
        return None
    value = original[match.start(1) : match.end(1)].strip(" .;")
    return value or None


def _amounts_after(folded: str, label: str) -> list[float]:
    match = re.search(
        rf"(?:^|\n)[^\n]*?(?<![a-z]){re.escape(label)}(?![a-z]){GAP}((?:{AMOUNT_PATTERN})(?:{COLUMN}(?:{AMOUNT_PATTERN}))*)",
        folded,
    )
    if not match:
        return []
    return [a for a in (parse_amount(x) for x in re.findall(AMOUNT_PATTERN, match.group(1))) if a is not None]


def extract(schema: ExtractionSchema, text: str) -> dict:
    folded = fold(text)
    fields: dict = {f.name: None for f in schema.fields}
    confidence: dict[str, float] = {}

    for f in schema.fields:
        if f.name == "chiffre_affaires_n1":
            continue
        for label, conf in LABELS.get(f.name, ()):
            value = None
            if f.type == "date":
                found = _find(folded, text, label, DATE_PATTERN)
                parsed = parse_date(found[0]) if found else None
                value = parsed.isoformat() if parsed else None
            elif f.type == "number":
                amounts = _amounts_after(folded, label)
                if amounts:
                    value = amounts[0]
                    if f.name == "chiffre_affaires" and len(amounts) > 1 and "chiffre_affaires_n1" in fields:
                        fields["chiffre_affaires_n1"], confidence["chiffre_affaires_n1"] = amounts[1], conf * 0.95
            elif f.type == "integer":
                found = _find(folded, text, label, r"\d{1,6}")
                value = int(found[0]) if found else None
            elif f.type in ("string", "list"):
                value = _line_value(folded, text, label)
                if value and f.name in IDENTIFIERS:
                    # Un identifiant s'arrête à la première ponctuation (« NCC : 1234567A, est à jour… »).
                    value = re.split(r"[,;]| - | – | \(", value)[0].strip() or None
            if value is not None:
                fields[f.name], confidence[f.name] = value, conf
                break

    # Périodes « du … au … » (période couverte, exercice).
    period = PERIOD.search(folded)
    if period:
        start, end = parse_date(period.group(1)), parse_date(period.group(2))
        for start_field, end_field in (("periode_debut", "periode_fin"), ("exercice_debut", "exercice_fin")):
            if start_field in fields and fields[start_field] is None and start and end:
                fields[start_field], fields[end_field] = start.isoformat(), end.isoformat()
                confidence[start_field] = confidence[end_field] = 0.92
    if "exercice_fin" in fields and fields["exercice_fin"] is None:
        found = _find(folded, text, "exercice clos le", DATE_PATTERN) or _find(folded, text, "clos le", DATE_PATTERN)
        if found and (parsed := parse_date(found[0])):
            fields["exercice_fin"], confidence["exercice_fin"] = parsed.isoformat(), 0.95
    if "systeme" in fields and fields["systeme"]:
        folded_value = fold(fields["systeme"])
        fields["systeme"] = (
            "SMT"
            if "minimal" in folded_value or "smt" in folded_value
            else ("NORMAL" if "normal" in folded_value else "INCONNU")
        )
    if "mention_regularite" in fields:
        if re.search(r"n'est pas a jour|irreguli|non a jour|pas en regle", folded):
            fields["mention_regularite"], confidence["mention_regularite"] = False, 0.9
        elif re.search(r"est a jour de ses (?:cotisations|obligations)|en regle|situation reguliere", folded):
            fields["mention_regularite"], confidence["mention_regularite"] = True, 0.92
    if "dirigeants" in fields:
        names = []
        for label in ("gerant", "dirigeant", "president", "directeur general", "administrateur"):
            for match in re.finditer(rf"(?<![a-z]){label}s?(?:\(s\))?\s*:\s*([^\n]+)", folded):
                names.extend(n.strip() for n in re.split(r",| et ", text[match.start(1) : match.end(1)]) if n.strip())
        if names:
            fields["dirigeants"], confidence["dirigeants"] = list(dict.fromkeys(names)), 0.85
    return {"fields": fields, "field_confidence": confidence}


# --- Pré-diagnostic --------------------------------------------------------------------------------------------

SOURCE_CONFIDENCE = {"DOCUMENT_VERIFIE": 0.9, "DECLARATIF_CORROBORE": 0.7, "DECLARATIF": 0.55, "INFERE": 0.4}


def prediagnose(criteria: list[dict]) -> dict:
    """Proposition par critère à partir des réponses, des preuves et des indicateurs déjà calculés."""
    proposals = []
    for c in criteria:
        sources = [f"Question « {a['question']} » : {a['answer']} ({a['source']}, {a['date']})" for a in c["answers"]]
        sources += [f"Document vérifié : {d}" for d in c["evidence"]]
        if c.get("metrics"):
            parts = [
                f"{m['name']} = {m['display']} ({m['band'] or 'hors barème'})"
                for m in c["metrics"]
                if m["value"] is not None
            ]
            proposals.append(
                {
                    "code": c["code"],
                    "proposed_level": None,
                    "justification": (
                        "Critère calculé par le moteur à partir des indicateurs : " + "; ".join(parts) + "."
                        if parts
                        else "Indicateurs non calculables : données financières manquantes."
                    ),
                    "sources": sources
                    + [f"Indicateur {m['name']} ({', '.join(m['sources']) or 'aucune source'})" for m in c["metrics"]],
                    "confidence": 0.8 if parts else 0.3,
                }
            )
            continue
        declared = c["declared_level"]
        if declared is None:
            proposals.append(
                {
                    "code": c["code"],
                    "proposed_level": None,
                    "justification": "Aucune réponse exploitable : niveau à établir en entretien.",
                    "sources": sources,
                    "confidence": 0.2,
                }
            )
            continue
        level, notes = declared, []
        proven = c["evidence_level"]
        if c["evidence_policy"] == "REQUIRED" and declared > c["cap"] and (proven is None or proven < declared):
            level = max(c["cap"], proven or 0)
            expected = ", ".join(c["expected_documents"]) or "un justificatif"
            notes.append(
                f"niveau déclaré {declared} non prouvé : {level} proposé (plafond déclaratif, RM-01) ; "
                f"document attendu : {expected}"
            )
        elif proven is not None and proven >= declared:
            notes.append("niveau corroboré par un document vérifié")
        if c.get("inconsistencies"):
            notes.extend(c["inconsistencies"])
        rubric = c["rubric"][level] if 0 <= level < len(c["rubric"]) else ""
        justification = f"Niveau {level}" + (f" — « {rubric} »" if rubric else "") + "."
        if notes:
            justification += " " + " ; ".join(n[0].upper() + n[1:] for n in notes) + "."
        confidence = SOURCE_CONFIDENCE.get(c["source"], 0.5)
        if proven is not None and proven >= level:
            confidence = max(confidence, 0.9)
        if c.get("inconsistencies"):
            confidence = min(confidence, 0.5)
        proposals.append(
            {
                "code": c["code"],
                "proposed_level": level,
                "justification": justification,
                "sources": sources,
                "confidence": round(confidence, 2),
            }
        )
    return {"criteria": proposals}


# --- Commentaire financier -------------------------------------------------------------------------------------


def interpret(metrics: list[dict]) -> dict:
    points, limits = [], []
    for m in metrics:
        if m["value"] is None:
            limits.append(f"{m['name']} : non calculable ({m.get('missing') or 'donnée manquante'}).")
            continue
        tone = (
            "neutre"
            if m["points"] is None
            else "positif"
            if m["points"] >= 70
            else "vigilance"
            if m["points"] >= 40
            else "alerte"
        )
        comment = f"{m['name']} : {m['display']}" + (f" — {m['band']}." if m["band"] else ".")
        points.append({"metric": m["code"], "comment": comment, "tone": tone})
        if "DOCUMENT_IA" in m["sources"]:
            limits.append(f"{m['name']} repose sur une extraction non encore vérifiée.")
        if set(m["sources"]) <= {"DECLARATIF"}:
            limits.append(f"{m['name']} repose sur des données déclarées, sans justificatif.")
    alerts = [p for p in points if p["tone"] == "alerte"]
    good = [p for p in points if p["tone"] == "positif"]
    if not points:
        summary = "Aucun indicateur financier calculable : les états financiers ou les données déclarées manquent."
    else:
        summary = (
            f"{len(points)} indicateur(s) calculé(s) : {len(good)} favorable(s), "
            f"{sum(p['tone'] == 'vigilance' for p in points)} à surveiller, {len(alerts)} en alerte."
        )
    return {"summary": summary, "points": points, "limits": list(dict.fromkeys(limits))}
