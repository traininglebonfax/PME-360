from django.contrib.auth import logout
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from pme360.audit import services as audit
from pme360.core.authentication import SessionAuthentication
from pme360.core.exceptions import problem_response
from pme360.core.permissions import get_access
from pme360.organizations.models import Organization

from . import services
from .access import active_membership_q
from .catalog import ADVISOR_ROLE_CODES
from .models import Role, User, UserMembership
from .serializers import (
    CodeSerializer,
    InviteSerializer,
    LoginSerializer,
    LoginStatusSerializer,
    MembershipSerializer,
    MeSerializer,
    MfaSetupSerializer,
    OrganizationMemberSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RoleAdminSerializer,
    RolesAdminSerializer,
    RoleSerializer,
    RoleWriteSerializer,
    SwitchOrganizationSerializer,
    UserSummarySerializer,
)

INVALID_CREDENTIALS = "Identifiants invalides ou compte temporairement verrouillé."
INVALID_CODE = "Code invalide ou expiré."


class PublicAuthView(APIView):
    """Point d'entrée d'authentification : anonyme autorisé, CSRF vérifié même sans session, débit limité."""

    permission_classes = [AllowAny]
    requires_organization = False
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        SessionAuthentication().enforce_csrf(request)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    permission_classes = [AllowAny]
    requires_organization = False

    @extend_schema(responses={204: None})
    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(PublicAuthView):
    @extend_schema(request=LoginSerializer, responses={200: LoginStatusSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.password_login(request, **serializer.validated_data)
        if result is None:
            return problem_response(400, "invalid_credentials", INVALID_CREDENTIALS, request)
        return Response({"status": result.value})


class MfaVerifyView(PublicAuthView):
    @extend_schema(request=CodeSerializer, responses={200: LoginStatusSerializer})
    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not services.mfa_verify(request, serializer.validated_data["code"]):
            return problem_response(400, "invalid_code", INVALID_CODE, request)
        return Response({"status": "ok"})


class MfaSetupView(PublicAuthView):
    @extend_schema(request=None, responses={200: MfaSetupSerializer})
    def post(self, request):
        return Response(services.mfa_setup_begin(request))


class MfaConfirmView(PublicAuthView):
    @extend_schema(request=CodeSerializer, responses={200: LoginStatusSerializer})
    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not services.mfa_setup_confirm(request, serializer.validated_data["code"]):
            return problem_response(400, "invalid_code", INVALID_CODE, request)
        return Response({"status": "ok"})


class OtpRequestView(PublicAuthView):
    throttle_scope = "otp"

    @extend_schema(request=OtpRequestSerializer, responses={202: None})
    def post(self, request):
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_login_code(serializer.validated_data["email"])
        return Response(status=status.HTTP_202_ACCEPTED)


class OtpVerifyView(PublicAuthView):
    @extend_schema(request=OtpVerifySerializer, responses={200: LoginStatusSerializer})
    def post(self, request):
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not services.verify_login_code(request, **serializer.validated_data):
            return problem_response(400, "invalid_code", INVALID_CODE, request)
        return Response({"status": "ok"})


class PasswordResetRequestView(PublicAuthView):
    throttle_scope = "otp"

    @extend_schema(request=PasswordResetRequestSerializer, responses={202: None})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(PublicAuthView):
    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(**serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    requires_organization = False

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        audit.record("auth.logout", entity_type="user", entity_id=request.user.pk)
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    requires_organization = False

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        user = request.user
        access = get_access(request)
        all_memberships = services.user_memberships_all_orgs(user)
        organization = None
        if access.organization_id:
            org = Organization.objects.get(pk=access.organization_id)
            from pme360.organizations.branding import brand

            organization = {
                "id": org.id,
                "name": org.name,
                "slug": org.slug,
                "branding": org.branding,
                "brand": brand(org),
            }
        if access.memberships:
            portal = "pme" if access.is_pme_user else "gude"
        else:
            portal = "platform" if user.is_platform_admin else "none"
        data = {
            "user": user,
            "organization": organization,
            "memberships": [
                {
                    "organization_id": m.organization_id,
                    "organization_name": m.organization.name,
                    "role": m.role.code,
                    "role_label": m.role.label,
                    "scope": m.scope,
                    "scope_ref_id": m.scope_ref_id,
                }
                for m in all_memberships
            ],
            "permissions": sorted(access.permissions),
            "roles": sorted(access.role_codes),
            "portal": portal,
            "pme_ids": sorted(access.own_pme_ids, key=str),
        }
        return Response(MeSerializer(data).data)


class SwitchOrganizationView(APIView):
    permission_classes = [IsAuthenticated]
    requires_organization = False

    @extend_schema(request=SwitchOrganizationSerializer, responses={204: None})
    def post(self, request):
        serializer = SwitchOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.switch_organization(request, serializer.validated_data["organization_id"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationMembersView(APIView):
    """Utilisateurs de l'organisation active et leurs appartenances."""

    required_permissions = "org.manage_users"

    @extend_schema(responses=OrganizationMemberSerializer(many=True))
    def get(self, request):
        memberships = UserMembership.objects.select_related("role").order_by("created_at")
        users = (
            User.objects.filter(memberships__in=memberships)
            .distinct()
            .prefetch_related(Prefetch("memberships", queryset=memberships, to_attr="org_memberships"))
            .order_by("full_name")
        )
        return Response(OrganizationMemberSerializer(users, many=True).data)


class InviteView(APIView):
    """Invitation : ADMIN_ORG (tout rôle) ou dirigeant de PME (collaborateurs de sa PME) ; contrôle dans le service."""

    @extend_schema(request=InviteSerializer, responses={201: MembershipSerializer})
    def post(self, request):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = services.invite_user(
            get_access(request),
            email=data["email"],
            full_name=data["full_name"],
            phone=data.get("phone", ""),
            role_code=data["role"],
            scope=data.get("scope"),
            scope_ref_id=data.get("scope_ref_id"),
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class RevokeMembershipView(APIView):
    required_permissions = "org.manage_users"

    @extend_schema(request=None, responses={200: MembershipSerializer})
    def post(self, request, membership_id):
        membership = get_object_or_404(UserMembership.objects.select_related("role"), pk=membership_id)
        if membership.user_id == request.user.pk:
            return problem_response(
                400, "cannot_revoke_self", "Vous ne pouvez pas retirer votre propre accès.", request
            )
        services.revoke_membership(membership)
        return Response(MembershipSerializer(membership).data)


class RoleListView(APIView):
    required_permissions = "org.manage_users"

    @extend_schema(responses=RoleSerializer(many=True))
    def get(self, request):
        return Response(RoleSerializer(Role.objects.prefetch_related("permissions"), many=True).data)


class AdvisorListView(APIView):
    """Utilisateurs pouvant suivre une PME (conseillers, experts, responsables)."""

    required_permissions = "pme.view"

    @extend_schema(responses={200: OpenApiResponse(UserSummarySerializer(many=True))})
    def get(self, request):
        users = (
            User.objects.filter(
                is_active=True,
                memberships__in=UserMembership.objects.filter(active_membership_q()).filter(
                    Q(role__code__in=ADVISOR_ROLE_CODES)
                    # Rôle personnalisé à périmètre portefeuille : suit des PME comme un conseiller.
                    | Q(role__organization__isnull=False, role__default_scope="PORTEFEUILLE")
                ),
            )
            .distinct()
            .order_by("full_name")
        )
        return Response(UserSummarySerializer(users, many=True).data)


# --- Rôles personnalisés (V1) --------------------------------------------------------------------------------


def _roles_payload(request) -> dict:
    from .catalog import PERMISSIONS
    from .roles import PERMISSION_GROUPS, PME_ONLY_PERMISSIONS

    access = get_access(request)
    roles = Role.objects.prefetch_related("permissions").order_by("organization_id", "code")
    grantable = sorted(
        code
        for code in PERMISSIONS
        if code not in PME_ONLY_PERMISSIONS and (access.has(code) or request.user.is_platform_admin)
    )
    return {
        "roles": roles,
        "permission_groups": [
            {"label": label, "permissions": [{"code": c, "label": PERMISSIONS[c]} for c in codes]}
            for label, codes in PERMISSION_GROUPS
        ],
        "grantable": grantable,
    }


class RoleAdminListView(APIView):
    """Rôles système et personnalisés, avec leurs permissions et le nombre de personnes qui les détiennent."""

    required_permissions = "org.manage_users"

    @extend_schema(responses=RolesAdminSerializer)
    def get(self, request):
        return Response(RolesAdminSerializer(_roles_payload(request)).data)

    @extend_schema(request=RoleWriteSerializer, responses={201: RoleAdminSerializer})
    def post(self, request):
        from .roles import create_role

        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = create_role(get_access(request), serializer.validated_data)
        return Response(RoleAdminSerializer(role).data, status=status.HTTP_201_CREATED)


class RoleAdminDetailView(APIView):
    required_permissions = "org.manage_users"

    @extend_schema(request=RoleWriteSerializer, responses=RoleAdminSerializer)
    def patch(self, request, role_id):
        from .roles import update_role

        role = get_object_or_404(Role, pk=role_id)
        serializer = RoleWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(RoleAdminSerializer(update_role(get_access(request), role, serializer.validated_data)).data)

    @extend_schema(responses={204: None})
    def delete(self, request, role_id):
        from .roles import delete_role

        delete_role(get_access(request), get_object_or_404(Role, pk=role_id))
        return Response(status=status.HTTP_204_NO_CONTENT)
