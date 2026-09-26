"""Configuration par défaut du dossier de conformité, des obligations, des alertes et des notifications.

Données copiées dans chaque organisation, puis modifiables. Sources : Document 8 (types de documents, registre
réglementaire, périodicités), Document 7, § 8 (alertes et notifications).

RÈGLE (RM-08) : les règles réglementaires sont installées avec leur statut de vérification RÉEL au 25/09/2026
(aucune n'est « vérifiée ») ; les obligations qui en dépendent sont donc INACTIVES jusqu'à ce qu'un juriste ou un
expert-comptable confirme la source et la périodicité dans l'interface.
"""

# --- Catégories et types de documents (Document 8, § 3) ----------------------------------------------------
CATEGORIES = [
    ("JURIDIQUE", "Juridique"),
    ("FISCAL", "Fiscalité"),
    ("SOCIAL", "Social (CNPS et RH)"),
    ("FINANCE", "Finance"),
    ("COMMERCIAL", "Commercial"),
    ("ORGANISATION", "Organisation"),
    ("DIGITAL", "Digital"),
    ("RISQUES", "Risques"),
    ("QUALITE", "Qualité et sectoriel"),
    ("FINANCEMENT", "Financement"),
    ("INNOVATION", "Innovation"),
    ("STRATEGIE", "Stratégie"),
    ("AUTRE", "Autres documents"),
]

