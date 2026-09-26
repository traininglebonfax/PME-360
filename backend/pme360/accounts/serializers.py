from rest_framework import serializers

from .models import Role, Scope, User, UserMembership


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, max_length=256)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


class OtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OtpVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=10)
    trusted_device = serializers.BooleanField(default=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=100)
    new_password = serializers.CharField(trim_whitespace=False, max_length=256)


class SwitchOrganizationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class LoginStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "mfa_required", "mfa_setup_required"])


class MfaSetupSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "code", "label", "default_scope", "is_pme_role", "permissions"]


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name", "email"]


class MembershipSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.code", read_only=True)
    role_label = serializers.CharField(source="role.label", read_only=True)

    class Meta:
        model = UserMembership
        fields = ["id", "role", "role_label", "scope", "scope_ref_id", "valid_from", "valid_to", "is_active"]


class OrganizationMemberSerializer(serializers.ModelSerializer):
    """Utilisateur vu depuis une organisation : ses seules appartenances dans CETTE organisation."""

    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "full_name", "email", "phone", "is_active", "mfa_enabled", "last_login", "memberships"]

    def get_memberships(self, user: User) -> MembershipSerializer(many=True):
        return MembershipSerializer(getattr(user, "org_memberships", []), many=True).data


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    role = serializers.CharField(max_length=60)
    scope = serializers.ChoiceField(choices=Scope.choices, required=False)
    scope_ref_id = serializers.UUIDField(required=False, allow_null=True)


class BrandSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    short_name = serializers.CharField()
    primary_color = serializers.CharField()
    logo = serializers.CharField(allow_null=True)
    tagline = serializers.CharField(allow_blank=True)


class MeOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    branding = serializers.DictField()
    brand = BrandSerializer()


class MeMembershipSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    organization_name = serializers.CharField()
    role = serializers.CharField()
    role_label = serializers.CharField()
    scope = serializers.CharField()
    scope_ref_id = serializers.UUIDField(allow_null=True)


class MeUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "locale", "mfa_enabled", "is_platform_admin"]


class MeSerializer(serializers.Serializer):
    user = MeUserSerializer()
    organization = MeOrganizationSerializer(allow_null=True)
    memberships = MeMembershipSerializer(many=True)
    permissions = serializers.ListField(child=serializers.CharField())
    roles = serializers.ListField(child=serializers.CharField())
    portal = serializers.ChoiceField(choices=["gude", "pme", "platform", "none"])
    pme_ids = serializers.ListField(child=serializers.UUIDField())


# --- Rôles personnalisés (V1) --------------------------------------------------------------------------------


class RoleAdminSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)
    is_system = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "code", "label", "default_scope", "is_pme_role", "is_system", "members", "permissions"]
        read_only_fields = fields

    def get_is_system(self, obj) -> bool:
        return obj.organization_id is None

    def get_members(self, obj) -> int:
        from .roles import members_count

        return members_count(obj)


class PermissionItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class PermissionGroupSerializer(serializers.Serializer):
    label = serializers.CharField()
    permissions = PermissionItemSerializer(many=True)


class RolesAdminSerializer(serializers.Serializer):
    roles = RoleAdminSerializer(many=True)
    permission_groups = PermissionGroupSerializer(many=True)
    grantable = serializers.ListField(child=serializers.CharField(), help_text="Permissions que vous pouvez accorder.")


class RoleWriteSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40, required=False)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)
    default_scope = serializers.ChoiceField(choices=["ORG", "PROGRAMME", "PORTEFEUILLE"], required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)
