"""Jeu d'évaluation de l'IA documentaire (Document 4, § 12) — documents ENTIÈREMENT FICTIFS, générés.

Variations : mises en page, libellés synonymes, casse, formats de montants (espaces, points, espaces insécables,
colonnes N / N-1) et de dates (JJ/MM/AAAA, « 15 mars 2025 », AAAA-MM-JJ), en-têtes et lignes parasites.
Il mesure la NON-RÉGRESSION des prompts et du moteur local ; l'exactitude réelle se mesure sur des documents
réels anonymisés avec accord, annotés par un expert, pendant le pilote.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

COMPANIES = [
    "Alpha Démo Services SARL",
    "Bêta Négoce Démo SA",
    "Gamma Agro Démo SARLU",
    "Delta Bâtiment Démo SAS",
    "Epsilon Textile Démo SARL",
    "Zêta Logistique Démo SA",
    "Êta Conseil Démo SARLU",
    "Thêta Pêche Démo SARL",
]
MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
HEADERS = [
    "RÉPUBLIQUE DE CÔTE D'IVOIRE\nUnion – Discipline – Travail",
    "DOCUMENT FICTIF — JEU D'ÉVALUATION",
    "Ministère (fictif) — Exemplaire de démonstration",
]


@dataclass
class Sample:
    document_type: str
    text: str
    expected: dict = field(default_factory=dict)


def _date(rng: random.Random, value: date) -> str:
    style = rng.randrange(3)
    if style == 0:
        return value.strftime("%d/%m/%Y")
    if style == 1:
        day = "1er" if value.day == 1 else str(value.day)
        return f"{day} {MONTHS[value.month - 1]} {value.year}"
    return value.isoformat()


def _amount(rng: random.Random, value: int) -> str:
    sep = rng.choice([" ", ".", " ", " "])
    text = f"{abs(value):,}".replace(",", sep)
    if value < 0:
        text = rng.choice([f"-{text}", f"({text})"])
    return text


def _label(rng: random.Random, *options: str) -> str:
    label = rng.choice(options)
    return rng.choice([label, label.upper(), label.capitalize()])


def _rccm(rng: random.Random) -> str:
    return f"CI-ABJ-{rng.randint(2005, 2022)}-B-{rng.randint(10000, 99999)}"


def _ncc(rng: random.Random) -> str:
    return f"{rng.randint(1000000, 9999999)}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"


def _head(rng: random.Random) -> str:
    return rng.choice(HEADERS) + "\n\n"


def rccm(rng: random.Random) -> Sample:
    name, number = rng.choice(COMPANIES), _rccm(rng)
    created = date(rng.randint(2008, 2023), rng.randint(1, 12), rng.randint(1, 28))
    title = rng.choice(
        [
            "EXTRAIT DU REGISTRE DU COMMERCE ET DU CRÉDIT MOBILIER",
            "Registre du Commerce et du Crédit Mobilier — Extrait",
        ]
    )
    text = (
        _head(rng)
        + f"{title}\nGreffe du Tribunal de Commerce d'Abidjan (fictif)\n\n"
        + f"{_label(rng, 'Numéro RCCM', 'N° RCCM')} : {number}\n"
        + f"{_label(rng, 'Dénomination sociale', 'Raison sociale')} : {name}\n"
        + f"Forme juridique : {name.split()[-1]}\n"
        + f"{_label(rng, 'Date d’immatriculation', 'Immatriculé le')} : {_date(rng, created)}\n"
        + "Siège social : Abidjan, Cocody (adresse fictive)\n"
        + "Gérant : Personne Fictive\n"
    )
    return Sample(
        "RCCM", text, {"numero_rccm": number, "raison_sociale": name, "date_immatriculation": created.isoformat()}
    )


def dfe(rng: random.Random) -> Sample:
    name, ncc = rng.choice(COMPANIES), _ncc(rng)
    issued = date(rng.randint(2015, 2025), rng.randint(1, 12), rng.randint(1, 28))
    regime = rng.choice(["Réel normal d'imposition", "Réel simplifié d'imposition", "Taxe d'État de l'entreprenant"])
    text = (
        _head(rng)
        + "DIRECTION GÉNÉRALE DES IMPÔTS (fictive)\n"
        + f"{rng.choice(['DÉCLARATION FISCALE D’EXISTENCE', 'Déclaration Fiscale d’Existence (DFE)'])}\n\n"
        + f"{_label(rng, 'Numéro de compte contribuable', 'N° de compte contribuable', 'NCC')} : {ncc}\n"
        + f"Raison sociale : {name}\n"
        + f"Régime d’imposition : {regime}\n"
        + "Centre des impôts : Centre fictif de Cocody\n"
        + f"{_label(rng, 'Date de délivrance', 'Délivrée le')} : {_date(rng, issued)}\n"
    )
    return Sample("DFE", text, {"ncc": ncc, "raison_sociale": name, "date_delivrance": issued.isoformat()})


def attest_cnps(rng: random.Random) -> Sample:
    name = rng.choice(COMPANIES)
    employer = f"{rng.randint(100000, 999999)}"
    issued = date(2026, rng.randint(1, 8), rng.randint(1, 28))
    valid = issued + timedelta(days=rng.choice([90, 180]))
    headcount = rng.randint(3, 60)
    text = (
        _head(rng)
        + "CAISSE NATIONALE DE PRÉVOYANCE SOCIALE (fictive)\n"
        + f"{rng.choice(['ATTESTATION DE SITUATION COTISANTE', 'Attestation de régularité CNPS'])}\n\n"
        + f"{_label(rng, 'Numéro employeur', 'N° employeur', 'Matricule employeur')} : {employer}\n"
        + f"Raison sociale : {name}\n"
        + f"{_label(rng, 'Effectif déclaré', 'Nombre de salariés')} : {headcount}\n"
        + "Nous certifions que l'entreprise est à jour de ses cotisations sociales.\n"
        + f"{_label(rng, 'Date de délivrance', 'Délivrée le')} : {_date(rng, issued)}\n"
        + f"{_label(rng, 'Valable jusqu’au', 'Date de validité')} : {_date(rng, valid)}\n"
    )
    return Sample(
        "ATTEST_CNPS",
        text,
        {
            "numero_employeur": employer,
            "raison_sociale": name,
            "date_delivrance": issued.isoformat(),
            "date_validite": valid.isoformat(),
            "effectif_declare": headcount,
            "mention_regularite": True,
        },
    )


def attest_fisc(rng: random.Random) -> Sample:
    name, ncc = rng.choice(COMPANIES), _ncc(rng)
    issued = date(2026, rng.randint(1, 8), rng.randint(1, 28))
    valid = issued + timedelta(days=90)
    text = (
        _head(rng)
        + "DIRECTION GÉNÉRALE DES IMPÔTS (fictive)\n"
        + "ATTESTATION DE RÉGULARITÉ FISCALE\n\n"
        + f"Le contribuable {name}, NCC : {ncc}, est à jour de ses obligations fiscales.\n"
        + f"Raison sociale : {name}\n"
        + f"{_label(rng, 'Date de délivrance', 'Délivrée le')} : {_date(rng, issued)}\n"
        + f"{_label(rng, 'Valable jusqu’au', 'Date d’expiration')} : {_date(rng, valid)}\n"
        + "Émetteur : Centre fictif des moyennes entreprises\n"
    )
    return Sample(
        "ATTEST_REGUL_FISC",
        text,
        {"raison_sociale": name, "date_delivrance": issued.isoformat(), "date_validite": valid.isoformat()},
    )


def attest_assurance(rng: random.Random) -> Sample:
    name = rng.choice(COMPANIES)
    policy = f"POL-{rng.randint(100000, 999999)}"
    start = date(2026, rng.randint(1, 6), 1)
    end = start.replace(year=2027) - timedelta(days=1)
    text = (
        _head(rng)
        + "Compagnie Fictive d'Assurances\n"
        + f"{rng.choice(['ATTESTATION D’ASSURANCE', 'Attestation d’assurance responsabilité civile'])}\n\n"
        + f"{_label(rng, 'Numéro de police', 'Police n°')} : {policy}\n"
        + f"{_label(rng, 'Assuré', 'Souscripteur')} : {name}\n"
        + "Garanties : Responsabilité civile, incendie (montants fictifs)\n"
        + f"{_label(rng, 'Date d’effet', 'Prise d’effet')} : {_date(rng, start)}\n"
        + f"{_label(rng, 'Date d’échéance', 'Date de fin')} : {_date(rng, end)}\n"
    )
    return Sample(
        "ATTEST_ASSURANCE", text, {"numero_police": policy, "raison_sociale": name, "date_fin": end.isoformat()}
    )


def etats_financiers(rng: random.Random) -> Sample:
    name = rng.choice(COMPANIES)
    year = rng.randint(2022, 2025)
    ca = rng.randrange(40_000_000, 3_000_000_000, 1000)
    ca1 = int(ca * rng.uniform(0.8, 1.15)) // 1000 * 1000
    ebe = int(ca * rng.uniform(-0.02, 0.2)) // 1000 * 1000
    rn = int(ebe * rng.uniform(-0.5, 0.7)) // 1000 * 1000
    cp = rng.randrange(5_000_000, 900_000_000, 1000)
    df = rng.randrange(0, 600_000_000, 1000)
    other = rng.randrange(10_000_000, 900_000_000, 1000)
    total = cp + df + other
    sep = rng.choice(["  ", " | ", "\t", "    "])
    rows = [
        ("Chiffre d'affaires (XB)", ca, ca1),
        (rng.choice(["Excédent brut d'exploitation (XD)", "EBE"]), ebe, int(ebe * 0.9)),
        (rng.choice(["Résultat net (XI)", "Résultat net de l'exercice"]), rn, int(rn * 0.8)),
        ("Total actif", total, int(total * 0.95)),
        (rng.choice(["Capitaux propres", "Total capitaux propres"]), cp, int(cp * 0.9)),
        (rng.choice(["Dettes financières", "Emprunts et dettes financières"]), df, int(df * 1.1)),
        ("Total passif", total, int(total * 0.95)),
    ]
    table = "\n".join(
        f"{label} {'.' * rng.randint(0, 12)}{sep}{_amount(rng, n)}{sep}{_amount(rng, n1)}" for label, n, n1 in rows
    )
    text = (
        _head(rng)
        + f"ÉTATS FINANCIERS {year} — SYSCOHADA RÉVISÉ (système normal)\n"
        + f"Raison sociale : {name}\n"
        + f"Exercice du 01/01/{year} au 31/12/{year}\n\n"
        + f"BILAN ET COMPTE DE RÉSULTAT{sep}Exercice N{sep}Exercice N-1\n"
        + table
        + "\n"
    )
    return Sample(
        "ETATS_FIN_SYSCOHADA",
        text,
        {
            "raison_sociale": name,
            "exercice_fin": f"{year}-12-31",
            "chiffre_affaires": float(ca),
            "chiffre_affaires_n1": float(ca1),
            "ebe": float(ebe),
            "resultat_net": float(rn),
            "total_actif": float(total),
            "total_passif": float(total),
            "capitaux_propres": float(cp),
            "dettes_financieres": float(df),
        },
    )


def statuts(rng: random.Random) -> Sample:
    name = rng.choice(COMPANIES)
    text = (
        _head(rng)
        + f"STATUTS\n{name}\nArticle 1 — Forme\nArticle 2 — Objet social : commerce (fictif)\nArticle 6 — Capital social : 1 000 000 FCFA réparti entre les associés.\nAssemblée générale ordinaire.\n"
    )
    return Sample("STATUTS", text)


def decl_cnps(rng: random.Random) -> Sample:
    text = (
        _head(rng)
        + f"Caisse Nationale de Prévoyance Sociale (fictive)\nDÉCLARATION DE COTISATIONS SOCIALES — {rng.choice(['1er', '2e', '3e'])} trimestre\nMasse salariale : {_amount(rng, rng.randrange(1_000_000, 90_000_000, 1000))} FCFA\nCotisations dues : {_amount(rng, rng.randrange(100_000, 9_000_000, 1000))} FCFA\n"
    )
    return Sample("DECL_CNPS_PERIODIQUE", text)


def tresorerie(rng: random.Random) -> Sample:
    text = (
        _head(rng)
        + "TABLEAU DE TRÉSORERIE (fictif)\nMois | Encaissements | Décaissements | Solde\n"
        + "\n".join(
            f"{m} | {_amount(rng, rng.randrange(1_000_000, 50_000_000, 1000))} | {_amount(rng, rng.randrange(1_000_000, 50_000_000, 1000))} | —"
            for m in MONTHS[:3]
        )
    )
    return Sample("TABLEAU_TRESORERIE", text)


def attest_bancaire(rng: random.Random) -> Sample:
    name = rng.choice(COMPANIES)
    text = (
        _head(rng)
        + f"Banque Fictive de Côte d'Ivoire\nATTESTATION BANCAIRE\nNous certifions que {name} est titulaire du compte n° 000-{rng.randint(1000, 9999)} ouvert dans nos livres. Relation bancaire depuis {rng.randint(2010, 2022)}.\n"
    )
    return Sample("ATTEST_BANCAIRE", text)


def autre(rng: random.Random) -> Sample:
    text = rng.choice(
        [
            "Compte rendu de réunion (fictif)\nOrdre du jour : organisation de la fête de fin d'année.\n",
            "Facture pro forma n° 12 (fictive)\nDésignation : fournitures de bureau.\n",
            "Lettre de motivation (fictive)\nMadame, Monsieur, je souhaite rejoindre votre équipe.\n",
        ]
    )
    return Sample("AUTRE", text)


GENERATORS = {
    "RCCM": rccm,
    "DFE": dfe,
    "ATTEST_CNPS": attest_cnps,
    "ATTEST_REGUL_FISC": attest_fisc,
    "ATTEST_ASSURANCE": attest_assurance,
    "ETATS_FIN_SYSCOHADA": etats_financiers,
    "STATUTS": statuts,
    "DECL_CNPS_PERIODIQUE": decl_cnps,
    "TABLEAU_TRESORERIE": tresorerie,
    "ATTEST_BANCAIRE": attest_bancaire,
    "AUTRE": autre,
}

NAME = "pme360-docs-fictifs-v1"


def build(per_type: int = 12, seed: int = 2026) -> list[Sample]:
    rng = random.Random(seed)
    samples = []
    for generator in GENERATORS.values():
        samples.extend(generator(rng) for _ in range(per_type))
    return samples
