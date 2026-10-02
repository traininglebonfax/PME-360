"""Services d'authentification et de gestion des accès (Document 2, § 8.1 ; décision D-07).

- Équipes GUDE-PME : e-mail + mot de passe (Argon2id) + TOTP obligatoire (MFA).
- Utilisateurs PME : e-mail + code à usage unique envoyé par e-mail (OTP) ;
  session de 30 jours sur appareil de confiance.
- Verrouillage progressif après échecs répétés ; aucune réponse ne révèle l'existence d'un compte.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import timedelta
from enum import StrEnum

import pyotp
from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError
from pme360.core.middleware import SESSION_ORG_KEY
from pme360.core.request_context import get_request_context
from pme360.core.tenancy import system_context

from . import emails
from .access import AccessContext, active_membership_q
from .models import OneTimeCode, Role, Scope, User, UserMembership

PENDING_KEY = "auth_pending"
_DUMMY_HASH = make_password(secrets.token_urlsafe(16))


class LoginStatus(StrEnum):
    OK = "ok"
    MFA_REQUIRED = "mfa_required"
    MFA_SETUP_REQUIRED = "mfa_setup_required"


# --- Utilitaires ---------------------------------------------------------------------------------------------


def find_user(email: str) -> User | None:
    return User.objects.filter(email=(email or "").strip().lower()).first()


def has_staff_membership(user: User) -> bool:
    with system_context():
        return UserMembership.objects.filter(active_membership_q(), user=user, role__is_pme_role=False).exists()


def has_any_membership(user: User) -> bool:
    with system_context():
        return UserMembership.objects.filter(active_membership_q(), user=user).exists()


def requires_mfa(user: User) -> bool:
    return settings.MFA_ENFORCED and (user.is_platform_admin or has_staff_membership(user))


def default_organization(user: User) -> uuid.UUID | None:
    with system_context():
        return (
            UserMembership.objects.filter(active_membership_q(), user=user)
            .order_by("created_at")
            .values_list("organization_id", flat=True)
            .first()
        )


def user_memberships_all_orgs(user: User) -> list[UserMembership]:
    """Appartenances actives de l'utilisateur dans toutes ses organisations (lecture système, filtrée sur lui)."""
    with system_context():
        return list(
            UserMembership.objects.filter(active_membership_q(), user=user)
            .select_related("role", "organization")
            .order_by("organization__name", "created_at")
        )


def _register_failure(user: User) -> None:
    user.failed_login_count += 1
    if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
        # Verrouillage progressif : 15 min, puis 30, 60… (plafonné à 24 h).
        factor = 2 ** (user.failed_login_count - settings.LOGIN_MAX_FAILURES)
        minutes = min(settings.LOGIN_LOCK_MINUTES * factor, 24 * 60)
        user.locked_until = timezone.now() + timedelta(minutes=minutes)
    user.save(update_fields=["failed_login_count", "locked_until", "updated_at"])
    audit.record(
        "auth.login_failed",
        entity_type="user",
        entity_id=user.pk,
        organization_id=None,
        after={"failed_login_count": user.failed_login_count, "locked": user.is_locked},
    )


def _reset_failures(user: User) -> None:
    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_count", "locked_until", "updated_at"])


def complete_login(request, user: User, *, method: str, trusted_device: bool = False) -> None:
    django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.pop(PENDING_KEY, None)
    org_id = default_organization(user)
    if org_id:
        request.session[SESSION_ORG_KEY] = str(org_id)
    request.session.set_expiry(
        settings.PME_TRUSTED_DEVICE_SESSION_AGE if trusted_device else settings.SESSION_COOKIE_AGE
    )
    ctx = get_request_context()
    if ctx is not None:
        ctx["user_id"] = str(user.pk)
    audit.record(
        "auth.login",
        entity_type="user",
        entity_id=user.pk,
        actor=user,
        organization_id=org_id,
        after={"method": method, "trusted_device": trusted_device},
    )


# --- Connexion par mot de passe + MFA ------------------------------------------------------------------------


def _set_pending(request, user: User, stage: str) -> None:
    request.session[PENDING_KEY] = {"user_id": str(user.pk), "stage": stage, "at": time.time()}


def get_pending_user(request, stage: str) -> User | None:
    pending = request.session.get(PENDING_KEY)
    if not pending or pending.get("stage") != stage:
        return None
    if time.time() - pending.get("at", 0) > settings.AUTH_PENDING_TTL_SECONDS:
        request.session.pop(PENDING_KEY, None)
        return None
    return User.objects.filter(pk=pending["user_id"], is_active=True).first()


def password_login(request, email: str, password: str) -> LoginStatus | None:
    """Première étape de connexion. ``None`` = échec (message générique côté API)."""
    user = find_user(email)
    if user is None or not user.is_active or not user.has_usable_password():
        check_password(password, _DUMMY_HASH)  # temps de réponse homogène
        return None
    if user.is_locked:
        return None
    if not user.check_password(password):
        _register_failure(user)
        return None
    _reset_failures(user)
    if requires_mfa(user):
        if user.mfa_enabled:
            _set_pending(request, user, "mfa")
            return LoginStatus.MFA_REQUIRED
        _set_pending(request, user, "mfa_setup")
        return LoginStatus.MFA_SETUP_REQUIRED
    complete_login(request, user, method="password")
    return LoginStatus.OK


