from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Recipient-facing notification payload (email delivery internals are not exposed)."""

    class Meta:
        model = Notification
        fields = [
            'id',
            'event_type',
            'title',
            'message',
            'link',
            'resource_type',
            'resource_id',
            'is_read',
            'read_at',
            'created_at',
        ]
        read_only_fields = fields
