"""Accompagnement (phase 5, Document 7) : règles, recommandations, plan, actions, livrables, score mis à jour."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from pme360.alerts import engine as alerts
from pme360.alerts.models import Alert
from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context
from pme360.diagnostic.referential import install_gude360
from pme360.plans import priority
from pme360.plans.models import Action, ActionTransition, CriterionProgress, RecommendationRule

from . import files
from .test_diagnostic import answer_everything, start, validate_full

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
def leader(org, pme, make_user):
    return make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)


@pytest.fixture
def api(client_for, advisor, org):
    return client_for(advisor, org)


@pytest.fixture
def pme_api(client_for, leader, org):
    return client_for(leader, org)


@pytest.fixture
def run_pipeline(django_capture_on_commit_callbacks):
    def runner(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    return runner


@pytest.fixture
def diagnosed(api, pme):
    """Diagnostic validé avec des pratiques faibles (niveau 1) : les règles se déclenchent."""
    diagnostic_id = start(api, pme)
    answer_everything(api, diagnostic_id, level=1)
    validate_full(api, diagnostic_id)
    return diagnostic_id


def _recommendations(api, pme):
    response = api.post(f"/api/v1/pmes/{pme.id}/recommendations")
    assert response.status_code == 200, response.content
    return {r["offer"]["code"]: r for r in response.json()}


def _decide(api, rec, status, **extra):
    response = api.post(f"/api/v1/recommendations/{rec['id']}/decision", {"status": status, **extra}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def _live_plan(api, pme_api, pme, accept=("OFF-RH-BASE", "OFF-FIN-TRESO", "OFF-FIN-REPORTING")):
    recs = _recommendations(api, pme)
    for code in accept:
        _decide(api, recs[code], "ACCEPTEE")
    plan = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json").json()
    for step in ("submit", "validate"):
        assert api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": step}, format="json").status_code == 200
    response = pme_api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "accept"}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def _upload_deliverable(client, pme, deliverable_id, name="livrable.pdf"):
    payload = {"file": SimpleUploadedFile(name, files.pdf()), "deliverable_id": deliverable_id}
    response = client.post(f"/api/v1/pmes/{pme.id}/documents", payload, format="multipart")
    assert response.status_code == 201, response.content
    return response.json()["id"]


def _criterion(result, code):
    return next(c for c in result["criteria"] if c["code"] == code)


# --- Recommandations ---------------------------------------------------------------------------------------------


def test_rules_propose_scored_recommendations_with_rationale(api, pme, diagnosed):
    recs = _recommendations(api, pme)
    assert {"OFF-RH-BASE", "OFF-FIN-TRESO", "OFF-SOC-CNPS", "OFF-RIS-CI"} <= set(recs)
    rh = recs["OFF-RH-BASE"]
    assert rh["source"] == "REGLE" and rh["rules"] == [{"code": "R-RHO-001", "version": 1}]
    assert "RHO-01 niveau 1" in rh["rationale"] and "{{" not in rh["rationale"]
    assert all(1 <= rh[axis] <= 5 for axis in ("impact", "urgency", "risk", "effort"))
    assert 13 <= rh["priority_computed"] <= 100
    assert rh["evidence_refs"]["criteria"]["RHO-01"]["level"] == 1
    # Une obligation légale non prouvée est urgente (Document 6, § 9.1).
    assert recs["OFF-SOC-CNPS"]["urgency"] == 5
    # Offre de croissance non proposée sous le niveau N3.
    assert "OFF-FIO-DOSSIER" not in recs
    # Idempotent : relancer ne duplique rien.
    assert len(_recommendations(api, pme)) == len(recs)


def test_recommendations_require_a_validated_diagnostic(api, pme):
    response = api.post(f"/api/v1/pmes/{pme.id}/recommendations")
    assert response.status_code == 400 and response.json()["code"] == "no_validated_diagnostic"


def test_review_reject_needs_reason_and_priority_override_is_justified(api, pme, diagnosed):
    recs = _recommendations(api, pme)
    rec = recs["OFF-DIG-SECU"]
    bad = api.post(f"/api/v1/recommendations/{rec['id']}/decision", {"status": "REJETEE"}, format="json")
    assert bad.status_code == 400 and "reason" in bad.json()["errors"]
    no_reason = api.post(
        f"/api/v1/recommendations/{rec['id']}/decision", {"status": "ACCEPTEE", "urgency": 5}, format="json"
    )
    assert no_reason.status_code == 400 and "priority_reason" in no_reason.json()["errors"]
    accepted = _decide(api, rec, "ACCEPTEE", urgency=5, priority_reason="Perte de données récente")
    assert accepted["urgency"] == 5 and accepted["priority_final"] != accepted["priority_computed"]
    assert accepted["priority_override_reason"] == "Perte de données récente"
    # Une décision prise n'est pas écrasée par une nouvelle génération.
    assert _recommendations(api, pme)["OFF-DIG-SECU"]["status"] == "ACCEPTEE"


def test_manual_recommendation_by_advisor(api, pme, diagnosed):
    response = api.post(
        f"/api/v1/pmes/{pme.id}/recommendations/manual",
        {"offer_code": "OFF-OPE-ACHATS", "problem": "Achats non tracés", "rationale": "Constaté lors de la visite."},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["source"] == "CONSEILLER" and response.json()["status"] == "ACCEPTEE"


# --- Plan ----------------------------------------------------------------------------------------------------------


def test_plan_generation_orders_horizons_and_dependencies(api, pme, diagnosed):
    recs = _recommendations(api, pme)
    for code in ("OFF-RH-BASE", "OFF-FIN-TRESO", "OFF-FIN-REPORTING"):
        _decide(api, recs[code], "ACCEPTEE")
    response = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json")
    assert response.status_code == 201, response.content
    plan = response.json()
    assert plan["status"] == "BROUILLON" and plan["version"] == 1
    actions = {a["offer_code"]: a for a in plan["actions"]}
    tréso, reporting = actions["OFF-FIN-TRESO"], actions["OFF-FIN-REPORTING"]
    assert reporting["status"] == "BLOQUE" and reporting["depends_on"][0]["id"] == tréso["id"]
    assert priority.PHASE_ORDER.index(reporting["phase"]) > priority.PHASE_ORDER.index(tréso["phase"])
    assert tréso["human_ref"].startswith(f"ACT-{timezone.localdate().year}-")
    assert "Constat" in actions["OFF-RH-BASE"]["why"]
    detail = api.get(f"/api/v1/actions/{actions['OFF-RH-BASE']['id']}").json()
    assert [d["document_type_code"] for d in detail["deliverables"]] == ["ORGANIGRAMME", "FICHES_POSTE"]
    assert detail["deliverables"][0]["template"]["instructions"]
    # Régénérer un brouillon remplace ses actions sans doublon.
    again = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json").json()
    assert again["id"] == plan["id"] and len(again["actions"]) == 3


def test_plan_validation_then_pme_acceptance(api, pme_api, pme, diagnosed):
    recs = _recommendations(api, pme)
    _decide(api, recs["OFF-RH-BASE"], "ACCEPTEE")
    plan = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json").json()
    assert pme_api.get(f"/api/v1/pmes/{pme.id}/plan").status_code == 204  # brouillon invisible pour la PME
    assert (
        pme_api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "submit"}, format="json").status_code == 404
    )
    api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "submit"}, format="json")
    early = pme_api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "accept"}, format="json")
    assert early.status_code == 404  # pas encore validé par GUDE-PME : invisible
    api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "validate"}, format="json")
    assert pme_api.get(f"/api/v1/pmes/{pme.id}/plan").json()["status"] == "EN_VALIDATION"
    accepted = pme_api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "accept"}, format="json").json()
    assert accepted["status"] == "VALIDE" and accepted["accepted_by_name"]
    with tenant_context(pme.organization_id):
        assert AuditLog.objects.filter(action="plan.accept").exists()


def test_actions_cannot_start_before_acceptance(api, pme, diagnosed):
    recs = _recommendations(api, pme)
    _decide(api, recs["OFF-RH-BASE"], "ACCEPTEE")
    plan = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json").json()
    response = api.post(f"/api/v1/actions/{plan['actions'][0]['id']}/transition", {"to": "EN_COURS"}, format="json")
    assert response.status_code == 400 and response.json()["code"] == "plan_not_live"


# --- Parcours complet : de la faiblesse au score mis à jour --------------------------------------------------------


def test_verified_deliverables_finish_action_and_raise_live_score(api, pme_api, pme, diagnosed, run_pipeline):
    plan = _live_plan(api, pme_api, pme)
    rh = next(a for a in plan["actions"] if a["offer_code"] == "OFF-RH-BASE")
    started = pme_api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_COURS"}, format="json")
    assert started.status_code == 200 and started.json()["started_at"]
    assert api.get(f"/api/v1/pmes/{pme.id}/plan").json()["status"] == "EN_COURS"
    before = api.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    before_score = (before["live"] or before["snapshot"])["global_score"]

    organigramme, fiches = started.json()["deliverables"]
    document_id = run_pipeline(lambda: _upload_deliverable(pme_api, pme, organigramme["id"], "organigramme.pdf"))
    action = api.get(f"/api/v1/actions/{rh['id']}").json()
    assert action["status"] == "A_VERIFIER" and action["deliverables"][0]["status"] == "A_VERIFIER"

    api.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")
    action = api.get(f"/api/v1/actions/{rh['id']}").json()
    assert action["deliverables"][0]["status"] == "CONFORME" and action["status"] == "DOCUMENT_DEMANDE"

    # Livrable refusé : motif renvoyé à la PME, puis nouveau dépôt (nouvelle version du même document).
    fiches_doc = run_pipeline(lambda: _upload_deliverable(pme_api, pme, fiches["id"], "fiches.pdf"))
    api.post(
        f"/api/v1/documents/{fiches_doc}/verify",
        {"decision": "NON_CONFORME", "reason": "Il manque la fiche du comptable."},
        format="json",
    )
    action = api.get(f"/api/v1/actions/{rh['id']}").json()
    assert action["status"] == "NON_CONFORME" and action["deliverables"][1]["reason"].startswith("Il manque")
    again = run_pipeline(lambda: _upload_deliverable(pme_api, pme, fiches["id"], "fiches-v2.pdf"))
    assert again == fiches_doc
    api.post(f"/api/v1/documents/{fiches_doc}/verify", {"decision": "CONFORME"}, format="json")

    action = api.get(f"/api/v1/actions/{rh['id']}").json()
    assert action["status"] == "TERMINE" and action["completed_at"]
    assert {t["to_status"] for t in action["transitions"]} >= {"CONFORME", "TERMINE"}
    with tenant_context(pme.organization_id):
        assert set(CriterionProgress.objects.filter(pme=pme).values_list("criterion_code", flat=True)) == {
            "RHO-01",
            "RHO-02",
        }
    health = api.get(f"/api/v1/pmes/{pme.id}/health-check").json()
    rho01 = _criterion(health["live"]["result"], "RHO-01")
    assert rho01["level"] == 3 and rho01["proven"] and rho01["progress"] == action["human_ref"]
    assert health["live"]["global_score"] > before_score
    assert _criterion(health["snapshot"]["result"], "RHO-01")["level"] == 1  # snapshot figé inchangé (RM-04)
    # La situation s'est améliorée : l'offre RH n'est plus proposée (seule la recommandation convertie reste).
    assert _recommendations(api, pme)["OFF-RH-BASE"]["status"] == "CONVERTIE"


def test_finishing_a_prerequisite_unblocks_dependents(api, pme_api, pme, diagnosed, run_pipeline):
    plan = _live_plan(api, pme_api, pme)
    tréso = next(a for a in plan["actions"] if a["offer_code"] == "OFF-FIN-TRESO")
    reporting = next(a for a in plan["actions"] if a["offer_code"] == "OFF-FIN-REPORTING")
    blocked = pme_api.post(f"/api/v1/actions/{reporting['id']}/transition", {"to": "EN_COURS"}, format="json")
    assert blocked.status_code == 400  # une action bloquée ne démarre pas
    started = pme_api.post(f"/api/v1/actions/{tréso['id']}/transition", {"to": "EN_COURS"}, format="json").json()
    document_id = run_pipeline(lambda: _upload_deliverable(pme_api, pme, started["deliverables"][0]["id"]))
    api.post(f"/api/v1/documents/{document_id}/verify", {"decision": "CONFORME"}, format="json")
    assert api.get(f"/api/v1/actions/{tréso['id']}").json()["status"] == "TERMINE"
    unblocked = api.get(f"/api/v1/actions/{reporting['id']}").json()
    assert unblocked["status"] == "NON_COMMENCE"
    assert unblocked["transitions"][-1]["actor_type"] == "SYSTEM"


def test_pme_permissions_and_abandon_reason(api, pme_api, pme, diagnosed):
    plan = _live_plan(api, pme_api, pme)
    rh = next(a for a in plan["actions"] if a["offer_code"] == "OFF-RH-BASE")
    forbidden = pme_api.post(
        f"/api/v1/actions/{rh['id']}/transition", {"to": "ABANDONNE", "reason": "x"}, format="json"
    )
    assert forbidden.status_code == 403
    no_reason = api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "ABANDONNE"}, format="json")
    assert no_reason.status_code == 400
    steps = [{"title": s["title"], "done": i == 0} for i, s in enumerate(rh["sub_actions"])]
    ticked = pme_api.patch(f"/api/v1/actions/{rh['id']}", {"sub_actions": steps}, format="json")
    assert ticked.status_code == 200 and ticked.json()["sub_actions"][0]["done"]
    renamed = pme_api.patch(f"/api/v1/actions/{rh['id']}", {"due_date": "2030-01-01"}, format="json")
    assert renamed.status_code == 403
    finish = api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "TERMINE"}, format="json")
    assert finish.status_code == 400  # pas encore EN_COURS
    api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_COURS"}, format="json")
    pending = api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "TERMINE"}, format="json")
    assert pending.status_code == 400 and pending.json()["code"] == "deliverables_pending"


def test_dependency_cycles_are_refused(api, pme_api, pme, diagnosed):
    plan = _live_plan(api, pme_api, pme)
    tréso = next(a for a in plan["actions"] if a["offer_code"] == "OFF-FIN-TRESO")
    reporting = next(a for a in plan["actions"] if a["offer_code"] == "OFF-FIN-REPORTING")
    cycle = api.post(f"/api/v1/actions/{tréso['id']}/dependencies", {"depends_on": reporting["id"]}, format="json")
    assert cycle.status_code == 400 and "cycle" in str(cycle.json()["errors"])


def test_overdue_action_raises_alert(api, pme_api, pme, diagnosed):
    plan = _live_plan(api, pme_api, pme)
    rh = next(a for a in plan["actions"] if a["offer_code"] == "OFF-RH-BASE")
    today = timezone.localdate()
    with tenant_context(pme.organization_id):
        Action.objects.filter(pk=rh["id"]).update(due_date=today - timedelta(days=20))
        alerts.evaluate_pme(pme, today)
        alert = Alert.objects.get(rule__kind="ACTION_RETARD", pme=pme)
    assert alert.severity == "ELEVEE" and "20 j de retard" in alert.message
    listed = api.get("/api/v1/actions", {"overdue": "1"}).json()
    assert [a["id"] for a in listed] == [rh["id"]] and listed[0]["overdue"]


def test_new_plan_version_keeps_history_and_open_actions(api, pme_api, pme, diagnosed):
    plan = _live_plan(api, pme_api, pme)
    recs = _recommendations(api, pme)
    _decide(api, recs["OFF-DIG-SECU"], "ACCEPTEE")
    response = api.post(f"/api/v1/plans/{plan['id']}/new-version", {"reason": "Réévaluation à 6 mois"}, format="json")
    assert response.status_code == 201, response.content
    new = response.json()
    assert new["version"] == 2 and new["status"] == "BROUILLON"
    assert {a["offer_code"] for a in new["actions"]} == {
        "OFF-RH-BASE",
        "OFF-FIN-TRESO",
        "OFF-FIN-REPORTING",
        "OFF-DIG-SECU",
    }
    history = api.get(f"/api/v1/pmes/{pme.id}/plans").json()
    assert [p["status"] for p in history] == ["BROUILLON", "CLOS"]
    assert "Réévaluation" in history[1]["close_reason"]


def test_actions_are_tenant_isolated(api, pme_api, pme, diagnosed, other_org, make_user, client_for):
    plan = _live_plan(api, pme_api, pme)
    stranger = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert stranger.get(f"/api/v1/actions/{plan['actions'][0]['id']}").status_code == 404
    assert stranger.get(f"/api/v1/plans/{plan['id']}").status_code == 404


# --- Règles et priorisation ---------------------------------------------------------------------------------------


def test_rule_versioning_requires_test_before_activation(org, make_user, client_for, api, pme, diagnosed):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    payload = {
        "code": "R-RHO-001",
        "name": "Organisation RH non formalisée (v2)",
        "condition": {"<=": [{"var": "criterion.RHO-01.level"}, 1]},
        "offer_code": "OFF-RH-BASE",
        "problem_template": "Pas d'organigramme",
        "rationale_template": "Organigramme au niveau {{criterion.RHO-01.level}}.",
    }
    created = admin.post("/api/v1/recommendation-rules", payload, format="json")
    assert created.status_code == 201, created.content
    rule = created.json()
    assert rule["version"] == 2 and rule["status"] == "DRAFT"
    not_tested = admin.post(f"/api/v1/recommendation-rules/{rule['id']}/activate")
    assert not_tested.status_code == 400 and not_tested.json()["code"] == "not_tested"
    tested = admin.post(f"/api/v1/recommendation-rules/{rule['id']}/test").json()
    assert tested["evaluated"] == 1 and tested["matched"][0]["pme_name"] == "Atelier Test SARL"
    assert "niveau 1" in tested["matched"][0]["rationale"]
    assert admin.post(f"/api/v1/recommendation-rules/{rule['id']}/activate").json()["status"] == "ACTIVE"
    with tenant_context(org.id):
        statuses = dict(RecommendationRule.objects.filter(code="R-RHO-001").values_list("version", "status"))
    assert statuses == {1: "INACTIVE", 2: "ACTIVE"}
    bad = admin.post("/api/v1/recommendation-rules", {**payload, "condition": {"exec": ["rm"]}}, format="json")
    assert bad.status_code == 400
    assert api.post("/api/v1/recommendation-rules", payload, format="json").status_code == 403


def test_priority_score_formula_and_bounds():
    settings = priority.settings_for(type("O", (), {"settings": {}})())
    assert priority.priority_score(5, 5, 5, 1, settings) == 100.0
    assert priority.priority_score(1, 1, 1, 5, settings) == 13.0
    assert priority.priority_score(4, 3, 3, 2, settings) == round(20 * (1.6 + 0.9 + 0.9) * 0.95, 1)


def test_phase_assignment_respects_dependencies_and_capacity():
    items = [{"key": f"A{i}", "phase": "J1_30", "depends": []} for i in range(6)]
    items.append({"key": "B", "phase": "J1_30", "depends": ["A0"]})
    priority.assign_phases(items, capacity=5)
    phases = {i["key"]: i["phase"] for i in items}
    assert sum(p == "J1_30" for p in phases.values()) == 5
    assert phases["A5"] == "J31_60" and phases["B"] == "J31_60"


def test_transition_log_is_append_only(api, pme_api, pme, diagnosed):
    from django.db import InternalError, ProgrammingError, transaction

    plan = _live_plan(api, pme_api, pme)
    api.post(f"/api/v1/actions/{plan['actions'][0]['id']}/transition", {"to": "EN_COURS"}, format="json")
    with tenant_context(pme.organization_id):
        entry = ActionTransition.objects.first()
        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
            ActionTransition.objects.filter(pk=entry.pk).update(reason="modifié")


def test_advisor_records_offline_acceptance_with_reason(api, pme, diagnosed):
    recs = _recommendations(api, pme)
    _decide(api, recs["OFF-RH-BASE"], "ACCEPTEE")
    plan = api.post(f"/api/v1/pmes/{pme.id}/plan/generate", {}, format="json").json()
    for step in ("submit", "validate"):
        api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": step}, format="json")
    missing = api.post(f"/api/v1/plans/{plan['id']}/transition", {"action": "accept_offline"}, format="json")
    assert missing.status_code == 400 and "reason" in missing.json()["errors"]
    accepted = api.post(
        f"/api/v1/plans/{plan['id']}/transition",
        {"action": "accept_offline", "reason": "Accepté en entretien, PV signé le 26/09"},
        format="json",
    ).json()
    assert accepted["status"] == "VALIDE" and accepted["accepted_offline"]
    with tenant_context(pme.organization_id):
        entry = AuditLog.objects.filter(action="plan.accept_offline").get()
    assert "PV signé" in entry.after["reason"]


def test_rules_are_readable_in_french(org, make_user, client_for, pme):
    from pme360.plans.rule_labels import describe, is_simple, readable_template

    names = {"criterion.RHO-01.level": "Organigramme à jour (RHO-01) — niveau", "dimension.D08.score": "Score RH (D08)"}
    condition = {"or": [{"<=": [{"var": "criterion.RHO-01.level"}, 2]}, {"<": [{"var": "dimension.D08.score"}, 50]}]}
    assert (
        describe(condition, names) == "Organigramme à jour (RHO-01) — niveau au plus 2 OU Score RH (D08) inférieur à 50"
    )
    assert readable_template("RH à {{dimension.D08.score}}, RHO-01 niveau {{criterion.RHO-01.level}}", names) == (
        "RH à [score RH], RHO-01 niveau [niveau RHO-01]"
    )
    assert is_simple(condition) and not is_simple({"and": [condition]})

    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    variables = admin.get("/api/v1/recommendation-rules/variables").json()
    rho = next(v for v in variables if v["key"] == "criterion.RHO-01.level")
    assert rho["type"] == "level" and "(RHO-01)" in rho["label"]
    admin.get("/api/v1/support-offers")  # installe le catalogue par défaut
    rule = next(r for r in admin.get("/api/v1/recommendation-rules").json() if r["code"] == "R-RHO-001")
    assert rule["condition_text"].startswith("Organigramme") and " OU " in rule["condition_text"]
    assert "{{" not in rule["rationale_readable"] and rule["editable_visually"]


def test_action_comments_internal_and_shared(api, pme_api, pme, diagnosed, org, other_org, make_user, client_for):
    from pme360.notifications.models import Notification
    from pme360.plans.models import Comment

    plan = _live_plan(api, pme_api, pme)
    action_id = plan["actions"][0]["id"]
    url = f"/api/v1/actions/{action_id}/comments"
    internal = api.post(url, {"body": "Dirigeante difficile à joindre.", "visibility": "INTERNE_GUDE"}, format="json")
    assert internal.status_code == 201 and internal.json()["visibility"] == "INTERNE_GUDE"
    shared = api.post(url, {"body": "Pensez à signer la procédure.", "visibility": "PARTAGE_PME"}, format="json")
    assert shared.status_code == 201
    # La PME ne voit que les échanges partagés, et écrit toujours en partagé.
    assert [c["body"] for c in pme_api.get(url).json()] == ["Pensez à signer la procédure."]
    answer = pme_api.post(url, {"body": "C'est fait, merci.", "visibility": "INTERNE_GUDE"}, format="json").json()
    assert answer["visibility"] == "PARTAGE_PME" and answer["author_is_pme"]
    assert [c["body"] for c in api.get(url).json()] == [
        "Dirigeante difficile à joindre.",
        "Pensez à signer la procédure.",
        "C'est fait, merci.",
    ]
    assert api.post(url, {"body": "   "}, format="json").status_code == 400
    with tenant_context(org.id):
        # Notifications : la PME pour le message partagé, le conseiller pour la réponse ; rien pour l'interne.
        events = list(Notification.objects.filter(event_code="ACTION_COMMENTED").values_list("user__email", flat=True))
        assert len(events) == 2
        from django.db import InternalError, ProgrammingError, transaction

        with pytest.raises((InternalError, ProgrammingError)), transaction.atomic():
            Comment.objects.filter(pk=internal.json()["id"]).update(body="modifié")
    stranger = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert stranger.get(url).status_code == 404
    auditor = client_for(make_user(org, "AUDITEUR"), org)
    assert auditor.post(url, {"body": "x", "visibility": "PARTAGE_PME"}, format="json").status_code == 403


def test_configured_workflow_governs_manual_transitions(org, make_user, client_for, api, pme_api, pme, diagnosed):
    """Workflow activé par l'administrateur : transitions, motifs, libellés et boutons suivent la configuration."""
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    draft = admin.post("/api/v1/config/workflows/action/draft").json()["draft"]
    transitions = []
    for t in draft["transitions"]:
        if (t["from"], t["to"]) == ("NON_COMMENCE", "EN_ATTENTE_PME"):
            continue  # l'attente PME n'est plus possible avant le démarrage
        if t["to"] == "EN_COURS":
            t = {**t, "reason_required": True, "pme_button": "C'est parti"}
        transitions.append(t)
    admin.patch("/api/v1/config/workflows/action/draft", {"transitions": transitions}, format="json")
    assert admin.post("/api/v1/config/workflows/action/draft/activate").status_code == 200

    plan = _live_plan(api, pme_api, pme)
    rh = next(a for a in plan["actions"] if a["offer_code"] == "OFF-RH-BASE")
    detail = pme_api.get(f"/api/v1/actions/{rh['id']}").json()
    start = next(o for o in detail["transition_options"] if o["to"] == "EN_COURS")
    assert start == {"to": "EN_COURS", "label": "C'est parti", "reason_required": True}
    assert "EN_ATTENTE_PME" not in api.get(f"/api/v1/actions/{rh['id']}").json()["allowed_transitions"]
    refused = api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_ATTENTE_PME"}, format="json")
    assert refused.status_code == 400 and refused.json()["code"] == "invalid_transition"
    no_reason = pme_api.post(f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_COURS"}, format="json")
    assert no_reason.status_code == 400 and "reason" in no_reason.json()["errors"]
    started = pme_api.post(
        f"/api/v1/actions/{rh['id']}/transition", {"to": "EN_COURS", "reason": "Réunion faite"}, format="json"
    )
    assert started.status_code == 200, started.content


def test_missing_deliverables_and_regional_map(api, pme_api, pme, diagnosed, advisor, org, run_pipeline):
    """Analyses V1 : livrables demandés non fournis après 30 jours, délai de fourniture ; carte régionale."""
    from datetime import timedelta

    from django.utils import timezone

    from pme360.accounts.access import build_access
    from pme360.analytics import portfolio

    plan = _live_plan(api, pme_api, pme)
    details = [api.get(f"/api/v1/actions/{a['id']}").json() for a in plan["actions"]]
    with_deliverables = [a for a in details if a["deliverables"] and a["status"] == "NON_COMMENCE"][:2]
    assert len(with_deliverables) == 2
    for action in with_deliverables:
        api.post(f"/api/v1/actions/{action['id']}/transition", {"to": "EN_COURS"}, format="json")
        moved = api.post(f"/api/v1/actions/{action['id']}/transition", {"to": "DOCUMENT_DEMANDE"}, format="json")
        assert moved.status_code == 200, moved.content
    delivered = with_deliverables[0]["deliverables"][0]
    run_pipeline(lambda: _upload_deliverable(pme_api, pme, delivered["id"]))
    with tenant_context(org.id):
        access = build_access(advisor, org.id)
        soon = portfolio.missing_deliverables(access, today=timezone.localdate())
        later = portfolio.missing_deliverables(access, today=timezone.localdate() + timedelta(days=45))
    requested = sum(r["requested"] for r in later["deliverables"])
    assert requested == sum(len(a["deliverables"]) for a in with_deliverables)
    assert sum(r["missing"] for r in soon["deliverables"]) == 0  # délai de grâce de 30 jours
    assert sum(r["missing"] for r in later["deliverables"]) == requested - 1
    assert any(r["average_delay_days"] is not None for r in later["deliverables"])

    with tenant_context(org.id):
        regional = portfolio.regional_map(access)
    total = sum(r["pmes"] for r in regional["regions"]) + regional["without_region"]
    assert total == 1 and len(regional["regions"]) == 33
    assert all(r["average_score"] is None for r in regional["regions"])  # moins de 5 PME évaluées : masqué
