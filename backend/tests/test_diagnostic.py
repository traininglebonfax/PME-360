"""Référentiel versionné, parcours de diagnostic (questionnaire → revue → validation → snapshot) et comparaison."""

import pytest
from django.db import InternalError, ProgrammingError, connection, transaction

from pme360.core.tenancy import tenant_context
from pme360.diagnostic.models import AnswerHistory, Criterion, Diagnostic, FrameworkVersion
from pme360.diagnostic.referential import install_gude360, publish_version, validate_version
from pme360.pmes.models import LegalForm, Pme, Sector
from pme360.scoring import services as scoring
from pme360.scoring.models import ScoreSnapshot

pytestmark = pytest.mark.django_db

FINANCIALS = {
    "ca_n": 500_000_000,
    "ca_n1": 450_000_000,
    "ebe": 60_000_000,
    "resultat_net": 25_000_000,
    "dotations": 10_000_000,
    "capitaux_propres": 120_000_000,
    "total_passif": 300_000_000,
    "dettes_financieres": 60_000_000,
    "actif_circulant": 180_000_000,
    "passif_circulant": 130_000_000,
    "creances_clients": 70_000_000,
    "part_client_1": 30,
    "part_clients_top5": 55,
    "part_fournisseur_1": 25,
}


@pytest.fixture
def framework(org):
    with tenant_context(org.id):
        return install_gude360(org)


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, framework, make_pme, advisor):
    pme = make_pme(org, advisor=advisor, headcount=12, creation_date="2015-01-01")
    with tenant_context(org.id):
        Pme.objects.filter(pk=pme.pk).update(
            legal_form=LegalForm.objects.get(code="SARL"), lifecycle_status=Pme.LifecycleStatus.ONBOARDING
        )
    return pme


@pytest.fixture
def api(client_for, advisor, org):
    return client_for(advisor, org)


def start(api, pme, kind="INITIAL", reference_date="2026-03-15"):
    response = api.post(
        f"/api/v1/pmes/{pme.id}/diagnostics", {"type": kind, "reference_date": reference_date}, format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()["id"]


def answer_everything(api, diagnostic_id, level=2, financials=FINANCIALS, overrides=None):
    questionnaire = api.get(f"/api/v1/diagnostics/{diagnostic_id}/questionnaire").json()
    overrides = overrides or {}
    answers = []
    for step in questionnaire["steps"]:
        for question in step["questions"]:
            code = question["code"]
            if code in overrides:
                value = overrides[code]
            elif question["type"] == "SINGLE":
                value = next(o["value"] for o in question["options"] if o["level"] == level)
            elif question["type"] == "BOOLEAN":
                value = False
            elif code == "PRO-EFF":
                value = 12
            elif code.startswith("FIN-IN-"):
                value = financials.get(code.removeprefix("FIN-IN-"))
            else:
                continue
            answers.append({"question": code, "value": value})
    response = api.put(f"/api/v1/diagnostics/{diagnostic_id}/answers", {"answers": answers}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def validate_full(api, diagnostic_id):
    assert api.post(f"/api/v1/diagnostics/{diagnostic_id}/submit").status_code == 200
    assert api.post(f"/api/v1/diagnostics/{diagnostic_id}/review/accept-remaining").status_code == 200
    response = api.post(f"/api/v1/diagnostics/{diagnostic_id}/validate")
    assert response.status_code == 200, response.content
    return response.json()


# --- Référentiel -------------------------------------------------------------------------------------------


def test_gude360_is_installed_valid_and_published(org, framework):
    with tenant_context(org.id):
        assert framework.status == FrameworkVersion.Status.PUBLISHED
        validate_version(framework)  # aucune anomalie
        assert Criterion.objects.filter(framework_version=framework).count() >= 90
        assert Criterion.objects.filter(framework_version=framework, is_critical=True).count() == 8
        assert install_gude360(org).pk == framework.pk  # idempotent


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE criterion SET weight = 99",
        "DELETE FROM question",
        "UPDATE framework_version SET settings = '{}'::jsonb",
    ],
)
def test_published_framework_is_immutable(org, framework, statement):
    with tenant_context(org.id):
        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(statement)


