"""Tableaux de bord (phase 1), seed de démonstration, santé, schéma OpenAPI."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from pme360.accounts.models import User
from pme360.core.tenancy import system_context, tenant_context
from pme360.diagnostic.models import Diagnostic
from pme360.organizations.models import Organization
from pme360.pmes.models import Pme
from pme360.scoring.models import ScoreSnapshot

pytestmark = pytest.mark.django_db


def test_advisor_dashboard_counts_only_own_portfolio(org, make_user, make_pme, client_for):
    advisor = make_user(org, "CONSEILLER")
    make_pme(org, advisor=advisor)
    stale = make_pme(org, advisor=advisor)
    make_pme(org)  # hors portefeuille
    with tenant_context(org.id):
        Pme.objects.filter(pk=stale.pk).update(
            last_activity_at=timezone.now() - timedelta(days=90), created_at=timezone.now() - timedelta(days=120)
        )
    data = client_for(advisor, org).get("/api/v1/dashboards/advisor").json()
    assert data["kpis"]["pmes_followed"] == 2
    assert data["kpis"]["pmes_inactive"] == 1
    assert data["kpis"]["documents_to_verify"] == {"value": None, "available_in_phase": 3}


def test_portfolio_dashboard_requires_permission(org, make_user, make_pme, client_for):
    make_pme(org)
    pme = make_pme(org)
    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert leader.get("/api/v1/dashboards/portfolio").status_code == 403
    data = client_for(make_user(org, "ADMIN_ORG"), org).get("/api/v1/dashboards/portfolio").json()
    assert data["kpis"]["pmes_total"] == 2
    assert data["kpis"]["pmes_without_advisor"] == 2
    assert data["by_sector"][0] == {"key": "COMMERCE", "label": "Commerce et distribution", "count": 2}


def test_pme_dashboard_scoped_to_own_pme(org, make_user, make_pme, client_for):
    advisor = make_user(org, "CONSEILLER")
    pme = make_pme(org, advisor=advisor)
    other = make_pme(org)
    client = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    data = client.get(f"/api/v1/dashboards/pme/{pme.id}").json()
    assert data["advisor"]["full_name"] == advisor.full_name
    assert data["score"] is None and data["open_diagnostic"] is None
    assert client.get(f"/api/v1/dashboards/pme/{other.id}").status_code == 404


def test_seed_demo_is_idempotent_and_fictitious():
    call_command("seed_demo")
    call_command("seed_demo")
    with system_context():
        gude = Organization.objects.get(slug="gude-pme-demo")
        assert Organization.objects.filter(slug__in=["gude-pme-demo", "banque-demo"]).count() == 2
    with tenant_context(gude.id):
        pmes = Pme.objects.all()
        assert pmes.count() == 6
        assert all(p.rccm_number.startswith("DEMO-") for p in pmes)
        assert pmes.get(legal_name="Boutik Plus Distribution SARL").lifecycle_status == "ACCOMPAGNEMENT_ACTIF"
        # Profils de démonstration du Document 3, § 7.
        boutik = ScoreSnapshot.objects.get(pme__legal_name="Boutik Plus Distribution SARL")
        assert boutik.quadrant == "PERFORMANTE_FRAGILE"  # CA élevé, gouvernance informelle (RM-02)
        delices = list(
            ScoreSnapshot.objects.filter(pme__legal_name="Délices du Bandama SAS").order_by("reference_date")
        )
        assert len(delices) == 3 and delices[0].global_score < delices[1].global_score < delices[2].global_score
        assert ScoreSnapshot.objects.get(pme__legal_name="Bâti Lagune BTP SARL").intervention_priority == "P1"
        assert Diagnostic.objects.filter(status="EN_REVUE").count() == 1
    assert all(u.email.endswith("@demo.test") for u in User.objects.all())


def test_seed_refused_in_production(settings):
    from django.core.management.base import CommandError

    settings.ENVIRONMENT = "prod"
    with pytest.raises(CommandError):
        call_command("seed_demo")


def test_health_and_schema(anon):
    assert anon.get("/api/v1/health").json() == {"status": "ok"}
    schema = anon.get("/api/v1/schema")
    assert schema.status_code == 200
    assert b"/api/v1/pmes" in schema.content


def test_unknown_route_and_method(org, make_user, client_for):
    client = client_for(make_user(org, "ADMIN_ORG"), org)
    response = client.delete("/api/v1/pmes")
    assert response.status_code == 405
    assert response["Content-Type"] == "application/problem+json"
