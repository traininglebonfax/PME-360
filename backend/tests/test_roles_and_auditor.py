"""Rôles personnalisés et tableau de bord auditeur (V1)."""

import pytest

from pme360.accounts.models import User
from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context

pytestmark = pytest.mark.django_db
ROLES = "/api/v1/config/roles"


@pytest.fixture
def admin_user(org, make_user):
    return make_user(org, "ADMIN_ORG")


@pytest.fixture
def admin(admin_user, org, client_for):
    return client_for(admin_user, org)


def _invite(client, email, role, scope=None):
    body = {"email": email, "full_name": "Personne Test", "role": role}
    if scope:
        body["scope"] = scope
    response = client.post("/api/v1/users/invite", body, format="json")
    assert response.status_code == 201, response.content
    return User.objects.get(email=email)


def test_custom_role_lifecycle_and_guardrails(org, admin, client_for, make_pme):
    catalog = admin.get(ROLES).json()
    assert {g["label"] for g in catalog["permission_groups"]} >= {"PME", "Pilotage et contrôle"}
    system = next(r for r in catalog["roles"] if r["code"] == "CONSEILLER")
    assert system["is_system"] is True
    refused = admin.patch(f"{ROLES}/{system['id']}", {"label": "x"}, format="json")
    assert refused.status_code == 400 and refused.json()["code"] == "system_role"

    pme_only = admin.post(
        ROLES, {"code": "MIXTE", "label": "Mixte", "permissions": ["pme.view", "plan.accept"]}, format="json"
    )
    assert pme_only.status_code == 400 and "permissions" in pme_only.json()["errors"]
    created = admin.post(
        ROLES,
        {
            "code": "charge_suivi",
            "label": "Chargé de suivi",
            "default_scope": "PORTEFEUILLE",
            "permissions": ["pme.view", "document.verify", "task.update"],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    role = created.json()
    assert role["code"] == "CHARGE_SUIVI" and role["is_system"] is False and role["members"] == 0

    member = _invite(admin, "suivi@test.test", "CHARGE_SUIVI")
    client = client_for(member, org)
    assert client.get("/api/v1/pmes").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403
    # Rôle à périmètre portefeuille : proposé pour suivre des PME.
    assert "suivi@test.test" in [u["email"] for u in admin.get("/api/v1/users/advisors").json()]

    # Les permissions ajoutées valent immédiatement pour les personnes qui détiennent le rôle.
    updated = admin.patch(
        f"{ROLES}/{role['id']}",
        {"permissions": ["pme.view", "document.verify", "task.update", "audit.view"]},
        format="json",
    )
    assert updated.status_code == 200 and updated.json()["members"] == 1
    assert client.get("/api/v1/audit-logs").status_code == 200

    in_use = admin.delete(f"{ROLES}/{role['id']}")
    assert in_use.status_code == 400 and in_use.json()["code"] == "role_in_use"
    spare = admin.post(ROLES, {"code": "TEMP_ROLE", "label": "Temporaire", "permissions": ["pme.view"]}, format="json")
    assert admin.delete(f"{ROLES}/{spare.json()['id']}").status_code == 204
    with tenant_context(org.id):
        actions = set(AuditLog.objects.filter(action__startswith="role.").values_list("action", flat=True))
    assert actions == {"role.created", "role.updated", "role.deleted"}


def test_no_privilege_escalation_and_no_self_lockout(org, admin, client_for):
    manager_role = admin.post(
        ROLES,
        {
            "code": "GEST_EQUIPE",
            "label": "Gestion d'équipe",
            "default_scope": "ORG",
            "permissions": ["org.manage_users", "pme.view"],
        },
        format="json",
    ).json()
    manager = client_for(_invite(admin, "gestion@test.test", "GEST_EQUIPE"), org)
    escalate = manager.post(ROLES, {"code": "PLUS", "label": "Plus", "permissions": ["audit.view"]}, format="json")
    assert escalate.status_code == 403
    assert manager.get(ROLES).json()["grantable"] == ["org.manage_users", "pme.view"]
    lockout = manager.patch(f"{ROLES}/{manager_role['id']}", {"permissions": ["pme.view"]}, format="json")
    assert lockout.status_code == 400 and lockout.json()["code"] == "self_lockout"


def test_custom_roles_are_isolated_per_organization(org, other_org, admin, make_user, client_for):
    admin.post(ROLES, {"code": "PROPRE_ORG", "label": "Propre", "permissions": ["pme.view"]}, format="json")
    other = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    assert "PROPRE_ORG" not in [r["code"] for r in other.get(ROLES).json()["roles"]]
    invite = other.post(
        "/api/v1/users/invite", {"email": "x@test.test", "full_name": "X", "role": "PROPRE_ORG"}, format="json"
    )
    assert invite.status_code == 400


def test_auditor_dashboard_sample_and_export(org, admin, make_user, make_pme, client_for):
    for index in range(6):
        make_pme(org, legal_name=f"Dossier {index} SARL")
    for code in ("ROLE_A", "ROLE_B"):
        admin.post(ROLES, {"code": code, "label": code, "permissions": ["pme.view"]}, format="json")
    auditor = client_for(make_user(org, "AUDITEUR"), org)
    overview = auditor.get("/api/v1/audit/overview")
    assert overview.status_code == 200, overview.content
    data = overview.json()
    assert data["total"] >= 2 and any(d["domain"] == "Utilisateurs et accès" for d in data["by_domain"])
    assert [e["action"] for e in data["sensitive"]][:2] == ["role.created", "role.created"]
    assert data["ai_review"]["suggestions_reviewed"] == 0 and data["ai_review"]["suggestions_change_rate"] is None

    first = auditor.get("/api/v1/audit/sample", {"seed": "controle-2026", "size": 3}).json()
    again = auditor.get("/api/v1/audit/sample", {"seed": "controle-2026", "size": 3}).json()
    assert [i["id"] for i in first["items"]] == [i["id"] for i in again["items"]]
    assert first["population"] == 6 and len(first["items"]) == 3
    random_seed = auditor.get("/api/v1/audit/sample").json()
    assert random_seed["seed"] and len(random_seed["items"]) == 5

    export = auditor.get("/api/v1/audit-logs/export", {"action": "role.created"})
    assert export.status_code == 200 and export["Content-Type"].startswith("text/csv")
    lines = export.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("N°;Date;Action") and len(lines) == 3
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="audit.exported").exists()
        assert AuditLog.objects.filter(action="audit.sampled").count() == 3

    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.get("/api/v1/audit/overview").status_code == 403
    assert advisor.get("/api/v1/audit-logs/export").status_code == 403