def test_clone_edit_and_publish_new_version(org, framework, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert (
        advisor.post(
            f"/api/v1/framework-versions/{framework.id}/clone", {"version": "1.1.0"}, format="json"
        ).status_code
        == 403
    )
    response = admin.post(f"/api/v1/framework-versions/{framework.id}/clone", {"version": "1.1.0"}, format="json")
    assert response.status_code == 201
    draft_id = response.json()["id"]
    with tenant_context(org.id):
        draft = FrameworkVersion.objects.get(pk=draft_id)
        # Un brouillon se modifie librement ; une pondération incohérente bloque la publication.
        Criterion.objects.filter(framework_version=draft, code="FOR-01").update(weight=25)
    bad = admin.post(f"/api/v1/framework-versions/{draft_id}/publish")
    assert bad.status_code == 400 and any("D01" in e for e in bad.json()["errors"]["framework_version"])
    with tenant_context(org.id):
        Criterion.objects.filter(framework_version=draft, code="FOR-01").update(weight=20)
    assert admin.post(f"/api/v1/framework-versions/{draft_id}/publish").status_code == 200
    with tenant_context(org.id):
        framework.refresh_from_db()
        assert framework.status == FrameworkVersion.Status.RETIRED
    detail = advisor.get(f"/api/v1/framework-versions/{draft_id}").json()
    assert detail["status"] == "PUBLISHED" and len(detail["dimensions"]) == 12


def test_publish_requires_draft(org, framework):
    from rest_framework.exceptions import ValidationError

    with tenant_context(org.id), pytest.raises(ValidationError):
        publish_version(framework, None)


# --- Démarrage et questionnaire ------------------------------------------------------------------------------


def test_start_diagnostic_moves_pme_to_diagnostic(api, pme, org):
    diagnostic_id = start(api, pme)
    with tenant_context(org.id):
        assert Pme.objects.get(pk=pme.pk).lifecycle_status == Pme.LifecycleStatus.DIAGNOSTIC_EN_COURS
    duplicate = api.post(f"/api/v1/pmes/{pme.id}/diagnostics", {"type": "INITIAL"}, format="json")
    assert duplicate.status_code == 400 or duplicate.status_code == 409
    follow_up = api.post(f"/api/v1/diagnostics/{diagnostic_id}/cancel", {"reason": "Test"}, format="json")
    assert follow_up.status_code == 200
    assert api.post(f"/api/v1/pmes/{pme.id}/diagnostics", {"type": "SUIVI"}, format="json").json()["code"] == (
        "initial_required"
    )


def test_questionnaire_adapts_to_profile_and_audience(api, pme, org, make_user, client_for):
    diagnostic_id = start(api, pme)

    def codes(client):
        payload = client.get(f"/api/v1/diagnostics/{diagnostic_id}/questionnaire").json()
        return {q["code"]: q for step in payload["steps"] for q in step["questions"]}, payload

    questions, payload = codes(api)
    assert payload["steps"][0]["code"] == "PROFIL"
    assert questions["PRO-EFF"]["value"] == 12  # pré-rempli depuis la fiche PME
    assert "Q-SOC-03" in questions  # la PME a des salariés
    assert "Q-FOR-08" not in questions  # pas une entreprise familiale (réponse inconnue)
    assert "Q-OPE-COMM-01" in questions and "Q-OPE-BTP-01" not in questions  # module sectoriel commerce
    assert "level" in questions["Q-FOR-01"]["options"][0]

    api.put(
        f"/api/v1/diagnostics/{diagnostic_id}/answers",
        {"answers": [{"question": "PRO-EFF", "value": 0}, {"question": "PRO-FAM", "value": True}]},
        format="json",
    )
    questions, _ = codes(api)
    assert "Q-SOC-03" not in questions and "Q-FOR-08" in questions

    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    pme_questions, pme_payload = codes(leader)
    assert pme_payload["editable"] is True
    assert "level" not in pme_questions["Q-FOR-01"]["options"][0]  # pas de niveaux affichés à la PME


def test_answer_validation_and_history(api, pme, org):
    diagnostic_id = start(api, pme)
    url = f"/api/v1/diagnostics/{diagnostic_id}/answers"
    assert api.put(url, {"answers": [{"question": "Q-FOR-01", "value": "9"}]}, format="json").status_code == 400
    assert (
        api.put(url, {"answers": [{"question": "FIN-IN-part_client_1", "value": 150}]}, format="json").status_code
        == 400
    )
    assert api.put(url, {"answers": [{"question": "INCONNUE", "value": 1}]}, format="json").status_code == 400
    assert api.put(url, {"answers": [{"question": "Q-FOR-01", "value": "1"}]}, format="json").status_code == 200
    assert api.put(url, {"answers": [{"question": "Q-FOR-01", "value": "3"}]}, format="json").status_code == 200
    with tenant_context(org.id):
        assert list(AnswerHistory.objects.values_list("value", flat=True)) == ["1"]


def test_submit_requires_completion(api, pme):
    diagnostic_id = start(api, pme)
    response = api.post(f"/api/v1/diagnostics/{diagnostic_id}/submit")
    assert response.status_code == 400 and response.json()["code"] == "incomplete"


# --- Revue, validation, snapshot -----------------------------------------------------------------------------


def test_full_diagnostic_produces_frozen_reproducible_snapshot(api, pme, org, make_user, client_for):
    diagnostic_id = start(api, pme)
    progress = answer_everything(api, diagnostic_id, level=3)["progress"]
    assert progress["completion"] == 1.0
    assert api.post(f"/api/v1/diagnostics/{diagnostic_id}/submit").json()["status"] == "EN_REVUE"

    review_url = f"/api/v1/diagnostics/{diagnostic_id}/review"
    review = api.get(review_url).json()
    assert review["pending"] and review["preview"]["global_score"] is not None
    no_reason = api.post(f"{review_url}/FIN-03", {"status": "MODIFIE", "level_final": 1}, format="json")
    assert no_reason.status_code == 400 and "comment" in no_reason.json()["errors"]
    assert (
        api.post(
            f"{review_url}/FIN-03",
            {"status": "MODIFIE", "level_final": 1, "comment": "Pas de rapprochement bancaire constaté en entretien"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        api.post(f"{review_url}/FOR-05", {"status": "VALIDE", "corroborated": True}, format="json").status_code == 200
    )
    blocked = api.post(f"/api/v1/diagnostics/{diagnostic_id}/validate")
    assert blocked.status_code == 400 and blocked.json()["code"] == "review_incomplete"
    assert api.post(f"{review_url}/accept-remaining").json()["accepted"] > 50
    validated = api.post(f"/api/v1/diagnostics/{diagnostic_id}/validate").json()
    assert validated["status"] == "VALIDE" and validated["snapshot_id"]

    health = api.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    snapshot = health["snapshot"]
    result = snapshot["result"]
    assert snapshot["kind"] == "BASELINE" and health["baseline"]["id"] == snapshot["id"]
    fin03 = next(c for c in result["criteria"] if c["code"] == "FIN-03")
    assert fin03["level"] == 1
    for005 = next(c for c in result["criteria"] if c["code"] == "FOR-05")
    assert for005["source"] == "DECLARATIF_CORROBORE"
    # Critères de conformité plafonnés sans preuve vérifiée : niveau « Maîtrisée » inaccessible en phase 2.
    assert next(c for c in result["criteria"] if c["code"] == "FOR-01")["capped"]
    assert snapshot["maturity_level"] <= 3
    marge = next(m for m in result["metrics"] if m["code"] == "MARGE_NETTE")
    assert marge["value"] == pytest.approx(0.05) and marge["band"] == "Bon"
    assert snapshot["intervention_priority"] in {"P1", "P2", "P3", "P4"}

    with tenant_context(org.id):
        diagnostic = Diagnostic.objects.get(pk=diagnostic_id)
        stored = ScoreSnapshot.objects.get(pk=snapshot["id"])
        # Reproductibilité : le recalcul à partir des mêmes entrées donne exactement le résultat figé.
        assert scoring.compute(diagnostic) == stored.result
        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
            ScoreSnapshot.objects.filter(pk=stored.pk).update(global_score=99)

    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    assert leader.get(f"/api/v1/pmes/{pme.id}/health-check").json()["snapshot"]["id"] == snapshot["id"]


def test_follow_up_is_prefilled_and_change_is_explained(api, pme, org):
    first = start(api, pme, reference_date="2025-09-15")
    answer_everything(api, first, level=1)
    validate_full(api, first)
    second = start(api, pme, kind="SUIVI", reference_date="2026-03-15")
    questionnaire = api.get(f"/api/v1/diagnostics/{second}/questionnaire").json()
    sources = {q["source"] for step in questionnaire["steps"] for q in step["questions"] if q["answered"]}
    assert sources == {"REPRISE"}
    answer_everything(api, second, level=3)
    validate_full(api, second)

    health = api.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    history = health["history"]
    assert [h["kind"] for h in history] == ["BASELINE", "FOLLOW_UP"]
    comparison = api.get(f"/api/v1/snapshots/{history[1]['id']}/compare/{history[0]['id']}").json()
    assert comparison["delta_global"] > 0 and not comparison["reprojected_baseline"]
    assert sum(c["contribution"] for c in comparison["contributions"]) == pytest.approx(
        comparison["delta_global"] - comparison["other"], abs=0.05
    )


def test_pme_leader_answers_but_cannot_review(org, pme, api, make_user, client_for):
    diagnostic_id = start(api, pme)
    leader = client_for(make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id), org)
    ok = leader.put(
        f"/api/v1/diagnostics/{diagnostic_id}/answers",
        {"answers": [{"question": "Q-FOR-01", "value": "3"}]},
        format="json",
    )
    assert ok.status_code == 200
    reserved = leader.put(
        f"/api/v1/diagnostics/{diagnostic_id}/answers",
        {"answers": [{"question": "Q-FOR-01", "value": "9"}]},
        format="json",
    )
    assert reserved.status_code == 400
    assert leader.get(f"/api/v1/diagnostics/{diagnostic_id}/review").status_code == 403
    assert leader.post(f"/api/v1/pmes/{pme.id}/diagnostics", {"type": "INITIAL"}, format="json").status_code == 403


def test_other_advisor_cannot_see_diagnostic(org, pme, api, make_user, client_for):
    diagnostic_id = start(api, pme)
    stranger = client_for(make_user(org, "CONSEILLER"), org)
    assert stranger.get(f"/api/v1/diagnostics/{diagnostic_id}/questionnaire").status_code == 404
    assert stranger.get(f"/api/v1/pmes/{pme.id}/health-check").status_code == 404


def test_sector_module_follows_pme_sector(org, framework, make_pme, advisor, client_for):
    with tenant_context(org.id):
        btp = make_pme(org, advisor=advisor, headcount=30)
        Pme.objects.filter(pk=btp.pk).update(sector=Sector.objects.get(code="BTP"))
    client = client_for(advisor, org)
    diagnostic_id = start(client, btp)
    payload = client.get(f"/api/v1/diagnostics/{diagnostic_id}/questionnaire").json()
    codes = {q["code"] for step in payload["steps"] for q in step["questions"]}
    assert "Q-OPE-BTP-01" in codes and "Q-OPE-COMM-01" not in codes
