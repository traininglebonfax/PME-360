from django.db import migrations

from pme360.core.rls import EnableRLS


class Migration(migrations.Migration):
    dependencies = [("compliance", "0002_initial"), ("core", "0002_security")]

    operations = [EnableRLS(table) for table in ('regulatory_rule', 'obligation_template', 'pme_obligation', 'deadline', 'deadline_reminder')]
