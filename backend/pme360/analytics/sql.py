"""Vues matérialisées analytiques (Document 3, § 6) et leurs vues filtrées par tenant.

Une vue matérialisée ne supporte pas la Row-Level Security : chaque vue ``mv_*`` n'est donc JAMAIS lue
directement. L'application lit la vue ``v_*`` correspondante (``security_barrier``), qui applique exactement le
prédicat des politiques RLS (tenant courant, ou contexte système explicite). Le rafraîchissement se fait en
contexte système pour inclure toutes les organisations.
"""

from pme360.core.rls import BYPASS, CURRENT_ORG

# Snapshot « courant » d'une PME : le dernier snapshot figé, remplacé par le score courant (LIVE) quand celui-ci
# est calculé sur ce même diagnostic (preuves et progrès vérifiés depuis la validation).
CURRENT_SNAPSHOT = """
    SELECT DISTINCT ON (f.pme_id)
        f.organization_id, f.pme_id, f.id AS frozen_id, COALESCE(l.id, f.id) AS current_id
    FROM score_snapshot f
    LEFT JOIN score_snapshot l
        ON l.pme_id = f.pme_id AND l.kind = 'LIVE' AND l.result->>'source_diagnostic' = f.diagnostic_id::text
    WHERE f.is_frozen
    ORDER BY f.pme_id, f.reference_date DESC, f.computed_at DESC
"""

CLOSED_ACTIONS = "('TERMINE', 'ABANDONNE', 'BLOQUE')"