# (code, catégorie, nom, période, validité (jours), fraîcheur (jours), sensible, conseil pour l'obtenir)
DOCUMENT_TYPES = [
    (
        "RCCM",
        "JURIDIQUE",
        "Extrait ou certificat RCCM",
        "AUCUNE",
        None,
        365,
        False,
        "Demandez un extrait récent au greffe du tribunal de commerce (ou au guichet unique).",
    ),
    (
        "STATUTS",
        "JURIDIQUE",
        "Statuts à jour",
        "AUCUNE",
        None,
        None,
        False,
        "Déposez la dernière version signée, avec les modifications éventuelles.",
    ),
    (
        "DFE",
        "JURIDIQUE",
        "Déclaration fiscale d'existence (NCC)",
        "AUCUNE",
        None,
        None,
        False,
        "Document délivré par l'administration fiscale lors de l'immatriculation fiscale.",
    ),
    ("PV_AG", "JURIDIQUE", "Procès-verbaux d'assemblée ou décisions", "EXERCICE", None, 550, False, ""),
    ("DELEGATIONS", "JURIDIQUE", "Délégations de pouvoirs et de signature", "AUCUNE", None, None, False, ""),
    (
        "CONTRATS_CLES",
        "JURIDIQUE",
        "Contrats structurants (bail, clients, fournisseurs)",
        "AUCUNE",
        None,
        None,
        False,
        "",
    ),
    (
        "DECL_FISCALE_PERIODIQUE",
        "FISCAL",
        "Déclaration fiscale périodique (preuve de dépôt)",
        "MOIS",
        None,
        None,
        False,
        "",
    ),
    ("PREUVE_PAIEMENT_FISC", "FISCAL", "Quittance ou preuve de paiement fiscal", "MOIS", None, None, False, ""),
    (
        "ATTEST_REGUL_FISC",
        "FISCAL",
        "Attestation de régularité fiscale",
        "AUCUNE",
        None,
        None,
        False,
        "Délivrée par votre centre des impôts. Sa durée de validité est saisie à la vérification (règle REG-FISC-03 à vérifier).",
    ),
    ("IMMAT_CNPS", "SOCIAL", "Attestation d'immatriculation employeur CNPS", "AUCUNE", None, None, False, ""),
    (
        "DECL_CNPS_PERIODIQUE",
        "SOCIAL",
        "Déclaration ou justificatif CNPS de la période",
        "TRIMESTRE",
        None,
        None,
        False,
        "Téléchargez le justificatif depuis votre espace employeur e-CNPS.",
    ),
    ("PREUVE_PAIEMENT_CNPS", "SOCIAL", "Preuve de paiement des cotisations CNPS", "TRIMESTRE", None, None, False, ""),
    ("ATTEST_CNPS", "SOCIAL", "Attestation de situation ou de régularité CNPS", "AUCUNE", None, None, False, ""),
    (
        "CONTRAT_TRAVAIL_ECHANTILLON",
        "SOCIAL",
        "Échantillon de contrats de travail (données masquées)",
        "AUCUNE",
        None,
        None,
        True,
        "Masquez les données personnelles (salaire, adresse, numéro d'identité) avant le dépôt.",
    ),
    (
        "BULLETIN_PAIE_ECHANTILLON",
        "SOCIAL",
        "Échantillon de bulletins de paie (données masquées)",
        "MOIS",
        None,
        365,
        True,
        "Masquez les données personnelles avant le dépôt.",
    ),
    (
        "ETATS_FIN_SYSCOHADA",
        "FINANCE",
        "États financiers annuels (bilan, compte de résultat, notes)",
        "EXERCICE",
        None,
        550,
        False,
        "Déposez la liasse complète du dernier exercice clos, telle que déposée à l'administration.",
    ),
    ("SITUATION_INTERMEDIAIRE", "FINANCE", "Situation comptable intermédiaire", "SEMESTRE", None, 240, False, ""),
    (
        "TABLEAU_TRESORERIE",
        "FINANCE",
        "Tableau de trésorerie (3 derniers mois)",
        "TRIMESTRE",
        None,
        120,
        False,
        "Un modèle Excel est disponible auprès de votre conseiller.",
    ),
    ("TABLEAU_BORD_FIN", "FINANCE", "Tableau de bord financier (reporting)", "TRIMESTRE", None, 120, False, ""),
    ("BUDGET", "FINANCE", "Budget annuel", "ANNEE", None, 400, False, ""),
    ("PREVISIONNEL", "FINANCE", "Prévisionnel financier", "AUCUNE", None, 730, False, ""),
    ("PLAN_STRATEGIQUE", "STRATEGIE", "Plan stratégique", "AUCUNE", None, 730, False, ""),
    ("BUSINESS_MODEL", "STRATEGIE", "Modèle économique (business model)", "AUCUNE", None, 730, False, ""),
    ("BUSINESS_PLAN", "STRATEGIE", "Plan d'affaires (business plan)", "AUCUNE", None, 730, False, ""),
    ("FEUILLE_ROUTE", "STRATEGIE", "Feuille de route", "AUCUNE", None, 730, False, ""),
    (
        "EXPORT_FICHIER_CLIENTS",
        "COMMERCIAL",
        "Portefeuille clients agrégé (sans données personnelles)",
        "ANNEE",
        None,
        400,
        False,
        "",
    ),
    (
        "TABLEAU_SUIVI_COMMERCIAL",
        "COMMERCIAL",
        "Tableau de suivi commercial (pipeline)",
        "TRIMESTRE",
        None,
        120,
        False,
        "",
    ),
    ("GRILLE_TARIFAIRE", "COMMERCIAL", "Grille tarifaire et calcul des prix", "AUCUNE", None, 730, False, ""),
    ("PLAN_MARKETING", "COMMERCIAL", "Plan marketing et communication", "ANNEE", None, 400, False, ""),
    ("REGISTRE_RECLAMATIONS", "COMMERCIAL", "Registre des réclamations clients", "AUCUNE", None, 365, False, ""),
    ("ORGANIGRAMME", "ORGANISATION", "Organigramme", "AUCUNE", None, 365, False, ""),
    ("FICHES_POSTE", "ORGANISATION", "Fiches de poste des postes clés", "AUCUNE", None, 730, False, ""),
    ("PLAN_FORMATION", "ORGANISATION", "Plan de formation", "ANNEE", None, 400, False, ""),
    ("MANUEL_PROC", "ORGANISATION", "Manuel de procédures administratives", "AUCUNE", None, 730, False, ""),
    ("CARTO_PROCESSUS", "ORGANISATION", "Cartographie des processus", "AUCUNE", None, 730, False, ""),
    ("PROC_ACHATS", "ORGANISATION", "Procédure d'achats", "AUCUNE", None, 730, False, ""),
    ("ETAT_STOCKS", "ORGANISATION", "État des stocks ou fiche d'inventaire", "TRIMESTRE", None, 180, False, ""),
    ("PLAN_MAINTENANCE", "ORGANISATION", "Plan de maintenance des équipements", "AUCUNE", None, 730, False, ""),
    ("INVENTAIRE_SI", "DIGITAL", "Inventaire des équipements et logiciels", "AUCUNE", None, 365, False, ""),
    ("POLITIQUE_SI", "DIGITAL", "Politique informatique et de sécurité", "AUCUNE", None, 730, False, ""),
    ("POLITIQUE_SAUVEGARDE", "DIGITAL", "Politique de sauvegarde et preuve de test", "AUCUNE", None, 365, False, ""),
    ("REGISTRE_RISQUES", "RISQUES", "Registre ou cartographie des risques", "AUCUNE", None, 365, False, ""),
    ("PROC_CONTROLE_INTERNE", "RISQUES", "Procédure de contrôle interne", "AUCUNE", None, 730, False, ""),
    ("PROC_CAISSE", "RISQUES", "Procédure de caisse et rapprochements", "AUCUNE", None, 365, False, ""),
    ("PCA", "RISQUES", "Plan de continuité d'activité", "AUCUNE", None, 730, False, ""),
    (
        "ATTEST_ASSURANCE",
        "RISQUES",
        "Attestations d'assurance",
        "AUCUNE",
        None,
        None,
        False,
        "La date de fin de validité figurant sur l'attestation est saisie à la vérification.",
    ),
    ("CERTIFICAT", "QUALITE", "Certification qualité (ISO ou autre)", "AUCUNE", None, None, False, ""),
    ("MANUEL_QUALITE", "QUALITE", "Manuel ou procédures qualité", "AUCUNE", None, 730, False, ""),
    ("AGREMENT_SANITAIRE", "QUALITE", "Autorisation ou agrément sanitaire", "AUCUNE", None, None, False, ""),
    ("AGREMENT_BTP", "QUALITE", "Agrément ou qualification professionnelle BTP", "AUCUNE", None, None, False, ""),
    ("PLAN_FINANCEMENT", "FINANCEMENT", "Plan de financement", "AUCUNE", None, 365, False, ""),
    ("ATTEST_BANCAIRE", "FINANCEMENT", "Attestation bancaire", "AUCUNE", None, 180, False, ""),
    (
        "CERTIFICAT_PI",
        "INNOVATION",
        "Certificat de dépôt de marque ou de brevet (OAPI)",
        "AUCUNE",
        None,
        None,
        False,
        "",
    ),
    ("AUTRE", "AUTRE", "Autre document", "AUCUNE", None, None, False, ""),
]

