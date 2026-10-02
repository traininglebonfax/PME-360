"""Module PME : création (doublons, assignation), modification, cycle de vie, dirigeants, timeline."""

import pytest

from pme360.core.models import DomainEvent
from pme360.core.tenancy import tenant_context
from pme360.pmes.models import Pme, PmeAssignment, Sector
from pme360.pmes.services import normalize_compact, normalize_rccm

pytestmark = pytest.mark.django_db


def _sector_id(org, code="SERVICES"):
    with tenant_context(org.id):
        return str(Sector.objects.get(code=code).id)


def test_identifier_normalization():
    assert normalize_rccm(" ci abj 2016 b 12345 ") == "CI-ABJ-2016-B-12345"
    assert normalize_rccm("CI/ABJ/2016/B/12345") == "CI-ABJ-2016-B-12345"
    assert normalize_compact("1234 567-a") == "1234567A"


def test_advisor_creates_pme_with_leader_and_is_assigned(org, make_user, client_for):
    advisor = make_user(org, "CONSEILLER")
    client = client_for(advisor, org)
    response = client.post(
        "/api/v1/pmes",
        {
            "legal_name": "  Nouvelle   Boulangerie SARL ",
            "rccm_number": "ci abj 2025 b 999",
            "sector": _sector_id(org),
            "headcount": 4,
            "primary_person": {"full_name": "Awa K.", "role": "GERANT", "share_pct": "100"},
            "start_onboarding": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["legal_name"] == "Nouvelle Boulangerie SARL"
    assert body["rccm_number"] == "CI-ABJ-2025-B-999"
    assert body["sector"]["code"] == "SERVICES"
    assert body["lifecycle_status"] == "ONBOARDING" and body["onboarding_started_at"]
    assert body["principal_advisor"]["id"] == str(advisor.id)
    assert body["persons"][0]["is_primary_contact"] is True
    # Le conseiller voit la PME dans son portefeuille, et un événement de domaine est émis.
    assert body["id"] in {row["id"] for row in client.get("/api/v1/pmes").json()["results"]}
    with tenant_context(org.id):
        assert DomainEvent.objects.filter(event_type="pme.created").count() == 1


def test_duplicate_identifier_is_blocking(org, make_user, make_pme, client_for):
    make_pme(org, rccm_number="CI-ABJ-2020-B-1")
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.post(
        "/api/v1/pmes",
        {"legal_name": "Tout autre nom", "rccm_number": "ci abj 2020 b 1", "confirm_duplicates": True},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_identifier"
    assert response.json()["duplicates"][0]["reasons"] == ["rccm"]


def test_similar_name_requires_confirmation(org, make_user, make_pme, client_for):
    make_pme(org, legal_name="Boulangerie du Plateau SARL")
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    payload = {"legal_name": "Boulangerie Du Plateau SARLU"}
    first = client.post("/api/v1/pmes", payload, format="json")
    assert first.status_code == 409 and first.json()["code"] == "possible_duplicates"
    assert first.json()["duplicates"][0]["similarity"] >= 0.55
    check = client.get("/api/v1/pmes/duplicates", {"legal_name": payload["legal_name"]})
    assert check.status_code == 200 and check.json()[0]["accessible"] is True
    second = client.post("/api/v1/pmes", {**payload, "confirm_duplicates": True}, format="json")
    assert second.status_code == 201


def test_rejected_creation_leaves_no_trace(org, make_user, make_pme, client_for):
    make_pme(org, rccm_number="CI-X-1")
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    client.post("/api/v1/pmes", {"legal_name": "Autre", "rccm_number": "CI-X-1"}, format="json")
    with tenant_context(org.id):
        assert Pme.objects.count() == 1


def test_creation_date_cannot_be_in_future(org, make_user, client_for):
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.post("/api/v1/pmes", {"legal_name": "Futur SARL", "creation_date": "2999-01-01"}, format="json")
    assert response.status_code == 400 and "creation_date" in response.json()["errors"]


def test_assigning_another_advisor_requires_permission(org, make_user, client_for):
    advisor = make_user(org, "CONSEILLER")
    colleague = make_user(org, "CONSEILLER")
    response = client_for(advisor, org).post(
        "/api/v1/pmes", {"legal_name": "Assignée SARL", "advisor_id": str(colleague.id)}, format="json"
    )
    assert response.status_code == 403


def test_update_is_audited_with_diff(org, make_user, make_pme, client_for):
    pme = make_pme(org, headcount=5)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.patch(f"/api/v1/pmes/{pme.id}", {"headcount": 7, "commune": "Cocody"}, format="json")
    assert response.status_code == 200
    timeline = client.get(f"/api/v1/pmes/{pme.id}/timeline").json()
    update = next(entry for entry in timeline if entry["action"] == "pme.updated")
    assert update["before"] == {"headcount": 5, "commune": ""}
    assert update["after"] == {"headcount": 7, "commune": "Cocody"}
    assert update["label"] == "Fiche PME modifiée"


def test_lifecycle_transitions(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    invalid = client.post(f"/api/v1/pmes/{pme.id}/transition", {"to": "ACCOMPAGNEMENT_ACTIF"}, format="json")
    assert invalid.status_code == 400 and invalid.json()["code"] == "invalid_transition"
    assert set(invalid.json()["allowed"]) == {"ONBOARDING", "SORTIE"}
    for status in ("ONBOARDING", "DIAGNOSTIC_EN_COURS", "ACCOMPAGNEMENT_ACTIF", "SUSPENDU", "ACCOMPAGNEMENT_ACTIF"):
        response = client.post(f"/api/v1/pmes/{pme.id}/transition", {"to": status}, format="json")
        assert response.status_code == 200, (status, response.content)
    no_reason = client.post(f"/api/v1/pmes/{pme.id}/transition", {"to": "SORTIE"}, format="json")
    assert no_reason.status_code == 400
    exit_ = client.post(f"/api/v1/pmes/{pme.id}/transition", {"to": "SORTIE", "exit_reason": "DIPLOMEE"}, format="json")
    assert exit_.json()["lifecycle_status"] == "SORTIE" and exit_.json()["exit_reason"] == "DIPLOMEE"


def test_leader_cannot_change_lifecycle(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    client = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert client.post(f"/api/v1/pmes/{pme.id}/transition", {"to": "ONBOARDING"}, format="json").status_code == 403


def test_persons_shares_and_single_primary_contact(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    url = f"/api/v1/pmes/{pme.id}/persons"
    first = client.post(
        url, {"full_name": "A", "role": "ASSOCIE", "share_pct": "60", "is_primary_contact": True}, format="json"
    )
    assert first.status_code == 201, first.content
    too_much = client.post(url, {"full_name": "B", "role": "ASSOCIE", "share_pct": "50"}, format="json")
    assert too_much.status_code == 400 and "share_pct" in too_much.json()["errors"]
    second = client.post(
        url, {"full_name": "C", "role": "DG", "share_pct": "40", "is_primary_contact": True}, format="json"
    )
    assert second.status_code == 201
    persons = client.get(url).json()
    assert [p["full_name"] for p in persons if p["is_primary_contact"]] == ["C"]
    assert client.delete(f"{url}/{first.json()['id']}").status_code == 204


def test_reassigning_principal_advisor_ends_previous(org, make_user, make_pme, client_for):
    first = make_user(org, "CONSEILLER")
    second = make_user(org, "CONSEILLER")
    pme = make_pme(org, advisor=first)
    client = client_for(make_user(org, "RESPONSABLE_PROGRAMME", scope="ORG"), org)
    response = client.post(
        f"/api/v1/pmes/{pme.id}/assignments",
        {"user_id": str(second.id), "role_in_pme": "CONSEILLER_PRINCIPAL"},
        format="json",
    )
    assert response.status_code == 201, response.content
    with tenant_context(org.id):
        active = PmeAssignment.objects.filter(pme=pme, end_date__isnull=True)
        assert list(active.values_list("user_id", flat=True)) == [second.id]
    # Le premier conseiller perd l'accès à la PME.
    assert client_for(first, org).get(f"/api/v1/pmes/{pme.id}").status_code == 404


def test_existing_pme_joins_existing_programme(org, make_user, make_pme, client_for, cohort):
    advisor = make_user(org, "CONSEILLER")
    pme = make_pme(org, advisor=advisor)
    url = f"/api/v1/pmes/{pme.id}/enrollments"
    client = client_for(advisor, org)
    response = client.post(url, {"cohort_id": str(cohort.id)}, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["cohort"]["programme"] == "Programme test"
    assert client.get(f"/api/v1/pmes/{pme.id}").json()["enrollments"][0]["cohort"]["name"] == "Cohorte A"
    again = client.post(url, {"cohort_id": str(cohort.id)}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "already_enrolled"
    leader = make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)
    assert client_for(leader, org).post(url, {"cohort_id": str(cohort.id)}, format="json").status_code == 403


def test_cannot_assign_pme_user_as_advisor(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    leader = make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.post(
        f"/api/v1/pmes/{pme.id}/assignments", {"user_id": str(leader.id), "role_in_pme": "EXPERT"}, format="json"
    )
    assert response.status_code == 400


def test_list_filters_and_search(org, make_user, make_pme, client_for):
    advisor = make_user(org, "CONSEILLER")
    target = make_pme(org, legal_name="Cacao Premium SARL", advisor=advisor)
    make_pme(org, legal_name="Garage Central SARL")
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    assert {r["id"] for r in client.get("/api/v1/pmes", {"q": "cacao"}).json()["results"]} == {str(target.id)}
    assert {r["id"] for r in client.get("/api/v1/pmes", {"advisor": str(advisor.id)}).json()["results"]} == {
        str(target.id)
    }
    ordered = client.get("/api/v1/pmes", {"ordering": "legal_name"}).json()["results"]
    assert [r["legal_name"] for r in ordered] == ["Cacao Premium SARL", "Garage Central SARL"]
    assert ordered[0]["principal_advisor"]["id"] == str(advisor.id)


def test_reference_lists(org, make_user, client_for):
    client = client_for(make_user(org, "CONSEILLER"), org)
    regions = client.get("/api/v1/ref/regions").json()
    assert len(regions) == 33  # 31 régions + 2 districts autonomes
    assert client.get("/api/v1/ref/inconnu").status_code == 404
