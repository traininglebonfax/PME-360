from rest_framework import serializers

from .models import Cohort, Organization, Programme
from .services import effective_settings, validate_settings


class OrganizationSerializer(serializers.ModelSerializer):
    settings = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "type", "country", "branding", "settings", "ai_external_allowed", "status"]
        read_only_fields = ["id", "slug", "type", "country", "status"]

    def get_settings(self, obj: Organization) -> dict:
        return effective_settings(obj)


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    settings = serializers.DictField(required=False)

    class Meta:
        model = Organization
        fields = ["name", "branding", "settings", "ai_external_allowed"]

    def validate_settings(self, value: dict) -> dict:
        return validate_settings(value)

    def update(self, instance: Organization, validated_data: dict) -> Organization:
        new_settings = validated_data.pop("settings", None)
        if new_settings is not None:
            instance.settings = {**instance.settings, **new_settings}
        return super().update(instance, validated_data)


class CohortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cohort
        fields = ["id", "programme", "name", "start_date", "created_at"]
        read_only_fields = ["id", "programme", "created_at"]


class ProgrammeSerializer(serializers.ModelSerializer):
    cohorts = CohortSerializer(many=True, read_only=True)

    class Meta:
        model = Programme
        fields = [
            "id",
            "name",
            "description",
            "start_date",
            "end_date",
            "funder",
            "objectives",
            "cohorts",
            "created_at",
        ]
        read_only_fields = ["id", "cohorts", "created_at"]

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": ["La date de fin précède la date de début."]})
        return attrs


class PlatformOrganizationSerializer(serializers.ModelSerializer):
    """Vue plateforme : aucune donnée métier, uniquement l'identité du tenant."""

    admin_email = serializers.EmailField(write_only=True)
    admin_full_name = serializers.CharField(write_only=True, max_length=200)

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "type", "status", "created_at", "admin_email", "admin_full_name"]
        read_only_fields = ["id", "status", "created_at"]
