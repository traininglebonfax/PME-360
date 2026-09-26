"""Accès aux vues analytiques (Document 3, § 6) : rafraîchissement et lectures filtrées par tenant et périmètre."""

from __future__ import annotations

import time

from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from pme360.core.tenancy import system_context

from .sql import VIEWS

DEBOUNCE_SECONDS = 30  # plafond de fréquence des rafraîchissements déclenchés par événement
LOCK_KEY = "pme360:analytics:refresh-scheduled"


def refresh() -> None:
    """Rafraîchit toutes les vues en contexte système (toutes organisations), sans bloquer les lectures."""
    from .models import AnalyticsRefresh

    cache.delete(LOCK_KEY)
    with system_context(), connection.cursor() as cursor:
        for name in VIEWS:
            started = time.monotonic()
            cursor.execute("SELECT relispopulated FROM pg_class WHERE relname = %s", [name])
            populated = cursor.fetchone()[0]
            cursor.execute(f"REFRESH MATERIALIZED VIEW {'CONCURRENTLY ' if populated else ''}{name}")
            AnalyticsRefresh.objects.update_or_create(
                view=name,
                defaults={"refreshed_at": timezone.now(), "duration_ms": int((time.monotonic() - started) * 1000)},
            )


_last_eager_refresh = 0.0


def request_refresh() -> None:
    """À appeler après un fait qui modifie les indicateurs ; exécuté après validation de la transaction.

    Mode immédiat (développement, tests) : au plus un rafraîchissement par seconde. Sinon : une tâche différée
    par fenêtre de 30 s (plafond de fréquence).
    """
    from django.conf import settings

    def run():
        global _last_eager_refresh
        if settings.CELERY_TASK_ALWAYS_EAGER:
            if time.monotonic() - _last_eager_refresh >= 1:
                _last_eager_refresh = time.monotonic()
                refresh()
        elif cache.add(LOCK_KEY, 1, timeout=DEBOUNCE_SECONDS):
            from .tasks import refresh_views

            refresh_views.apply_async(countdown=DEBOUNCE_SECONDS)

    transaction.on_commit(run)


def freshness():
    from .models import AnalyticsRefresh

    return AnalyticsRefresh.objects.order_by("refreshed_at").values_list("refreshed_at", flat=True).first()


def _rows(sql: str, params: list) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [c.name for c in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _scope(access) -> list:
    """Identifiants des PME du périmètre (organisation, programme, portefeuille ou PME)."""
    from pme360.pmes.models import Pme

    return [str(pk) for pk in access.pme_queryset(Pme.objects.all()).values_list("pk", flat=True)]


def current_states(access) -> list[dict]:
    """État courant de chaque PME du périmètre (score LIVE ou figé, actions, alertes, secteur…)."""
    return _rows(
        """
        SELECT v.*, s.name AS sector_name, s.code AS sector_code, r.name AS region_name, r.code AS region_code
        FROM v_pme_current_state v
        LEFT JOIN sector s ON s.id = v.sector_id
        LEFT JOIN region r ON r.id = v.region_id
        WHERE v.pme_id::text = ANY(%s)
        ORDER BY v.legal_name
        """,
        [_scope(access)],
    )


def weaknesses(access, kind: str = "DIMENSION") -> list[dict]:
    """Scores par PME × dimension (ou critère), avec secteur, région et taille pour les ventilations."""
    return _rows(
        """
        SELECT w.pme_id, w.code, w.name, w.score, w.level, p.sector_id, p.region_id, p.size_category,
            s.code AS sector_code, s.name AS sector_name
        FROM v_portfolio_weaknesses w
        JOIN pme p ON p.id = w.pme_id
        LEFT JOIN sector s ON s.id = p.sector_id
        WHERE w.kind = %s AND w.pme_id::text = ANY(%s)
        """,
        [kind, _scope(access)],
    )


def trajectories(access) -> list[dict]:
    return _rows(
        """
        SELECT t.*, p.legal_name AS pme_name
        FROM v_score_trajectories t JOIN pme p ON p.id = t.pme_id
        WHERE t.pme_id::text = ANY(%s)
        """,
        [_scope(access)],
    )