# --- Registre réglementaire (Document 8, § 2) — statuts RÉELS au 25/09/2026 ---------------------------------
REGULATORY_RULES = [
    dict(
        code="REG-CNPS-01",
        authority="CNPS",
        status="PRE_VERIFIE",
        title="Périodicité des déclarations et versements CNPS",
        content="Mensuelle pour les employeurs de 20 salariés ou plus ; trimestrielle en dessous. Versement dans les "
        "15 premiers jours suivant le mois ou le trimestre échu. À CONFIRMER : lecture intégrale et version en vigueur.",
        sources=[
            {
                "title": "CNPS — Recouvrement",
                "url": "https://www.cnps.ci/wp-content/uploads/2021/04/RECOUVREMENT-R.pdf",
            },
            {"title": "CNPS — Espace employeur", "url": "https://www.cnps.ci/employeur/"},
        ],
    ),
    dict(
        code="REG-CNPS-02",
        authority="CNPS",
        status="HORS_PERIMETRE",
        title="Taux de cotisation CNPS",
        content="Non intégrés au MVP : la plateforme ne calcule pas les cotisations.",
        sources=[
            {"title": "CNPS — Recouvrement", "url": "https://www.cnps.ci/wp-content/uploads/2020/08/Recouvrement.pdf"}
        ],
    ),
    dict(
        code="REG-PME-01",
        authority="Ministère des PME",
        status="A_VERIFIER",
        title="Définition et catégories de PME",
        content="Loi n° 2014-140 du 24 mars 2014 : PME = moins de 200 salariés et CA HT ≤ 1 milliard FCFA ; "
        "stratification micro / petite / moyenne à confirmer sur le texte officiel.",
        sources=[
            {
                "title": "Loi n° 2014-140",
                "url": "https://pme.gouv.ci/static/docs/documentspublics/loi_n_2014_140_poltique_ntle_pme.pdf",
            },
            {"title": "FAQ du ministère", "url": "https://pme.gouv.ci/views/faq-pme/"},
        ],
    ),
    dict(
        code="REG-FISC-01",
        authority="DGI",
        status="A_VERIFIER",
        title="Régimes d'imposition et seuils de chiffre d'affaires",
        content="Seuils issus de sources secondaires, à vérifier sur le Code général des impôts et la dernière annexe fiscale.",
        sources=[
            {
                "title": "DGI — Le système fiscal ivoirien",
                "url": "https://www.dgi.gouv.ci/assets/documents/LE%20SYSTEME%20FISCAL%20IVOIRIEN.pdf",
            }
        ],
    ),
    dict(
        code="REG-FISC-02",
        authority="DGI",
        status="A_VERIFIER",
        title="Obligations déclaratives fiscales périodiques et échéances",
        content="Non déterminé : aucune échéance fiscale n'est générée tant que cette règle n'est pas vérifiée.",
        sources=[{"title": "DGI", "url": "https://www.dgi.gouv.ci/"}],
    ),
    dict(
        code="REG-FISC-03",
        authority="DGI",
        status="A_VERIFIER",
        title="Attestation de régularité fiscale : délivrance et durée de validité",
        content="Non déterminé : la date de validité est saisie à la vérification du document.",
        sources=[{"title": "DGI", "url": "https://www.dgi.gouv.ci/"}],
    ),
    dict(
        code="REG-FISC-04",
        authority="DGI",
        status="A_VERIFIER",
        title="Dépôt des états financiers annuels (délais)",
        content="Non déterminé.",
        sources=[{"title": "DGI", "url": "https://www.dgi.gouv.ci/"}],
    ),
    dict(
        code="REG-FISC-05",
        authority="DGI",
        status="A_VERIFIER",
        title="Facturation normalisée",
        content="Un dispositif de factures normalisées existe ; périmètre et calendrier à vérifier.",
        sources=[{"title": "CCI Côte d'Ivoire", "url": "https://www.cci.ci/factures-normalisees/"}],
    ),
    dict(
        code="REG-COMPTA-01",
        authority="OHADA",
        status="A_VERIFIER",
        title="Référentiel comptable SYSCOHADA et SMT",
        content="SYSCOHADA révisé ; système minimal de trésorerie pour les très petites entités (seuils à vérifier).",
        sources=[{"title": "OHADA", "url": "https://www.ohada.org/"}],
    ),
    dict(
        code="REG-DATA-01",
        authority="ARTCI",
        status="PRE_VERIFIE",
        title="Protection des données à caractère personnel",
        content="Loi n° 2013-450 du 19 juin 2013. À confirmer : autorité compétente actuelle, formalités, transferts internationaux.",
        sources=[
            {"title": "Loi n° 2013-450", "url": "https://www.artci.ci/images/stories/pdf/lois/loi_2013_450.pdf"},
            {"title": "Autorité de protection", "url": "https://www.autoritedeprotection.ci/lois/"},
        ],
    ),
    dict(
        code="REG-PI-01",
        authority="OAPI",
        status="A_VERIFIER",
        title="Propriété intellectuelle (marques, brevets)",
        content="Dépôt auprès de l'OAPI (Accord de Bangui).",
        sources=[{"title": "OAPI", "url": "https://oapi.int/"}],
    ),
]

