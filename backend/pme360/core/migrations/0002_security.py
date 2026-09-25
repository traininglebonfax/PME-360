from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION pme360_forbid_mutation() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'Table % en ajout seul : % interdit', TG_TABLE_NAME, TG_OP
                        USING ERRCODE = 'insufficient_privilege';
                END;
                $$ LANGUAGE plpgsql;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS pme360_forbid_mutation();",
        ),
        EnableRLS("domain_event_outbox"),
    ]
