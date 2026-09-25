from datetime import date

from rest_framework import serializers

from .models import LegalForm, Pme, PmeAssignment, PmeEnrollment, PmePerson, Region, Sector


class RefField(serializers.PrimaryKeyRelatedField):
    """Clé étrangère vers une nomenclature : écrite par identifiant, lue sous forme ``{id, code, name}``.

    Le ``queryset`` doit être un Manager (évalué à chaque requête, dans le tenant courant), jamais un QuerySet
    construit à l'import du module.
    """

    def use_pk_only_optimization(self) -> bool:
        return False

    def to_representation(self, value):
        return {"id": value.pk, "code": value.code, "name": value.name}


class RefItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = PmePerson
        fields = [
            "id",
            "full_name",
            "role",
            "share_pct",
            "is_primary_contact",
            "phone",
            "email",
            "gender",
            "birth_year",
        ]
        read_only_fields = ["id"]

    def validate_birth_year(self, value):
        if value is not None and not 1900 <= value <= date.today().year - 15:
            raise serializers.ValidationError("Année de naissance invalide.")
        return value


class AssignedUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class AssignmentSerializer(serializers.ModelSerializer):
    user = AssignedUserSerializer(read_only=True)

    class Meta:
        model = PmeAssignment
        fields = ["id", "user", "role_in_pme", "start_date", "end_date"]
        read_only_fields = fields


class AssignmentCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role_in_pme = serializers.ChoiceField(choices=PmeAssignment.RoleInPme.choices)


class EnrolledCohortSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    programme = serializers.CharField(source="programme.name")


class EnrollmentSerializer(serializers.ModelSerializer):
    cohort = EnrolledCohortSerializer(read_only=True)

    class Meta:
        model = PmeEnrollment
        fields = ["id", "cohort", "enrolled_at", "exited_at", "exit_reason"]
        read_only_fields = fields


class AdvisorSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


def _principal_advisor(pme: Pme):
    assignments = getattr(pme, "active_principal", None)
    if assignments is None:
        assignments = list(
            pme.assignments.filter(
                end_date__isnull=True, role_in_pme=PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL
            ).select_related("user")
        )
    return {"id": assignments[0].user_id, "full_name": assignments[0].user.full_name} if assignments else None


class PmeListSerializer(serializers.ModelSerializer):
    sector = RefItemSerializer(allow_null=True)
    region = RefItemSerializer(allow_null=True)
    principal_advisor = serializers.SerializerMethodField()

    class Meta:
        model = Pme
        fields = [
            "id",
            "legal_name",
            "trade_name",
            "rccm_number",
            "sector",
            "region",
            "commune",
            "size_category",
            "headcount",
            "lifecycle_status",
            "principal_advisor",
            "last_activity_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_principal_advisor(self, obj) -> AdvisorSummarySerializer(allow_null=True):
        return _principal_advisor(obj)


class PmeSerializer(serializers.ModelSerializer):
    legal_form = RefField(queryset=LegalForm.objects, allow_null=True, required=False)
    sector = RefField(queryset=Sector.objects, allow_null=True, required=False)
    region = RefField(queryset=Region.objects, allow_null=True, required=False)
    principal_advisor = serializers.SerializerMethodField()
    persons = PersonSerializer(many=True, read_only=True)
    assignments = serializers.SerializerMethodField()
    enrollments = serializers.SerializerMethodField()

    class Meta:
        model = Pme
        fields = [
            "id",
            "legal_name",
            "trade_name",
            "legal_form",
            "rccm_number",
            "ncc",
            "cnps_employer_number",
            "creation_date",
            "sector",
            "region",
            "commune",
            "address",
            "phone",
            "email",
            "website",
            "headcount",
            "size_category",
            "lifecycle_status",
            "onboarding_started_at",
            "exited_at",
            "exit_reason",
            "last_activity_at",
            "created_at",
            "updated_at",
            "principal_advisor",
            "persons",
            "assignments",
            "enrollments",
        ]
        read_only_fields = [
            "id",
            "lifecycle_status",
            "onboarding_started_at",
            "exited_at",
            "exit_reason",
            "last_activity_at",
            "created_at",
            "updated_at",
        ]

    def validate_legal_name(self, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Raison sociale trop courte.")
        return value

    def validate_creation_date(self, value):
        if value and value > date.today():
            raise serializers.ValidationError("La date de création ne peut pas être dans le futur.")
        return value

    def get_principal_advisor(self, obj) -> AdvisorSummarySerializer(allow_null=True):
        return _principal_advisor(obj)

    def get_assignments(self, obj) -> AssignmentSerializer(many=True):
        active = obj.assignments.filter(end_date__isnull=True).select_related("user")
        return AssignmentSerializer(active, many=True).data

    def get_enrollments(self, obj) -> EnrollmentSerializer(many=True):
        return EnrollmentSerializer(obj.enrollments.select_related("cohort__programme"), many=True).data


class PmeCreateSerializer(PmeSerializer):
    primary_person = PersonSerializer(required=False, write_only=True)
    advisor_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    cohort_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    confirm_duplicates = serializers.BooleanField(default=False, write_only=True)
    start_onboarding = serializers.BooleanField(default=False, write_only=True)

    class Meta(PmeSerializer.Meta):
        fields = PmeSerializer.Meta.fields + [
            "primary_person",
            "advisor_id",
            "cohort_id",
            "confirm_duplicates",
            "start_onboarding",
        ]


class TransitionSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=Pme.LifecycleStatus.choices)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    exit_reason = serializers.ChoiceField(choices=Pme.ExitReason.choices, required=False, allow_blank=True, default="")


class DuplicateQuerySerializer(serializers.Serializer):
    legal_name = serializers.CharField(required=False, allow_blank=True, default="")
    rccm_number = serializers.CharField(required=False, allow_blank=True, default="")
    ncc = serializers.CharField(required=False, allow_blank=True, default="")


class DuplicateSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    legal_name = serializers.CharField()
    rccm_number = serializers.CharField()
    reasons = serializers.ListField(child=serializers.ChoiceField(choices=["rccm", "ncc", "name"]))
    similarity = serializers.FloatField(required=False)
    accessible = serializers.BooleanField()


class TimelineEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    label = serializers.CharField()
    actor = serializers.CharField(allow_null=True)
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
