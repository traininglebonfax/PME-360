"""Registre réglementaire (RM-08), obligations, échéances, relances, taux de conformité, alertes, notifications."""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from pme360.alerts import engine as alerts
from pme360.alerts.models import Alert
from pme360.audit.models import AuditLog
from pme360.compliance import services
from pme360.compliance.models import Deadline, DeadlineReminder, ObligationTemplate, PmeObligation, RegulatoryRule
from pme360.compliance.tasks import run_daily_for
from pme360.core.tenancy import tenant_context
from pme360.notifications.models import Notification, NotificationPreference
from pme360.pmes.models import Pme

from . import files

pytestmark = pytest.mark.django_db
TODAY = date(2026, 9, 25)


@pytest.fixture
def advisor(org, make_user):
    return make_user(org, "CONSEILLER")


@pytest.fixture
def pme(org, make_pme, advisor):
    pme = make_pme(org, advisor=advisor, headcount=12)
    with tenant_context(org.id):
        Pme.objects.filter(pk=pme.pk).update(lifecycle_status=Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF)
        pme.refresh_from_db()
    return pme


@pytest.fixture
def leader(org, pme, make_user):
    return make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)


def verify_cnps_rule(org, user):
    with tenant_context(org.id):
        rule = RegulatoryRule.objects.get(code="REG-CNPS-01")
        services.verify_rule(
            rule,
            user,
            source_reference="Document CNPS « Recouvrement », section périodicité",
            verified_at=TODAY,
            note="Confirmé par l'expert-comptable du projet",
        )
        services.set_template_active(ObligationTemplate.objects.get(code="OBL-CNPS-PERIODIQUE"), True)


# --- RM-08 : registre sourcé ----------------------------------------------------------------------------------


def test_unverified_rule_blocks_obligation_activation(org, make_user, client_for):
    admin_user = make_user(org, "ADMIN_ORG")
    admin = client_for(admin_user, org)
    templates = {t["code"]: t for t in admin.get("/api/v1/obligation-templates").json()}
    cnps = templates["OBL-CNPS-PERIODIQUE"]
    assert cnps["is_active"] is False and cnps["regulatory_status"] == "PRE_VERIFIE"
    refused = admin.post(f"/api/v1/obligation-templates/{cnps['id']}/activation", {"active": True}, format="json")
    assert refused.status_code == 400 and refused.json()["code"] == "rule_not_verified"

    rules = {r["code"]: r for r in admin.get("/api/v1/regulatory-rules").json()}
    incomplete = admin.post(
        f"/api/v1/regulatory-rules/{rules['REG-CNPS-01']['id']}/verify",
        {"source_reference": "", "verified_at": str(TODAY)},
        format="json",
    )
    assert incomplete.status_code == 400
    verified = admin.post(
        f"/api/v1/regulatory-rules/{rules['REG-CNPS-01']['id']}/verify",
        {"source_reference": "CNPS, Recouvrement, § périodicité", "verified_at": str(TODAY)},
        format="json",
    )
    assert verified.json()["status"] == "VERIFIE" and verified.json()["verified_by_name"] == admin_user.full_name
    assert (
        admin.post(f"/api/v1/obligation-templates/{cnps['id']}/activation", {"active": True}, format="json").json()[
            "is_active"
        ]
        is True
    )
    # Une règle qui repasse « à vérifier » désactive les obligations qui en dépendent.
    admin.post(f"/api/v1/regulatory-rules/{rules['REG-CNPS-01']['id']}/status", {"status": "A_VERIFIER"}, format="json")
    with tenant_context(org.id):
        assert not ObligationTemplate.objects.get(code="OBL-CNPS-PERIODIQUE").is_active
    advisor_client = client_for(make_user(org, "CONSEILLER"), org)
    assert (
        advisor_client.post(
            f"/api/v1/obligation-templates/{cnps['id']}/activation", {"active": True}, format="json"
        ).status_code
        == 403
    )


def test_verified_rule_requires_documentation_at_database_level(org):
    from django.db import IntegrityError, transaction

    with tenant_context(org.id), pytest.raises(IntegrityError), transaction.atomic():
        RegulatoryRule.objects.filter(code="REG-FISC-02").update(status="VERIFIE")


