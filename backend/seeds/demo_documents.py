"""Documents de démonstration — FICTIFS (PDF générés, contenu « DOCUMENT DE DÉMONSTRATION »).

(PME, type de document, décision du conseiller ou None pour « à vérifier », motif, jours avant expiration)
"""

DOCUMENTS = [
    # Délices du Bandama : preuves vérifiées → score courant relevé (plafond déclaratif levé).
    ("DELICES", "RCCM", "CONFORME", "", None),
    ("DELICES", "DFE", "CONFORME", "", None),
    ("DELICES", "ETATS_FIN_SYSCOHADA", "CONFORME", "", None),
    ("DELICES", "TABLEAU_TRESORERIE", "CONFORME_SOUS_RESERVE", "Le rapprochement bancaire de juillet manque.", None),
    ("DELICES", "ATTEST_ASSURANCE", "CONFORME", "", 20),  # expire bientôt → alerte de préavis
    # Boutik Plus : dépôts de la dirigeante en attente de vérification (file du conseiller). Les états financiers
    # déposés montrent un CA nettement inférieur au CA déclaré : « Incohérence détectée. Vérification requise. »
    ("BOUTIK", "RCCM", None, "", None),
    ("BOUTIK", "TABLEAU_TRESORERIE", None, "", None),
    ("BOUTIK", "ETATS_FIN_SYSCOHADA", None, "", None),
    # Ivoire Métal : justificatif refusé avec un motif en langage simple.
    (
        "IVOIRE_METAL",
        "ATTEST_CNPS",
        "NON_CONFORME",
        "L'attestation date de 2024 : merci de déposer l'attestation de situation de cette année.",
        None,
    ),
    ("IVOIRE_METAL", "RCCM", "CONFORME", "", None),
    # Bâti Lagune : attestation d'assurance expirée.
    ("BATI_LAGUNE", "RCCM", "CONFORME", "", None),
]


HEADER = ["DOCUMENT DE DÉMONSTRATION — FICTIF", "RÉPUBLIQUE DE CÔTE D'IVOIRE (exemplaire fictif)", ""]

# États financiers fictifs du dernier exercice clos (cohérents avec les déclarations, sauf Boutik Plus).
FINANCIALS = {
    "DELICES": {
        "chiffre_affaires": (186_000_000, 165_000_000),
        "ebe": (18_500_000, 11_000_000),
        "resultat_net": (8_700_000, 4_000_000),
        "dotations": (6_000_000, 5_000_000),
        "stocks": (21_000_000, 19_000_000),
        "creances": (22_000_000, 26_000_000),
        "autres_creances": (4_000_000, 3_000_000),
        "tresorerie_actif": (27_000_000, 18_000_000),
        "total": (130_000_000, 125_000_000),
        "capitaux_propres": (31_000_000, 22_000_000),
        "dettes_financieres": (34_000_000, 40_000_000),
        "fournisseurs": (30_000_000, 33_000_000),
        "dettes_fiscales_sociales": (15_000_000, 14_000_000),
        "autres_dettes": (6_000_000, 8_000_000),
        "tresorerie_passif": (4_000_000, 7_000_000),
    },
    "BOUTIK": {
        "chiffre_affaires": (310_000_000, 290_000_000),
        "ebe": (29_000_000, 24_000_000),
        "resultat_net": (11_000_000, 9_000_000),
        "dotations": (6_000_000, 5_000_000),
        "stocks": (62_000_000, 55_000_000),
        "creances": (35_000_000, 30_000_000),
        "autres_creances": (8_000_000, 6_000_000),
        "tresorerie_actif": (45_000_000, 30_000_000),
        "total": (190_000_000, 170_000_000),
        "capitaux_propres": (55_000_000, 44_000_000),
        "dettes_financieres": (40_000_000, 45_000_000),
        "fournisseurs": (60_000_000, 52_000_000),
        "dettes_fiscales_sociales": (20_000_000, 17_000_000),
        "autres_dettes": (10_000_000, 7_000_000),
        "tresorerie_passif": (5_000_000, 5_000_000),
    },
}


