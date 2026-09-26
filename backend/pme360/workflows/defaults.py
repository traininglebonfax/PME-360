"""Workflow d'action par défaut (Document 7, § 2.2) et garde-fous de configuration."""

STAFF, PME = "STAFF", "PME"

ACTION_STATES = {
    "BLOQUE": {"label": "Bloquée", "pme_label": "Disponible plus tard"},
    "NON_COMMENCE": {"label": "Non commencée", "pme_label": "À démarrer"},
    "EN_COURS": {"label": "En cours", "pme_label": "En cours"},
    "DOCUMENT_DEMANDE": {"label": "Document demandé", "pme_label": "Document à déposer"},
    "DOCUMENT_RECU": {"label": "Document reçu", "pme_label": "Document reçu"},
    "A_VERIFIER": {"label": "À vérifier", "pme_label": "En vérification"},
    "CONFORME": {"label": "Conforme", "pme_label": "Validée"},
    "NON_CONFORME": {"label": "Non conforme", "pme_label": "Document à reprendre"},
    "TERMINE": {"label": "Terminée", "pme_label": "Terminée"},
    "EN_ATTENTE_PME": {"label": "En attente PME", "pme_label": "En attente de votre part"},
    "EN_ATTENTE_GUDE": {"label": "En attente GUDE-PME", "pme_label": "En attente de votre conseiller"},
    "ABANDONNE": {"label": "Abandonnée", "pme_label": "Abandonnée"},
}
TERMINAL = {"TERMINE", "ABANDONNE"}
# États atteints seulement par le moteur (dépendances, dépôt, analyse, vérification des livrables).
SYSTEM_ONLY_TARGETS = {"BLOQUE", "DOCUMENT_RECU", "A_VERIFIER", "CONFORME", "NON_CONFORME"}
# La PME ne peut que démarrer / reprendre ou signaler qu'elle attend GUDE-PME : jamais terminer ni abandonner.
PME_TARGETS = {"EN_COURS", "EN_ATTENTE_GUDE"}
ABANDON = "ABANDONNE"

BUTTONS = {
    "EN_COURS": ("Démarrer / reprendre", "Je démarre cette action"),
    "DOCUMENT_DEMANDE": ("Demander le document", ""),
    "EN_ATTENTE_PME": ("En attente de la PME", ""),
    "EN_ATTENTE_GUDE": ("En attente de GUDE-PME", "J'attends mon conseiller"),
    "TERMINE": ("Terminer l'action", ""),
    "ABANDONNE": ("Abandonner", ""),
    "NON_COMMENCE": ("Remettre à démarrer", ""),
}

_MANUAL = {
    "NON_COMMENCE": ["EN_COURS", "EN_ATTENTE_PME", "EN_ATTENTE_GUDE", "ABANDONNE"],
    "EN_COURS": ["DOCUMENT_DEMANDE", "EN_ATTENTE_PME", "EN_ATTENTE_GUDE", "ABANDONNE", "TERMINE"],
    "DOCUMENT_DEMANDE": ["EN_COURS", "EN_ATTENTE_PME", "EN_ATTENTE_GUDE", "ABANDONNE"],
    "NON_CONFORME": ["EN_COURS", "DOCUMENT_DEMANDE", "ABANDONNE"],
    "CONFORME": ["TERMINE", "ABANDONNE"],
    "EN_ATTENTE_PME": ["EN_COURS", "ABANDONNE"],
    "EN_ATTENTE_GUDE": ["EN_COURS", "ABANDONNE"],
    "BLOQUE": ["ABANDONNE"],
    "DOCUMENT_RECU": ["ABANDONNE"],
    "A_VERIFIER": ["ABANDONNE"],
}


def transition(source: str, target: str) -> dict:
    button, pme_button = BUTTONS.get(target, (target, ""))
    return {
        "from": source,
        "to": target,
        "actors": [STAFF, PME] if target in PME_TARGETS else [STAFF],
        "reason_required": target == ABANDON,
        "button": button,
        "pme_button": pme_button,
    }


ACTION_TRANSITIONS = [transition(source, target) for source, targets in _MANUAL.items() for target in targets]

# Transitions réalisées par le moteur : affichées dans l'éditeur, non modifiables.
SYSTEM_TRANSITIONS = [
    {"from": "NON_COMMENCE", "to": "BLOQUE", "trigger": "Une dépendance non terminée est ajoutée"},
    {"from": "BLOQUE", "to": "NON_COMMENCE", "trigger": "Toutes les dépendances sont terminées (PME notifiée)"},
    {"from": "DOCUMENT_DEMANDE", "to": "DOCUMENT_RECU", "trigger": "La PME dépose un livrable"},
    {"from": "DOCUMENT_RECU", "to": "A_VERIFIER", "trigger": "Analyse du document terminée"},
    {"from": "A_VERIFIER", "to": "CONFORME", "trigger": "Le conseiller valide tous les livrables"},
    {"from": "A_VERIFIER", "to": "NON_CONFORME", "trigger": "Le conseiller refuse un livrable (motif pour la PME)"},
    {"from": "A_VERIFIER", "to": "DOCUMENT_DEMANDE", "trigger": "Livrable conforme, d'autres documents attendus"},
    {"from": "CONFORME", "to": "TERMINE", "trigger": "Automatique si tous les livrables sont conformes"},
]