# --- Échéances --------------------------------------------------------------------------------------------------


def test_deadline_generation_is_idempotent_and_follows_frequency(org, pme, advisor):
    verify_cnps_rule(org, advisor)
    with tenant_context(org.id):
        first = services.run_for_pme(pme, TODAY)
        second = services.run_for_pme(pme, TODAY)
        assert first["deadlines_created"] > 0 and second["deadlines_created"] == 0
        cnps = Deadline.objects.filter(pme=pme, pme_obligation__template__code="OBL-CNPS-PERIODIQUE").order_by(
            "due_date"
        )
        assert cnps[0].period_label == "T3 2026" and cnps[0].period_end == date(2026, 9, 30)
        assert cnps[0].due_date == date(2026, 10, 30)  # fin de période + 15 jours légaux + 15 jours de transmission
        assert all(d.due_date <= TODAY + timedelta(days=120) for d in Deadline.objects.filter(pme=pme))
        obligations = set(PmeObligation.objects.filter(pme=pme).values_list("template__code", flat=True))
        assert "OBL-FISC-PERIODIQUE" not in obligations  # règle fiscale non vérifiée : aucune échéance générée
        assert {"OBL-RCCM", "OBL-TRESORERIE", "OBL-ATTEST-CNPS"} <= obligations


def test_frequency_switches_to_monthly_from_next_period(org, pme, advisor):
    verify_cnps_rule(org, advisor)
    with tenant_context(org.id):
        services.run_for_pme(pme, TODAY)
        Pme.objects.filter(pk=pme.pk).update(headcount=25)
        pme.refresh_from_db()
        services.run_for_pme(pme, TODAY)
        obligation = PmeObligation.objects.get(pme=pme, template__code="OBL-CNPS-PERIODIQUE")
        assert obligation.frequency == "MENSUELLE"
        labels = list(obligation.deadlines.order_by("period_start").values_list("period_label", flat=True))
        assert labels[0] == "T3 2026" and "Octobre 2026" in labels  # historique conservé, nouveau rythme ensuite
        from pme360.audit.models import AuditLog

        assert AuditLog.objects.filter(action="obligation.frequency_changed").exists()


def test_reminders_from_j_minus_30_to_j_plus_15(org, pme, leader, advisor):
    with tenant_context(org.id):
        # Obligations et échéances seulement (sans relance), puis on ne garde que l'échéance RCCM.
        obligations = services.sync_obligations(pme, TODAY - timedelta(days=40))
        rccm = next(o for o in obligations if o.template.code == "OBL-RCCM")
        services.generate_deadlines(rccm, TODAY - timedelta(days=40))
        Deadline.objects.filter(pme=pme).exclude(pme_obligation=rccm).delete()
        deadline = Deadline.objects.get(pme=pme)
        due = deadline.due_date
        mail.outbox.clear()
        timeline = []
        for offset in (-31, -30, -30, -15, -7, 0, 7, 15):
            day = due + timedelta(days=offset)
            services.update_temporal_statuses(pme, day)
            timeline.append((offset, services.send_reminders(pme, day)))
        assert timeline == [(-31, 0), (-30, 1), (-30, 0), (-15, 1), (-7, 1), (0, 1), (7, 1), (15, 1)]
        assert sorted(DeadlineReminder.objects.filter(deadline=deadline).values_list("offset_days", flat=True)) == [
            -30,
            -15,
            -7,
            0,
            7,
            15,
        ]
        deadline.refresh_from_db()
        assert deadline.status == Deadline.Status.EN_RETARD
        events = list(Notification.objects.filter(user=leader).values_list("event_code", flat=True))
        assert (
            events.count("DEADLINE_REMINDER") == 3
            and "DEADLINE_DUE_TODAY" in events
            and events.count("DEADLINE_OVERDUE") == 2
        )
        # À J+15, le conseiller est aussi prévenu.
        assert Notification.objects.filter(user=advisor, event_code="DEADLINE_OVERDUE").count() == 1
        assert len(mail.outbox) == 7


