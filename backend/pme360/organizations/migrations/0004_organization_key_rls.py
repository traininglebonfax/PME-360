from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("organizations", "0003_organization_key"), ("core", "0002_security")]

    operations = [EnableRLS("organization_key")]