HAS_EMPLOYEES = {">=": [{"var": "headcount"}, 1]}
IN_SUPPORT = {"in": [{"var": "lifecycle_status"}, ["DIAGNOSTIC_EN_COURS", "ACCOMPAGNEMENT_ACTIF"]]}
REMINDERS = [-30, -15, -7, 0, 7, 15, 30]

# --- Modèles d'obligations (Document 8, § 3 et § 4) ------------------------------------------------------------
OBLIGATIONS = [
    dict(
        code="OBL-CNPS-PERIODIQUE",
        name="Justificatif CNPS de la période",
        nature="PROGRAMME",
        document_type="DECL_CNPS_PERIODIQUE",
        rule="REG-CNPS-01",
        frequency="TRIMESTRIELLE",
        frequency_rule={"if": [{">=": [{"var": "headcount"}, 20]}, "MENSUELLE", "TRIMESTRIELLE"]},
        due_days=30,
        applicability=HAS_EMPLOYEES,
        critical=True,
        active=False,
        description="Transmettre à votre organisation d'accompagnement le justificatif CNPS de chaque période (15 jours légaux + 15 jours de "
        "transmission). Activation après vérification de REG-CNPS-01.",
    ),
    dict(
        code="OBL-FISC-PERIODIQUE",
        name="Preuve de dépôt des déclarations fiscales",
        nature="PROGRAMME",
        document_type="DECL_FISCALE_PERIODIQUE",
        rule="REG-FISC-02",
        frequency="MENSUELLE",
        due_days=30,
        critical=True,
        active=False,
        description="Activation après vérification de REG-FISC-02 (périodicité par régime).",
    ),
    dict(
        code="OBL-ETATS-FIN",
        name="États financiers annuels",
        nature="PROGRAMME",
        document_type="ETATS_FIN_SYSCOHADA",
        rule="REG-FISC-04",
        frequency="ANNUELLE",
        due_days=180,
        critical=True,
        active=False,
        description="Échéance programme : 30 jours après la date légale de dépôt, une fois REG-FISC-04 vérifiée.",
    ),
    dict(
        code="OBL-RCCM",
        name="Extrait RCCM à jour",
        nature="PROGRAMME",
        document_type="RCCM",
        frequency="PONCTUELLE",
        due_days=30,
        active=True,
        description="Une fois à l'entrée dans le programme, puis à chaque modification.",
    ),
    dict(
        code="OBL-DFE",
        name="Déclaration fiscale d'existence",
        nature="PROGRAMME",
        document_type="DFE",
        frequency="PONCTUELLE",
        due_days=30,
        active=True,
    ),
    dict(
        code="OBL-ATTEST-CNPS",
        name="Attestation de situation CNPS",
        nature="PROGRAMME",
        document_type="ATTEST_CNPS",
        frequency="ANNUELLE",
        due_days=60,
        applicability=HAS_EMPLOYEES,
        active=True,
    ),
    dict(
        code="OBL-ATTEST-FISC",
        name="Attestation de régularité fiscale",
        nature="PROGRAMME",
        document_type="ATTEST_REGUL_FISC",
        frequency="ANNUELLE",
        due_days=60,
        active=True,
    ),
    dict(
        code="OBL-ASSURANCE",
        name="Attestations d'assurance",
        nature="BONNE_PRATIQUE",
        document_type="ATTEST_ASSURANCE",
        frequency="ANNUELLE",
        due_days=60,
        active=True,
    ),
    dict(
        code="OBL-TRESORERIE",
        name="Tableau de trésorerie",
        nature="BONNE_PRATIQUE",
        document_type="TABLEAU_TRESORERIE",
        frequency="TRIMESTRIELLE",
        due_days=20,
        applicability=IN_SUPPORT,
        active=True,
        description="Transmis chaque trimestre pendant l'accompagnement.",
    ),
    dict(
        code="OBL-SUIVI-COMMERCIAL",
        name="Tableau de suivi commercial",
        nature="BONNE_PRATIQUE",
        document_type="TABLEAU_SUIVI_COMMERCIAL",
        frequency="TRIMESTRIELLE",
        due_days=20,
        applicability=IN_SUPPORT,
        active=True,
    ),
    dict(
        code="OBL-SITUATION",
        name="Situation comptable intermédiaire",
        nature="PROGRAMME",
        document_type="SITUATION_INTERMEDIAIRE",
        frequency="SEMESTRIELLE",
        due_days=45,
        applicability={"in": [{"var": "size_category"}, ["PETITE", "MOYENNE"]]},
        active=True,
    ),
]