def test_notification_preferences_and_mandatory_events(org, pme, leader, client_for):
    client = client_for(leader, org)
    preferences = client.get("/api/v1/me/notification-preferences").json()
    assert next(p for p in preferences if p["event_code"] == "DEADLINE_ESCALATION")["mandatory"] is True
    client.put(
        "/api/v1/me/notification-preferences",
        [{"event_code": "DEADLINE_REMINDER", "in_app": True, "email": False}],
        format="json",
    )
    with tenant_context(org.id):
        assert NotificationPreference.objects.get(user=leader, event_code="DEADLINE_REMINDER").email is False
        services.run_for_pme(pme, TODAY)
        deadline = Deadline.objects.get(pme=pme, pme_obligation__template__code="OBL-RCCM")
        mail.outbox.clear()
        services.send_reminders(pme, deadline.due_date - timedelta(days=7))
    assert mail.outbox == []  # e-mail désactivé…
    unread = client.get("/api/v1/notifications/unread-count").json()["unread"]
    assert unread >= 1  # … mais notification in-app conservée
    assert client.post("/api/v1/notifications/read", {"all": True}, format="json").json() == {"unread": 0}


# --- Dépôt sur échéance, taux de conformité, alertes ----------------------------------------------------------


def test_deadline_fulfilled_by_verified_document_and_compliance_rate(
    org, pme, advisor, client_for, django_capture_on_commit_callbacks
):
    client = client_for(advisor, org)
    with tenant_context(org.id):
        services.run_for_pme(pme, TODAY)
        deadline = Deadline.objects.get(pme=pme, pme_obligation__template__code="OBL-RCCM")
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/v1/pmes/{pme.id}/documents",
            {"file": SimpleUploadedFile("rccm.pdf", files.pdf()), "deadline_id": str(deadline.id)},
            format="multipart",
        )
    assert response.status_code == 201, response.content
    with tenant_context(org.id):
        deadline.refresh_from_db()
        assert deadline.status == Deadline.Status.VERIF_HUMAINE_REQUISE
    client.post(f"/api/v1/documents/{response.json()['id']}/verify", {"decision": "CONFORME"}, format="json")
    with tenant_context(org.id):
        deadline.refresh_from_db()
        assert deadline.status == Deadline.Status.CONFORME
        rate = services.compliance_rate(pme, deadline.due_date + timedelta(days=1))
    assert rate["counts"]["CONFORME"] >= 1 and rate["rate"] is not None
    folder = client.get(f"/api/v1/pmes/{pme.id}/compliance-folder").json()
    juridique = next(c for c in folder["categories"] if c["code"] == "JURIDIQUE")
    assert next(i for i in juridique["items"] if i["document_type"]["code"] == "RCCM")["state"] == "CONFORME"


def test_compliance_rate_formula(org, pme):
    with tenant_context(org.id):
        services.run_for_pme(pme, TODAY)
        deadlines = list(Deadline.objects.filter(pme=pme).order_by("due_date")[:4])
        for deadline, status in zip(
            deadlines, ["CONFORME", "CONFORME_SOUS_RESERVE", "EN_RETARD", "DISPENSE"], strict=True
        ):
            deadline.status = status
            deadline.save()
        last_due = max(d.due_date for d in deadlines)
        rate = services.compliance_rate(pme, last_due)
        eligible = Deadline.objects.filter(pme=pme, due_date__lte=last_due).exclude(status="DISPENSE").count()
    assert rate["eligible"] == eligible
    assert rate["points"] == 1.5 and rate["rate"] == round(1.5 / eligible, 3)


