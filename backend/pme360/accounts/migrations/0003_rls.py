from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_initial"), ("core", "0002_security")]

    operations = [
        EnableRLS("role", allow_null_read=True),
        EnableRLS("user_membership"),
    ]
