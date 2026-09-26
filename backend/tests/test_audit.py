"""Journal d'audit : ajout seul, chaînage par hash, détection d'altération, isolation, API."""

import pytest
from django.db import InternalError, ProgrammingError, connection, transaction

from pme360.audit import services as audit
from pme360.audit.models import AuditLog
from pme360.core.tenancy import system_context, tenant_context

pytestmark = pytest.mark.django_db


def _write_entries(org, n=3):
    with tenant_context(org.id):
        return [audit.record("test.event", entity_type="test", entity_id=str(i), after={"i": i}) for i in range(n)]


def test_chain_links_entries_and_verifies(org):
    entries = _write_entries(org)
    assert entries[0].prev_hash == audit.GENESIS
    assert entries[1].prev_hash == entries[0].hash
    with tenant_context(org.id):
        result = audit.verify_chain(org.id)
    assert result.valid and result.entries_checked == 3


def test_chains_are_independent_per_organization(org, other_org):
    _write_entries(org, 2)
    other = _write_entries(other_org, 1)
    assert other[0].prev_hash == audit.GENESIS


@pytest.mark.parametrize("statement", ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"])
def test_audit_log_is_append_only(org, statement):
    _write_entries(org, 1)
    with system_context():
        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)


def test_tampering_is_detected(org):
    entries = _write_entries(org)
    with system_context(), connection.cursor() as cursor:
        # Simule une altération directe en base par un acteur disposant des droits du propriétaire.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # clés étrangères différées en attente
        cursor.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cursor.execute("UPDATE audit_log SET after = '{\"i\": 99}' WHERE id = %s", [entries[1].id])
        cursor.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    with tenant_context(org.id):
        result = audit.verify_chain(org.id)
    assert not result.valid and result.first_invalid_id == entries[1].id


def test_platform_entries_are_not_visible_to_tenants(org):
    audit.record("platform.event", organization_id=None)
    with tenant_context(org.id):
        assert not AuditLog.objects.filter(action="platform.event").exists()
    with system_context():
        assert AuditLog.objects.filter(action="platform.event", organization__isnull=True).exists()


def test_audit_api_requires_permission_and_is_scoped(org, other_org, make_user, client_for):
    _write_entries(org, 2)
    _write_entries(other_org, 5)
    assert client_for(make_user(org, "CONSEILLER"), org).get("/api/v1/audit-logs").status_code == 403
    auditor = client_for(make_user(org, "AUDITEUR"), org)
    entries = auditor.get("/api/v1/audit-logs", {"action": "test.event"}).json()
    assert len(entries) == 2
    verification = auditor.get("/api/v1/audit-logs/verify").json()
    assert verification["valid"] is True


def test_request_metadata_is_recorded(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    admin = make_user(org, "ADMIN_ORG")
    client = client_for(admin, org)
    client.patch(f"/api/v1/pmes/{pme.id}", {"commune": "Marcory"}, format="json", HTTP_X_REQUEST_ID="req-test-12345")
    with tenant_context(org.id):
        entry = AuditLog.objects.get(action="pme.updated")
    assert entry.actor_id == admin.id and entry.request_id == "req-test-12345" and entry.pme_id == pme.id


def test_verify_audit_command_checks_every_chain(org, make_user, client_for):
    from io import StringIO

    from django.core.management import call_command

    client_for(make_user(org, "ADMIN_ORG"), org).get("/api/v1/auth/me")
    out = StringIO()
    call_command("verify_audit", stdout=out)
    assert "plateforme" in out.getvalue() and "Journal d'audit intègre." in out.getvalue()
