"""Modèles de notification modifiables par l'organisation (V1) : validation, rendu sûr, audit, repli par défaut."""

import pytest
from django.core import mail

from pme360.audit.models import AuditLog
from pme360.compliance.defaults import NOTIFICATION_TEMPLATES
from pme360.core.tenancy import tenant_context
from pme360.notifications import catalog
from pme360.notifications import services as notifications
from pme360.notifications.models import Notification, NotificationTemplate

pytestmark = pytest.mark.django_db
URL = "/api/v1/config/notification-templates"


def test_render_substitutes_only_declared_names():
    assert catalog.render("{pme} : {{ok}} {absent}", {"pme": "Alpha"}) == "Alpha : {ok} "
    # Pas d'accès aux attributs : la syntaxe Python n'est pas interprétée.
    assert catalog.check("{pme.__class__}", "PLAN_ACCEPTED")
    assert catalog.check("{pme} {inconnue}", "PLAN_ACCEPTED") == [
        "Variable(s) inconnue(s) pour cet événement : {inconnue}. Disponibles : {pme}."
    ]
    assert catalog.check("Bonjour {pme", "PLAN_ACCEPTED")
    for code, (subject, body) in NOTIFICATION_TEMPLATES.items():
        assert not catalog.check(subject, code) and not catalog.check(body, code), code


def test_admin_edits_resets_and_tests_a_template(org, make_user, client_for):
    admin_user = make_user(org, "ADMIN_ORG")
    admin = client_for(admin_user, org)
    items = admin.get(URL).json()
    assert len(items) == len(NOTIFICATION_TEMPLATES)
    plan = next(i for i in items if i["event_code"] == "PLAN_TO_ACCEPT")
    assert plan["is_default"] and plan["audience"] == "PME"
    assert {v["name"] for v in plan["variables"]} == {"pme", "actions"}

    bad = admin.put(f"{URL}/PLAN_TO_ACCEPT", {"subject": "Plan {nom}", "body": "Bonjour {pme"}, format="json")
    assert bad.status_code == 400
    assert set(bad.json()["errors"]) == {"subject", "body"}

    saved = admin.put(
        f"{URL}/PLAN_TO_ACCEPT",
        {"subject": "{pme} : votre plan est prêt", "body": "Votre plan compte {actions} actions. Acceptez-le."},
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["is_default"] is False

    sent = admin.post(
        f"{URL}/PLAN_TO_ACCEPT/test", {"subject": "{pme} : test", "body": "{actions} actions"}, format="json"
    )
    assert sent.json() == {"email": admin_user.email}
    assert mail.outbox[-1].subject == "[Test] Boutik Plus SARL : test"
    assert "6 actions" in mail.outbox[-1].body

    with tenant_context(org.id):
        pme_user = make_user(org, "ADMIN_ORG")
        notifications.notify([pme_user], "PLAN_TO_ACCEPT", {"pme": "Alpha SARL", "actions": 3})
        notification = Notification.objects.get(user=pme_user)
        assert notification.title == "Alpha SARL : votre plan est prêt"
        assert notification.body == "Votre plan compte 3 actions. Acceptez-le."
        assert AuditLog.objects.filter(action="notification_template.updated").exists()

    reset = admin.post(f"{URL}/PLAN_TO_ACCEPT/reset")
    assert reset.json()["is_default"] is True
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="notification_template.reset").exists()

    assert admin.put(f"{URL}/INCONNU", {"subject": "x", "body": "y"}, format="json").status_code == 404
    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert advisor.get(URL).status_code == 403
    assert advisor.put(f"{URL}/PLAN_TO_ACCEPT", {"subject": "x", "body": "y"}, format="json").status_code == 403


def test_invalid_stored_template_falls_back_to_default(org, make_user):
    user = make_user(org, "ADMIN_ORG")
    with tenant_context(org.id):
        NotificationTemplate.objects.filter(event_code="PLAN_ACCEPTED").update(subject="{pme.__class__}", body="x")
        notifications.notify([user], "PLAN_ACCEPTED", {"pme": "Alpha SARL"})
        assert Notification.objects.get(user=user).title == "Plan accepté : Alpha SARL"


def test_templates_are_isolated_per_organization(org, other_org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    admin.put(f"{URL}/PLAN_ACCEPTED", {"subject": "Accepté : {pme}", "body": "OK"}, format="json")
    other = client_for(make_user(other_org, "ADMIN_ORG"), other_org)
    item = next(i for i in other.get(URL).json() if i["event_code"] == "PLAN_ACCEPTED")
    assert item["is_default"] is True
