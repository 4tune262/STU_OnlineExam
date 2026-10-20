
from django.urls import path

from .consumers import ScreenShareSignalingConsumer


websocket_urlpatterns = [
    path(
        "ws/screen-share/<int:student_exam_id>/",
        ScreenShareSignalingConsumer.as_asgi(),
        name="screen_share_signaling",
    ),
]
