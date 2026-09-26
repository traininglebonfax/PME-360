"""Schémas d'extraction versionnés par type de document (Document 4, § 4) et schémas de sortie des tâches IA.

Chaque champ déclare son type, s'il est CRITIQUE (confiance ≥ 0,90 exigée sinon vérification humaine) et son
poids dans la confiance du document (Document 4, § 6.2). Les codes de rubriques SYSCOHADA (XA à XI) restent
« à confirmer » par l'expert-comptable du projet : les libellés servent à la lecture, jamais au calcul.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str  # string | date | number | integer | boolean | list
    critical: bool = False
    weight: float = 1.0
    personal: bool = False  # donnée personnelle : pseudonymisée avant tout envoi externe


@dataclass(frozen=True)
class ExtractionSchema:
    code: str
    document_type: str
    version: str
    fields: tuple[Field, ...]

    def field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def critical(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.critical)

    def json_schema(self) -> dict:
        """Schéma de sortie de l'extraction : valeurs + confiance par champ (0..1)."""
        types = {
            "string": {"type": ["string", "null"]},
            "date": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "number": {"type": ["number", "null"]},
            "integer": {"type": ["integer", "null"]},
            "boolean": {"type": ["boolean", "null"]},
            "list": {"type": ["array", "null"], "items": {"type": "string"}},
        }
        return {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "object",
                    "properties": {f.name: types[f.type] for f in self.fields},
                    "additionalProperties": False,
                },
                "field_confidence": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "required": ["fields", "field_confidence"],
            "additionalProperties": False,
        }


def _schema(code: str, document_type: str, *fields: Field) -> ExtractionSchema:
    return ExtractionSchema(code=code, document_type=document_type, version=SCHEMA_VERSION, fields=fields)


AMOUNT = "number"

EXTRACTION_SCHEMAS: dict[str, ExtractionSchema] = {
    s.document_type: s
    for s in (
        _schema(
            "RCCM",
            "RCCM",
            Field("numero_rccm", "N° RCCM", "string", critical=True, weight=3),
            Field("raison_sociale", "Raison sociale", "string", critical=True, weight=3),
            Field("forme_juridique", "Forme juridique", "string"),
            Field("date_immatriculation", "Date d'immatriculation", "date", critical=True, weight=2),
            Field("siege", "Siège social", "string"),
            Field("dirigeants", "Dirigeants", "list", personal=True),
        ),
        _schema(
            "DFE",
            "DFE",
            Field("ncc", "N° de compte contribuable (NCC)", "string", critical=True, weight=3),
            Field("raison_sociale", "Raison sociale", "string", critical=True, weight=3),
            Field("regime_fiscal", "Régime d'imposition", "string"),
            Field("centre_impots", "Centre des impôts", "string"),
            Field("date_delivrance", "Date de délivrance", "date", critical=True, weight=1),
        ),
        _schema(
            "ATTEST_CNPS",
            "ATTEST_CNPS",
            Field("numero_employeur", "N° employeur CNPS", "string", critical=True, weight=2),
            Field("raison_sociale", "Raison sociale", "string", critical=True, weight=2),
            Field("periode_debut", "Début de la période couverte", "date"),
            Field("periode_fin", "Fin de la période couverte", "date"),
            Field("date_delivrance", "Date de délivrance", "date", critical=True, weight=2),
            Field("date_validite", "Valable jusqu'au", "date", critical=True, weight=2),
            Field("effectif_declare", "Effectif déclaré", "integer"),
            Field("mention_regularite", "Mention de régularité", "boolean", critical=True, weight=2),
        ),
        _schema(
            "ATTEST_REGUL_FISC",
            "ATTEST_REGUL_FISC",
            Field("ncc", "N° de compte contribuable (NCC)", "string", weight=2),
            Field("raison_sociale", "Raison sociale", "string", critical=True, weight=2),
            Field("periode_debut", "Début de la période", "date"),
            Field("periode_fin", "Fin de la période", "date"),
            Field("date_delivrance", "Date de délivrance", "date", critical=True, weight=2),
            Field("date_validite", "Valable jusqu'au", "date", critical=True, weight=2),
            Field("emetteur", "Émetteur", "string"),
        ),
        _schema(
            "ATTEST_ASSURANCE",
            "ATTEST_ASSURANCE",
            Field("assureur", "Assureur", "string"),
            Field("numero_police", "N° de police", "string", critical=True, weight=2),
            Field("raison_sociale", "Assuré (raison sociale)", "string", critical=True, weight=2),
            Field("garanties", "Garanties", "string"),
            Field("date_debut", "Date d'effet", "date"),
            Field("date_fin", "Date d'échéance", "date", critical=True, weight=3),
        ),
        _schema(
            "ETATS_FIN_SYSCOHADA",
            "ETATS_FIN_SYSCOHADA",
            Field("raison_sociale", "Raison sociale", "string", critical=True, weight=1),
            Field("ncc", "NCC", "string"),
            Field("rccm", "RCCM", "string"),
            Field("exercice_debut", "Début de l'exercice", "date"),
            Field("exercice_fin", "Clôture de l'exercice", "date", critical=True, weight=2),
            Field("systeme", "Système (NORMAL / SMT)", "string"),
            Field("chiffre_affaires", "Chiffre d'affaires (XB)", AMOUNT, critical=True, weight=3),
            Field("chiffre_affaires_n1", "Chiffre d'affaires N-1", AMOUNT),
            Field("marge_commerciale", "Marge commerciale (XA)", AMOUNT),
            Field("valeur_ajoutee", "Valeur ajoutée (XC)", AMOUNT),
            Field("ebe", "Excédent brut d'exploitation (XD)", AMOUNT, critical=True, weight=2),
            Field("resultat_exploitation", "Résultat d'exploitation (XE)", AMOUNT),
            Field("resultat_financier", "Résultat financier (XF)", AMOUNT),
            Field("resultat_net", "Résultat net (XI)", AMOUNT, critical=True, weight=3),
            Field("charges_personnel", "Charges de personnel", AMOUNT),
            Field("dotations_amortissements", "Dotations aux amortissements et provisions", AMOUNT),
            Field("frais_financiers", "Frais financiers", AMOUNT),
            Field("actif_immobilise_net", "Actif immobilisé net", AMOUNT),
            Field("stocks", "Stocks", AMOUNT),
            Field("creances_clients", "Créances clients", AMOUNT),
            Field("autres_creances", "Autres créances", AMOUNT),
            Field("tresorerie_actif", "Trésorerie – actif", AMOUNT),
            Field("total_actif", "Total actif", AMOUNT, critical=True, weight=2),
            Field("capitaux_propres", "Capitaux propres", AMOUNT, critical=True, weight=2),
            Field("dettes_financieres", "Dettes financières", AMOUNT, critical=True, weight=2),
            Field("fournisseurs", "Fournisseurs", AMOUNT),
            Field("dettes_fiscales_sociales", "Dettes fiscales et sociales", AMOUNT),
            Field("autres_dettes", "Autres dettes", AMOUNT),
            Field("tresorerie_passif", "Trésorerie – passif", AMOUNT),
            Field("total_passif", "Total passif", AMOUNT, critical=True, weight=2),
        ),
    )
}

