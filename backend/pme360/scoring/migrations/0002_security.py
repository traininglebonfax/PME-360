from django.db import migrations

from pme360.core.rls import EnableRLS

FROZEN_FUNCTION = """
CREATE OR REPLACE FUNCTION pme360_protect_frozen_snapshot() RETURNS trigger AS $$
DECLARE
    frozen boolean;
BEGIN
    IF TG_TABLE_NAME = 'score_snapshot' THEN
        IF OLD.is_frozen THEN
            RAISE EXCEPTION 'Snapshot figé : % interdit', TG_OP USING ERRCODE = 'insufficient_privilege';
        END IF;
    ELSE
        SELECT is_frozen INTO frozen FROM score_snapshot
         WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.snapshot_id ELSE NEW.snapshot_id END;
        -- Les lignes d'un snapshot figé sont écrites dans la transaction de création, jamais modifiées ensuite.
        IF frozen AND TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Snapshot figé : % interdit sur %', TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def trigger(table: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        sql=f"CREATE TRIGGER {table}_frozen_guard BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION pme360_protect_frozen_snapshot();",
        reverse_sql=f"DROP TRIGGER IF EXISTS {table}_frozen_guard ON {table};",
    )


class Migration(migrations.Migration):
    dependencies = [("scoring", "0001_initial"), ("core", "0002_security")]

    operations = [
        *[EnableRLS(table) for table in ("score_snapshot", "score_item", "metric_value")],
        migrations.RunSQL(FROZEN_FUNCTION, "DROP FUNCTION IF EXISTS pme360_protect_frozen_snapshot();"),
        *[trigger(table) for table in ("score_snapshot", "score_item", "metric_value")],
    ]
