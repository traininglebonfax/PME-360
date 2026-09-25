"""Rôles + périmètres (Document 1, § 6) appliqués par l'API."""

import pytest

from pme360.accounts.models import UserMembership
from pme360.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db


def _ids(response) -> set[str]:
    assert response.status_code == 200, response.content
    return {row["id"] for row in response.json()["results"]}


def test_other_tenant_pme_is_invisible_through_api(org, other_org, make_user, make_pme, client_for):
    mine = make_pme(org)
    foreign = make_pme(other_org)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    assert _ids(client.get("/api/v1/pmes")) == {str(mine.id)}
    assert client.get(f"/api/v1/pmes/{foreign.id}").status_code == 404
    assert client.patch(f"/api/v1/pmes/{foreign.id}", {"legal_name": "X"}, format="json").status_code == 404


def test_advisor_sees_only_assigned_pmes(org, make_user, make_pme, client_for):
    advisor = make_user(org, "CONSEILLER")
    assigned = make_pme(org, advisor=advisor)
    other = make_pme(org)
    client = client_for(advisor, org)
    assert _ids(client.get("/api/v1/pmes")) == {str(assigned.id)}
    assert client.get(f"/api/v1/pmes/{other.id}").status_code == 404


def test_programme_manager_sees_programme_pmes(org, programme, cohort, make_user, make_pme, client_for):
    manager = make_user(org, "RESPONSABLE_PROGRAMME", scope_ref_id=programme.id)
    enrolled = make_pme(org, cohort=cohort)
    make_pme(org)
    assert _ids(client_for(manager, org).get("/api/v1/pmes")) == {str(enrolled.id)}


def test_org_admin_and_auditor_see_all(org, make_user, make_pme, client_for):
    pmes = {str(make_pme(org).id) for _ in range(3)}
    assert _ids(client_for(make_user(org, "ADMIN_ORG"), org).get("/api/v1/pmes")) == pmes
    assert _ids(client_for(make_user(org, "AUDITEUR"), org).get("/api/v1/pmes")) == pmes


def test_auditor_is_read_only(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    client = client_for(make_user(org, "AUDITEUR"), org)
    assert client.post("/api/v1/pmes", {"legal_name": "Nouvelle SARL"}, format="json").status_code == 403
    assert client.patch(f"/api/v1/pmes/{pme.id}", {"phone": "01"}, format="json").status_code == 403


def test_pme_leader_edits_only_contact_fields_of_own_pme(org, make_user, make_pme, client_for):
    pme = make_pme(org, rccm_number="CI-ABJ-2020-B-1")
    other = make_pme(org)
    leader = make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)
    client = client_for(leader, org)
    assert _ids(client.get("/api/v1/pmes")) == {str(pme.id)}
    assert client.get(f"/api/v1/pmes/{other.id}").status_code == 404
    ok = client.patch(f"/api/v1/pmes/{pme.id}", {"phone": "+225 01 02 03 04"}, format="json")
    assert ok.status_code == 200 and ok.json()["phone"] == "+225 01 02 03 04"
    denied = client.patch(f"/api/v1/pmes/{pme.id}", {"rccm_number": "AUTRE"}, format="json")
    assert denied.status_code == 403


def test_pme_collaborator_cannot_edit_pme(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    client = client_for(make_user(org, "COLLABORATEUR_PME", scope_ref_id=pme.id), org)
    assert client.get(f"/api/v1/pmes/{pme.id}").status_code == 200
    assert client.patch(f"/api/v1/pmes/{pme.id}", {"phone": "01"}, format="json").status_code == 403


def test_leader_can_invite_collaborator_only_in_own_pme(org, make_user, make_pme, client_for):
    pme = make_pme(org)
    other = make_pme(org)
    client = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    payload = {"email": "collab@test.test", "full_name": "Collab", "role": "COLLABORATEUR_PME", "scope": "PME"}
    assert (
        client.post("/api/v1/users/invite", {**payload, "scope_ref_id": str(pme.id)}, format="json").status_code == 201
    )
    assert (
        client.post("/api/v1/users/invite", {**payload, "scope_ref_id": str(other.id)}, format="json").status_code
        == 403
    )
    admin_invite = {**payload, "role": "ADMIN_ORG", "scope": "ORG", "email": "boss@test.test"}
    assert client.post("/api/v1/users/invite", admin_invite, format="json").status_code == 403


def test_admin_invites_staff_and_membership_is_scoped(org, make_user, client_for):
    from django.core import mail

    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.post(
        "/api/v1/users/invite",
        {"email": "nouveau@test.test", "full_name": "Nouveau Conseiller", "role": "CONSEILLER"},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["scope"] == "PORTEFEUILLE"
    assert "mot de passe" in mail.outbox[0].body.lower()
    members = client.get("/api/v1/users").json()
    assert "nouveau@test.test" in {m["email"] for m in members}


def test_invite_validates_scope_reference(org, other_org, make_user, make_pme, client_for):
    foreign = make_pme(other_org)
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.post(
        "/api/v1/users/invite",
        {
            "email": "d@test.test",
            "full_name": "D",
            "role": "DIRIGEANT_PME",
            "scope": "PME",
            "scope_ref_id": str(foreign.id),
        },
        format="json",
    )
    assert response.status_code == 400 and "scope_ref_id" in response.json()["errors"]


def test_members_of_other_org_are_not_listed(org, other_org, make_user, client_for):
    make_user(other_org, "CONSEILLER", email="etranger@test.test")
    members = client_for(make_user(org, "ADMIN_ORG"), org).get("/api/v1/users").json()
    assert "etranger@test.test" not in {m["email"] for m in members}


def test_revoke_membership(org, make_user, client_for):
    admin = make_user(org, "ADMIN_ORG")
    target = make_user(org, "CONSEILLER")
    client = client_for(admin, org)
    with tenant_context(org.id):
        membership = UserMembership.objects.get(user=target)
    assert client.post(f"/api/v1/memberships/{membership.id}/revoke").status_code == 200
    with tenant_context(org.id):
        membership.refresh_from_db()
    assert not membership.is_active
    with tenant_context(org.id):
        own = UserMembership.objects.get(user=admin)
    assert client.post(f"/api/v1/memberships/{own.id}/revoke").json()["code"] == "cannot_revoke_self"


def test_user_without_organization_gets_explicit_error(make_user, client_for):
    client = client_for(make_user())
    response = client.get("/api/v1/pmes")
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "no_organization" and body["type"].endswith("no_organization")
