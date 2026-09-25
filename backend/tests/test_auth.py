"""Authentification : mot de passe + MFA (équipes), OTP e-mail (PME), verrouillage, CSRF, réinitialisation."""

import re

import pyotp
import pytest
from django.core import mail
from rest_framework.test import APIClient

from pme360.accounts.models import User
from pme360.accounts.services import password_link
from pme360.audit.models import AuditLog
from pme360.core.tenancy import tenant_context

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", {"email": email, "password": password}, format="json")


def _next_code(user: User) -> str:
    """Code TOTP d'un pas futur (évite le refus anti-rejeu si le pas courant a déjà servi)."""
    user.refresh_from_db()
    totp = pyotp.TOTP(user.mfa_secret)
    import time

    step = int(time.time()) // totp.interval
    if user.mfa_last_timestep is not None and step <= user.mfa_last_timestep:
        step = user.mfa_last_timestep + 1
    return totp.generate_otp(step)


def test_staff_login_requires_mfa_then_opens_session_on_default_org(org, make_user, anon):
    user = make_user(org, "CONSEILLER")
    response = _login(anon, user.email)
    assert response.status_code == 200 and response.json() == {"status": "mfa_required"}
    assert anon.get("/api/v1/me").status_code == 401  # pas encore connecté

    response = anon.post("/api/v1/auth/mfa/verify", {"code": _next_code(user)}, format="json")
    assert response.status_code == 200, response.content
    me = anon.get("/api/v1/me").json()
    assert me["organization"]["id"] == str(org.id)
    assert me["portal"] == "gude"
    assert "pme.view" in me["permissions"]
    with tenant_context(org.id):
        assert AuditLog.objects.filter(action="auth.login", actor=user).exists()


def test_totp_code_cannot_be_replayed(org, make_user):
    user = make_user(org, "CONSEILLER")
    code = _next_code(user)
    first = APIClient()
    _login(first, user.email)
    assert first.post("/api/v1/auth/mfa/verify", {"code": code}, format="json").status_code == 200
    second = APIClient()
    _login(second, user.email)
    assert second.post("/api/v1/auth/mfa/verify", {"code": code}, format="json").status_code == 400


def test_mfa_setup_flow_for_staff_without_mfa(org, make_user, anon):
    user = make_user(org, "ADMIN_ORG", mfa=False)
    assert _login(anon, user.email).json() == {"status": "mfa_setup_required"}
    setup = anon.post("/api/v1/auth/mfa/setup", format="json").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert anon.post("/api/v1/auth/mfa/confirm", {"code": "000000"}, format="json").status_code == 400
    code = pyotp.TOTP(setup["secret"]).now()
    assert anon.post("/api/v1/auth/mfa/confirm", {"code": code}, format="json").status_code == 200
    user.refresh_from_db()
    assert user.mfa_enabled
    assert anon.get("/api/v1/me").status_code == 200


