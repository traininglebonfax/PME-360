from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("organizations", "0001_initial"), ("core", "0002_security")]

    operations = [
        EnableRLS("organization", column="id"),
        EnableRLS("programme"),
        EnableRLS("cohort"),
    ]
