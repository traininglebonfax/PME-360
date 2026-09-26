"""Reporting (phase 6, Document 9) : rapport PDF de diagnostic, vues analytiques, analyses de portefeuille."""

import io
from pathlib import Path

import pytest
from django.db import InternalError, ProgrammingError, connection, transaction
from pypdf import PdfReader

from pme360.analytics import portfolio
from pme360.analytics import services as analytics
from pme360.core.tenancy import tenant_context
from pme360.diagnostic.referential import install_gude360
from pme360.reports.builders import SECTIONS
from pme360.reports.models import Report
from pme360.scoring.models import ScoreSnapshot

from .test_diagnostic import answer_everything, start, validate_full

pytestmark = pytest.mark.django_db


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, make_pme, advisor):
    with tenant_context(org.id):
        install_gude360(org)
    return make_pme(org, legal_name="Rapport Test SARL", advisor=advisor, headcount=12, creation_date="2015-01-01")


@pytest.fixture
def api(client_for, advisor, org):
    return client_for(advisor, org)


@pytest.fixture
def validated(api, pme, django_capture_on_commit_callbacks):
    """Diagnostic validé ; le rapport est généré « après commit » (tâche de validation)."""
    diagnostic_id = start(api, pme)
    answer_everything(api, diagnostic_id, level=2)
    with django_capture_on_commit_callbacks(execute=True):
        validate_full(api, diagnostic_id)
    return diagnostic_id


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


# --- Rapport de diagnostic -----------------------------------------------------------------------------------------


def test_validation_generates_a_16_section_pdf_report(api, pme, validated):
    reports = api.get(f"/api/v1/pmes/{pme.id}/reports").json()
    assert len(reports) == 1
    report = reports[0]
    assert report["version"] == 1 and report["diagnostic"] == validated and report["type"] == "DIAGNOSTIC"
    response = api.get(f"/api/v1/reports/{report['id']}/pdf")
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    content = response.content
    assert content.startswith(b"%PDF") and len(content) == report["size_bytes"]
    text = _pdf_text(content)
    for number, title in enumerate(SECTIONS, start=1):
        assert f"{number}. {title}" in text, title
    assert "Rapport Test SARL" in text and "/100" in text
    with tenant_context(pme.organization_id):
        stored = Report.objects.get(pk=report["id"])
        assert len(stored.data_snapshot["sections"]) == 16
        snapshot = ScoreSnapshot.objects.get(diagnostic_id=validated, is_frozen=True)
        assert round(stored.data_snapshot["score"]["global"], 1) == float(snapshot.global_score)


def test_new_version_keeps_archive_and_reports_are_immutable(api, pme, validated):
    response = api.post(f"/api/v1/diagnostics/{validated}/report")
    assert response.status_code == 201 and response.json()["version"] == 2
    assert [r["version"] for r in api.get(f"/api/v1/pmes/{pme.id}/reports").json()] == [2, 1]
    with tenant_context(pme.organization_id):
        report = Report.objects.get(version=1)
        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
            Report.objects.filter(pk=report.pk).update(title="modifié")


def test_report_access_rights(api, pme, validated, org, other_org, make_user, client_for):
    report_id = api.get(f"/api/v1/pmes/{pme.id}/reports").json()[0]["id"]
    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert leader.get(f"/api/v1/reports/{report_id}/pdf").status_code == 200  # la PME reçoit son rapport
    assert leader.post(f"/api/v1/diagnostics/{validated}/report").status_code == 403
    outsider = client_for(make_user(org, "CONSEILLER"), org)  # hors portefeuille
    assert outsider.get(f"/api/v1/reports/{report_id}/pdf").status_code == 404
    stranger = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert stranger.get(f"/api/v1/reports/{report_id}/pdf").status_code == 404


def test_tampered_archive_is_refused(api, pme, validated, settings):
    report = api.get(f"/api/v1/pmes/{pme.id}/reports").json()[0]
    with tenant_context(pme.organization_id):
        key = Report.objects.get(pk=report["id"]).storage_key
    path = Path(settings.PME360_LOCAL_STORAGE_ROOT) / key
    path.write_bytes(path.read_bytes() + b"x")
    response = api.get(f"/api/v1/reports/{report['id']}/pdf")
    assert response.status_code == 400 and response.json()["code"] == "integrity_error"


# --- Vues analytiques --------------------------------------------------------------------------------------------


def test_analytics_views_are_tenant_isolated(org, other_org, make_pme, make_user):
    from pme360.accounts.access import build_access

    make_pme(org, legal_name="PME A")
    make_pme(other_org, legal_name="PME B")
    analytics.refresh()
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM v_pme_current_state")  # hors contexte : rien
        assert cursor.fetchone()[0] == 0
    with tenant_context(org.id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT legal_name FROM v_pme_current_state")
            assert [row[0] for row in cursor.fetchall()] == ["PME A"]
        admin = make_user(org, "ADMIN_ORG")
        assert [s["legal_name"] for s in analytics.current_states(build_access(admin, org.id))] == ["PME A"]


def test_materialized_views_are_only_read_through_filtered_views():
    """Une vue matérialisée ignore la RLS : aucun code ne doit la lire directement (seulement v_*)."""
    root = Path(__file__).resolve().parents[1] / "pme360"
    allowed = {root / "analytics" / "sql.py", root / "analytics" / "services.py"}
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path not in allowed and "migrations" not in path.parts and "mv_" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_portfolio_kpis_match_the_underlying_data(api, pme, validated, org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    analytics.refresh()
    data = admin.get("/api/v1/dashboards/portfolio").json()
    with tenant_context(org.id):
        live = ScoreSnapshot.objects.filter(pme=pme, kind="LIVE").first()
        frozen = ScoreSnapshot.objects.get(pme=pme, is_frozen=True)
        expected = (
            live.global_score if live and live.result.get("source_diagnostic") == validated else frozen.global_score
        )
    assert data["kpis"]["pmes_total"] == 1 and data["kpis"]["pmes_diagnosed"] == 1
    assert data["kpis"]["average_score"] == round(float(expected), 1)
    assert data["definitions"]["pmes_accompanied"].startswith("PME ayant un plan")
    analyses = admin.get("/api/v1/dashboards/portfolio/analyses").json()
    dims = analyses["frequent_problems"]["dimensions"]
    assert len(dims) == 12 and all(d["evaluated"] == 1 for d in dims)
    assert analyses["trajectories"]["notice"] == portfolio.RM09
    cells = analyses["sector_heatmap"]["cells"]
    assert cells and all(c["average"] is None and c["n"] < 5 for c in cells)  # masquées si n < 5


def test_portfolio_table_and_csv_export(api, pme, validated, org, make_user, client_for):
    analytics.refresh()
    rows = api.get("/api/v1/dashboards/portfolio/pmes").json()
    assert [r["legal_name"] for r in rows] == ["Rapport Test SARL"] and rows[0]["current_score"] is not None
    export = api.get("/api/v1/dashboards/portfolio/pmes", {"export": "csv"})
    assert export["Content-Type"].startswith("text/csv")
    lines = export.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("PME;Secteur;Région") and lines[1].startswith("Rapport Test SARL;")
    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert leader.get("/api/v1/dashboards/portfolio/pmes").status_code == 403
