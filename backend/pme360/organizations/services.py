"""Création et configuration des organisations (tenants)."""

from __future__ import annotations

from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from pme360.audit import services as audit
from pme360.core.tenancy import system_context, tenant_context

from .models import DEFAULT_SETTINGS, Organization

# Paramètres de tenant modifiables et leurs bornes (validation de la configuration sans code).
SETTING_RULES = {
    "inactivity_days": (int, 7, 365),
    "duplicate_name_similarity": (float, 0.3, 0.95),
}


def validate_settings(values: dict) -> dict:
    cleaned = {}
    errors = {}
    for key, value in values.items():
        rule = SETTING_RULES.get(key)
        if rule is None:
            errors[key] = ["Paramètre inconnu."]
            continue
        kind, minimum, maximum = rule
        try:
            number = kind(value)
        except (TypeError, ValueError):
            errors[key] = ["Valeur invalide."]
            continue
        if not minimum <= number <= maximum:
            errors[key] = [f"Doit être compris entre {minimum} et {maximum}."]
            continue
        cleaned[key] = number
    if errors:
        raise ValidationError(errors)
    return cleaned


def effective_settings(organization: Organization) -> dict:
    return {**DEFAULT_SETTINGS, **organization.settings}


def create_organization(
    *, name: str, slug: str, type: str, admin_email: str, admin_full_name: str, created_by
) -> Organization:
    """Crée un tenant, installe ses nomenclatures par défaut et invite son premier administrateur."""
    from pme360.accounts.access import AccessContext
    from pme360.accounts.services import invite_user
    from pme360.pmes.defaults import install_defaults

    with system_context():
        try:
            organization = Organization.objects.create(name=name, slug=slug, type=type, created_by=created_by)
        except IntegrityError as exc:
            raise ValidationError({"slug": ["Cet identifiant est déjà utilisé."]}) from exc
        audit.record(
            "organization.created",
            instance=organization,
            actor=created_by,
            organization_id=None,
            after={"name": name, "slug": slug, "type": type},
        )
    with tenant_context(organization.id):
        install_defaults(organization)
        bootstrap_access = AccessContext(
            user=created_by, organization_id=organization.id, permissions=frozenset({"org.manage_users"})
        )
        invite_user(bootstrap_access, email=admin_email, full_name=admin_full_name, role_code="ADMIN_ORG")
    return organization
