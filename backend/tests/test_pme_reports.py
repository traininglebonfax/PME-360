"""Rapports de suivi, annuel et de conformité d'une PME (V1, Document 9, § 7)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from pme360.core.tenancy import tenant_context
from pme360.diagnostic.referential import install_gude360
from pme360.notifications.models import Notification
from pme360.reports import services
from pme360.reports.models import Report
from pme360.reports.pme_builder import ANNUAL_SECTIONS, COMPLIANCE_SECTIONS, FOLLOW_UP_SECTIONS

from .test_diagnostic import answer_everything, start, validate_full
from .test_plans import _live_plan, _upload_deliverable
from .test_reporting import _pdf_text

pytestmark = pytest.mark.django_db


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, make_pme, advisor):
    with tenant_context(org.id):
        install_gude360(org)
    return make_pme(org, legal_name="Atelier Test SARL", advisor=advisor, headcount=12, creation_date="2015-01-01")


@pytest.fixture
def api(client_for, advisor, org):
    return client_for(advisor, org)


@pytest.fixture
def pme_api(client_for, org, pme, make_user):
    return client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)


@pytest.fixture
def run_pipeline(django_capture_on_commit_callbacks):
    def runner(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    return runner


@pytest.fixture
def diagnosed(api, pme):
    """Diagnostic validé avec des pratiques faibles (niveau 1) : les règles d'accompagnement se déclenchent."""
    diagnostic_id = start(api, pme)
    answer_everything(api, diagnostic_id, level=1)
    validate_full(api, diagnostic_id)
    return diagnostic_id


def _finish_rh_action(api, pme_api, pme, run_pipeline):
    """Plan accepté, action RH terminée avec ses deux livrables conformes (progrès vérifié RHO-01 et RHO-02)."""
    plan = _live_plan(api, pme_api, pme)
    rh = next(a for a in plan["actions"] if a["offer_code"] == "OFF-RH-BASE")
    started = pme_api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_COURS"}, format="json").json()
    for deliverable in started["deliverables"]:
        document_id = run_pipeline(lambda d=deliverable: _upload_deliverable(pme_api, pme, d["id"], "livrable.pdf"))
        api.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")
    action = api.get(f"/api/v1/actions/{rh['id']}").json()
    assert action["status"] == "TERMINE"
    return action


