"""Workflows configurables (V1) : défaut valide, brouillon, garde-fous, activation, isolation."""

import copy

import pytest

from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context
from pme360.workflows import defaults, services
from pme360.workflows.models import WorkflowDefinition

pytestmark = pytest.mark.django_db
URL = "/api/v1/config/workflows/action"


def test_default_action_workflow_passes_its_own_checks():
    errors, warnings = services.check(defaults.ACTION_STATES, defaults.ACTION_TRANSITIONS)
    assert errors == [] and warnings == []


def _without(transitions, source, target):
    return [t for t in transitions if not (t["from"] == source and t["to"] == target)]


def test_guardrails():
    states, transitions = defaults.ACTION_STATES, copy.deepcopy(defaults.ACTION_TRANSITIONS)
    errors, _ = services.check(states, _without(transitions, "EN_COURS", "ABANDONNE"))
    assert any("abandon par GUDE-PME" in e for e in errors)
    bad = [*transitions, {**defaults.transition("EN_COURS", "CONFORME")}]
    assert any("automatiquement" in e for e in services.check(states, bad)[0])
    pme_ends = [
        {**t, "actors": ["PME", "STAFF"]} if (t["from"], t["to"]) == ("EN_COURS", "TERMINE") else t for t in transitions
    ]
    assert any("la PME ne peut" in e for e in services.check(states, pme_ends)[0])
    reopen = [*transitions, defaults.transition("TERMINE", "EN_COURS")]
    assert any("état final" in e for e in services.check(states, reopen)[0])
    no_end = [t for t in transitions if t["to"] != "TERMINE"] + [
        t for t in transitions if t["to"] == "TERMINE" and t["from"] == "CONFORME"
    ]
    no_end = _without(no_end, "EN_COURS", "DOCUMENT_DEMANDE")
    no_end = _without(no_end, "NON_CONFORME", "DOCUMENT_DEMANDE")
    assert any("ne peut plus jamais être terminée" in e for e in services.check(states, no_end)[0])
    blank = {**states, "EN_COURS": {"label": "", "pme_label": "En cours"}}
    assert any("libellé obligatoire" in e for e in services.check(blank, transitions)[0])


def test_admin_configures_and_activates_action_workflow(org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    payload = admin.get(URL).json()
    assert payload["active"]["version"] == 0 and payload["draft"] is None
    assert len(payload["system_transitions"]) == len(defaults.SYSTEM_TRANSITIONS)

    created = admin.post(f"{URL}/draft")
    assert created.status_code == 201
    draft = created.json()["draft"]
    assert draft["version"] == 1 and created.json()["issues"] == {"errors": [], "warnings": []}
    assert admin.post(f"{URL}/draft").json()["code"] == "draft_exists"

    # Nouvelle règle maison : la PME peut signaler une attente, le conseiller doit motiver une remise en attente.
    states = {**draft["states"], "EN_ATTENTE_PME": {"label": "Relance PME", "pme_label": "Nous attendons votre retour"}}
    transitions = [
        {**t, "reason_required": True} if (t["from"], t["to"]) == ("EN_COURS", "EN_ATTENTE_PME") else t
        for t in draft["transitions"]
    ]
    transitions = _without(transitions, "NON_COMMENCE", "EN_ATTENTE_PME")
    saved = admin.patch(
        f"{URL}/draft", {"states": states, "transitions": transitions, "notes": "Pilote"}, format="json"
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["issues"]["errors"] == []

    broken = _without(transitions, "EN_COURS", "ABANDONNE")
    admin.patch(f"{URL}/draft", {"transitions": broken}, format="json")
    refused = admin.post(f"{URL}/draft/activate")
    assert refused.status_code == 400 and any("abandon" in e for e in refused.json()["errors"]["workflow"])

    admin.patch(f"{URL}/draft", {"transitions": transitions}, format="json")
    activated = admin.post(f"{URL}/draft/activate")
    assert activated.status_code == 200, activated.content
    body = activated.json()
    assert body["active"]["version"] == 1 and body["draft"] is None
    assert body["active"]["states"]["EN_ATTENTE_PME"]["label"] == "Relance PME"
    assert body["history"][0]["status"] == "ACTIVE"

    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.get(URL).status_code == 403
    assert advisor.get("/api/v1/workflows/action").json()["version"] == 1
    with tenant_context(org.id):
        assert WorkflowDefinition.objects.get(version=1).status == "ACTIVE"
        assert AuditLog.objects.filter(action="workflow.activated").exists()

    # Deuxième version : la première est retirée ; un brouillon peut être abandonné.
    admin.post(f"{URL}/draft")
    assert admin.delete(f"{URL}/draft").json()["draft"] is None
    admin.post(f"{URL}/draft")
    admin.post(f"{URL}/draft/activate")
    with tenant_context(org.id):
        assert WorkflowDefinition.objects.get(version=1).status == "RETIRED"
        assert WorkflowDefinition.objects.get(version=2).status == "ACTIVE"  # numéro du brouillon supprimé réutilisé


def test_workflows_are_isolated_per_organization(org, other_org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    admin.post(f"{URL}/draft")
    admin.post(f"{URL}/draft/activate")
    other = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert other.get("/api/v1/workflows/action").json()["version"] == 0
