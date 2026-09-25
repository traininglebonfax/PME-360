"""Contrôle d'accès des vues : rôle (permission) + périmètre (Document 1, § 6).

Une vue déclare ``required_permissions`` :
- une chaîne : permission exigée pour toutes les actions ;
- un dict ``{action_ou_méthode: code | None}`` (ViewSet : ``list``, ``create``… ; APIView : ``GET``, ``POST``…).
Le périmètre (quelles PME) est appliqué par les querysets via ``AccessContext.pme_queryset``.
Les vues qui ne dépendent d'aucune organisation (``/me``, authentification) posent ``requires_organization = False``.
"""

from rest_framework.permissions import BasePermission

from .exceptions import NoOrganization


def get_access(request):
    request = getattr(request, "_request", request)  # Request DRF → HttpRequest Django
    access = getattr(request, "_pme360_access", None)
    if access is None:
        from pme360.accounts.access import build_access

        access = build_access(request.user, getattr(request, "organization_id", None))
        request._pme360_access = access
    return access


def _required_code(request, view) -> str | None:
    required = getattr(view, "required_permissions", None)
    if required is None or isinstance(required, str):
        return required
    action = getattr(view, "action", None)
    if action and action in required:
        return required[action]
    return required.get(request.method)


class HasOrganizationPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        access = get_access(request)
        if getattr(view, "requires_organization", True) and access.organization_id is None:
            raise NoOrganization()
        code = _required_code(request, view)
        return code is None or access.has(code)


class IsPlatformAdmin(BasePermission):
    """Administration de la plateforme (création des tenants) : aucun accès aux contenus métier."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_platform_admin)
