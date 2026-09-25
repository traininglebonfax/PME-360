"""Opérations de migration pour la Row-Level Security PostgreSQL (Document 2, § 5 ; Document 3, § 5.5)."""

from django.db import migrations

BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
CURRENT_ORG = "NULLIF(current_setting('app.current_org', true), '')::uuid"


def EnableRLS(table: str, column: str = "organization_id", allow_null_read: bool = False) -> migrations.RunSQL:  # noqa: N802
    """Active et force la RLS sur ``table``.

    ``FORCE`` applique la politique au propriétaire de la table (le rôle applicatif) ; seul un superutilisateur
    ou un rôle BYPASSRLS y échappe, et l'application n'en utilise aucun.
    ``allow_null_read`` : les lignes à ``column`` NULL (objets système partagés, par ex. rôles système) sont
    lisibles par tous les tenants mais ne peuvent être écrites qu'en contexte système.
    """
    using = f"{BYPASS} OR {column} = {CURRENT_ORG}"
    if allow_null_read:
        using += f" OR {column} IS NULL"
    check = f"{BYPASS} OR {column} = {CURRENT_ORG}"
    return migrations.RunSQL(
        sql=f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY tenant_isolation ON {table} USING ({using}) WITH CHECK ({check});
        """,
        reverse_sql=f"""
            DROP POLICY IF EXISTS tenant_isolation ON {table};
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """,
    )


def AppendOnly(table: str) -> migrations.RunSQL:  # noqa: N802
    """Interdit UPDATE et DELETE sur ``table`` (journal d'audit, revues humaines, snapshots figés)."""
    return migrations.RunSQL(
        sql=f"""
            CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION pme360_forbid_mutation();
        """,
        reverse_sql=f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};",
    )