# --- Règles d'alerte (Document 7, § 8.2) ----------------------------------------------------------------------
ALERT_RULES = [
    dict(
        code="ALR-DOC-EXPIRE",
        kind="DOC_EXPIRE",
        name="Document expiré",
        severity="ELEVEE",
        params={"notice_days": 30},
        recipients=["PME", "CONSEILLER"],
    ),
    dict(
        code="ALR-DOC-MANQUANT",
        kind="DOC_MANQUANT",
        name="Document manquant",
        severity="MOYENNE",
        params={"days_after_request": 30},
        recipients=["PME", "CONSEILLER"],
    ),
    dict(
        code="ALR-ECHEANCE-PROCHE",
        kind="ECHEANCE_PROCHE",
        name="Échéance proche",
        severity="INFO",
        params={"days": 7},
        recipients=["PME"],
    ),
    dict(
        code="ALR-OBLIGATION-DEPASSEE",
        kind="OBLIGATION_DEPASSEE",
        name="Obligation dépassée",
        severity="ELEVEE",
        params={"days_overdue": 15, "critical_days_overdue": 30},
        recipients=["PME", "CONSEILLER", "RESPONSABLE_PROGRAMME"],
    ),
    dict(
        code="ALR-INCOHERENCE",
        kind="INCOHERENCE",
        name="Incohérence détectée",
        severity="MOYENNE",
        recipients=["CONSEILLER", "EXPERT"],
    ),
    dict(
        code="ALR-ANOMALIE-DOC",
        kind="ANOMALIE_DOC",
        name="Anomalie documentaire",
        severity="ELEVEE",
        recipients=["CONSEILLER"],
    ),
    dict(
        code="ALR-SCORE-BAISSE",
        kind="SCORE_BAISSE",
        name="Score en baisse",
        severity="MOYENNE",
        params={"global_drop": 5, "dimension_drop": 10},
        recipients=["CONSEILLER"],
    ),
    dict(
        code="ALR-RISQUE-ELEVE",
        kind="RISQUE_ELEVE",
        name="Risque élevé",
        severity="ELEVEE",
        params={"risk_index": 70},
        recipients=["CONSEILLER", "RESPONSABLE_PROGRAMME"],
    ),
    dict(
        code="ALR-ACTION-RETARD",
        kind="ACTION_RETARD",
        name="Action en retard",
        severity="MOYENNE",
        params={"late_days": 15, "critical_priority": 70},
        recipients=["PME", "CONSEILLER"],
    ),
    dict(
        code="ALR-STAGNATION",
        kind="STAGNATION",
        name="Absence de progression",
        severity="MOYENNE",
        params={"months": 6, "min_gain": 2},
        recipients=["CONSEILLER", "RESPONSABLE_PROGRAMME"],
    ),
    dict(
        code="ALR-CA-BAISSE",
        kind="CA_BAISSE",
        name="Baisse importante du chiffre d'affaires",
        severity="ELEVEE",
        params={"growth_max": -0.20},
        recipients=["CONSEILLER"],
    ),
    dict(
        code="ALR-DEGRADATION-FIN",
        kind="DEGRADATION_FIN",
        name="Dégradation financière",
        severity="ELEVEE",
        recipients=["CONSEILLER", "EXPERT"],
        available_in_phase=6,
    ),
]