VIEWS = {
    "mv_pme_current_state": f"""
        WITH cur AS ({CURRENT_SNAPSHOT}),
        base AS (
            SELECT DISTINCT ON (pme_id) pme_id, global_score, reference_date
            FROM score_snapshot WHERE is_frozen AND kind = 'BASELINE'
            ORDER BY pme_id, reference_date, computed_at
        ),
        act AS (
            SELECT a.pme_id,
                count(*) AS actions_total,
                count(*) FILTER (WHERE a.status = 'TERMINE') AS actions_done,
                count(*) FILTER (WHERE a.status NOT IN {CLOSED_ACTIONS}) AS actions_open,
                count(*) FILTER (
                    WHERE a.due_date < CURRENT_DATE AND a.status NOT IN {CLOSED_ACTIONS}
                    AND ap.status IN ('VALIDE', 'EN_COURS')
                ) AS actions_overdue
            FROM action a JOIN action_plan ap ON ap.id = a.plan_id
            WHERE ap.status <> 'BROUILLON'
            GROUP BY a.pme_id
        ),
        plans AS (
            SELECT pme_id, bool_or(status IN ('VALIDE', 'EN_COURS')) AS accompanied
            FROM action_plan GROUP BY pme_id
        ),
        alerts AS (
            SELECT pme_id, count(*) AS alerts_open,
                count(*) FILTER (WHERE severity IN ('ELEVEE', 'CRITIQUE')) AS alerts_high
            FROM alert WHERE status IN ('OUVERTE', 'PRISE_EN_COMPTE') GROUP BY pme_id
        )
        SELECT p.id AS pme_id, p.organization_id, p.legal_name, p.sector_id, p.region_id, p.size_category,
            p.lifecycle_status, p.onboarding_started_at, p.last_activity_at,
            f.id AS frozen_snapshot_id, f.reference_date, f.global_score AS frozen_score,
            c.id AS current_snapshot_id, c.kind AS current_kind, c.global_score AS current_score, c.imo, c.ipe,
            c.risk_index, c.confidence, c.maturity_level, c.result->'maturity'->>'label' AS maturity_label,
            c.intervention_priority, c.quadrant,
            base.global_score AS baseline_score, base.reference_date AS baseline_date,
            COALESCE(act.actions_total, 0) AS actions_total, COALESCE(act.actions_done, 0) AS actions_done,
            COALESCE(act.actions_open, 0) AS actions_open, COALESCE(act.actions_overdue, 0) AS actions_overdue,
            COALESCE(plans.accompanied, false) AS accompanied,
            COALESCE(alerts.alerts_open, 0) AS alerts_open, COALESCE(alerts.alerts_high, 0) AS alerts_high
        FROM pme p
        LEFT JOIN cur ON cur.pme_id = p.id
        LEFT JOIN score_snapshot f ON f.id = cur.frozen_id
        LEFT JOIN score_snapshot c ON c.id = cur.current_id
        LEFT JOIN base ON base.pme_id = p.id
        LEFT JOIN act ON act.pme_id = p.id
        LEFT JOIN plans ON plans.pme_id = p.id
        LEFT JOIN alerts ON alerts.pme_id = p.id
    """,
    "mv_portfolio_weaknesses": f"""
        WITH cur AS ({CURRENT_SNAPSHOT})
        SELECT cur.organization_id, cur.pme_id, 'DIMENSION'::text AS kind, d->>'code' AS code,
            COALESCE(d->>'short_name', d->>'name') AS name, (d->>'score')::numeric AS score, NULL::int AS level
        FROM cur JOIN score_snapshot s ON s.id = cur.current_id,
            jsonb_array_elements(s.result->'dimensions') d
        WHERE d->>'score' IS NOT NULL
        UNION ALL
        SELECT cur.organization_id, cur.pme_id, 'CRITERE'::text, c->>'code', c->>'name',
            (c->>'score')::numeric, (c->>'level')::int
        FROM cur JOIN score_snapshot s ON s.id = cur.current_id,
            jsonb_array_elements(s.result->'criteria') c
        WHERE c->>'status' = 'EVALUE' AND c->>'score' IS NOT NULL
    """,
    "mv_score_trajectories": f"""
        WITH cur AS ({CURRENT_SNAPSHOT}),
        base AS (
            SELECT DISTINCT ON (pme_id) pme_id, id, global_score, reference_date
            FROM score_snapshot WHERE is_frozen AND kind = 'BASELINE'
            ORDER BY pme_id, reference_date, computed_at
        )
        SELECT p.organization_id, p.id AS pme_id,
            date_trunc('month', p.onboarding_started_at)::date AS cohort_month,
            base.id AS baseline_id, base.global_score AS baseline_score, base.reference_date AS baseline_date,
            f.id AS last_frozen_id, f.global_score AS last_score, f.reference_date AS last_date,
            c.global_score AS current_score,
            CASE WHEN base.id <> f.id THEN f.global_score - base.global_score END AS delta,
            CASE WHEN base.id <> f.id THEN round((f.reference_date - base.reference_date) / 30.44, 1) END AS months,
            c.global_score - base.global_score AS delta_current
        FROM pme p
        JOIN base ON base.pme_id = p.id
        JOIN cur ON cur.pme_id = p.id
        JOIN score_snapshot f ON f.id = cur.frozen_id
        JOIN score_snapshot c ON c.id = cur.current_id
    """,
}

UNIQUE_KEYS = {
    "mv_pme_current_state": "(pme_id)",
    "mv_portfolio_weaknesses": "(pme_id, kind, code)",
    "mv_score_trajectories": "(pme_id)",
}

TENANT_FILTER = f"{BYPASS} OR organization_id = {CURRENT_ORG}"


def create_sql() -> str:
    parts = []
    for name, query in VIEWS.items():
        view = "v_" + name.removeprefix("mv_")
        parts.append(f"CREATE MATERIALIZED VIEW {name} AS {query} WITH NO DATA;")
        parts.append(f"CREATE UNIQUE INDEX {name}_key ON {name} {UNIQUE_KEYS[name]};")
        parts.append(f"CREATE INDEX {name}_org ON {name} (organization_id);")
        parts.append(
            f"CREATE VIEW {view} WITH (security_barrier = true) AS SELECT * FROM {name} WHERE {TENANT_FILTER};"
        )
    return "\n".join(parts)


def drop_sql() -> str:
    parts = []
    for name in VIEWS:
        parts.append(f"DROP VIEW IF EXISTS v_{name.removeprefix('mv_')};")
        parts.append(f"DROP MATERIALIZED VIEW IF EXISTS {name};")
    return "\n".join(parts)
