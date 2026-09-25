"""Données de démonstration — ENTIÈREMENT FICTIVES (Document 3, § 7 ; Document 0, § 3).

Noms, numéros RCCM/NCC/CNPS et personnes sont inventés ; les identifiants portent le préfixe ``DEMO-``
et les adresses e-mail le domaine réservé ``.test`` (RFC 2606). Aucune donnée réelle.
"""

DEMO_PASSWORD = "Demo-PME360-2026!"  # noqa: S105 — compte de démonstration fictif

ORGANIZATIONS = [
    {
        "slug": "gude-pme-demo",
        "name": "GUDE-PME Côte d'Ivoire (DÉMO)",
        "type": "AGENCE_PUBLIQUE",
        "branding": {"product_name": "GUDE-PME 360", "primary_color": "#0F6B4F"},
    },
    {
        "slug": "banque-demo",
        "name": "Banque Démo Invest (DÉMO)",
        "type": "BANQUE",
        "branding": {"product_name": "PME360"},
    },
]

PROGRAMME = {
    "name": "Programme pilote 2026 (DÉMO)",
    "funder": "Bailleur fictif",
    "start_date": "2026-01-15",
    "end_date": "2027-01-14",
    "cohort": "Cohorte 1",
}

# (e-mail, nom, organisation, rôle, périmètre, référence) — la référence désigne un programme ou une PME (clé DEMO).
USERS = [
    ("superadmin@demo.test", "Admin Plateforme", None, None, None, None),
    ("admin@demo.test", "Mariam Ouattara", "gude-pme-demo", "ADMIN_ORG", "ORG", None),
    ("programme@demo.test", "Serge Kouadio", "gude-pme-demo", "RESPONSABLE_PROGRAMME", "PROGRAMME", "programme"),
    ("konan.conseiller@demo.test", "Konan Brou", "gude-pme-demo", "CONSEILLER", "PORTEFEUILLE", None),
    ("awa.conseillere@demo.test", "Awa Coulibaly", "gude-pme-demo", "CONSEILLER", "PORTEFEUILLE", None),
    ("expert@demo.test", "Dr Awa Touré", "gude-pme-demo", "EXPERT", "PORTEFEUILLE", None),
    ("auditeur@demo.test", "Paul Yao", "gude-pme-demo", "AUDITEUR", "ORG", None),
    ("aya.dirigeante@demo.test", "Aya Kouassi", "gude-pme-demo", "DIRIGEANT_PME", "PME", "BOUTIK"),
    ("moussa.collab@demo.test", "Moussa Diabaté", "gude-pme-demo", "COLLABORATEUR_PME", "PME", "BOUTIK"),
    ("banque.admin@demo.test", "Rachel N'Guessan", "banque-demo", "ADMIN_ORG", "ORG", None),
]

