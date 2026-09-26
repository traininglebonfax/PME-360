from django.db import migrations

from pme360.core.rls import AppendOnly, EnableRLS


class Migration(migrations.Migration):
    dependencies = [("reports", "0001_initial"), ("core", "0002_security")]

    operations = [
        EnableRLS("report"),
        # Un rapport archivé n'est plus modifiable : une correction produit une nouvelle version.
        AppendOnly("report"),
    ]
