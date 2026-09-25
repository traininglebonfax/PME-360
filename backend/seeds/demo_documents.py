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
    # Boutik Plus : dépôts de la dirigeante en attente de vérification (file du conseiller).
    ("BOUTIK", "RCCM", None, "", None),
    ("BOUTIK", "TABLEAU_TRESORERIE", None, "", None),
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
