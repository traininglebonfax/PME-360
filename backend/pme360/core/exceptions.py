"""Erreurs au format RFC 9457 « Problem Details » avec un code métier stable (Document 2, § 6)."""

from django.db import connection, transaction
from rest_framework import exceptions, status

PROBLEM_BASE = "https://pme360.ci/problemes/"


class BusinessError(exceptions.APIException):
    """Erreur métier : ``code`` stable, ``detail`` lisible, ``extra`` fusionné dans le corps de la réponse."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_error"
    default_detail = "Opération impossible."

    def __init__(self, detail: str | None = None, code: str | None = None, status_code: int | None = None, **extra):
        super().__init__(detail=detail or self.default_detail, code=code or self.default_code)
        if status_code:
            self.status_code = status_code
        self.code = code or self.default_code
        self.extra = extra


class Conflict(BusinessError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Conflit avec l'état actuel de la ressource."


class NoOrganization(exceptions.PermissionDenied):
    default_code = "no_organization"
    default_detail = "Aucune organisation active : sélectionnez une organisation."


_TITLES = {
    400: "Requête invalide",
    401: "Authentification requise",
    403: "Accès refusé",
    404: "Ressource introuvable",
    405: "Méthode non autorisée",
    409: "Conflit",
    415: "Type de contenu non pris en charge",
    423: "Ressource verrouillée",
    429: "Trop de requêtes",
}


def problem_response(status_code: int, code: str, detail: str, request=None, **extra):
    """Réponse d'erreur construite sans lever d'exception : les écritures déjà faites sont CONSERVÉES
    (ex. compteur d'échecs de connexion), contrairement aux exceptions qui annulent la transaction."""
    from rest_framework.response import Response

    body = {
        "type": PROBLEM_BASE + code,
        "title": _TITLES.get(status_code, "Erreur"),
        "status": status_code,
        "code": code,
        "detail": detail,
        **extra,
    }
    if request is not None and getattr(request, "request_id", None):
        body["request_id"] = request.request_id
    return Response(body, status=status_code, content_type="application/problem+json")


def _code_of(exc) -> str:
    if isinstance(exc, BusinessError):
        return exc.code
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    codes = exc.get_codes() if hasattr(exc, "get_codes") else None
    return codes if isinstance(codes, str) else getattr(exc, "default_code", "error")


def problem_exception_handler(exc, context):
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    # Toute exception levée par une vue annule les écritures de la requête (équivalent d'ATOMIC_REQUESTS).
    if connection.in_atomic_block:
        transaction.set_rollback(True)
    code = _code_of(exc)
    body = {
        "type": PROBLEM_BASE + code,
        "title": _TITLES.get(response.status_code, "Erreur"),
        "status": response.status_code,
        "code": code,
    }
    if isinstance(exc, exceptions.ValidationError):
        body["detail"] = "Certaines données sont invalides."
        body["errors"] = response.data
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else response.data
        body["detail"] = str(detail)
    if isinstance(exc, BusinessError):
        body.update(exc.extra)
    request = context.get("request")
    if request is not None and getattr(request, "request_id", None):
        body["request_id"] = request.request_id
    response.data = body
    response.content_type = "application/problem+json"
    return response
