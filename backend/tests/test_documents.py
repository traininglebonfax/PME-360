"""Dépôt sécurisé, pipeline, vérification humaine, téléchargement signé et preuves (phase 3)."""

from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from pme360.alerts.models import Alert
from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context
from pme360.documents.models import Document, DocumentVersion
from pme360.notifications.models import Notification

from . import files

pytestmark = pytest.mark.django_db


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, make_pme, advisor):
    return make_pme(org, advisor=advisor, headcount=12)


@pytest.fixture
def leader(org, pme, make_user):
    return make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)


def upload(client, pme, name, content, document_type="RCCM", **extra):
    payload = {"file": SimpleUploadedFile(name, content), "document_type": document_type, **extra}
    return client.post(f"/api/v1/pmes/{pme.id}/documents", payload, format="multipart")


class Processed:
    """Réponse du dépôt, complétée par l'état du document APRÈS le traitement asynchrone."""

    def __init__(self, response, client):
        self.status_code = response.status_code
        self.content = response.content
        self._body = response.json()
        if response.status_code == 201:
            self._body = client.get(f"/api/v1/documents/{self._body['id']}").json()

    def json(self):
        return self._body


@pytest.fixture
def run_pipeline(django_capture_on_commit_callbacks):
    """Exécute les tâches différées « après commit » (pipeline asynchrone, Celery en mode immédiat)."""

    def runner(call, client=None):
        with django_capture_on_commit_callbacks(execute=True):
            response = call()
        return Processed(response, client) if client else response

    return runner


def test_pme_leader_uploads_and_document_waits_for_human_verification(
    org, pme, leader, advisor, client_for, run_pipeline
):
    client = client_for(leader, org)
    response = run_pipeline(lambda: upload(client, pme, "rccm.pdf", files.pdf()), client)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "A_VERIFIER" and body["verification_status"] == "VERIF_HUMAINE_REQUISE"
    assert body["uploaded_via"] == "PORTAIL_PME" and body["conformity_status"] == "NON_EVALUE"  # dépôt ≠ conformité
    version = body["versions"][0]
    assert (
        version["av_status"] == "SAIN" and version["text_status"] == "OCR_REQUIS"
    )  # PDF sans texte → lecture visuelle
    assert {c["check_code"] for c in version["checks"]} >= {"DOUBLON", "QUALITE_LECTURE", "DATE_VALIDITE"}
    with tenant_context(org.id):
        stored = DocumentVersion.objects.get(pk=version["id"]).storage_key
        assert stored.startswith(f"org/{org.id}/pme/{pme.id}/") and "rccm" not in stored  # nom régénéré
        assert Notification.objects.filter(user=advisor, event_code="DOCUMENT_TO_VERIFY").exists()
    assert (Path(settings.PME360_LOCAL_STORAGE_ROOT) / stored).exists()
    assert any("Document à vérifier" in m.subject for m in mail.outbox)


def test_eicar_is_blocked_before_any_storage(org, pme, leader, advisor, client_for):
    client = client_for(leader, org)
    response = upload(client, pme, "releve.csv", files.eicar_csv(), document_type="AUTRE")
    assert response.status_code == 422 and response.json()["code"] == "infected_file"
    with tenant_context(org.id):
        document = Document.objects.get(pk=response.json()["document_id"])
        version = document.versions.get()
        assert document.integrity_status == "REJETE_SECURITE" and document.status_display == "REJETE_SECURITE"
        assert version.av_status == "INFECTE" and version.storage_key == "" and "Eicar" in version.av_signature
        alert = Alert.objects.get(pme=pme, rule__code="ALR-ANOMALIE-DOC")
        assert alert.severity == "CRITIQUE"
        assert AuditLog.objects.filter(action="document.infected").exists()
        assert Notification.objects.filter(user=advisor, event_code="DOCUMENT_REJECTED_SECURITY").exists()
    root = Path(settings.PME360_LOCAL_STORAGE_ROOT) / f"org/{org.id}/pme/{pme.id}/{document.id}"
    assert not root.exists()  # jamais écrit sur disque


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("statuts.pdf", files.png(), "mime_mismatch"),
        ("statuts.docm", files.office("docx"), "macro_refused"),
        ("budget.xlsx", files.office("xlsx", macro=True), "macro_refused"),
        ("rccm.pdf", files.pdf(javascript=True), "active_pdf_refused"),
        ("outil.exe", b"MZ\x90\x00", "extension_refused"),
    ],
)
def test_dangerous_or_invalid_files_are_refused(org, pme, advisor, client_for, name, content, code):
    response = upload(client_for(advisor, org), pme, name, content, document_type="STATUTS")
    assert response.status_code == 400 and response.json()["code"] == code, response.content
    with tenant_context(org.id):
        assert not Document.objects.filter(pme=pme).exists()
        assert AuditLog.objects.filter(action="document.refused").exists()


