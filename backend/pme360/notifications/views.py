from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from pme360.compliance.defaults import MANDATORY_EVENTS, NOTIFICATION_TEMPLATES

from .models import Notification, NotificationPreference
from .services import EVENT_LABELS


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "event_code", "title", "body", "link", "severity", "read_at", "emailed_at", "created_at"]
        read_only_fields = fields


class ReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    all = serializers.BooleanField(default=False)


class CountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()


class PreferenceSerializer(serializers.Serializer):
    event_code = serializers.ChoiceField(choices=list(NOTIFICATION_TEMPLATES))
    label = serializers.CharField(read_only=True)
    in_app = serializers.BooleanField()
    email = serializers.BooleanField()
    mandatory = serializers.BooleanField(read_only=True)


class NotificationListView(APIView):
    """Notifications de l'utilisateur dans l'organisation active."""

    @extend_schema(parameters=[OpenApiParameter("unread", bool)], responses=NotificationSerializer(many=True))
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        if request.query_params.get("unread") in ("1", "true"):
            notifications = notifications.filter(read_at__isnull=True)
        return Response(NotificationSerializer(notifications[:100], many=True).data)


class NotificationCountView(APIView):
    @extend_schema(responses=CountSerializer)
    def get(self, request):
        return Response({"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count()})


class NotificationReadView(APIView):
    @extend_schema(request=ReadSerializer, responses=CountSerializer)
    def post(self, request):
        serializer = ReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unread = Notification.objects.filter(user=request.user, read_at__isnull=True)
        if not serializer.validated_data["all"]:
            unread = unread.filter(pk__in=serializer.validated_data["ids"])
        unread.update(read_at=timezone.now())
        return Response({"unread": Notification.objects.filter(user=request.user, read_at__isnull=True).count()})


class NotificationPreferencesView(APIView):
    def _payload(self, user):
        existing = {p.event_code: p for p in NotificationPreference.objects.filter(user=user)}
        return [
            {
                "event_code": code,
                "label": EVENT_LABELS.get(code, code),
                "in_app": existing[code].in_app if code in existing else True,
                "email": existing[code].email if code in existing else True,
                "mandatory": code in MANDATORY_EVENTS,
            }
            for code in NOTIFICATION_TEMPLATES
        ]

    @extend_schema(responses=PreferenceSerializer(many=True))
    def get(self, request):
        return Response(PreferenceSerializer(self._payload(request.user), many=True).data)

    @extend_schema(request=PreferenceSerializer(many=True), responses=PreferenceSerializer(many=True))
    def put(self, request):
        serializer = PreferenceSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data:
            NotificationPreference.objects.update_or_create(
                user=request.user,
                event_code=item["event_code"],
                defaults={"in_app": item["in_app"], "email": item["email"]},
            )
        return Response(PreferenceSerializer(self._payload(request.user), many=True).data)
