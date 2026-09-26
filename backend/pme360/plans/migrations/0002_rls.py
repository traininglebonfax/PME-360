from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS

TABLES = (
    "deliverable_template",
    "support_offer",
    "recommendation_rule",
    "recommendation",
    "action_plan",
    "action",
    "action_dependency",
    "deliverable",
    "action_transition",
    "criterion_progress",
)


def activate_action_rule(apps, schema_editor):
    """La règle « Action en retard » était annoncée pour la phase 5 : elle devient active."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        cursor.execute(
            "UPDATE alert_rule SET available_in_phase = NULL, is_active = TRUE, "
            "params = '{\"late_days\": 15, \"critical_priority\": 70}'::jsonb, "
            "recipients = '[\"PME\", \"CONSEILLER\"]'::jsonb "
            "WHERE kind = 'ACTION_RETARD' AND available_in_phase = 5"
        )


class Migration(migrations.Migration):
    dependencies = [("plans", "0001_initial"), ("core", "0002_security"), ("alerts", "0002_rls")]

    operations = [
        *(EnableRLS(table) for table in TABLES),
        # Journal des transitions d'actions : ajout seul (Document 3, § 3.7).
        AppendOnly("action_transition"),
        migrations.RunPython(activate_action_rule, migrations.RunPython.noop),
    ]