def test_size_limit(org, pme, advisor, client_for, settings):
    settings.PME360_MAX_UPLOAD_BYTES = 1024
    response = upload(client_for(advisor, org), pme, "gros.pdf", files.pdf() + b"%" * 2048)
    assert response.status_code == 400 and response.json()["code"] == "file_too_large"


def test_antivirus_unavailable_fails_closed(org, pme, advisor, client_for, monkeypatch):
    from pme360.documents import antivirus

    def unavailable(self, content):
        raise antivirus.ScannerUnavailable("hors ligne")

    monkeypatch.setattr(antivirus.EicarScanner, "scan", unavailable)
    response = upload(client_for(advisor, org), pme, "rccm.pdf", files.pdf())
    assert response.status_code == 503 and response.json()["code"] == "antivirus_unavailable"
    with tenant_context(org.id):
        assert not Document.objects.filter(pme=pme).exists()


def test_office_document_text_and_duplicates(org, pme, advisor, client_for, run_pipeline):
    client = client_for(advisor, org)
    first = run_pipeline(
        lambda: upload(client, pme, "organigramme.docx", files.office("docx"), document_type="ORGANIGRAMME"), client
    )
    assert first.json()["versions"][0]["text_status"] == "TEXTE_NATIF"
    second = run_pipeline(
        lambda: upload(client, pme, "copie.docx", files.office("docx"), document_type="MANUEL_PROC"), client
    )
    checks = {c["check_code"]: c["result"] for c in second.json()["versions"][0]["checks"]}
    assert second.json()["versions"][0]["duplicate_of"] and checks["DOUBLON"] == "ALERTE"  # signalé, non bloquant


def test_new_version_resets_verification(org, pme, advisor, client_for, run_pipeline):
    client = client_for(advisor, org)
    document_id = run_pipeline(lambda: upload(client, pme, "rccm.pdf", files.pdf())).json()["id"]
    client.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")
    again = run_pipeline(lambda: upload(client, pme, "rccm-2.pdf", files.pdf(2), document_id=document_id), client)
    body = again.json()
    assert body["current_version_no"] == 2 and body["conformity_status"] == "NON_EVALUE"
    assert [v["version_no"] for v in body["versions"]] == [2, 1]


def test_verification_rules_and_feedback(org, pme, advisor, leader, client_for, run_pipeline):
    client = client_for(advisor, org)
    document_id = run_pipeline(
        lambda: upload(client, pme, "assurance.pdf", files.pdf(), document_type="ATTEST_ASSURANCE")
    ).json()["id"]
    url = f"/api/v1/documents/{document_id}/verify"
    no_reason = client.post(url, {"decision": "NON_CONFORME"}, format="json")
    assert no_reason.status_code == 400 and "reason" in no_reason.json()["errors"]
    expired = client.post(
        url, {"decision": "CONFORME", "expires_at": str(timezone.localdate() - timedelta(days=1))}, format="json"
    )
    assert expired.status_code == 400 and "expires_at" in expired.json()["errors"]
    leader_client = client_for(leader, org)
    assert leader_client.post(url, {"decision": "CONFORME"}, format="json").status_code == 403
    ok = client.post(
        url, {"decision": "CONFORME", "expires_at": str(timezone.localdate() + timedelta(days=200))}, format="json"
    )
    assert ok.status_code == 200 and ok.json()["status"] == "CONFORME"
    with tenant_context(org.id):
        assert Notification.objects.filter(user=leader, event_code="DOCUMENT_DECISION").exists()
    assert client.get("/api/v1/verifications").json() == []


def test_verified_history_lists_decided_documents(org, pme, advisor, leader, client_for, run_pipeline):
    client = client_for(advisor, org)
    decided = run_pipeline(lambda: upload(client, pme, "rccm.pdf", files.pdf())).json()["id"]
    pending = run_pipeline(lambda: upload(client, pme, "statuts.pdf", files.pdf(), document_type="STATUTS")).json()[
        "id"
    ]
    client.post(f"/api/v1/documents/{decided}/verify", {"decision": "CONFORME"}, format="json")

    history = client.get("/api/v1/verifications/history").json()
    assert [d["id"] for d in history] == [decided] and history[0]["verified_by_name"] == advisor.full_name
    assert [d["id"] for d in client.get("/api/v1/verifications/history?mine=1").json()] == [decided]
    assert pending in [d["id"] for d in client.get("/api/v1/verifications").json()]
    assert client_for(leader, org).get("/api/v1/verifications/history").status_code == 403


