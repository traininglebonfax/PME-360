from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("pmes", "0001_initial"), ("core", "0002_security")]

    operations = [
        EnableRLS(table)
        for table in ("sector", "legal_form", "region", "pme", "pme_person", "pme_assignment", "pme_enrollment")
    ]
