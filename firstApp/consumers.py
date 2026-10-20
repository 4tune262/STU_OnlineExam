
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .models import StudentExam, TeachingAssignment, UserProfile


class ScreenShareSignalingConsumer(AsyncJsonWebsocketConsumer):
    """
    Chuyển tiếp tín hiệu WebRTC giữa:
    - Sinh viên sở hữu lượt thi.
    - Giảng viên được phân công giám sát lượt thi đó.

    WebSocket chỉ chuyển tiếp offer, answer và ICE candidate.
    Video được truyền qua WebRTC, không đi qua Django.
    """

    async def connect(self):
        self.student_exam_id = self.scope["url_route"]["kwargs"].get(
            "student_exam_id"
        )
        self.room_group_name = (
            f"screen_share_exam_{self.student_exam_id}"
        )

        user = self.scope.get("user", AnonymousUser())

        if not user.is_authenticated:
            await self.close(code=4401)
            return

        permission = await self.check_permission(
            user.pk,
            self.student_exam_id,
        )

        if not permission["allowed"]:
            await self.close(code=4403)
            return

        self.peer_role = permission["role"]

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        await self.send_json({
            "type": "connected",
            "role": self.peer_role,
            "student_exam_id": int(self.student_exam_id),
        })

        # Báo cho phía còn lại biết có người mới tham gia.
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "peer_joined",
                "sender_channel": self.channel_name,
                "role": self.peer_role,
            },
        )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "peer_left",
                    "sender_channel": self.channel_name,
                    "role": getattr(self, "peer_role", ""),
                },
            )

    async def receive_json(self, content, **kwargs):
        """
        Chỉ cho phép các loại tín hiệu WebRTC cần thiết.
        Không nhận dữ liệu video hoặc file từ client.
        """

        message_type = content.get("type")

        allowed_types = {
            "offer",
            "answer",
            "ice_candidate",
            "request_offer",
        }
        if message_type not in allowed_types:
            await self.send_json({
                "type": "error",
                "message": "Loại tín hiệu không hợp lệ.",
            })
            return
        if message_type == "request_offer":
            if self.peer_role != "lecturer":
                await self.send_json({
                    "type": "error",
                    "message": "Chỉ giảng viên được yêu cầu tạo offer.",
                })
                return

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "request_student_offer",
                    "sender_channel": self.channel_name,
                },
            )
            return
        # Phân vai để không cho sinh viên giả làm giảng viên.
        if message_type == "offer" and self.peer_role != "student":
            await self.send_json({
                "type": "error",
                "message": "Chỉ sinh viên được gửi offer.",
            })
            return

        if message_type == "answer" and self.peer_role != "lecturer":
            await self.send_json({
                "type": "error",
                "message": "Chỉ giảng viên được gửi answer.",
            })
            return

        payload = {
            "type": message_type,
            "sender_channel": self.channel_name,
            "sender_role": self.peer_role,
        }

        # Chỉ chuyển tiếp các trường tín hiệu đã cho phép.
        if message_type in {"offer", "answer"}:
            description = content.get("description")

            if not isinstance(description, dict):
                await self.send_json({
                    "type": "error",
                    "message": "Thiếu dữ liệu SDP hợp lệ.",
                })
                return

            if description.get("type") != message_type:
                await self.send_json({
                    "type": "error",
                    "message": "Loại SDP không khớp.",
                })
                return

            if not isinstance(description.get("sdp"), str):
                await self.send_json({
                    "type": "error",
                    "message": "SDP không hợp lệ.",
                })
                return

            if len(description["sdp"]) > 100_000:
                await self.send_json({
                    "type": "error",
                    "message": "SDP vượt quá giới hạn.",
                })
                return

            payload["description"] = description

        elif message_type == "ice_candidate":
            candidate = content.get("candidate")

            if not isinstance(candidate, dict):
                await self.send_json({
                    "type": "error",
                    "message": "ICE candidate không hợp lệ.",
                })
                return

            if len(json.dumps(candidate)) > 10_000:
                await self.send_json({
                    "type": "error",
                    "message": "ICE candidate vượt quá giới hạn.",
                })
                return

            payload["candidate"] = candidate

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "relay_signal",
                "payload": payload,
            },
        )

    async def relay_signal(self, event):
        # Không gửi tín hiệu ngược lại cho chính người gửi.
        if event["payload"]["sender_channel"] == self.channel_name:
            return

        await self.send_json(event["payload"])

    async def request_student_offer(self, event):
        if event["sender_channel"] == self.channel_name:
            return

        if self.peer_role != "student":
            return

        await self.send_json({
            "type": "request_offer",
        })
    async def peer_joined(self, event):
        if event["sender_channel"] == self.channel_name:
            return

        await self.send_json({
            "type": "peer_joined",
            "role": event["role"],
        })

    async def peer_left(self, event):
        if event["sender_channel"] == self.channel_name:
            return

        await self.send_json({
            "type": "peer_left",
            "role": event["role"],
        })

    @database_sync_to_async
    def check_permission(self, user_id, student_exam_id):
        """
        Kiểm tra quyền trên database.
        Không tin student_exam_id do trình duyệt gửi lên.
        """

        try:
            student_exam = (
                StudentExam.objects
                .select_related(
                    "student",
                    "exam",
                    "exam__offering",
                )
                .get(pk=student_exam_id)
            )
        except (
            StudentExam.DoesNotExist,
            ValueError,
            TypeError,
        ):
            return {"allowed": False}

        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return {"allowed": False}

        # Sinh viên chỉ được tham gia lượt thi của chính mình.
        if student_exam.student_id == user.pk:
            if (
                student_exam.is_submitted
                or student_exam.is_terminated
                or not student_exam.is_screen_sharing
            ):
                return {"allowed": False}

            return {
                "allowed": True,
                "role": "student",
            }

        # Admin Django được phép giám sát.
        if user.is_staff or user.is_superuser:
            return {
                "allowed": True,
                "role": "lecturer",
            }

        # Giảng viên phải được phân công vào lớp học phần
        # của bài thi đang được giám sát.
        try:
            profile = user.userprofile
        except UserProfile.DoesNotExist:
            return {"allowed": False}

        if profile.role != "lecturer":
            return {"allowed": False}

        offering_id = student_exam.exam.offering_id

        if not offering_id:
            return {"allowed": False}

        assigned = TeachingAssignment.objects.filter(
            course_offering_id=offering_id,
            lecturer=profile,
        ).exists()

        if not assigned:
            return {"allowed": False}

        if (
            student_exam.is_submitted
            or student_exam.is_terminated
            or not student_exam.is_screen_sharing
        ):
            return {"allowed": False}

        return {
            "allowed": True,
            "role": "lecturer",
        }
