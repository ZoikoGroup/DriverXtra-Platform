from django.urls import re_path
from apps.workshops import consumers

websocket_urlpatterns = [
    re_path(
        r"^ws/workshops/conversations/(?P<conversation_id>[0-9a-fA-F-]+)/?$",
        consumers.WorkshopChatConsumer.as_asgi(),
    ),
]