# --- Modèles de notifications (Document 7, § 8.3) : variables entre accolades --------------------------------
NOTIFICATION_TEMPLATES = {
    "AI_BUDGET_WARNING": (
        "IA : 80 % du budget mensuel de jetons atteint",
        "La consommation d'IA externe atteint {usage} jetons sur {quota} ce mois-ci. Au-delà du quota, "
        "les analyses passent automatiquement par le moteur local.",
    ),
    "PREDIAGNOSTIC_READY": (
        "Pré-diagnostic prêt : {pme}",
        "Les propositions de l'IA pour le diagnostic de {pme} sont prêtes ({count} critères). "
        "Elles restent à valider, modifier ou écarter lors de la revue.",
    ),
    "DOCUMENT_TO_VERIFY": (
        "Document à vérifier : {pme}",
        "{document} a été déposé pour {pme} et attend votre vérification.",
    ),
    "DOCUMENT_DECISION": ("Votre document a été examiné", "{document} : {decision}. {reason}"),
    "DOCUMENT_REJECTED_SECURITY": (
        "Fichier refusé pour raison de sécurité",
        "Le fichier « {filename} » déposé pour {pme} a été bloqué par l'antivirus et n'a pas été enregistré.",
    ),
    "DEADLINE_REMINDER": (
        "Rappel : {document} à transmettre",
        "{document} ({period}) est à transmettre avant le {due_date}.",
    ),
    "DEADLINE_DUE_TODAY": ("Échéance aujourd'hui : {document}", "{document} ({period}) est à transmettre aujourd'hui."),
    "DEADLINE_OVERDUE": (
        "Retard : {document}",
        "{document} ({period}) devait être transmis le {due_date}. Merci de le déposer dès que possible.",
    ),
    "DEADLINE_ESCALATION": (
        "Obligation critique en retard : {pme}",
        "{document} ({period}) n'a pas été transmis ({days} jours de retard).",
    ),
    "ALERT_RAISED": ("Alerte {severity} : {title}", "{message}"),
    "PLAN_TO_ACCEPT": (
        "Votre plan d'accompagnement est prêt",
        "Votre conseiller a préparé un plan de {actions} actions pour {pme}. Consultez-le et acceptez-le pour démarrer.",
    ),
    "PLAN_ACCEPTED": ("Plan accepté : {pme}", "La direction de {pme} a accepté le plan d'accompagnement."),
    "ACTION_DOCUMENT_REQUESTED": (
        "Document attendu : {action}",
        "Pour l'action « {action} », merci de déposer : {documents}. Un modèle et des instructions sont disponibles.",
    ),
    "ACTION_DELIVERABLE_REJECTED": (
        "Document à reprendre : {action}",
        "Le document déposé pour « {action} » doit être repris : {reason}",
    ),
    "ACTION_UNBLOCKED": ("Nouvelle action disponible", "L'action « {action} » peut maintenant démarrer."),
    "ACTION_COMMENTED": (
        "Nouveau message : {action}",
        "{author} a écrit au sujet de « {action} » : {excerpt}",
    ),
    "REPORT_READY": (
        "Rapport de diagnostic disponible : {pme}",
        "La version {version} du rapport de diagnostic de {pme} est disponible au téléchargement.",
    ),
}
# Messages toujours envoyés, quelles que soient les préférences (Document 7, § 8.3).
MANDATORY_EVENTS = {"DEADLINE_ESCALATION", "DOCUMENT_REJECTED_SECURITY"}


