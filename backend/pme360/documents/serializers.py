from rest_framework import serializers

from .models import Document, DocumentCheck, DocumentType, DocumentVersion


class DocumentTypeSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.code", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = DocumentType
        fields = [
            "id",
            "code",
            "name",
            "category",
            "category_name",
            "description",
            "guidance",
            "period_kind",
            "validity_days",
            "freshness_days",
            "sensitive",
        ]
        read_only_fields = fields


class DocumentCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCheck
        fields = ["check_code", "result", "message", "details"]
        read_only_fields = fields


class DocumentVersionSerializer(serializers.ModelSerializer):
    checks = DocumentCheckSerializer(many=True, read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True, default=None)
    downloadable = serializers.SerializerMethodField()

    class Meta:
        model = DocumentVersion
        fields = [
            "id",
            "version_no",
            "original_filename",
            "extension",
            "mime_detected",
            "size_bytes",
            "sha256",
            "av_status",
            "av_engine",
            "av_signature",
            "text_status",
            "page_count",
            "duplicate_of",
            "processed_at",
            "uploaded_by_name",
            "created_at",
            "checks",
            "downloadable",
        ]
        read_only_fields = fields

    def get_downloadable(self, obj) -> bool:
        return bool(obj.storage_key) and obj.av_status == DocumentVersion.Antivirus.SAIN


class PmeRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class DeadlineRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    period_label = serializers.CharField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    due_date = serializers.DateField()


class DocumentSerializer(serializers.ModelSerializer):
    document_type = DocumentTypeSerializer(read_only=True)
    status = serializers.CharField(source="status_display", read_only=True)
    pme = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()
    verified_by_name = serializers.CharField(source="verified_by.full_name", read_only=True, default=None)
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True, default=None)

    class Meta:
        model = Document
        fields = [
            "id",
            "pme",
            "document_type",
            "title",
            "status",
            "deadline",
            "period_start",
            "period_end",
            "issued_at",
            "expires_at",
            "integrity_status",
            "validity_status",
            "currency_status",
            "verification_status",
            "conformity_status",
            "decision_reason",
            "verified_by_name",
            "verified_at",
            "uploaded_by_name",
            "uploaded_via",
            "current_version_no",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_pme(self, obj) -> PmeRefSerializer:
        return {"id": str(obj.pme_id), "name": obj.pme.legal_name}

    def get_deadline(self, obj) -> DeadlineRefSerializer(allow_null=True):
        if not obj.deadline_id:
            return None
        return {
            "id": str(obj.deadline_id),
            "period_label": obj.deadline.period_label,
            "period_start": obj.deadline.period_start,
            "period_end": obj.deadline.period_end,
            "due_date": obj.deadline.due_date,
        }


class DocumentDetailSerializer(DocumentSerializer):
    versions = DocumentVersionSerializer(many=True, read_only=True)

    class Meta(DocumentSerializer.Meta):
        fields = [*DocumentSerializer.Meta.fields, "versions"]
        read_only_fields = fields


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    document_type = serializers.CharField(max_length=40, required=False, allow_blank=True)
    document_id = serializers.UUIDField(required=False, allow_null=True)
    deadline_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")
    period_start = serializers.DateField(required=False, allow_null=True)
    period_end = serializers.DateField(required=False, allow_null=True)
    issued_at = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if not (attrs.get("document_type") or attrs.get("document_id") or attrs.get("deadline_id")):
            raise serializers.ValidationError({"document_type": ["Précisez le type de document."]})
        if attrs.get("period_start") and attrs.get("period_end") and attrs["period_end"] < attrs["period_start"]:
            raise serializers.ValidationError({"period_end": ["La fin de période précède son début."]})
        return attrs


class VerifySerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[c for c in Document.Conformity.choices if c[0] != "NON_EVALUE"])
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    period_start = serializers.DateField(required=False, allow_null=True)
    period_end = serializers.DateField(required=False, allow_null=True)
    issued_at = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateField(required=False, allow_null=True)


class DownloadUrlSerializer(serializers.Serializer):
    url = serializers.CharField()
    expires_in = serializers.IntegerField()
