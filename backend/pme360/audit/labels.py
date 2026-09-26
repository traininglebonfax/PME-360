"""Libellés lisibles des actions journalisées (timeline de la fiche PME, journal d'audit)."""

ACTION_LABELS = {
    "auth.login": "Connexion",
    "auth.logout": "Déconnexion",
    "auth.login_failed": "Échec de connexion",
    "auth.mfa_enabled": "Double authentification activée",
    "auth.password_set": "Mot de passe défini",
    "auth.organization_switched": "Changement d'organisation",
    "organization.created": "Organisation créée",
    "organization.updated": "Paramètres de l'organisation modifiés",
    "programme.created": "Programme créé",
    "programme.updated": "Programme modifié",
    "cohort.created": "Cohorte créée",
    "user.invited": "Utilisateur invité",
    "user.membership_revoked": "Accès retiré",
    "pme.created": "PME créée",
    "pme.updated": "Fiche PME modifiée",
    "pme.lifecycle_changed": "Statut de la PME modifié",
    "pme.enrolled": "PME inscrite dans une cohorte",
    "pme.person_added": "Dirigeant ou contact ajouté",
    "pme.person_updated": "Dirigeant ou contact modifié",
    "pme.person_removed": "Dirigeant ou contact retiré",
    "pme.assigned": "Conseiller ou expert assigné",
    "pme.unassigned": "Fin de suivi par un conseiller ou expert",
    "document.infected": "Fichier bloqué par l'antivirus",
    "organization.key_rotated": "Clé de chiffrement des fichiers renouvelée",
    "role.created": "Rôle personnalisé créé",
    "role.updated": "Rôle personnalisé modifié",
    "role.deleted": "Rôle personnalisé supprimé",
    "audit.exported": "Journal d'audit exporté",
    "audit.sampled": "Échantillon de dossiers tiré",
    "workflow.activated": "Workflow activé",
    "framework.published": "Référentiel publié",
    "notification_template.updated": "Modèle de notification modifié",
    "document_type.created": "Type de document créé",
    "document_type.updated": "Type de document modifié",
    "obligation.created": "Obligation créée",
    "obligation.updated": "Obligation modifiée",
}


def label_for(action: str) -> str:
    return ACTION_LABELS.get(action, action)