def _generate(client, pme, report_type):
    response = client.post(f"/api/v1/pmes/{pme.id}/reports", {"type": report_type}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def test_follow_up_report_describes_period_actions_progress_and_score_change(
    api, pme_api, pme, diagnosed, run_pipeline
):
    action = _finish_rh_action(api, pme_api, pme, run_pipeline)
    report = _generate(api, pme, "SUIVI")
    assert report["type"] == "SUIVI" and report["version"] == 1 and report["diagnostic"] is None
    text = _pdf_text(api.get(f"/api/v1/reports/{report['id']}/pdf").content)
    for number, title in enumerate(FOLLOW_UP_SECTIONS, start=1):
        assert f"{number}. {title}" in text, title
    assert "Atelier Test SARL" in text and action["human_ref"] in text and "RHO-01" in text

    with tenant_context(pme.organization_id):
        data = Report.objects.get(pk=report["id"]).data_snapshot
        # Période par défaut : 90 jours (le diagnostic date d'aujourd'hui), jusqu'à la date d'édition.
        assert data["period"]["end"] == timezone.localdate().isoformat() and data["period"]["days"] == 90
        assert [a["ref"] for a in data["actions"]["completed"]] == [action["human_ref"]]
        assert {p["criterion"] for p in data["progress"]} == {"RHO-01", "RHO-02"}
        # Le score courant a progressé depuis le diagnostic ; l'écart est expliqué par dimension et par critère.
        assert data["score"]["current_is_live"] and data["score"]["delta"] > 0
        criteria = {c["code"] for dim in data["explanation"]["dimensions"] for c in dim["criteria"]}
        assert "RHO-01" in criteria
        assert any("ne sont pas attribuées à une cause unique" in line for line in data["summary"])  # RM-09
        notified = Notification.objects.filter(event_code="REPORT_READY", pme=pme).first()
        assert notified and "rapport de suivi" in notified.body


def test_follow_up_periods_chain_and_same_day_edition_is_a_new_version(api, pme, diagnosed):
    first = _generate(api, pme, "SUIVI")
    again = _generate(api, pme, "SUIVI")
    assert again["version"] == 2 and again["period"] == first["period"]
    tomorrow = timezone.localdate() + timedelta(days=1)
    with tenant_context(pme.organization_id):
        later = services.generate_pme_report(pme, Report.Type.SUIVI, today=tomorrow)
    # Le rapport suivant reprend là où le précédent s'est arrêté.
    assert later.version == 1 and later.period == f"{tomorrow.isoformat()}_{tomorrow.isoformat()}"


def test_annual_report_has_a_twelve_month_trajectory(api, pme, diagnosed):
    report = _generate(api, pme, "ANNUEL")
    text = _pdf_text(api.get(f"/api/v1/reports/{report['id']}/pdf").content)
    for number, title in enumerate(ANNUAL_SECTIONS, start=1):
        assert f"{number}. {title}" in text, title
    with tenant_context(pme.organization_id):
        data = Report.objects.get(pk=report["id"]).data_snapshot
    assert data["kind"] == "ANNUEL" and data["period"]["days"] == 365
    assert data["trajectory"][0]["kind"] == "Diagnostic initial" and data["trajectory"][0]["score"] is not None


def test_compliance_report_lists_what_remains_to_provide(api, pme, diagnosed):
    report = _generate(api, pme, "CONFORMITE")
    assert report["period"] == timezone.localdate().isoformat() and report["confidence"] is None
    text = _pdf_text(api.get(f"/api/v1/reports/{report['id']}/pdf").content)
    for number, title in enumerate(COMPLIANCE_SECTIONS, start=1):
        assert f"{number}. {title}" in text, title
    assert "ne vaut pas attestation de régularité" in text
    with tenant_context(pme.organization_id):
        data = Report.objects.get(pk=report["id"]).data_snapshot
    # Aucun document déposé : chaque document exigé figure dans « ce qu'il reste à faire ».
    required = [item for category in data["categories"] for item in category["items"] if item["required"]]
    assert required and len(data["todo"]) == len(required)
    assert all(item["state"] == "MANQUANT" for item in data["todo"])
    assert data["rate"]["rate"] == 0


def test_pme_report_rights(api, pme_api, pme, diagnosed, other_org, make_user, client_for):
    # La PME consulte et télécharge ; elle n'édite pas.
    assert pme_api.post(f"/api/v1/pmes/{pme.id}/reports", {"type": "SUIVI"}, format="json").status_code == 403
    report = _generate(api, pme, "CONFORMITE")
    assert [r["type"] for r in pme_api.get(f"/api/v1/pmes/{pme.id}/reports").json()][0] == "CONFORMITE"
    download = pme_api.get(f"/api/v1/reports/{report['id']}/pdf")
    assert download.status_code == 200 and "rapport-conformite-v1" in download["Content-Disposition"]
    # Types refusés : inconnu, ou rapport de diagnostic (édité depuis le diagnostic).
    for invalid in ("INCONNU", "DIAGNOSTIC", "PORTEFEUILLE"):
        assert api.post(f"/api/v1/pmes/{pme.id}/reports", {"type": invalid}, format="json").status_code == 400
    # Étanchéité : une autre organisation ne voit ni la PME ni le rapport.
    outsider = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert outsider.post(f"/api/v1/pmes/{pme.id}/reports", {"type": "SUIVI"}, format="json").status_code == 404
    assert outsider.get(f"/api/v1/reports/{report['id']}/pdf").status_code == 404


def test_quarterly_task_edits_a_follow_up_for_each_accompanied_pme(api, pme_api, pme, diagnosed, org, make_pme):
    from pme360.reports.tasks import generate_quarterly_follow_up_reports

    _live_plan(api, pme_api, pme)
    make_pme(org, legal_name="Sans Plan SARL")
    assert generate_quarterly_follow_up_reports() == 1
    with tenant_context(org.id):
        report = Report.objects.get(type="SUIVI")
        assert report.pme_id == pme.id and report.generated_by is None
