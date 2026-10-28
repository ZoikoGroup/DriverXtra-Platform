from django.utils import timezone
from rest_framework import generics, permissions, status, views
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer

TRUE_VALUES = {'true', '1', 'yes'}
FALSE_VALUES = {'false', '0', 'no'}


def recipient_notifications(user):
    """All notification queries are scoped to the authenticated recipient."""
    return Notification.objects.filter(recipient=user)


class NotificationListView(generics.ListAPIView):
    """List the current user's notifications, newest first.

    GET /api/v1/notifications/
    GET /api/v1/notifications/?unread=true
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        queryset = recipient_notifications(self.request.user).order_by('-created_at', '-id')
        unread_param = self.request.query_params.get('unread')
        if unread_param is not None:
            value = unread_param.strip().lower()
            if value in TRUE_VALUES:
                queryset = queryset.filter(is_read=False)
            elif value not in FALSE_VALUES:
                raise DRFValidationError({'unread': "Must be 'true' or 'false'."})
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type.strip())
        return queryset


class NotificationUnreadCountView(views.APIView):
    """Return the current user's unread notification count.

    GET /api/v1/notifications/unread-count/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = recipient_notifications(request.user).filter(is_read=False).count()
        return Response({"status": "success", "unread_count": count}, status=status.HTTP_200_OK)


class NotificationMarkReadView(views.APIView):
    """Mark one of the current user's notifications as read.

    POST /api/v1/notifications/<id>/read/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        notification = generics.get_object_or_404(recipient_notifications(request.user), id=id)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at', 'updated_at'])
        return Response(
            {
                "status": "success",
                "message": "Notification marked as read.",
                "notification": NotificationSerializer(notification).data,
            },
            status=status.HTTP_200_OK,
        )


class NotificationMarkAllReadView(views.APIView):
    """Mark all of the current user's unread notifications as read.

    POST /api/v1/notifications/read-all/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        updated = recipient_notifications(request.user).filter(is_read=False).update(
            is_read=True,
            read_at=now,
            updated_at=now,
        )
        return Response(
            {
                "status": "success",
                "message": "All notifications marked as read.",
                "updated_count": updated,
            },
            status=status.HTTP_200_OK,
        )


class NotificationDeleteView(views.APIView):
    """Delete one of the current user's notifications.

    DELETE /api/v1/notifications/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, id):
        notification = generics.get_object_or_404(recipient_notifications(request.user), id=id)
        notification.delete()
        return Response(
            {"status": "success", "message": "Notification deleted."},
            status=status.HTTP_200_OK,
        )