def test_mfa_verify_without_pending_login_is_rejected(anon):
    response = anon.post("/api/v1/auth/mfa/verify", {"code": "123456"}, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "no_pending_login"


def test_wrong_password_generic_error_and_progressive_lock(org, make_user, anon):
    user = make_user(org, "CONSEILLER")
    for _ in range(5):
        response = _login(anon, user.email, "mauvais-mot-de-passe")
        assert response.status_code == 400
        assert response["Content-Type"] == "application/problem+json"
        assert response.json()["code"] == "invalid_credentials"
    user.refresh_from_db()
    assert user.failed_login_count == 5 and user.is_locked
    # Même le bon mot de passe est refusé pendant le verrouillage, avec le même message générique.
    response = _login(anon, user.email)
    assert response.status_code == 400 and response.json()["code"] == "invalid_credentials"


def test_unknown_email_gives_same_error(anon):
    response = _login(anon, "inconnu@test.test")
    assert response.status_code == 400 and response.json()["code"] == "invalid_credentials"


def test_login_enforces_csrf(org, make_user):
    user = make_user(org, "CONSEILLER")
    client = APIClient(enforce_csrf_checks=True)
    assert _login(client, user.email).status_code == 403
    client.get("/api/v1/auth/csrf")
    token = client.cookies["pme360_csrftoken"].value
    response = client.post(
        "/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200


def test_pme_user_logs_in_with_email_code(org, make_user, make_pme, anon):
    pme = make_pme(org)
    user = make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)
    assert anon.post("/api/v1/auth/otp/request", {"email": user.email}, format="json").status_code == 202
    assert len(mail.outbox) == 1
    code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
    response = anon.post(
        "/api/v1/auth/otp/verify", {"email": user.email, "code": code, "trusted_device": True}, format="json"
    )
    assert response.status_code == 200
    me = anon.get("/api/v1/me").json()
    assert me["portal"] == "pme"
    assert me["pme_ids"] == [str(pme.id)]
    # Le code ne sert qu'une fois.
    again = anon.post("/api/v1/auth/otp/verify", {"email": user.email, "code": code}, format="json")
    assert again.status_code == 400


def test_otp_attempts_are_limited(org, make_user, make_pme, anon):
    pme = make_pme(org)
    user = make_user(org, "DIRIGEANT_PME", scope_ref_id=pme.id)
    anon.post("/api/v1/auth/otp/request", {"email": user.email}, format="json")
    code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        anon.post("/api/v1/auth/otp/verify", {"email": user.email, "code": wrong}, format="json")
    # Après 5 échecs, même le bon code est refusé.
    response = anon.post("/api/v1/auth/otp/verify", {"email": user.email, "code": code}, format="json")
    assert response.status_code == 400


def test_otp_request_does_not_reveal_accounts_nor_serve_staff(org, make_user, anon):
    staff = make_user(org, "CONSEILLER")
    assert anon.post("/api/v1/auth/otp/request", {"email": "inconnu@test.test"}, format="json").status_code == 202
    assert anon.post("/api/v1/auth/otp/request", {"email": staff.email}, format="json").status_code == 202
    assert mail.outbox == []


def test_auth_endpoints_are_rate_limited(anon, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "3/min", "otp": "5/min"})
    codes = [_login(anon, "x@test.test", "x").status_code for _ in range(4)]
    assert codes == [400, 400, 400, 429]


def test_password_reset_flow(org, make_user, anon):
    user = make_user(org, "CONSEILLER")
    assert anon.post("/api/v1/auth/password/reset", {"email": user.email}, format="json").status_code == 202
    assert len(mail.outbox) == 1
    link = password_link(user)
    uid = re.search(r"uid=([^&]+)", link).group(1)
    token = re.search(r"token=([^&\s]+)", link).group(1)
    weak = anon.post(
        "/api/v1/auth/password/reset/confirm", {"uid": uid, "token": token, "new_password": "123"}, format="json"
    )
    assert weak.status_code == 400 and "new_password" in weak.json()["errors"]
    new_password = "Nouveau-mot-de-passe-solide-42"
    response = anon.post(
        "/api/v1/auth/password/reset/confirm", {"uid": uid, "token": token, "new_password": new_password}, format="json"
    )
    assert response.status_code == 204
    # Le lien ne sert qu'une fois.
    reuse = anon.post(
        "/api/v1/auth/password/reset/confirm",
        {"uid": uid, "token": token, "new_password": new_password + "x"},
        format="json",
    )
    assert reuse.status_code == 400 and reuse.json()["code"] == "invalid_reset_link"
    assert _login(anon, user.email, new_password).json()["status"] == "mfa_required"


def test_switch_organization_only_to_own_memberships(org, other_org, make_user, client_for):
    user = make_user(org, "CONSEILLER")
    client = client_for(user, org)
    denied = client.post("/api/v1/auth/switch-organization", {"organization_id": str(other_org.id)}, format="json")
    assert denied.status_code == 403
    make_user  # noqa: B018
    from pme360.accounts.models import Role, UserMembership

    with tenant_context(other_org.id):
        UserMembership.objects.create(
            user=user, role=Role.objects.get(organization=None, code="EXPERT"), scope="PORTEFEUILLE"
        )
    ok = client.post("/api/v1/auth/switch-organization", {"organization_id": str(other_org.id)}, format="json")
    assert ok.status_code == 204
    me = client.get("/api/v1/me").json()
    assert me["organization"]["id"] == str(other_org.id)
    assert {m["organization_id"] for m in me["memberships"]} == {str(org.id), str(other_org.id)}


def test_logout(org, make_user, client_for):
    client = client_for(make_user(org, "CONSEILLER"), org)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_revoked_membership_loses_access_immediately(org, make_user, client_for):
    user = make_user(org, "CONSEILLER")
    client = client_for(user, org)
    assert client.get("/api/v1/pmes").status_code == 200
    from pme360.accounts.models import UserMembership

    with tenant_context(org.id):
        UserMembership.objects.filter(user=user).update(is_active=False)
    response = client.get("/api/v1/pmes")
    assert response.status_code == 403 and response.json()["code"] == "no_organization"
