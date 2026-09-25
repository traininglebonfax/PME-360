from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial"), ("core", "0002_security")]

    operations = [EnableRLS(table) for table in ('document_category', 'document_type', 'document', 'document_version', 'document_check')]
