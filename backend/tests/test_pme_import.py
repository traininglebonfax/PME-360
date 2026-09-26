"""Import en masse des PME par CSV (V1) : aperçu sans écriture, règles identiques à la saisie, bilan ligne par ligne."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context
from pme360.pmes.models import Pme, PmeAssignment, PmeEnrollment

pytestmark = pytest.mark.django_db

HEADER = (
    "Raison sociale;Forme juridique;RCCM;NCC;Date de création;Secteur;Région;Effectif;"
    "Nom du dirigeant;Fonction du dirigeant;E-mail du conseiller principal\n"
)


@pytest.fixture
def admin(org, make_user, client_for):
    return client_for(make_user(org, "ADMIN_ORG"), org)


def _csv(body: str, header: str = HEADER, encoding: str = "utf-8", name: str = "pme.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, (header + body).encode(encoding), content_type="text/csv")


def _preview(client, content, **extra):
    response = client.post("/api/v1/pme-import/preview", {"file": content, **extra}, format="multipart")
    assert response.status_code == 200, response.content
    return response.json()


def test_template_lists_columns(admin):
    response = admin.get("/api/v1/pme-import/template")
    assert response["Content-Type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Raison sociale (obligatoire);Nom commercial;Forme juridique")


def test_preview_validates_every_line_without_writing(admin, org, make_pme, make_user):
    advisor = make_user(org, "CONSEILLER")
    make_pme(org, legal_name="Déjà Là SARL", rccm_number="CI-ABJ-2015-B-00001")
    make_pme(org, legal_name="Boulangerie du Plateau SARL")
    body = (
        f"Atelier Neuf SARL;SARL;;;15/03/2019;COMMERCE;ABIDJAN;12;Awa Koné;Gérante;{advisor.email}\n"
        "Secteur Inconnu SA;;;;2019-01-01;AERONAUTIQUE;;;;;\n"
        "Date Folle SARL;;;;31/31/2019;;;;;;\n"
        "Doublon RCCM SARL;;CI-ABJ-2015-B-00001;;;;;;;;\n"
        "Boulangerie du Plateau SARL;;;;;;;;;;\n"
        "Atelier Neuf SARL;;;;;;;;;;\n"
        ";;;;;;;;;;\n"
    )
    report = _preview(admin, _csv(body))
    rows = {r["line"]: r for r in report["rows"]}
    assert rows[2]["status"] == "VALIDE"
    assert rows[3]["status"] == "ERREUR" and "secteur" in rows[3]["errors"]
    assert rows[4]["status"] == "ERREUR" and "date_creation" in rows[4]["errors"]
    assert rows[5]["status"] == "ERREUR" and "doublon" in rows[5]["errors"]
    assert (
        rows[6]["status"] == "DOUBLON_PROBABLE"
        and rows[6]["duplicates"][0]["legal_name"] == "Boulangerie du Plateau SARL"
    )
    assert rows[7]["status"] == "ERREUR" and "ligne 2" in rows[7]["errors"]["fichier"]
    assert report["summary"] == {"total": 6, "VALIDE": 1, "ERREUR": 4, "DOUBLON_PROBABLE": 1}  # ligne vide ignorée
    with tenant_context(org.id):
        assert Pme.objects.count() == 2  # l'aperçu n'écrit rien


def test_import_creates_valid_lines_with_leader_advisor_and_cohort(admin, org, make_pme, make_user, cohort):
    advisor = make_user(org, "CONSEILLER")
    make_pme(org, legal_name="Boulangerie du Plateau SARL")
    body = (
        "Atelier Neuf SARL;SARL;CI-ABJ-2019-B-777;;15/03/2019;commerce et distribution;Abidjan;12;Awa Koné;PDG;"
        f"{advisor.email}\n"
        "Boulangerie du Plateau SARL;;;;;;;;;;\n"
        "Erreur SARL;;;;demain;;;;;;\n"
    )
    response = admin.post("/api/v1/pme-import", {"file": _csv(body), "cohort_id": str(cohort.id)}, format="multipart")
    assert response.status_code == 200, response.content
    report = response.json()
    assert [r["status"] for r in report["rows"]] == ["CREEE", "IGNOREE", "ERREUR"]
    with tenant_context(org.id):
        pme = Pme.objects.get(pk=report["rows"][0]["pme_id"])
        assert pme.rccm_number == "CI-ABJ-2019-B-777" and pme.headcount == 12 and pme.sector.code == "COMMERCE"
        assert pme.lifecycle_status == Pme.LifecycleStatus.ONBOARDING
        assert pme.persons.get().role == "DG"
        assert PmeAssignment.objects.get(pme=pme).user == advisor
        assert PmeEnrollment.objects.filter(pme=pme, cohort=cohort).exists()
        assert AuditLog.objects.get(action="pme.imported").after["created"] == 1
    # Confirmation explicite : la raison sociale proche est alors importée.
    confirmed = admin.post(
        "/api/v1/pme-import",
        {"file": _csv("Boulangerie du Plateau SARL;;;;;;;;;;\n"), "confirm_similar": True},
        format="multipart",
    ).json()
    assert confirmed["rows"][0]["status"] == "CREEE"


def test_windows_excel_file_with_commas_is_accepted(admin, org):
    header = "Raison sociale,Secteur,Région\n"
    report = _preview(admin, _csv("Société Ivoirienne des Épices,COMMERCE,ABIDJAN\n", header=header, encoding="cp1252"))
    assert (
        report["rows"][0]["status"] == "VALIDE" and report["rows"][0]["legal_name"] == "Société Ivoirienne des Épices"
    )


def test_file_without_required_column_is_refused(admin):
    response = admin.post(
        "/api/v1/pme-import/preview", {"file": _csv("x;y\n", header="Nom commercial;Ville\n")}, format="multipart"
    )
    assert response.status_code == 400 and response.json()["code"] == "missing_columns"


def test_import_permissions(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert (
        leader.post("/api/v1/pme-import/preview", {"file": _csv("A SARL;;;;;;;;;;\n")}, format="multipart").status_code
        == 403
    )
    advisor_user = make_user(org, "CONSEILLER")
    advisor = client_for(advisor_user, org)
    report = advisor.post(
        "/api/v1/pme-import", {"file": _csv("Nouvelle PME SARL;;;;;;;;;;\n")}, format="multipart"
    ).json()
    assert report["rows"][0]["status"] == "CREEE"
    with tenant_context(org.id):
        # Un conseiller qui importe suit les PME créées (sinon elles sortiraient de son portefeuille).
        assert PmeAssignment.objects.get(pme_id=report["rows"][0]["pme_id"]).user == advisor_user