def verify_totp(user: User, code: str, secret: str | None = None) -> bool:
    """Vérifie un code TOTP (fenêtre ±1 pas) et interdit le rejeu d'un pas déjà utilisé."""
    code = (code or "").replace(" ", "")
    secret = secret or user.mfa_secret
    if not secret or len(code) != 6 or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    current_step = int(time.time()) // totp.interval
    for step in (current_step - 1, current_step, current_step + 1):
        if user.mfa_last_timestep is not None and step <= user.mfa_last_timestep:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            user.mfa_last_timestep = step
            user.save(update_fields=["mfa_last_timestep", "updated_at"])
            return True
    return False


def mfa_verify(request, code: str) -> bool:
    user = get_pending_user(request, "mfa")
    if user is None:
        raise BusinessError("Aucune connexion en attente : recommencez.", code="no_pending_login")
    if user.is_locked:
        return False
    if verify_totp(user, code):
        _reset_failures(user)
        complete_login(request, user, method="password+totp")
        return True
    _register_failure(user)
    return False


def mfa_setup_begin(request) -> dict:
    user = get_pending_user(request, "mfa_setup")
    if user is None:
        raise BusinessError("Aucune configuration MFA en attente : recommencez.", code="no_pending_login")
    user.mfa_secret = pyotp.random_base32()
    user.mfa_enabled = False
    user.mfa_last_timestep = None
    user.save(update_fields=["mfa_secret", "mfa_enabled", "mfa_last_timestep", "updated_at"])
    uri = pyotp.TOTP(user.mfa_secret).provisioning_uri(name=user.email, issuer_name=settings.MFA_ISSUER)
    return {"secret": user.mfa_secret, "otpauth_uri": uri}


def mfa_setup_confirm(request, code: str) -> bool:
    user = get_pending_user(request, "mfa_setup")
    if user is None or not user.mfa_secret:
        raise BusinessError("Aucune configuration MFA en attente : recommencez.", code="no_pending_login")
    if not verify_totp(user, code):
        _register_failure(user)
        return False
    user.mfa_enabled = True
    user.save(update_fields=["mfa_enabled", "updated_at"])
    audit.record("auth.mfa_enabled", entity_type="user", entity_id=user.pk, actor=user, organization_id=None)
    complete_login(request, user, method="password+totp")
    return True


# --- Connexion PME par code à usage unique --------------------------------------------------------------------


