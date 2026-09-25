"""Fixtures communes. Les tests tournent sur un vrai PostgreSQL (RLS comprise), avec le rôle applicatif."""

import itertools

import pyotp
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from pme360.accounts.models import Role, User, UserMembership
from pme360.core.middleware import SESSION_ORG_KEY
from pme360.core.tenancy import system_context, tenant_context
from pme360.organizations.models import Cohort, Organization, Programme
from pme360.pmes.defaults import install_defaults
from pme360.pmes.models import Pme, PmeAssignment, PmeEnrollment, Sector

PASSWORD = "Mot-de-passe-de-test-2026!"
_counter = itertools.count(1)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # compteurs de limitation de débit
    yield


@pytest.fixture
def make_org(db):
    def factory(name: str | None = None) -> Organization:
        n = next(_counter)
        with system_context():
            organization = Organization.objects.create(
                name=name or f"Organisation {n}", slug=f"org-{n}", type=Organization.Type.AGENCE_PUBLIQUE
            )
        with tenant_context(organization.id):
            install_defaults(organization)
        return organization

    return factory


@pytest.fixture
def org(make_org):
    return make_org("GUDE Test")


@pytest.fixture
def other_org(make_org):
    return make_org("Autre organisation")


@pytest.fixture
def make_user(db):
    def factory(
        organization=None,
        role: str | None = None,
        scope: str | None = None,
        scope_ref_id=None,
        email: str | None = None,
        mfa: bool = True,
        **extra,
    ) -> User:
        n = next(_counter)
        user = User.objects.create_user(email=email or f"user{n}@test.test", full_name=f"Utilisateur {n}", **extra)
        if role:
            role_obj = Role.objects.get(organization=None, code=role)
            if not role_obj.is_pme_role:
                user.set_password(PASSWORD)
                if mfa:
                    user.mfa_secret = pyotp.random_base32()
                    user.mfa_enabled = True
                user.save()
            with tenant_context(organization.id):
                UserMembership.objects.create(
                    user=user, role=role_obj, scope=scope or role_obj.default_scope, scope_ref_id=scope_ref_id
                )
        return user

    return factory


@pytest.fixture
def make_pme(db):
    def factory(organization, legal_name: str | None = None, advisor: User | None = None, cohort=None, **data) -> Pme:
        n = next(_counter)
        with tenant_context(organization.id):
            pme = Pme.objects.create(
                legal_name=legal_name or f"Entreprise Test {n} SARL",
                sector=Sector.objects.get(code="COMMERCE"),
                **data,
            )
            if advisor:
                PmeAssignment.objects.create(
                    pme=pme,
                    user=advisor,
                    role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL,
                    start_date="2026-01-01",
                )
            if cohort:
                PmeEnrollment.objects.create(pme=pme, cohort=cohort, enrolled_at="2026-01-01")
        return pme

    return factory


@pytest.fixture
def programme(org):
    with tenant_context(org.id):
        programme = Programme.objects.create(name="Programme test")
        Cohort.objects.create(programme=programme, name="Cohorte A")
    return programme


@pytest.fixture
def cohort(org, programme):
    with tenant_context(org.id):
        return programme.cohorts.get()


@pytest.fixture
def client_for():
    """Client API authentifié sur l'organisation donnée (session déjà ouverte, MFA déjà passée)."""

    def factory(user: User, organization: Organization | None = None) -> APIClient:
        client = APIClient()
        client.force_login(user)
        if organization is not None:
            session = client.session
            session[SESSION_ORG_KEY] = str(organization.id)
            session.save()
        return client

    return factory


@pytest.fixture
def anon():
    return APIClient()