def test_overdue_alert_is_deduplicated_and_auto_resolved(org, pme, advisor, client_for):
    with tenant_context(org.id):
        services.run_for_pme(pme, TODAY)
        deadline = Deadline.objects.get(pme=pme, pme_obligation__template__code="OBL-RCCM")
        late = deadline.due_date + timedelta(days=20)
        services.update_temporal_statuses(pme, late)
        alerts.evaluate_pme(pme, late)
        alerts.evaluate_pme(pme, late)
        open_alerts = Alert.objects.filter(
            pme=pme, rule__code="ALR-OBLIGATION-DEPASSEE", status__in=Alert.OPEN, target_id=str(deadline.id)
        )
        assert open_alerts.count() == 1
        services.waive(deadline, "Document remis en main propre au conseiller", advisor)
        alerts.evaluate_pme(pme, late)
        alert = Alert.objects.get(pme=pme, rule__code="ALR-OBLIGATION-DEPASSEE", target_id=str(deadline.id))
        assert alert.status == Alert.Status.RESOLUE and "automatiquement" in alert.resolution_note
    listed = client_for(advisor, org).get("/api/v1/alerts", {"status": "all", "pme": str(pme.id)}).json()
    assert any(a["rule"] == "ALR-OBLIGATION-DEPASSEE" for a in listed)


def test_alert_workflow_and_access(org, pme, advisor, leader, client_for):
    with tenant_context(org.id):
        services.run_for_pme(pme, TODAY)
        deadline = Deadline.objects.get(pme=pme, pme_obligation__template__code="OBL-RCCM")
        late = deadline.due_date + timedelta(days=20)
        services.update_temporal_statuses(pme, late)
        alerts.evaluate_pme(pme, late)
        alert = Alert.objects.get(pme=pme, rule__code="ALR-OBLIGATION-DEPASSEE", target_id=str(deadline.id))
    client = client_for(advisor, org)
    url = f"/api/v1/alerts/{alert.id}/transition"
    assert client.post(url, {"status": "IGNOREE"}, format="json").status_code == 400  # motif obligatoire
    assert client.post(url, {"status": "PRISE_EN_COMPTE"}, format="json").json()["status"] == "PRISE_EN_COMPTE"
    assert client_for(leader, org).get("/api/v1/alerts").status_code == 403


def test_open_critical_alert_forces_priority_p1(org, pme, advisor):
    from pme360.alerts.models import AlertRule
    from pme360.diagnostic.referential import install_gude360
    from pme360.scoring import engine
    from pme360.scoring.services import load_framework

    with tenant_context(org.id):
        rule = AlertRule.objects.get(code="ALR-ANOMALIE-DOC")
        Alert.objects.create(pme=pme, rule=rule, severity="CRITIQUE", title="t", message="m", dedup_key="k")
        version = install_gude360(org)
        spec, _ = load_framework(version)
        from pme360.diagnostic.models import Diagnostic
        from pme360.scoring.services import priority_context

        diagnostic = Diagnostic(pme=pme, framework_version=version, type="INITIAL", reference_date=TODAY)
        context = priority_context(diagnostic)
    assert context["open_critical_alerts"] == 1
    data = engine.DiagnosticInput(reference_date=TODAY, profile={}, context=context)
    assert engine.compute(spec, data)["priority"]["priority"] == "P1"


def test_daily_scheduler_runs_for_every_organization(org, other_org, pme, make_pme):
    make_pme(other_org, headcount=3)
    with tenant_context(other_org.id):
        Pme.objects.update(lifecycle_status=Pme.LifecycleStatus.ONBOARDING)
    totals = run_daily_for(TODAY)
    assert totals["pmes"] >= 2 and totals["deadlines_created"] > 0
    with tenant_context(other_org.id):
        assert Deadline.objects.exists()


# --- Configuration sans code (V1) -----------------------------------------------------------------------------------


