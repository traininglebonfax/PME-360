"""Catalogue par défaut des permissions et des rôles système (Document 1, § 6).

Synchronisé en base par la migration ``0002_rbac_catalog`` et par la commande ``sync_rbac``.
Le SUPER_ADMIN n'est pas un rôle d'organisation : c'est l'attribut ``User.is_platform_admin``.
"""

PERMISSIONS: dict[str, str] = {
    "org.configure": "Configurer l'organisation, les référentiels, règles et pondérations",
    "org.manage_users": "Gérer les utilisateurs de l'organisation",
    "programme.manage": "Gérer les programmes et les cohortes",
    "pme.view": "Consulter les PME de son périmètre",
    "pme.create": "Créer une PME",
    "pme.update": "Modifier une PME (y compris les identifiants légaux)",
    "pme.update_identity": "Modifier les coordonnées de sa PME",
    "pme.assign": "Assigner un conseiller ou un expert à une PME",
    "pme.lifecycle": "Changer le statut de cycle de vie d'une PME",
    "pme.manage_collaborators": "Inviter les collaborateurs de sa PME",
    "diagnostic.answer": "Répondre au questionnaire de diagnostic",
    "diagnostic.validate": "Valider un diagnostic et figer un score",
    "document.upload": "Déposer un document",
    "document.verify": "Vérifier ou rejeter un document",
    "ai.review": "Modifier un résultat de l'IA",
    "ai.ask": "Utiliser Ask AI",
    "plan.edit": "Créer ou modifier un plan d'action",
    "plan.propose": "Proposer des modifications de plan",
    "plan.accept": "Accepter un plan d'accompagnement (PME)",
    "task.update": "Mettre à jour le statut d'une action",
    "dashboard.portfolio": "Voir les tableaux de bord de portefeuille",
    "report.generate": "Générer des rapports",
    "audit.view": "Consulter le journal d'audit",
}

_ALL = set(PERMISSIONS)

# code → (libellé, périmètre par défaut, rôle PME ?, permissions)
ROLES: dict[str, tuple[str, str, bool, set[str]]] = {
    "ADMIN_ORG": (
        "Administrateur de l'organisation",
        "ORG",
        False,
        _ALL - {"pme.update_identity", "pme.manage_collaborators", "plan.accept", "plan.propose"},
    ),
    "RESPONSABLE_PROGRAMME": (
        "Responsable programme",
        "PROGRAMME",
        False,
        {
            "programme.manage",
            "pme.view",
            "pme.create",
            "pme.update",
            "pme.assign",
            "pme.lifecycle",
            "diagnostic.validate",
            "document.verify",
            "ai.review",
            "ai.ask",
            "plan.edit",
            "task.update",
            "dashboard.portfolio",
            "report.generate",
        },
    ),
    "CONSEILLER": (
        "Conseiller",
        "PORTEFEUILLE",
        False,
        {
            "pme.view",
            "pme.create",
            "pme.update",
            "pme.lifecycle",
            "diagnostic.answer",
            "diagnostic.validate",
            "document.upload",
            "document.verify",
            "ai.review",
            "ai.ask",
            "plan.edit",
            "task.update",
            "dashboard.portfolio",
            "report.generate",
        },
    ),
    "EXPERT": (
        "Expert",
        "PORTEFEUILLE",
        False,
        {
            "pme.view",
            "diagnostic.answer",
            "diagnostic.validate",
            "document.upload",
            "document.verify",
            "ai.review",
            "ai.ask",
            "plan.propose",
            "task.update",
            "report.generate",
        },
    ),
    "DIRIGEANT_PME": (
        "Dirigeant de PME",
        "PME",
        True,
        {
            "pme.view",
            "pme.update_identity",
            "pme.manage_collaborators",
            "diagnostic.answer",
            "document.upload",
            "plan.accept",
            "task.update",
            "report.generate",
        },
    ),
    "COLLABORATEUR_PME": (
        "Collaborateur de PME",
        "PME",
        True,
        {"pme.view", "diagnostic.answer", "document.upload", "task.update"},
    ),
    "AUDITEUR": ("Auditeur", "ORG", False, {"pme.view", "dashboard.portfolio", "audit.view"}),
}

PME_ROLE_CODES = {code for code, (_, _, is_pme, _) in ROLES.items() if is_pme}
# Rôles pouvant être assignés au suivi d'une PME (PmeAssignment).
ADVISOR_ROLE_CODES = {"CONSEILLER", "EXPERT", "RESPONSABLE_PROGRAMME", "ADMIN_ORG"}


def sync_rbac(permission_model, role_model, role_permission_model) -> None:
    """Crée ou met à jour les permissions et rôles système (idempotent, utilisable en migration)."""
    permissions = {}
    for code, label in PERMISSIONS.items():
        permission, _ = permission_model.objects.update_or_create(code=code, defaults={"label": label})
        permissions[code] = permission
    for code, (label, scope, is_pme, codes) in ROLES.items():
        role, _ = role_model.objects.update_or_create(
            organization=None,
            code=code,
            defaults={"label": label, "default_scope": scope, "is_pme_role": is_pme},
        )
        role_permission_model.objects.filter(role=role).exclude(permission__code__in=codes).delete()
        existing = set(role_permission_model.objects.filter(role=role).values_list("permission__code", flat=True))
        role_permission_model.objects.bulk_create(
            [role_permission_model(role=role, permission=permissions[c]) for c in sorted(codes - existing)]
        )