def _hash_code(user: User, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{user.pk}:{code}".encode(), hashlib.sha256).hexdigest()


def request_login_code(email: str) -> None:
    """Envoie un code si le compte est éligible ; ne révèle jamais s'il existe."""
    user = find_user(email)
    if user is None or not user.is_active or requires_mfa(user) or not has_any_membership(user):
        return
    now = timezone.now()
    codes = OneTimeCode.objects.filter(user=user, purpose=OneTimeCode.Purpose.LOGIN)
    if codes.filter(created_at__gte=now - timedelta(hours=1)).count() >= settings.OTP_MAX_PER_HOUR:
        return
    codes.filter(used_at__isnull=True, expires_at__gt=now).update(expires_at=now)  # un seul code valide
    code = f"{secrets.randbelow(10**6):06d}"
    OneTimeCode.objects.create(
        user=user,
        purpose=OneTimeCode.Purpose.LOGIN,
        code_hash=_hash_code(user, code),
        expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    emails.send_login_code(user.email, user.full_name, code)


def verify_login_code(request, email: str, code: str, trusted_device: bool) -> bool:
    user = find_user(email)
    if user is None or not user.is_active or requires_mfa(user):
        return False
    otp = (
        OneTimeCode.objects.filter(
            user=user, purpose=OneTimeCode.Purpose.LOGIN, used_at__isnull=True, expires_at__gt=timezone.now()
        )
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return False
    otp.attempts += 1
    if otp.attempts > settings.OTP_MAX_ATTEMPTS:
        otp.expires_at = timezone.now()
        otp.save(update_fields=["attempts", "expires_at"])
        return False
    if not hmac.compare_digest(otp.code_hash, _hash_code(user, (code or "").strip())):
        otp.save(update_fields=["attempts"])
        return False
    otp.used_at = timezone.now()
    otp.save(update_fields=["attempts", "used_at"])
    complete_login(request, user, method="email_otp", trusted_device=trusted_device)
    return True


# --- Mot de passe ---------------------------------------------------------------------------------------------


def password_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/mot-de-passe?uid={uid}&token={token}"


def request_password_reset(email: str) -> None:
    user = find_user(email)
    if user is None or not user.is_active or not has_staff_membership(user) and not user.is_platform_admin:
        return  # les comptes PME se connectent par code : pas de mot de passe
    emails.send_password_link(user.email, user.full_name, password_link(user), invitation=False)


def confirm_password_reset(uid: str, token: str, new_password: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise BusinessError("Ce lien n'est plus valide. Demandez un nouveau lien.", code="invalid_reset_link")
    try:
        validate_password(new_password, user)
    except Exception as exc:  # django.core.exceptions.ValidationError
        raise ValidationError({"new_password": list(getattr(exc, "messages", [str(exc)]))}) from exc
    user.set_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    user.save()
    audit.record("auth.password_set", entity_type="user", entity_id=user.pk, actor=user, organization_id=None)
    return user


# --- Organisation active --------------------------------------------------------------------------------------


def switch_organization(request, organization_id: uuid.UUID) -> None:
    with system_context():
        allowed = UserMembership.objects.filter(
            active_membership_q(), user=request.user, organization_id=organization_id
        ).exists()
    if not allowed:
        raise PermissionDenied("Vous n'appartenez pas à cette organisation.")
    request.session[SESSION_ORG_KEY] = str(organization_id)
    audit.record(
        "auth.organization_switched", entity_type="user", entity_id=request.user.pk, organization_id=organization_id
    )


# --- Invitations et appartenances -----------------------------------------------------------------------------


def invite_user(
    access: AccessContext,
    *,
    email: str,
    full_name: str,
    role_code: str,
    phone: str = "",
    scope: str | None = None,
    scope_ref_id: uuid.UUID | None = None,
) -> UserMembership:
    from pme360.organizations.models import Organization, Programme
    from pme360.pmes.models import Pme

    role = Role.objects.filter(code=role_code).first()
    if role is None:
        raise ValidationError({"role": ["Rôle inconnu."]})
    scope = scope or role.default_scope

    if not access.has("org.manage_users"):
        # Un dirigeant de PME peut seulement inviter des collaborateurs dans sa propre PME.
        if not (
            access.has("pme.manage_collaborators")
            and role.code == "COLLABORATEUR_PME"
            and scope == Scope.PME
            and scope_ref_id in access.own_pme_ids
        ):
            raise PermissionDenied("Vous ne pouvez pas inviter ce type d'utilisateur.")

    if role.is_pme_role and scope != Scope.PME:
        raise ValidationError({"scope": ["Un rôle PME a obligatoirement le périmètre PME."]})
    if scope in (Scope.ORG, Scope.PORTEFEUILLE):
        scope_ref_id = None
    elif scope_ref_id is None:
        raise ValidationError({"scope_ref_id": ["Référence de périmètre obligatoire (programme ou PME)."]})
    elif scope == Scope.PROGRAMME and not Programme.objects.filter(pk=scope_ref_id).exists():
        raise ValidationError({"scope_ref_id": ["Programme introuvable dans l'organisation."]})
    elif scope == Scope.PME and not Pme.objects.filter(pk=scope_ref_id).exists():
        raise ValidationError({"scope_ref_id": ["PME introuvable dans l'organisation."]})

    user = find_user(email)
    created = user is None
    if created:
        user = User.objects.create_user(email=email, full_name=full_name, phone=phone)
    membership, _ = UserMembership.objects.get_or_create(
        user=user,
        role=role,
        scope=scope,
        scope_ref_id=scope_ref_id,
        defaults={"valid_from": timezone.localdate()},
    )
    if not membership.is_active or membership.valid_to:
        membership.is_active = True
        membership.valid_to = None
        membership.save(update_fields=["is_active", "valid_to", "updated_at"])

    organization = Organization.objects.get(pk=access.organization_id)
    if role.is_pme_role:
        pme = Pme.objects.get(pk=scope_ref_id)
        emails.send_pme_invitation(user.email, user.full_name, organization.name, pme.legal_name)
    elif not user.has_usable_password():
        emails.send_password_link(
            user.email, user.full_name, password_link(user), invitation=True, organization_name=organization.name
        )
    audit.record(
        "user.invited",
        instance=membership,
        pme_id=scope_ref_id if scope == Scope.PME else None,
        after={
            "email": user.email,
            "role": role.code,
            "scope": scope,
            "scope_ref_id": scope_ref_id,
            "new_account": created,
        },
    )
    return membership


def update_user_profile(user: User, *, full_name: str | None = None, phone: str | None = None) -> User:
    """Correction du nom (ou du téléphone) d'un utilisateur par l'administrateur ; l'adresse e-mail reste fixe."""
    before = {"full_name": user.full_name, "phone": user.phone}
    if full_name is not None:
        full_name = " ".join(full_name.split())
        if not full_name:
            raise ValidationError({"full_name": ["Le nom est obligatoire."]})
        user.full_name = full_name
    if phone is not None:
        user.phone = phone.strip()
    user.save(update_fields=["full_name", "phone", "updated_at"])
    audit.record("user.updated", instance=user, before=before, after={"full_name": user.full_name, "phone": user.phone})
    return user


def revoke_membership(membership: UserMembership) -> None:
    membership.is_active = False
    membership.valid_to = timezone.localdate()
    membership.save(update_fields=["is_active", "valid_to", "updated_at"])
    audit.record(
        "user.membership_revoked",
        instance=membership,
        after={"user_id": membership.user_id, "role": membership.role.code},
    )