# Classification (Document 4, § 12 : 10 types principaux ; extraction sur les 6 types du MVP).
CLASSIFIABLE_TYPES: dict[str, str] = {
    "RCCM": "Extrait ou certificat RCCM",
    "STATUTS": "Statuts",
    "DFE": "Déclaration fiscale d'existence",
    "ATTEST_REGUL_FISC": "Attestation de régularité fiscale",
    "ATTEST_CNPS": "Attestation CNPS",
    "DECL_CNPS_PERIODIQUE": "Déclaration CNPS périodique",
    "ETATS_FIN_SYSCOHADA": "États financiers SYSCOHADA",
    "TABLEAU_TRESORERIE": "Tableau de trésorerie",
    "ATTEST_ASSURANCE": "Attestation d'assurance",
    "ATTEST_BANCAIRE": "Attestation bancaire",
}
AUTRE = "AUTRE"

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "document_type": {"type": "string", "enum": [*CLASSIFIABLE_TYPES, AUTRE]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "entity_name": {"type": ["string", "null"]},
        "period": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": ["document_type", "confidence", "rationale"],
    "additionalProperties": False,
}

PREDIAGNOSTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "proposed_level": {"type": ["integer", "null"], "minimum": 0, "maximum": 4},
                    "justification": {"type": "string", "minLength": 1},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["code", "proposed_level", "justification", "sources", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["criteria"],
    "additionalProperties": False,
}

INTERPRETATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "comment": {"type": "string"},
                    "tone": {"type": "string", "enum": ["positif", "vigilance", "alerte", "neutre"]},
                },
                "required": ["metric", "comment", "tone"],
                "additionalProperties": False,
            },
        },
        "limits": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "points", "limits"],
    "additionalProperties": False,
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "detail": {"type": "string"}},
                "required": ["label"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["ELEVEE", "MOYENNE", "FAIBLE"]},
        "limits": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "sources", "confidence", "limits"],
    "additionalProperties": False,
}

# Correspondance extraction → données d'indicateurs du référentiel (calculs déterministes du moteur).
FINANCIAL_INPUT_MAP = {
    "ca_n": ("chiffre_affaires",),
    "ca_n1": ("chiffre_affaires_n1",),
    "ebe": ("ebe",),
    "resultat_net": ("resultat_net",),
    "dotations": ("dotations_amortissements",),
    "capitaux_propres": ("capitaux_propres",),
    "total_passif": ("total_passif",),
    "dettes_financieres": ("dettes_financieres",),
    "creances_clients": ("creances_clients",),
    "actif_circulant": ("stocks", "creances_clients", "autres_creances", "tresorerie_actif"),
    "passif_circulant": ("fournisseurs", "dettes_fiscales_sociales", "autres_dettes", "tresorerie_passif"),
}
KEY_FINANCIAL_FIELDS = (
    "chiffre_affaires",
    "ebe",
    "resultat_net",
    "total_actif",
    "total_passif",
    "capitaux_propres",
    "dettes_financieres",
)
