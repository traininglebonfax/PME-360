from django.db import migrations

from pme360.analytics.sql import VIEWS, create_sql, drop_sql


def populate(apps, schema_editor):
    """Premier remplissage en contexte système : toutes les organisations (la RLS s'applique au propriétaire)."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        for name in VIEWS:
            cursor.execute(f"REFRESH MATERIALIZED VIEW {name}")


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_initial"),
        ("scoring", "0002_security"),
        ("plans", "0002_rls"),
        ("alerts", "0002_rls"),
        ("pmes", "0002_rls"),
    ]

    operations = [
        migrations.RunSQL(create_sql(), drop_sql()),
        migrations.RunPython(populate, migrations.RunPython.noop),
    ]
