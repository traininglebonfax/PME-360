"""Journaux techniques structurés (structlog) : JSON en production, lisibles en développement."""

import logging

import structlog
from django.conf import settings

from .request_context import get_request_context


def _add_request_context(_, __, event_dict):
    ctx = get_request_context()
    if ctx:
        event_dict.setdefault("request_id", ctx.get("request_id"))
        if ctx.get("user_id"):
            event_dict.setdefault("user_id", ctx["user_id"])
    return event_dict


def configure_logging() -> None:
    renderer = structlog.processors.JSONRenderer() if settings.LOG_JSON else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_request_context,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