def test_admin_creates_and_edits_document_types(org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    created = admin.post(
        "/api/v1/config/document-types",
        {
            "code": "plan_hygiene",
            "name": "Plan d'hygiène",
            "category": "QUALITE",
            "validity_days": 365,
            "evidence_level": 3,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["code"] == "PLAN_HYGIENE" and body["usage"] == {"documents": 0, "obligations": [], "criteria": []}
    assert (
        admin.post(
            "/api/v1/config/document-types", {"code": "PLAN_HYGIENE", "name": "x", "category": "QUALITE"}, format="json"
        ).status_code
        == 400
    )
    renamed = admin.patch(
        f"/api/v1/config/document-types/{body['id']}", {"name": "Plan HACCP", "code": "AUTRE_CODE"}, format="json"
    )
    assert renamed.status_code == 400 and "code" in renamed.json()["errors"]
    ok = admin.patch(f"/api/v1/config/document-types/{body['id']}", {"name": "Plan HACCP"}, format="json")
    assert ok.json()["name"] == "Plan HACCP"
    # Un type exigé par une obligation active ne peut pas être désactivé.
    rccm = next(t for t in admin.get("/api/v1/config/document-types").json() if t["code"] == "RCCM")
    assert (
        "OBL-RCCM" in rccm["usage"]["obligations"] and "FOR-01" not in rccm["usage"]["criteria"]
    )  # référentiel non installé
    refused = admin.patch(f"/api/v1/config/document-types/{rccm['id']}", {"is_active": False}, format="json")
    assert refused.status_code == 400 and refused.json()["code"] == "document_type_in_use"
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="document_type.updated").exists()
    advisor = client_for(make_user(org, "CONSEILLER"), org)
    assert (
        advisor.post(
            "/api/v1/config/document-types", {"code": "X1", "name": "x", "category": "QUALITE"}, format="json"
        ).status_code
        == 403
    )


def test_admin_creates_obligations_with_readable_rules_and_rm08(org, make_user, client_for):
    admin = client_for(make_user(org, "ADMIN_ORG"), org)
    base = {"code": "OBL-HYGIENE", "name": "Plan d'hygiène annuel", "document_type": "RCCM", "frequency": "ANNUELLE"}
    no_rule = admin.post("/api/v1/obligation-templates/new", {**base, "nature": "REGLEMENTAIRE"}, format="json")
    assert no_rule.status_code == 400 and "regulatory_rule" in no_rule.json()["errors"]
    bad_logic = admin.post(
        "/api/v1/obligation-templates/new",
        {**base, "nature": "PROGRAMME", "applicability": {"exec": ["x"]}},
        format="json",
    )
    assert bad_logic.status_code == 400 and "applicability" in bad_logic.json()["errors"]
    bad_frequency = admin.post(
        "/api/v1/obligation-templates/new",
        {
            **base,
            "nature": "PROGRAMME",
            "frequency_rule": {"if": [{">=": [{"var": "headcount"}, 20]}, "SOUVENT", "RARE"]},
        },
        format="json",
    )
    assert bad_frequency.status_code == 400 and "frequency_rule" in bad_frequency.json()["errors"]
    created = admin.post(
        "/api/v1/obligation-templates/new",
        {
            **base,
            "nature": "PROGRAMME",
            "applicability": {
                "and": [{">=": [{"var": "headcount"}, 5]}, {"in": [{"var": "size_category"}, ["PETITE", "MOYENNE"]]}]
            },
            "frequency_rule": {"if": [{">=": [{"var": "headcount"}, 20]}, "SEMESTRIELLE", "ANNUELLE"]},
            "reminder_offsets": [7, -7, 0, 7],
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    obligation = created.json()
    assert not obligation["is_active"] and obligation["reminder_offsets"] == [-7, 0, 7]
    assert (
        obligation["applicability_text"] == "Effectif au moins 5 ET Taille parmi Petite entreprise, Moyenne entreprise"
    )
    assert obligation["frequency_text"] == "Semestrielle si effectif au moins 20, sinon annuelle"
    # Réglementaire rattachée à une règle non vérifiée : enregistrable inactive, jamais activable (RM-08).
    rule = admin.patch(
        f"/api/v1/obligation-templates/{obligation['id']}",
        {"nature": "REGLEMENTAIRE", "regulatory_rule": "REG-CNPS-01"},
        format="json",
    )
    assert rule.status_code == 200 and rule.json()["regulatory_rule"] == "REG-CNPS-01"
    activation = admin.post(
        f"/api/v1/obligation-templates/{obligation['id']}/activation", {"active": True}, format="json"
    )
    assert activation.status_code == 400 and activation.json()["code"] == "rule_not_verified"
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="obligation.created").exists()
        assert AuditLog.objects.filter(action="obligation.updated").exists()
