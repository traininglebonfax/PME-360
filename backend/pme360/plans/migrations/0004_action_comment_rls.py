from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS


class Migration(migrations.Migration):
    dependencies = [("plans", "0003_action_comment"), ("core", "0002_security")]

    operations = [
        EnableRLS("action_comment"),
        # Les échanges sont conservés tels quels (traçabilité de l'accompagnement).
        AppendOnly("action_comment"),
    ]