PMES = [
    {
        "key": "BOUTIK",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "Boutik Plus Distribution SARL",
            "trade_name": "Boutik Plus",
            "legal_form": "SARL",
            "rccm_number": "DEMO-CI-ABJ-2018-B-00001",
            "ncc": "DEMO0000001A",
            "cnps_employer_number": "DEMO100001",
            "creation_date": "2018-03-12",
            "sector": "COMMERCE",
            "region": "ABIDJAN",
            "commune": "Adjamé",
            "headcount": 8,
            "size_category": "PETITE",
            "phone": "+225 00 00 00 01",
            "email": "contact@boutik.demo.test",
        },
        "person": {"full_name": "Aya Kouassi", "role": "GERANT", "share_pct": "70", "gender": "F"},
        "advisor": "konan.conseiller@demo.test",
        "status": "ACCOMPAGNEMENT_ACTIF",
        "cohort": True,
    },
    {
        "key": "IVOIRE_METAL",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "Ivoire Métal Industrie SA",
            "legal_form": "SA",
            "rccm_number": "DEMO-CI-ABJ-2009-B-00002",
            "ncc": "DEMO0000002B",
            "cnps_employer_number": "DEMO100002",
            "creation_date": "2009-06-01",
            "sector": "INDUSTRIE",
            "region": "ABIDJAN",
            "commune": "Yopougon",
            "headcount": 85,
            "size_category": "MOYENNE",
        },
        "person": {"full_name": "Jean-Marc Aka", "role": "DG", "gender": "H"},
        "advisor": "konan.conseiller@demo.test",
        "expert": "expert@demo.test",
        "status": "DIAGNOSTIC_EN_COURS",
        "cohort": True,
    },
    {
        "key": "BATI_LAGUNE",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "Bâti Lagune BTP SARL",
            "legal_form": "SARL",
            "rccm_number": "DEMO-CI-ABJ-2014-B-00003",
            "ncc": "DEMO0000003C",
            "creation_date": "2014-09-20",
            "sector": "BTP",
            "region": "GRANDS_PONTS",
            "commune": "Dabou",
            "headcount": 45,
            "size_category": "MOYENNE",
        },
        "person": {"full_name": "Ibrahim Konaté", "role": "GERANT", "share_pct": "60", "gender": "H"},
        "advisor": "konan.conseiller@demo.test",
        "status": "ACCOMPAGNEMENT_ACTIF",
        "cohort": True,
    },
    {
        "key": "AKWABA",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "Conseil & Formation Akwaba SARLU",
            "trade_name": "Akwaba Conseil",
            "legal_form": "SARLU",
            "rccm_number": "DEMO-CI-ABJ-2021-B-00004",
            "ncc": "DEMO0000004D",
            "creation_date": "2021-02-08",
            "sector": "SERVICES",
            "region": "ABIDJAN",
            "commune": "Cocody",
            "headcount": 3,
            "size_category": "MICRO",
        },
        "person": {"full_name": "Fatou Bamba", "role": "GERANT", "share_pct": "100", "gender": "F"},
        "advisor": "awa.conseillere@demo.test",
        "status": "ONBOARDING",
        "cohort": True,
    },
    {
        "key": "DELICES",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "Délices du Bandama SAS",
            "legal_form": "SAS",
            "rccm_number": "DEMO-CI-BKE-2016-B-00005",
            "ncc": "DEMO0000005E",
            "creation_date": "2016-11-15",
            "sector": "AGROALIMENTAIRE",
            "region": "GBEKE",
            "commune": "Bouaké",
            "headcount": 22,
            "size_category": "PETITE",
        },
        "person": {"full_name": "Adjoua Kra", "role": "PRESIDENT", "share_pct": "55", "gender": "F"},
        "advisor": "konan.conseiller@demo.test",
        "status": "ACCOMPAGNEMENT_ACTIF",
        "cohort": True,
    },
    {
        "key": "NOVATECH",
        "org": "gude-pme-demo",
        "data": {
            "legal_name": "NovaTech CI SAS",
            "legal_form": "SAS",
            "rccm_number": "DEMO-CI-ABJ-2024-B-00006",
            "creation_date": "2024-04-02",
            "sector": "TECH",
            "region": "ABIDJAN",
            "commune": "Plateau",
            "headcount": 6,
            "size_category": "MICRO",
            "website": "https://novatech.demo.test",
        },
        "person": {"full_name": "Kevin Gnagne", "role": "PRESIDENT", "share_pct": "45", "gender": "H"},
        "advisor": "awa.conseillere@demo.test",
        "status": "PROSPECT",
        "cohort": False,
    },
    {
        "key": "AGRO_INVEST",
        "org": "banque-demo",
        "data": {
            "legal_name": "Agro Invest Bouaké SARL",
            "legal_form": "SARL",
            "rccm_number": "DEMO-CI-BKE-2019-B-00101",
            "sector": "AGRICULTURE",
            "region": "GBEKE",
            "commune": "Bouaké",
            "headcount": 14,
            "size_category": "PETITE",
        },
        "person": {"full_name": "Yves Kouamé", "role": "GERANT", "gender": "H"},
        "advisor": None,
        "status": "ONBOARDING",
        "cohort": False,
    },
]

# Chemin des statuts de cycle de vie à parcourir pour atteindre le statut de démonstration.
LIFECYCLE_PATH = ["ONBOARDING", "DIAGNOSTIC_EN_COURS", "ACCOMPAGNEMENT_ACTIF"]