def _fcfa(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def content(pme: dict, type_code: str, today, expires_at, issued_at) -> list[str]:
    """Texte fictif d'un document de démonstration (lisible par l'analyse IA locale)."""
    from datetime import timedelta

    name, rccm, ncc = pme["legal_name"], pme.get("rccm_number", ""), pme.get("ncc", "")
    issued = issued_at.strftime("%d/%m/%Y")
    if type_code == "RCCM":
        return HEADER + [
            "EXTRAIT DU REGISTRE DU COMMERCE ET DU CRÉDIT MOBILIER",
            "Greffe du Tribunal de Commerce (fictif)",
            f"Numéro RCCM : {rccm}",
            f"Raison sociale : {name}",
            f"Forme juridique : {name.split()[-1]}",
            f"Date d'immatriculation : 15/03/{rccm.split('-')[3] if rccm.count('-') >= 4 else '2016'}",
            "Siège social : adresse fictive",
        ]
    if type_code == "DFE":
        return HEADER + [
            "DIRECTION GÉNÉRALE DES IMPÔTS (fictive)",
            "DÉCLARATION FISCALE D'EXISTENCE",
            f"Numéro de compte contribuable : {ncc}",
            f"Raison sociale : {name}",
            "Régime d'imposition : Réel simplifié d'imposition",
            "Centre des impôts : centre fictif",
            f"Date de délivrance : {issued}",
        ]
    if type_code == "ATTEST_ASSURANCE":
        end = expires_at or (today + timedelta(days=300))
        return HEADER + [
            "Compagnie Fictive d'Assurances",
            "ATTESTATION D'ASSURANCE",
            "Numéro de police : POL-DEMO-0001",
            f"Assuré : {name}",
            "Garanties : Responsabilité civile, incendie (montants fictifs)",
            f"Date d'effet : {issued}",
            f"Date d'échéance : {end:%d/%m/%Y}",
        ]
    if type_code == "ATTEST_CNPS":
        return HEADER + [
            "CAISSE NATIONALE DE PRÉVOYANCE SOCIALE (fictive)",
            "ATTESTATION DE SITUATION COTISANTE",
            f"Numéro employeur : {pme.get('cnps_employer_number', '')}",
            f"Raison sociale : {name}",
            f"Effectif déclaré : {pme.get('headcount', '')}",
            "Nous certifions que l'entreprise est à jour de ses cotisations sociales.",
            "Date de délivrance : 10/02/2024",
            "Valable jusqu'au : 10/05/2024",
        ]
    if type_code == "ETATS_FIN_SYSCOHADA":
        figures = FINANCIALS.get(pme["key"])
        if figures:
            year = today.year - 1
            rows = [
                ("Chiffre d'affaires (XB)", "chiffre_affaires"),
                ("Excédent brut d'exploitation (XD)", "ebe"),
                ("Dotations aux amortissements et provisions", "dotations"),
                ("Résultat net (XI)", "resultat_net"),
                ("Stocks", "stocks"),
                ("Créances clients", "creances"),
                ("Autres créances", "autres_creances"),
                ("Trésorerie actif", "tresorerie_actif"),
                ("Total actif", "total"),
                ("Capitaux propres", "capitaux_propres"),
                ("Dettes financières", "dettes_financieres"),
                ("Fournisseurs", "fournisseurs"),
                ("Dettes fiscales et sociales", "dettes_fiscales_sociales"),
                ("Autres dettes", "autres_dettes"),
                ("Trésorerie passif", "tresorerie_passif"),
                ("Total passif", "total"),
            ]
            return HEADER + [
                f"ÉTATS FINANCIERS {year} — SYSCOHADA RÉVISÉ (système normal)",
                f"Raison sociale : {name}",
                f"Exercice du 01/01/{year} au 31/12/{year}",
                "",
                "Rubrique | Exercice N | Exercice N-1",
                *(f"{label} | {_fcfa(figures[key][0])} | {_fcfa(figures[key][1])}" for label, key in rows),
            ]
    if type_code == "TABLEAU_TRESORERIE":
        return HEADER + [
            "TABLEAU DE TRÉSORERIE (fictif)",
            f"Entreprise : {name}",
            "Mois | Encaissements | Décaissements | Solde",
            "Janvier | 32 000 000 | 29 500 000 | 2 500 000",
            "Février | 30 500 000 | 31 000 000 | 2 000 000",
            "Mars | 35 000 000 | 30 000 000 | 7 000 000",
        ]
    return HEADER + [f"Document fictif ({type_code}) — {name}"]
