"""Utilisateurs, rôles, permissions et appartenances (Document 1, § 6 ; Document 3, § 3.1).

Les rôles et permissions sont des DONNÉES (tables) et non des constantes : le catalogue par défaut
(``catalog.py``) est synchronisé en base par migration et une organisation pourra créer ses propres rôles (V1).
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.utils import timezone

from pme360.core.fields import EncryptedTextField
from pme360.core.ids import uuid7
from pme360.core.models import TenantModel, TimeStampedModel
from pme360.core.tenancy import current_org_id, rls_bypassed


class Scope(models.TextChoices):
    ORG = "ORG", "Toute l'organisation"
    PROGRAMME = "PROGRAMME", "Un programme"
    PORTEFEUILLE = "PORTEFEUILLE", "PME assignées"
    PME = "PME", "Sa propre PME"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=email.strip().lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_platform_admin(self, email: str, password: str, **extra) -> "User":
        return self.create_user(email, password, is_platform_admin=True, **extra)

    def get_by_natural_key(self, username: str) -> "User":
        return self.get(email=username.strip().lower())


class User(AbstractBaseUser):
    """Compte global (hors tenant) ; ses droits dépendent de ses appartenances à des organisations."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    full_name = models.CharField(max_length=200)
    locale = models.CharField(max_length=10, default="fr")
    is_active = models.BooleanField(default=True)
    is_platform_admin = models.BooleanField(default=False)
    mfa_secret = EncryptedTextField(blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_last_timestep = models.BigIntegerField(null=True, blank=True)
    failed_login_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "app_user"  # « user » est un mot réservé PostgreSQL
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class Permission(models.Model):
    """Permission atomique (catalogue système, commun à tous les tenants)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    code = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=200)

    class Meta:
        db_table = "permission"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class RoleManager(models.Manager):
    """Rôles visibles : rôles système (organization NULL) + rôles propres au tenant courant."""

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        if rls_bypassed():
            return queryset
        org_id = current_org_id()
        if org_id is None:
            return queryset.filter(organization__isnull=True)
        return queryset.filter(Q(organization__isnull=True) | Q(organization_id=org_id))


class Role(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    code = models.CharField(max_length=60)
    label = models.CharField(max_length=200)
    default_scope = models.CharField(max_length=20, choices=Scope.choices)
    is_pme_role = models.BooleanField(default=False, help_text="Rôle côté PME (portail PME, connexion par OTP).")
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")

    objects = RoleManager()

    class Meta:
        db_table = "role"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="role_unique_code", nulls_distinct=False)
        ]

    def __str__(self) -> str:
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        db_table = "role_permission"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="role_permission_unique")]

    def __str__(self) -> str:
        return f"{self.role_id}:{self.permission_id}"


class UserMembership(TenantModel):
    """Appartenance d'un utilisateur à une organisation : un rôle + un périmètre."""

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    scope = models.CharField(max_length=20, choices=Scope.choices)
    scope_ref_id = models.UUIDField(null=True, blank=True, help_text="Programme ou PME selon le périmètre.")
    valid_from = models.DateField(default=timezone.localdate)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "user_membership"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization", "role", "scope", "scope_ref_id"],
                name="membership_unique",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(scope__in=["ORG", "PORTEFEUILLE"]) | Q(scope_ref_id__isnull=False),
                name="membership_scope_ref_required",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.role_id} {self.scope}"


class OneTimeCode(models.Model):
    """Code à usage unique envoyé par e-mail (connexion PME). Seul le hash est stocké."""

    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "Connexion"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="one_time_codes")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "one_time_code"
        indexes = [models.Index(fields=["user", "purpose", "created_at"], name="otp_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.purpose} {self.user_id}"
