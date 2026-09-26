"""Rôles personnalisés de l'organisation (Document 1, § 6 ; V1).

Une organisation compose ses propres rôles à partir des permissions atomiques du catalogue. Garde-fous :
- les rôles système (organisation NULL) ne se modifient pas ;
- un rôle personnalisé est un rôle d'équipe (le portail PME garde ses deux rôles système) ;
- on ne peut accorder que des permissions que l'on détient soi-même (pas d'élévation de privilèges) ;
- un rôle attribué à des personnes ne peut pas être supprimé ; ses changements valent immédiatement pour elles.
Tout est tracé au journal d'audit (avant / après).
"""

from __future__ import annotations

import re

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError

from .access import active_membership_q
from .catalog import PERMISSIONS, ROLES
from .models import Permission, Role, RolePermission, Scope, UserMembership

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,39}$")
# Permissions propres au portail PME : jamais dans un rôle d'équipe personnalisé.
PME_ONLY_PERMISSIONS = {"pme.update_identity", "pme.manage_collaborators", "plan.accept"}
STAFF_SCOPES = {Scope.ORG, Scope.PROGRAMME, Scope.PORTEFEUILLE}

# Regroupement pour l'affichage de la matrice des permissions.
PERMISSION_GROUPS = [
    ("Organisation", ["org.configure", "org.manage_users", "programme.manage"]),
    ("PME", ["pme.view", "pme.create", "pme.update", "pme.assign", "pme.lifecycle"]),
    ("Diagnostic et documents", ["diagnostic.answer", "diagnostic.validate", "document.upload", "document.verify"]),
    ("Intelligence artificielle", ["ai.review", "ai.ask"]),
    ("Accompagnement", ["plan.edit", "plan.propose", "task.update"]),
    ("Pilotage et contrôle", ["dashboard.portfolio", "report.generate", "audit.view"]),
]


def _require(access) -> None:
    if not access.has("org.manage_users") or access.is_pme_user:
        raise PermissionDenied()


def members_count(role: Role) -> int:
    return UserMembership.objects.filter(active_membership_q(), role=role).count()


def _permissions(access, codes) -> list[str]:
    codes = sorted(set(codes or []))
    unknown = set(codes) - set(PERMISSIONS)
    if unknown:
        raise ValidationError({"permissions": [f"Permissions inconnues : {', '.join(sorted(unknown))}."]})
    pme_only = set(codes) & PME_ONLY_PERMISSIONS
    if pme_only:
        raise ValidationError(
            {"permissions": [f"Réservé au portail PME, pas à un rôle d'équipe : {', '.join(sorted(pme_only))}."]}
        )
    beyond = set(codes) - set(access.permissions)
    if beyond and not access.user.is_platform_admin:
        raise PermissionDenied(
            "Vous ne pouvez pas accorder des permissions que vous ne détenez pas : "
            + ", ".join(PERMISSIONS[c] for c in sorted(beyond))
            + "."
        )
    if not codes:
        raise ValidationError({"permissions": ["Choisissez au moins une permission."]})
    return codes


def _set_permissions(role: Role, codes: list[str]) -> None:
    RolePermission.objects.filter(role=role).exclude(permission__code__in=codes).delete()
    existing = set(RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
    permissions = {p.code: p for p in Permission.objects.filter(code__in=codes)}
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=permissions[c]) for c in codes if c not in existing]
    )


def _snapshot(role: Role) -> dict:
    return {
        "code": role.code,
        "label": role.label,
        "default_scope": role.default_scope,
        "permissions": sorted(role.permissions.values_list("code", flat=True)),
    }


def _editable(role: Role) -> None:
    if role.organization_id is None:
        raise BusinessError(
            "Un rôle système ne se modifie pas : créez un rôle personnalisé à partir de celui-ci.", code="system_role"
        )


@transaction.atomic
def create_role(access, data: dict) -> Role:
    _require(access)
    code = (data.get("code") or "").strip().upper()
    if not CODE_PATTERN.match(code):
        raise ValidationError(
            {"code": ["Code en majuscules (lettres, chiffres, _), 3 à 40 caractères, commençant par une lettre."]}
        )
    if code in ROLES or Role.objects.filter(code=code).exists():
        raise ValidationError({"code": ["Ce code existe déjà."]})
    label = (data.get("label") or "").strip()
    if not label:
        raise ValidationError({"label": ["Libellé obligatoire."]})
    scope = data.get("default_scope") or Scope.PORTEFEUILLE
    if scope not in STAFF_SCOPES:
        raise ValidationError(
            {"default_scope": ["Périmètre d'équipe attendu : organisation, programme ou portefeuille."]}
        )
    codes = _permissions(access, data.get("permissions"))
    role = Role.objects.create(
        organization_id=access.organization_id, code=code, label=label[:200], default_scope=scope, is_pme_role=False
    )
    _set_permissions(role, codes)
    audit.record("role.created", instance=role, after=_snapshot(role))
    return role


@transaction.atomic
def update_role(access, role: Role, data: dict) -> Role:
    _require(access)
    _editable(role)
    before = _snapshot(role)
    if "code" in data and data["code"] != role.code:
        raise ValidationError({"code": ["Le code d'un rôle ne se modifie pas."]})
    if "label" in data:
        label = (data["label"] or "").strip()
        if not label:
            raise ValidationError({"label": ["Libellé obligatoire."]})
        role.label = label[:200]
    if "default_scope" in data:
        if data["default_scope"] not in STAFF_SCOPES:
            raise ValidationError({"default_scope": ["Périmètre d'équipe attendu."]})
        role.default_scope = data["default_scope"]
    role.save()
    if "permissions" in data:
        codes = _permissions(access, data["permissions"])
        # Retirer à soi-même la gestion des utilisateurs via son propre rôle bloquerait l'organisation.
        own = UserMembership.objects.filter(active_membership_q(), role=role, user=access.user).exists()
        if own and "org.manage_users" not in codes:
            raise BusinessError(
                "Vous détenez ce rôle : retirer « Gérer les utilisateurs » vous ferait perdre l'accès à cet écran.",
                code="self_lockout",
            )
        _set_permissions(role, codes)
    audit.record("role.updated", instance=role, before=before, after=_snapshot(role))
    return role


def delete_role(access, role: Role) -> None:
    _require(access)
    _editable(role)
    if UserMembership.objects.filter(role=role).exists():
        raise BusinessError(
            f"Ce rôle est ou a été attribué ({members_count(role)} personne(s) actuellement) : "
            "retirez-le d'abord ; il reste visible dans l'historique des accès.",
            code="role_in_use",
        )
    audit.record("role.deleted", instance=role, before=_snapshot(role))
    role.delete()
