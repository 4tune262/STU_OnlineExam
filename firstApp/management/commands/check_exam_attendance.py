from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from firstApp.models import ExamComputer, StudentExam


class Command(BaseCommand):
    help = (
        "Mark assigned students absent after the attendance grace period "
        "when the room camera is online."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--grace-minutes",
            type=int,
            default=20,
        )

        parser.add_argument(
            "--heartbeat-seconds",
            type=int,
            default=120,
        )

    def handle(self, *args, **options):
        now = timezone.now()

        grace_period = timedelta(
            minutes=options["grace_minutes"]
        )

        heartbeat_window = timedelta(
            seconds=options["heartbeat_seconds"]
        )

        online_since = now - heartbeat_window

        marked_absent = 0

        # ==========================================================
        # 1. LẤY CÁC MÁY ĐANG ĐƯỢC GÁN SINH VIÊN
        #    VÀ CAMERA PHÒNG VẪN ĐANG ONLINE
        # ==========================================================

        computers = (
            ExamComputer.objects
            .filter(
                status="assigned",
                student__isnull=False,
                camera_last_seen_at__gte=online_since,
            )
            .select_related(
                "student__user",
                "exam_session__exam",
            )
        )

        # ==========================================================
        # 2. DUYỆT TỪNG MÁY
        # ==========================================================

        for item in computers:

            session = item.exam_session

            # Chưa hết thời gian cho phép điểm danh.
            if now < session.start_time + grace_period:
                continue

            # Sinh viên đã được camera/presence phát hiện.
            if (
                item.presence_last_seen_at
                and item.presence_last_seen_at >= session.start_time
            ):
                continue

            # ======================================================
            # 3. KHÓA ExamComputer TRONG TRANSACTION
            #
            # QUAN TRỌNG:
            # Không dùng select_related() cùng select_for_update()
            # vì student/exam_session có thể là nullable FK.
            # PostgreSQL không cho FOR UPDATE trên nullable side
            # của OUTER JOIN.
            # ======================================================

            with transaction.atomic():

                computer = (
                    ExamComputer.objects
                    .select_for_update()
                    .get(pk=item.pk)
                )

                # ==================================================
                # 4. KIỂM TRA LẠI SAU KHI ĐÃ LOCK
                #
                # Có thể trong lúc chờ lock, một request khác đã
                # thay đổi trạng thái của máy.
                # ==================================================

                if computer.status != "assigned":
                    continue

                if not computer.student_id:
                    continue

                if (
                    not computer.camera_last_seen_at
                    or computer.camera_last_seen_at < online_since
                ):
                    continue

                if (
                    computer.presence_last_seen_at
                    and computer.presence_last_seen_at
                    >= computer.exam_session.start_time
                ):
                    continue

                # ==================================================
                # 5. LẤY SINH VIÊN VÀ BÀI THI
                #
                # Không dùng select_related() trong queryset
                # select_for_update() ở trên.
                # Django sẽ lấy các quan hệ này sau khi ExamComputer
                # đã được lock.
                # ==================================================

                student_user = computer.student.user
                exam = computer.exam_session.exam

                # ==================================================
                # 6. TÌM StudentExam ĐANG THI
                # ==================================================

                attempt = (
                    StudentExam.objects
                    .filter(
                        student=student_user,
                        exam=exam,
                        is_submitted=False,
                    )
                    .order_by("-started_at")
                    .first()
                )

                # ==================================================
                # 7. ĐÁNH DẤU MÁY LÀ ABSENT
                # ==================================================

                computer.status = "absent"

                computer.note = (
                    "Không phát hiện sinh viên trong 20 phút; "
                    "camera phòng đang hoạt động."
                )

                computer.save(
                    update_fields=[
                        "status",
                        "note",
                    ]
                )

                # ==================================================
                # 8. NẾU SINH VIÊN ĐÃ CÓ StudentExam
                #    → KẾT THÚC BÀI THI
                # ==================================================

                if attempt:

                    attempt.exam_computer = computer
                    attempt.score = 0
                    attempt.finished_at = now
                    attempt.is_submitted = True

                    attempt.termination_reason = (
                        "Vắng sau thời gian chờ điểm danh."
                    )

                    attempt.save(
                        update_fields=[
                            "exam_computer",
                            "score",
                            "finished_at",
                            "is_submitted",
                            "termination_reason",
                        ]
                    )

                # ==================================================
                # 9. NẾU CHƯA CÓ StudentExam
                #    → TẠO BẢN GHI VẮNG
                # ==================================================

                else:

                    StudentExam.objects.create(
                        student=student_user,
                        exam=exam,
                        exam_computer=computer,
                        score=0,
                        is_submitted=True,
                        finished_at=now,
                        termination_reason=(
                            "Vắng sau thời gian chờ điểm danh."
                        ),
                    )

                marked_absent += 1

        # ==========================================================
        # 10. THÔNG BÁO KẾT QUẢ
        # ==========================================================

        self.stdout.write(
            self.style.SUCCESS(
                f"Đã ghi nhận {marked_absent} sinh viên vắng."
            )
        )