def test_one_decision_per_version_unless_revised(org, pme, advisor, leader, client_for, run_pipeline):
    client = client_for(advisor, org)
    document_id = run_pipeline(lambda: upload(client, pme, "rccm.pdf", files.pdf())).json()["id"]
    url = f"/api/v1/documents/{document_id}/verify"
    assert client.post(url, {"decision": "CONFORME"}, format="json").status_code == 200

    again = client.post(url, {"decision": "CONFORME"}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "already_decided"
    no_reason = client.post(url, {"decision": "NON_CONFORME", "revise": True}, format="json")
    assert no_reason.status_code == 400 and "reason" in no_reason.json()["errors"]
    revised = client.post(
        url, {"decision": "NON_CONFORME", "reason": "Extrait de plus de 3 mois.", "revise": True}, format="json"
    )
    assert revised.status_code == 200 and revised.json()["status"] == "NON_CONFORME"
    with tenant_context(org.id):
        assert Notification.objects.filter(user=leader, event_code="DOCUMENT_DECISION").count() == 2
        assert AuditLog.objects.filter(entity_id=document_id, action="document.decision_revised").count() == 1


def test_signed_download_is_personal_short_lived_and_audited(org, pme, advisor, make_user, client_for, run_pipeline):
    client = client_for(advisor, org)
    content = files.pdf()
    document_id = run_pipeline(lambda: upload(client, pme, "rccm.pdf", content)).json()["id"]
    link = client.get(f"/api/v1/documents/{document_id}/versions/1/download-url").json()
    assert link["expires_in"] == 300 and link["url"].startswith("/api/v1/files/")
    response = client.get(link["url"])
    assert response.status_code == 200 and response.content == content
    assert response["Content-Disposition"].startswith("inline") and response["Cache-Control"] == "private, no-store"
    colleague = client_for(make_user(org, "ADMIN_ORG"), org)
    assert colleague.get(link["url"]).status_code == 404  # lien personnel
    assert client.get(link["url"].replace("/files/", "/files/x")).status_code == 404
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="document.downloaded", pme_id=pme.id).exists()
    stranger = client_for(make_user(org, "CONSEILLER"), org)
    assert stranger.get(f"/api/v1/documents/{document_id}/versions/1/download-url").status_code == 404


def test_pme_user_cannot_upload_for_another_pme(org, pme, make_pme, leader, client_for):
    other = make_pme(org)
    assert upload(client_for(leader, org), other, "rccm.pdf", files.pdf()).status_code == 404


def test_verified_proof_lifts_declarative_cap_in_live_score(org, advisor, make_pme, client_for, run_pipeline):
    """RM-01 : le niveau déclaré 4 de FOR-01 est plafonné à 2 ; l'extrait RCCM vérifié le relève à 3 (sa preuve)."""
    from pme360.diagnostic.referential import install_gude360
    from pme360.scoring.models import ScoreSnapshot

    from .test_diagnostic import answer_everything, start, validate_full

    with tenant_context(org.id):
        install_gude360(org)
    pme = make_pme(org, advisor=advisor, headcount=12, creation_date="2015-01-01")
    client = client_for(advisor, org)
    diagnostic_id = start(client, pme)
    answer_everything(client, diagnostic_id, level=4)
    validate_full(client, diagnostic_id)

    def for01(result):
        return next(c for c in result["criteria"] if c["code"] == "FOR-01")

    frozen = client.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    assert for01(frozen["snapshot"]["result"])["level"] == 2 and frozen["live"] is None

    document_id = run_pipeline(lambda: upload(client, pme, "rccm.pdf", files.pdf()), client).json()["id"]
    client.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")

    health = client.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    live = for01(health["live"]["result"])
    assert live["level"] == 3 and live["source"] == "DOCUMENT_VERIFIE" and live["confidence"] == 1.0
    assert for01(health["snapshot"]["result"])["level"] == 2  # le snapshot figé ne change pas (RM-04)
    assert health["live"]["global_score"] > health["snapshot"]["global_score"]
    with tenant_context(org.id):
        assert ScoreSnapshot.objects.filter(pme=pme, kind="LIVE", is_frozen=False).count() == 1


def test_pipeline_never_overwrites_a_human_decision(org, pme, advisor, client_for, django_capture_on_commit_callbacks):
    client = client_for(advisor, org)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        document_id = upload(client, pme, "rccm.pdf", files.pdf()).json()["id"]
        # Décision rendue AVANT la fin du traitement asynchrone.
        verified = client.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")
        assert verified.status_code == 200
    for callback in callbacks:
        callback()
    assert client.get(f"/api/v1/documents/{document_id}").json()["status"] == "CONFORME"
