from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS

TABLES = (
    "ai_analysis",
    "document_extraction",
    "financial_statement",
    "knowledge_chunk",
    "ai_conversation",
    "ai_conversation_message",
    "criterion_suggestion",
)


def activate_incoherence_rule(apps, schema_editor):
    """La règle « Incohérence détectée » était annoncée pour la phase 4 : elle devient active."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        cursor.execute(
            "UPDATE alert_rule SET available_in_phase = NULL WHERE kind = 'INCOHERENCE' AND available_in_phase = 4"
        )


class Migration(migrations.Migration):
    dependencies = [("ai", "0001_initial"), ("core", "0002_security"), ("alerts", "0002_rls")]

    operations = [
        *(EnableRLS(table) for table in TABLES),
        # Traçabilité IA (Document 4, § 11) : journal en ajout seul.
        AppendOnly("ai_analysis"),
        migrations.RunPython(activate_incoherence_rule, migrations.RunPython.noop),
    ]
