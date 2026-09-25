"""Isolation inter-tenants au niveau PostgreSQL (Document 2, § 5 et § 11 : tests OBLIGATOIRES)."""

import pytest
from django.apps import apps
from django.db import IntegrityError, ProgrammingError, connection, transaction

from pme360.accounts.models import Role
from pme360.audit.models import AuditLog
from pme360.core.models import TenantModel
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme

pytestmark = pytest.mark.django_db


def _rls_tables() -> set[str]:
    tables = {m._meta.db_table for m in apps.get_models() if issubclass(m, TenantModel)}
    return tables | {Organization._meta.db_table, Role._meta.db_table, AuditLog._meta.db_table}


def test_application_role_cannot_bypass_rls():
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        is_superuser, bypass = cursor.fetchone()
    assert not is_superuser and not bypass, "Le rôle applicatif ne doit être ni superutilisateur ni BYPASSRLS."


@pytest.mark.parametrize("table", sorted(_rls_tables()))
def test_every_tenant_table_has_forced_rls_and_policy(table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", [table])
        enabled, forced = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM pg_policies WHERE tablename = %s", [table])
        policies = cursor.fetchone()[0]
    assert enabled and forced, f"RLS non activée/forcée sur {table}"
    assert policies >= 1, f"Aucune politique RLS sur {table}"


def _raw_count(table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — nom de table interne
        return cursor.fetchone()[0]


def test_raw_sql_only_sees_current_tenant(org, other_org, make_pme):
    make_pme(org)
    make_pme(org)
    make_pme(other_org)
    with tenant_context(org.id):
        assert _raw_count("pme") == 2  # SQL brut, sans aucun filtre applicatif
        assert _raw_count("organization") == 1
        assert Pme.objects.count() == 2
    with tenant_context(other_org.id):
        assert _raw_count("pme") == 1
    with tenant_context(None):
        assert _raw_count("pme") == 0
        assert Pme.objects.count() == 0
    with system_context():
        assert _raw_count("pme") == 3


def test_manager_filter_and_rls_are_independent(org, other_org, make_pme):
    """Même en contournant le manager (``_base_manager``), la RLS bloque les lignes d'un autre tenant."""
    foreign = make_pme(other_org)
    with tenant_context(org.id):
        assert not Pme._base_manager.filter(pk=foreign.pk).exists()


def test_cannot_write_row_for_another_tenant(org, other_org):
    with tenant_context(org.id):
        with pytest.raises((ProgrammingError, IntegrityError)), transaction.atomic():
            Pme(legal_name="Intrusion", organization_id=other_org.id).save()


def test_cannot_update_another_tenant_rows(org, other_org, make_pme):
    foreign = make_pme(other_org, legal_name="Cible SARL")
    with tenant_context(org.id):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE pme SET legal_name = 'Piratée' WHERE id = %s", [foreign.pk])
            assert cursor.rowcount == 0
    with tenant_context(other_org.id):
        assert Pme.objects.get(pk=foreign.pk).legal_name == "Cible SARL"


def test_system_roles_visible_to_all_tenants_but_custom_roles_isolated(org, other_org):
    with tenant_context(org.id):
        Role.objects.create(organization=org, code="ROLE_PERSO", label="Rôle perso", default_scope="ORG")
        assert Role.objects.filter(code="CONSEILLER").exists()
        assert Role.objects.filter(code="ROLE_PERSO").exists()
    with tenant_context(other_org.id):
        assert Role.objects.filter(code="CONSEILLER").exists()
        assert not Role.objects.filter(code="ROLE_PERSO").exists()
        assert _raw_count("role") == Role.objects.filter(organization__isnull=True).count()


def test_tenant_context_restores_previous_tenant(org, other_org, make_pme):
    make_pme(org)
    with tenant_context(org.id):
        with tenant_context(other_org.id):
            assert _raw_count("pme") == 0
        assert _raw_count("pme") == 1
