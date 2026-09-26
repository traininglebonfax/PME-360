"""Chiffrement enveloppe des fichiers, clé propre à chaque organisation (V1)."""

from io import StringIO

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

from pme360.audit.models import AuditLog
from pme360.core.tenancy import system_context, tenant_context
from pme360.documents.models import DocumentVersion
from pme360.documents.storage import get_storage
from pme360.organizations import keys
from pme360.organizations.models import OrganizationKey

from . import files
from .test_documents import upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_key_cache():
    keys.clear_cache()
    yield
    keys.clear_cache()


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, make_pme, advisor):
    return make_pme(org, advisor=advisor, headcount=12)


def _store(client, pme, content, run_pipeline=None):
    response = upload(client, pme, "rccm.pdf", content)
    assert response.status_code == 201, response.content
    document_id = response.json()["id"]
    with system_context():
        version = DocumentVersion.objects.get(document_id=document_id, version_no=1)
    return document_id, version.storage_key


def _download(client, document_id):
    link = client.get(f"/api/v1/documents/{document_id}/versions/1/download-url").json()
    return client.get(link["url"]).content


def test_files_are_encrypted_at_rest_and_transparently_readable(org, pme, advisor, client_for):
    client = client_for(advisor, org)
    content = files.pdf()
    document_id, path = _store(client, pme, content)
    raw = get_storage().get_raw(path)
    assert keys.is_encrypted(raw) and keys.key_version(raw) == 1
    assert b"%PDF" not in raw and content not in raw
    assert _download(client, document_id) == content
    with system_context():
        key = OrganizationKey.objects.get(organization=org)
    assert key.status == "ACTIVE" and len(key.wrapped_key) > 60  # clé enveloppée, jamais en clair


def test_ciphertext_is_bound_to_its_path_and_organization(org, other_org, pme, advisor, client_for, make_pme):
    client = client_for(advisor, org)
    _, path = _store(client, pme, files.pdf())
    raw = get_storage().get_raw(path)
    # Même fichier recopié sous une autre PME de la même organisation : refusé (données associées = chemin).
    moved = path.replace(str(pme.id), "00000000-0000-0000-0000-000000000000")
    with pytest.raises(keys.StorageKeyError):
        keys.decrypt(moved, raw)
    # Chemin d'une autre organisation lu depuis le contexte de la première : refusé avant tout déchiffrement.
    foreign = path.replace(str(org.id), str(other_org.id))
    with tenant_context(org.id), pytest.raises(keys.StorageKeyError):
        keys.decrypt(foreign, raw)
    # Altération d'un octet : refusée.
    tampered = raw[:-1] + bytes([raw[-1] ^ 1])
    with pytest.raises(keys.StorageKeyError):
        keys.decrypt(path, tampered)
    # Chaque organisation a sa propre clé.
    other = make_pme(other_org)
    other_client = client_for(_admin(other_org), other_org)
    _, other_path = _store(other_client, other, files.pdf())
    with system_context():
        assert OrganizationKey.objects.filter(organization=org).get().wrapped_key != (
            OrganizationKey.objects.filter(organization=other_org).get().wrapped_key
        )
    assert keys.key_version(get_storage().get_raw(other_path)) == 1


def _admin(organization):
    from pme360.accounts.models import Role, User, UserMembership

    user = User.objects.create_user(email=f"admin-{organization.slug}@test.test", full_name="Admin")
    with tenant_context(organization.id):
        UserMembership.objects.create(
            user=user, role=Role.objects.get(organization=None, code="ADMIN_ORG"), scope="ORG"
        )
    return user


def test_rotation_keeps_old_files_readable_and_reencrypt_command(org, pme, advisor, make_user, client_for):
    client = client_for(advisor, org)
    old_content = files.pdf()
    old_id, old_path = _store(client, pme, old_content)

    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    rotated = admin.post("/api/v1/organization/encryption")
    assert rotated.status_code == 200 and rotated.json()["active_version"] == 2
    assert [v["status"] for v in rotated.json()["versions"]] == ["ACTIVE", "RETIRED"]
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="organization.key_rotated").exists()

    assert _download(client, old_id) == old_content  # ancienne version de clé toujours utilisable
    new_content = files.pdf(text_pages=2)
    _, new_path = _store(client, pme, new_content)
    assert keys.key_version(get_storage().get_raw(new_path)) == 2
    assert keys.key_version(get_storage().get_raw(old_path)) == 1

    out = StringIO()
    call_command("encrypt_storage", "--reencrypt", stdout=out)
    assert "1 rechiffrés" in out.getvalue()
    assert keys.key_version(get_storage().get_raw(old_path)) == 2
    assert _download(client, old_id) == old_content

    auditor = client_for(make_user(org, "AUDITEUR"), org)
    status = auditor.get("/api/v1/organization/encryption").json()
    assert status["enabled"] is True and status["can_rotate"] is False and "wrapped_key" not in str(status)
    assert auditor.post("/api/v1/organization/encryption").status_code == 403
    assert client.get("/api/v1/organization/encryption").status_code == 403  # conseiller


def test_legacy_plaintext_files_are_read_then_encrypted_by_command(org, pme, advisor, client_for):
    client = client_for(advisor, org)
    content = files.pdf()
    document_id, path = _store(client, pme, content)
    get_storage().put_raw(path, content)  # simule un fichier déposé avant la V1 (en clair)
    assert _download(client, document_id) == content
    out = StringIO()
    call_command("encrypt_storage", stdout=out)
    assert "1 chiffrés" in out.getvalue()
    assert keys.is_encrypted(get_storage().get_raw(path))
    assert _download(client, document_id) == content


def test_master_key_rotation_rewraps_without_touching_files(org, pme, advisor, client_for, settings):
    client = client_for(advisor, org)
    content = files.pdf()
    document_id, _ = _store(client, pme, content)
    old_master = settings.STORAGE_MASTER_KEYS[0]
    new_master = Fernet.generate_key().decode()
    settings.STORAGE_MASTER_KEYS = [new_master, old_master]
    assert keys.rewrap_all() == 1
    settings.STORAGE_MASTER_KEYS = [new_master]  # l'ancienne clé maîtresse peut être retirée
    keys.clear_cache()
    assert _download(client, document_id) == content
    with system_context():
        assert OrganizationKey.objects.get(organization=org).master_key_id == keys.master_key_id(new_master)