def install(organization) -> None:
    """Installation idempotente dans ``organization`` (à exécuter dans son contexte de tenant)."""
    from pme360.alerts.models import AlertRule
    from pme360.documents.models import DocumentCategory, DocumentType
    from pme360.notifications.models import NotificationTemplate

    from .models import ObligationTemplate, RegulatoryRule

    categories = {}
    for order, (code, name) in enumerate(CATEGORIES):
        categories[code], _ = DocumentCategory.objects.get_or_create(
            organization=organization, code=code, defaults={"name": name, "order": order}
        )
    types = {}
    for order, (code, category, name, period, validity, freshness, sensitive, guidance) in enumerate(DOCUMENT_TYPES):
        types[code], _ = DocumentType.objects.get_or_create(
            organization=organization,
            code=code,
            defaults={
                "category": categories[category],
                "name": name,
                "period_kind": period,
                "validity_days": validity,
                "freshness_days": freshness,
                "sensitive": sensitive,
                "guidance": guidance,
                "order": order,
            },
        )
    rules = {}
    for item in REGULATORY_RULES:
        rules[item["code"]], _ = RegulatoryRule.objects.get_or_create(
            organization=organization,
            code=item["code"],
            defaults={
                "title": item["title"],
                "content": item["content"],
                "authority": item["authority"],
                "sources": item["sources"],
                "status": item["status"],
            },
        )
    for item in OBLIGATIONS:
        ObligationTemplate.objects.get_or_create(
            organization=organization,
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item.get("description", ""),
                "nature": item["nature"],
                "document_type": types[item["document_type"]],
                "regulatory_rule": rules.get(item.get("rule")),
                "frequency": item["frequency"],
                "frequency_rule": item.get("frequency_rule"),
                "due_days_after_period_end": item["due_days"],
                "applicability": item.get("applicability"),
                "reminder_offsets": REMINDERS,
                "is_critical": item.get("critical", False),
                "is_active": item["active"],
            },
        )
    for item in ALERT_RULES:
        AlertRule.objects.get_or_create(
            organization=organization,
            code=item["code"],
            defaults={
                "kind": item["kind"],
                "name": item["name"],
                "severity": item["severity"],
                "params": item.get("params", {}),
                "recipients": item["recipients"],
                "is_active": item.get("available_in_phase") is None,
                "available_in_phase": item.get("available_in_phase"),
            },
        )
    for event, (subject, body) in NOTIFICATION_TEMPLATES.items():
        NotificationTemplate.objects.get_or_create(
            organization=organization, event_code=event, defaults={"subject": subject, "body": body}
        )
