from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial"), ("core", "0002_security")]

    operations = [
        EnableRLS("audit_log"),
        AppendOnly("audit_log"),
    ]
