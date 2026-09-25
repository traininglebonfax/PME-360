"""Routes de l'API v1 (Document 2, § 6.1)."""

from django.db import connection
from django.urls import include, path
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from pme360.accounts import views as accounts
from pme360.audit import views as audit
from pme360.dashboards import views as dashboards
from pme360.organizations import views as organizations
from pme360.pmes import views as pmes


@extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}))
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})


health.cls.requires_organization = False

router = SimpleRouter(trailing_slash=False, use_regex_path=False)
router.register("pmes", pmes.PmeViewSet, basename="pme")
router.register("pmes/<uuid:pme_pk>/persons", pmes.PmePersonViewSet, basename="pme-person")
router.register("programmes", organizations.ProgrammeViewSet, basename="programme")
router.register("platform/organizations", organizations.PlatformOrganizationViewSet, basename="platform-organization")

urlpatterns = [
    path("health", health),
    path("schema", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[AllowAny]), name="docs"),
    # Authentification
    path("auth/csrf", accounts.CsrfView.as_view()),
    path("auth/login", accounts.LoginView.as_view()),
    path("auth/logout", accounts.LogoutView.as_view()),
    path("auth/mfa/verify", accounts.MfaVerifyView.as_view()),
    path("auth/mfa/setup", accounts.MfaSetupView.as_view()),
    path("auth/mfa/confirm", accounts.MfaConfirmView.as_view()),
    path("auth/otp/request", accounts.OtpRequestView.as_view()),
    path("auth/otp/verify", accounts.OtpVerifyView.as_view()),
    path("auth/password/reset", accounts.PasswordResetRequestView.as_view()),
    path("auth/password/reset/confirm", accounts.PasswordResetConfirmView.as_view()),
    path("auth/switch-organization", accounts.SwitchOrganizationView.as_view()),
    path("me", accounts.MeView.as_view()),
    # Utilisateurs et rôles
    path("users", accounts.OrganizationMembersView.as_view()),
    path("users/invite", accounts.InviteView.as_view()),
    path("users/advisors", accounts.AdvisorListView.as_view()),
    path("memberships/<uuid:membership_id>/revoke", accounts.RevokeMembershipView.as_view()),
    path("roles", accounts.RoleListView.as_view()),
    # Organisation
    path("organization", organizations.CurrentOrganizationView.as_view()),
    # Nomenclatures
    path("ref/<str:kind>", pmes.ReferenceListView.as_view()),
    # Tableaux de bord
    path("dashboards/advisor", dashboards.AdvisorDashboardView.as_view()),
    path("dashboards/portfolio", dashboards.PortfolioDashboardView.as_view()),
    path("dashboards/pme/<uuid:pme_id>", dashboards.PmeDashboardView.as_view()),
    # Audit
    path("audit-logs", audit.AuditLogListView.as_view()),
    path("audit-logs/verify", audit.AuditVerifyView.as_view()),
    path("", include(router.urls)),
]
