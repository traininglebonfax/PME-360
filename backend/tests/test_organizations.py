"""Organisations (plateforme et paramètres), programmes et cohortes."""

import pytest
from django.core import mail

from pme360.accounts.models import User, UserMembership
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Organization
from pme360.pmes.models import Region

pytestmark = pytest.mark.django_db


def test_platform_admin_creates_tenant_with_defaults_and_first_admin(make_user, client_for):
    platform = client_for(make_user(is_platform_admin=True))
    response = platform.post(
        "/api/v1/platform/organizations",
        {
            "name": "Incubateur Test",
            "slug": "incubateur-test",
            "type": "INCUBATEUR",
            "admin_email": "chef@incubateur.test",
            "admin_full_name": "Chef Incubateur",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    with system_context():
        organization = Organization.objects.get(slug="incubateur-test")
    with tenant_context(organization.id):
        assert Region.objects.count() == 33
        membership = UserMembership.objects.get(user__email="chef@incubateur.test")
        assert membership.role.code == "ADMIN_ORG"
    assert "Incubateur Test" in mail.outbox[0].subject
    duplicate = platform.post(
        "/api/v1/platform/organizations",
        {"name": "Autre", "slug": "incubateur-test", "type": "ONG", "admin_email": "a@a.test", "admin_full_name": "A"},
        format="json",
    )
    assert duplicate.status_code == 400
    assert User.objects.filter(email="chef@incubateur.test").exists()


def test_platform_endpoints_forbidden_to_tenant_users(org, make_user, client_for):
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    assert client.get("/api/v1/platform/organizations").status_code == 403


def test_platform_admin_without_membership_sees_no_business_data(org, make_pme, make_user, client_for):
    make_pme(org)
    platform = client_for(make_user(is_platform_admin=True))
    assert platform.get("/api/v1/pmes").status_code == 403
    assert platform.get("/api/v1/me").json()["portal"] == "platform"


def test_org_settings_are_validated(org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    ok = admin.patch("/api/v1/organization", {"settings": {"inactivity_days": 90}}, format="json")
    assert ok.status_code == 200 and ok.json()["settings"]["inactivity_days"] == 90
    assert ok.json()["settings"]["duplicate_name_similarity"] == 0.55  # valeur par défaut conservée
    bad = admin.patch("/api/v1/organization", {"settings": {"inactivity_days": 1, "inconnu": 3}}, format="json")
    assert bad.status_code == 400
    errors = bad.json()["errors"]["settings"]
    assert "inactivity_days" in errors and "inconnu" in errors
    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.get("/api/v1/organization").status_code == 200
    assert advisor.patch("/api/v1/organization", {"name": "X"}, format="json").status_code == 403


def test_programmes_and_cohorts(org, make_user, client_for):
    manager = client_for(make_user(org, "RESPONSABLE_PROGRAMME", scope="ORG"), org)
    created = manager.post(
        "/api/v1/programmes",
        {"name": "Programme 2027", "start_date": "2027-01-01", "end_date": "2027-12-31"},
        format="json",
    )
    assert created.status_code == 201, created.content
    programme_id = created.json()["id"]
    cohort = manager.post(f"/api/v1/programmes/{programme_id}/cohorts", {"name": "Cohorte 1"}, format="json")
    assert cohort.status_code == 201
    bad_dates = manager.post(
        "/api/v1/programmes", {"name": "Invalide", "start_date": "2027-02-01", "end_date": "2027-01-01"}, format="json"
    )
    assert bad_dates.status_code == 400
    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.get("/api/v1/programmes").json()[0]["cohorts"][0]["name"] == "Cohorte 1"
    assert advisor.post("/api/v1/programmes", {"name": "Non"}, format="json").status_code == 403
    assert advisor.post(f"/api/v1/programmes/{programme_id}/cohorts", {"name": "Non"}, format="json").status_code == 403
