"""Contexte de la requête courante (identifiant, IP, agent, utilisateur) pour les logs et l'audit."""

from contextvars import ContextVar, Token

_request_context: ContextVar[dict | None] = ContextVar("pme360_request_context", default=None)


def get_request_context() -> dict | None:
    return _request_context.get()


def set_request_context(value: dict | None) -> Token:
    return _request_context.set(value)


def reset_request_context(token: Token) -> None:
    _request_context.reset(token)
