from django.db import migrations


def sync(apps, schema_editor):
    from pme360.accounts.catalog import sync_rbac

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    sync_rbac(apps.get_model("accounts", "Permission"), apps.get_model("accounts", "Role"),
              apps.get_model("accounts", "RolePermission"))


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_rls")]

    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
