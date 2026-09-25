"""Middlewares : contexte de requête et contexte de tenant (une transaction par requête, RLS positionnée)."""

import re
import uuid

from django.db import transaction

from .request_context import get_request_context, reset_request_context, set_request_context
from .tenancy import system_context, tenant_context

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
SESSION_ORG_KEY = "org_id"


def _client_ip(request) -> str | None:
    # Derrière le reverse proxy, seule la première adresse de X-Forwarded-For est retenue (proxy de confiance).
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = set_request_context(
            {
                "request_id": request_id,
                "ip": _client_ip(request),
                "user_agent": request.headers.get("User-Agent", "")[:300],
                "user_id": None,
            }
        )
        try:
            response = self.get_response(request)
        finally:
            reset_request_context(token)
        response["X-Request-ID"] = request_id
        return response


def resolve_session_organization(request) -> uuid.UUID | None:
    """Organisation active de la session, uniquement si l'utilisateur y a une appartenance active."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    raw = request.session.get(SESSION_ORG_KEY)
    if not raw:
        return None
    from pme360.accounts.access import active_membership_q
    from pme360.accounts.models import UserMembership

    try:
        org_id = uuid.UUID(str(raw))
    except ValueError:
        return None
    with system_context():
        is_member = UserMembership.objects.filter(active_membership_q(), user=user, organization_id=org_id).exists()
    if not is_member:
        request.session.pop(SESSION_ORG_KEY, None)
        return None
    return org_id


class TenantMiddleware:
    """Ouvre la transaction de la requête et positionne le tenant (applicatif + RLS)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = resolve_session_organization(request)
        request.organization_id = org_id
        ctx = get_request_context()
        if ctx is not None and request.user.is_authenticated:
            ctx["user_id"] = str(request.user.pk)
        with tenant_context(org_id):
            response = self.get_response(request)
            if response.status_code >= 500:
                transaction.set_rollback(True)
        return response
