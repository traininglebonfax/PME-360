from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS

CONTENT_TABLES = ("pillar", "dimension", "criterion", "question", "metric_definition")

IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION pme360_protect_published_framework() RETURNS trigger AS $$
DECLARE
    version_id uuid;
    version_status text;
BEGIN
    IF TG_TABLE_NAME = 'framework_version' THEN
        IF TG_OP = 'DELETE' THEN
            IF OLD.status <> 'DRAFT' THEN
                RAISE EXCEPTION 'Version de référentiel % publiée : suppression interdite', OLD.version
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN OLD;
        END IF;
        -- Seule transition autorisée sur une version publiée : le retrait (statut RETIRED), sans autre changement.
        IF OLD.status = 'RETIRED' OR (OLD.status = 'PUBLISHED' AND NOT (
               NEW.status = 'RETIRED' AND NEW.version = OLD.version AND NEW.settings = OLD.settings
               AND NEW.framework_id = OLD.framework_id)) THEN
            RAISE EXCEPTION 'Version de référentiel % publiée : modification interdite', OLD.version
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        version_id := OLD.framework_version_id;
    ELSE
        version_id := NEW.framework_version_id;
    END IF;
    SELECT status INTO version_status FROM framework_version WHERE id = version_id;
    IF version_status IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION 'Contenu d''une version de référentiel publiée : % interdit sur %', TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def trigger(table: str, events: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        sql=f"CREATE TRIGGER {table}_published_guard BEFORE {events} ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION pme360_protect_published_framework();",
        reverse_sql=f"DROP TRIGGER IF EXISTS {table}_published_guard ON {table};",
    )


class Migration(migrations.Migration):
    dependencies = [("diagnostic", "0001_initial"), ("core", "0002_security")]

    operations = [
        *[
            EnableRLS(table)
            for table in (
                "framework", "framework_version", *CONTENT_TABLES, "diagnostic", "answer", "answer_history",
                "criterion_assessment",
            )
        ],
        migrations.RunSQL(IMMUTABLE_FUNCTION, "DROP FUNCTION IF EXISTS pme360_protect_published_framework();"),
        trigger("framework_version", "UPDATE OR DELETE"),
        *[trigger(table, "INSERT OR UPDATE OR DELETE") for table in CONTENT_TABLES],
        AppendOnly("answer_history"),
    ]
