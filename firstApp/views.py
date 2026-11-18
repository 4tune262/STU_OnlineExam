import json
import base64
import copy
import math
import random
import re
import hmac
from collections import defaultdict
import logging
logger = logging.getLogger(__name__)
import uuid
from uuid import uuid4
from io import BytesIO
from datetime import timedelta
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import Http404, HttpResponse, JsonResponse, QueryDict, HttpResponseForbidden
from django.contrib.auth import login
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django_ratelimit.decorators import ratelimit
from django.core.exceptions import ValidationError
import pyotp
import time
from django.db import transaction
from django.utils import timezone

from .models import TOTPDevice
from .totp_utils import encrypt_totp_secret, decrypt_totp_secret
from .models import (
    UserProfile,
    FaceProfile,
    Course,
    CourseOffering,
    Exam,
    ExamComputer,
    ProctorEvent,
    StudentExam,
    StudentAnswer,
    TeachingAssignment,
    Enrollment,
    ExamAttendance,
    ExamAssignment,
    ExamPaper,
)
from .services.exam_paper_service import (
    create_exam_paper,
    copy_exam_paper,
    assign_paper_manual,
    assign_papers_random,
)
from .exam_engine import (
    build_student_snapshot,
    get_student_exam_questions,
)

from .vision import (
    classify_frame,
    proctoring_available,
)

from compiler.run import run_cpp, run_code_by_language


# ============================================================
# HOME
# ============================================================

def index(request):
    profile = (
        getattr(request.user, "userprofile", None)
        if request.user.is_authenticated
        else None
    )

    courses = Course.objects.none()
    exams = Exam.objects.none()
    completed_exam_count = 0
    now = timezone.now()

    if profile:

        # =====================================================
        # STUDENT
        # =====================================================

        if profile.role == "student":

            offering_ids = Enrollment.objects.filter(
                student=profile,
                status="active",
            ).values_list(
                "course_offering_id",
                flat=True,
            )

            courses = (
                Course.objects
                .filter(
                    is_active=True,
                    offerings__enrollments__student=profile,
                    offerings__enrollments__status="active",
                )
                .distinct()
            )

            exams = (
                Exam.objects
                .filter(
                    is_active=True,
                    end_time__gte=now,
                )
                .filter(
                    Q(offering__isnull=True)
                    | Q(offering_id__in=offering_ids)
                )
            )

            completed_exam_count = StudentExam.objects.filter(
                student=request.user,
                is_submitted=True,
            ).count()

        # =====================================================
        # LECTURER
        # =====================================================

        elif profile.role == "lecturer":

            offering_ids = TeachingAssignment.objects.filter(
                lecturer=profile,
            ).values_list(
                "course_offering_id",
                flat=True,
            )

            courses = (
                Course.objects
                .filter(
                    is_active=True,
                    offerings__teaching_assignments__lecturer=profile,
                )
                .distinct()
            )

            exams = (
                Exam.objects
                .filter(
                    is_active=True,
                    end_time__gte=now,
                )
                .filter(
                    Q(offering__isnull=True)
                    | Q(offering_id__in=offering_ids)
                )
            )

        # =====================================================
        # ADMIN
        # =====================================================

        else:

            courses = Course.objects.filter(
                is_active=True
            )

            exams = Exam.objects.filter(
                is_active=True,
                end_time__gte=now,
            )

    upcoming_exams = list(
        exams
        .select_related(
            "course",
            "offering",
        )
        .order_by("start_time")[:5]
    )

    for exam in upcoming_exams:

        exam.dashboard_course_label = (
            f"{exam.course.code} · {exam.offering.group_code}"
            if exam.offering_id
            else exam.course.code
        )

        if profile and profile.role == "student":

            is_open = now >= exam.start_time

            exam.dashboard_action_url = (
                reverse("take_exam", args=(exam.pk,))
                if is_open
                else "#"
            )

            exam.dashboard_action_label = (
                "Vào thi"
                if is_open
                else "Sắp mở"
            )

            exam.dashboard_action_icon = (
                "bi bi-arrow-up-right"
                if is_open
                else "bi bi-clock"
            )

            exam.dashboard_action_disabled = not is_open

        # elif profile and exam.offering_id:
        #
        #     exam.dashboard_action_url = reverse(
        #         "teacher_exam_report",
        #         args=(exam.pk,),
        #     )
        #
        #     exam.dashboard_action_label = "Xem kết quả lớp"
        #     exam.dashboard_action_icon = "bi bi-clipboard-data"
        #     exam.dashboard_action_disabled = False

        elif profile and profile.role == "lecturer" and exam.offering_id:

            exam.dashboard_action_url = reverse(
                "teacher_monitor"
            )

            exam.dashboard_action_label = "Vào giám sát"

            exam.dashboard_action_icon = (
                "bi bi-camera-video"
            )

            exam.dashboard_action_disabled = False

        else:

            exam.dashboard_action_url = reverse(
                "exam_list"
            )

            exam.dashboard_action_label = "Xem danh sách bài thi"
            exam.dashboard_action_icon = "bi bi-arrow-up-right"
            exam.dashboard_action_disabled = False

        exam.dashboard_action_class = (
            "exam-action exam-action-disabled"
            if exam.dashboard_action_disabled
            else "exam-action"
        )

    return render(
        request,
        "index.html",
        {
            "title": "Trang chủ STU Online Examination",
            "profile": profile,
            "dashboard_courses": courses.order_by("code")[:4],
            "upcoming_exams": upcoming_exams,
            "completed_exam_count": completed_exam_count,
            "now": timezone.now(),
        },
    )


# ============================================================
# QR LOGIN
# ============================================================

def qr_login_page(request):

    if request.user.is_authenticated:
        return redirect("home")

    return render(
        request,
        "login.html",
        {
            "title": "Đăng nhập Sinh viên",
        },
    )


@csrf_exempt
def verify_qr_login(request):

    if request.method == "POST":

        try:

            # data = json.loads(request.body)
            #
            # qr_token = data.get("qr_token")
            #
            # profile = (
            #     UserProfile.objects
            #     .filter(
            #         qr_token=qr_token
            #     )
            #     .select_related("user")
            #     .first()
            # )
            #
            # if profile and profile.user.is_active:
            #
            #     login(
            #         request,
            #         profile.user,
            #     )
            #
            #     return JsonResponse({
            #         "status": "success",
            #         "message": "Đăng nhập thành công!",
            #         "redirect_url": "/",
            #     })
            #
            # return JsonResponse({
            #     "status": "error",
            #     "message": (
            #         "Mã QR không hợp lệ "
            #         "hoặc tài khoản đã bị vô hiệu hóa."
            #     ),
            # })

            data = json.loads(request.body)
            qr_token_raw = data.get("qr_token")

            try:
                qr_token = uuid.UUID(str(qr_token_raw))
            except (ValueError, TypeError, AttributeError):
                return JsonResponse({
                    "status": "error",
                    "message": (
                        "Mã QR không hợp lệ "
                        "hoặc tài khoản đã bị vô hiệu hóa."
                    ),
                })

            profile = (
                UserProfile.objects
                .filter(qr_token=qr_token)
                .select_related("user")
                .first()
            )

            if profile and profile.user.is_active:
                login(request, profile.user)
                return JsonResponse({
                    "status": "success",
                    "message": "Đăng nhập thành công!",
                    "redirect_url": "/",
                })

            return JsonResponse({
                "status": "error",
                "message": (
                    "Mã QR không hợp lệ "
                    "hoặc tài khoản đã bị vô hiệu hóa."
                ),
            })




        except json.JSONDecodeError:

            return JsonResponse(

                {

                    "status": "error",

                    "message": "Dữ liệu đăng nhập không hợp lệ.",

                },

                status=400,

            )


        except Exception:

            return JsonResponse(

                {

                    "status": "error",

                    "message": (

                        "Không thể xử lý yêu cầu đăng nhập lúc này."

                    ),

                },

                status=500,

            )

    return JsonResponse({
        "status": "error",
        "message": "Invalid request method.",
    })


# ============================================================
# PROFILE
# ============================================================

@login_required(login_url="qr_login_page")
def profile_view(request):

    user_profile = request.user.userprofile

    if request.method == "POST":

        user_profile.phone = request.POST.get(
            "phone",
            "",
        )

        user_profile.address = request.POST.get(
            "address",
            "",
        )

        user_profile.birthday = (
            request.POST.get("birthday")
            or None
        )

        if "avatar" in request.FILES:
            user_profile.avatar = request.FILES["avatar"]

        user_profile.save()

        messages.success(
            request,
            "Cập nhật hồ sơ thành công!",
        )

        return redirect("profile")
    face_profile = FaceProfile.objects.filter(
        user_profile=user_profile
    ).first()
    totp_device = TOTPDevice.objects.filter(
        profile=user_profile
    ).first()
    return render(
        request,
        "profile.html",
        {
            "title": "Hồ sơ cá nhân",
            "profile": user_profile,
            "face_profile": face_profile,
            "totp_device": totp_device,
        },
    )


@login_required(login_url="qr_login_page")
@require_POST
def totp_setup(request):
    """
    Tạo hoặc cấp lại khóa TOTP đang ở trạng thái chưa kích hoạt.
    Chỉ người dùng đã đăng nhập mới được đăng ký TOTP.
    """
    try:
        profile = UserProfile.objects.get(user=request.user)

        # Khóa cũ đang bật không được âm thầm thay thế.
        device = TOTPDevice.objects.filter(
            profile=profile
        ).first()

        if device and device.is_enabled:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "TOTP đã được kích hoạt. "
                        "Không thể tạo lại khóa tại đây."
                    ),
                },
                status=409,
            )

        secret = pyotp.random_base32()

        # Sinh URI theo chuẩn otpauth để Authenticator quét.
        totp = pyotp.TOTP(secret)

        provisioning_uri = totp.provisioning_uri(
            name=request.user.username,
            issuer_name="STU Online Examination",
        )

        # Tạo ảnh QR PNG và chuyển thành Base64.
        import qrcode

        qr_image = qrcode.make(provisioning_uri)
        buffer = BytesIO()
        qr_image.save(buffer, format="PNG")

        qr_base64 = base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")

        # Chỉ lưu khóa đã mã hóa; chưa bật TOTP.
        with transaction.atomic():
            device, _ = TOTPDevice.objects.get_or_create(
                profile=profile,
                defaults={
                    "secret_encrypted": encrypt_totp_secret(
                        secret
                    ),
                    "is_enabled": False,
                },
            )

            if not device.is_enabled:
                device.secret_encrypted = encrypt_totp_secret(
                    secret
                )
                device.last_verified_counter = None
                device.failed_attempts = 0
                device.locked_until = None
                device.save(
                    update_fields=[
                        "secret_encrypted",
                        "last_verified_counter",
                        "failed_attempts",
                        "locked_until",
                        "updated_at",
                    ]
                )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    "Đã tạo mã đăng ký TOTP. "
                    "Hãy quét QR và xác minh mã để kích hoạt."
                ),
                "qr_image": f"data:image/png;base64,{qr_base64}",
            }
        )

    except UserProfile.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Tài khoản chưa có hồ sơ người dùng.",
            },
            status=400,
        )

    except Exception:
        logger.exception("Không thể tạo đăng ký TOTP.")
        return JsonResponse(
            {
                "success": False,
                "message": "Không thể tạo đăng ký TOTP lúc này.",
            },
            status=500,
        )





@login_required(login_url="qr_login_page")
@require_POST
def totp_confirm(request):
    """
    Xác minh mã TOTP trước khi kích hoạt phương thức đăng nhập.
    """
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "message": "Dữ liệu gửi lên không hợp lệ.",
            },
            status=400,
        )

    code = str(data.get("code", "")).strip()

    if not re.fullmatch(r"\d{6}", code):
        return JsonResponse(
            {
                "success": False,
                "message": "Mã xác minh phải gồm đúng 6 chữ số.",
            },
            status=400,
        )

    try:
        profile = UserProfile.objects.get(user=request.user)

        with transaction.atomic():
            device = (
                TOTPDevice.objects
                .select_for_update()
                .filter(profile=profile)
                .first()
            )

            if not device or not device.secret_encrypted:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Bạn chưa bắt đầu đăng ký TOTP.",
                    },
                    status=400,
                )

            if device.is_enabled:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "TOTP đã được kích hoạt.",
                    },
                    status=409,
                )

            secret = decrypt_totp_secret(
                device.secret_encrypted
            )

            totp = pyotp.TOTP(secret)

            # Cho phép sai lệch tối đa một chu kỳ 30 giây.
            if not totp.verify(code, valid_window=1):
                device.failed_attempts += 1

                if device.failed_attempts >= 5:
                    device.locked_until = (
                        timezone.now() + timedelta(minutes=5)
                    )
                    device.failed_attempts = 0

                device.save(
                    update_fields=[
                        "failed_attempts",
                        "locked_until",
                        "updated_at",
                    ]
                )

                return JsonResponse(
                    {
                        "success": False,
                        "message": "Mã TOTP không chính xác.",
                    },
                    status=400,
                )

            # Chỉ kích hoạt sau khi mã được xác minh.
            device.is_enabled = True
            device.failed_attempts = 0
            device.locked_until = None
            device.save(
                update_fields=[
                    "is_enabled",
                    "failed_attempts",
                    "locked_until",
                    "updated_at",
                ]
            )
            if (
                    device.locked_until
                    and device.locked_until > timezone.now()
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Bạn thử sai quá nhiều lần. Vui lòng thử lại sau.",
                    },
                    status=429,
                )

        return JsonResponse(
            {
                "success": True,
                "message": "Đã kích hoạt đăng nhập bằng TOTP.",
            }
        )

    except UserProfile.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Không tìm thấy hồ sơ người dùng.",
            },
            status=400,
        )

    except ValueError:
        logger.exception("Không thể giải mã khóa TOTP.")
        return JsonResponse(
            {
                "success": False,
                "message": "Không thể xác minh TOTP. Vui lòng liên hệ quản trị viên.",
            },
            status=500,
        )

    except Exception:
        logger.exception("Lỗi khi xác minh đăng ký TOTP.")
        return JsonResponse(
            {
                "success": False,
                "message": "Không thể xác minh TOTP lúc này.",
            },
            status=500,
        )




@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@require_POST
def verify_totp_login(request):
    """
    Đăng nhập bằng username/mã số + mã TOTP 6 chữ số.
    Không thay đổi luồng đăng nhập QR hoặc nhận diện khuôn mặt.
    """
    if getattr(request, "limited", False):
        return JsonResponse(
            {
                "success": False,
                "message": "Bạn thử đăng nhập quá nhiều lần. Vui lòng thử lại sau.",
            },
            status=429,
        )

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "success": False,
                "message": "Dữ liệu đăng nhập không hợp lệ.",
            },
            status=400,
        )

    identifier = str(data.get("identifier", "")).strip()
    code = str(data.get("code", "")).strip()

    if not identifier or not re.fullmatch(r"\d{6}", code):
        return JsonResponse(
            {
                "success": False,
                "message": "Vui lòng nhập tài khoản và mã xác minh gồm 6 chữ số.",
            },
            status=400,
        )

    # Tìm theo username, mã sinh viên hoặc mã giảng viên.
    profiles = (
        UserProfile.objects
        .filter(
            Q(user__username=identifier)
            | Q(student_id=identifier)
            | Q(lecturer_id=identifier)
        )
        .select_related("user")
        .distinct()
    )

    # Không chọn .first() vì mã số có thể bị trùng.
    if profiles.count() != 1:
        return JsonResponse(
            {
                "success": False,
                "message": "Thông tin đăng nhập hoặc mã TOTP không hợp lệ.",
            },
            status=401,
        )

    profile = profiles.first()

    if not profile.user.is_active:
        return JsonResponse(
            {
                "success": False,
                "message": "Thông tin đăng nhập hoặc mã TOTP không hợp lệ.",
            },
            status=401,
        )

    user = profile.user

    try:
        with transaction.atomic():
            device = (
                TOTPDevice.objects
                .select_for_update()
                .filter(profile=profile)
                .first()
            )

            if (
                not device
                or not device.is_enabled
                or not device.secret_encrypted
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Thông tin đăng nhập hoặc mã TOTP không hợp lệ.",
                    },
                    status=401,
                )

            now = timezone.now()

            if device.locked_until and device.locked_until > now:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Bạn thử sai quá nhiều lần. Vui lòng thử lại sau.",
                    },
                    status=429,
                )

            secret = decrypt_totp_secret(
                device.secret_encrypted
            )
            totp = pyotp.TOTP(secret)

            # Kiểm tra mã hiện tại và hai chu kỳ lân cận.
            # Chỉ chấp nhận counter mới hơn counter đã sử dụng.
            current_counter = int(time.time() // totp.interval)
            matched_counter = None

            for counter in (
                current_counter - 1,
                current_counter,
                current_counter + 1,
            ):
                if counter < 0:
                    continue

                if hmac.compare_digest(
                    totp.generate_otp(counter),
                    code,
                ):
                    matched_counter = counter
                    break

            if (
                matched_counter is None
                or (
                    device.last_verified_counter is not None
                    and matched_counter <= device.last_verified_counter
                )
            ):
                device.failed_attempts += 1

                if device.failed_attempts >= 5:
                    device.failed_attempts = 0
                    device.locked_until = (
                        now + timedelta(minutes=5)
                    )

                device.save(
                    update_fields=[
                        "failed_attempts",
                        "locked_until",
                        "updated_at",
                    ]
                )

                return JsonResponse(
                    {
                        "success": False,
                        "message": "Thông tin đăng nhập hoặc mã TOTP không hợp lệ.",
                    },
                    status=401,
                )

            # Ghi nhận counter đã dùng để chặn phát lại cùng mã.
            device.last_verified_counter = matched_counter
            device.failed_attempts = 0
            device.locked_until = None
            device.save(
                update_fields=[
                    "last_verified_counter",
                    "failed_attempts",
                    "locked_until",
                    "updated_at",
                ]
            )

        # Chỉ đăng nhập sau khi mã đã được xác minh thành công.
        login(request, user)

        return JsonResponse(
            {
                "success": True,
                "message": "Đăng nhập bằng TOTP thành công.",
                "redirect_url": "/",
            }
        )

    except ValueError:
        logger.exception("Không thể giải mã khóa TOTP khi đăng nhập.")
        return JsonResponse(
            {
                "success": False,
                "message": "Không thể xác minh TOTP lúc này.",
            },
            status=500,
        )

    except Exception:
        logger.exception("Lỗi khi đăng nhập bằng TOTP.")
        return JsonResponse(
            {
                "success": False,
                "message": "Không thể xử lý đăng nhập lúc này.",
            },
            status=500,
        )


# ============================================================
# FACE REGISTRATION
# ============================================================

@login_required(login_url="qr_login_page")
@require_POST
def register_face(request):
    """
    Đăng ký vector khuôn mặt cho tài khoản đang đăng nhập.
    Không lưu ảnh webcam gốc.
    """

    try:
        data = json.loads(request.body or "{}")

        # Người dùng phải đồng ý trước khi đăng ký.
        if data.get("consent") is not True:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Bạn cần đồng ý đăng ký khuôn mặt.",
                },
                status=400,
            )

        image_data = data.get("image", "")

        if not isinstance(image_data, str) or not image_data.startswith(
            "data:image/"
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Dữ liệu ảnh không hợp lệ.",
                },
                status=400,
            )

        # Chỉ chấp nhận ảnh JPEG hoặc PNG dạng Data URL.
        header, separator, encoded_image = image_data.partition(",")

        if (
            not separator
            or header.split(";")[0]
            not in ("data:image/jpeg", "data:image/png")
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Chỉ chấp nhận ảnh JPEG hoặc PNG.",
                },
                status=400,
            )

        # Kiểm tra kích thước dữ liệu trước khi giải mã.
        if len(encoded_image) > 3 * 1024 * 1024:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ảnh quá lớn. Vui lòng chụp lại.",
                },
                status=413,
            )

        try:
            image_bytes = base64.b64decode(
                encoded_image,
                validate=True,
            )
        except (ValueError, base64.binascii.Error):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không thể đọc dữ liệu ảnh.",
                },
                status=400,
            )

        # Giới hạn kích thước ảnh sau khi giải mã.
        if len(image_bytes) > 2 * 1024 * 1024:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ảnh vượt quá giới hạn 2 MB.",
                },
                status=413,
            )

        # Không cho phép đăng ký lại tự động để tránh ghi đè
        # hồ sơ khuôn mặt đã đăng ký.
        if FaceProfile.objects.filter(
            user_profile__user=request.user
        ).exists():
            return JsonResponse(
                {
                    "success": False,
                    "code": "face_already_registered",
                    "message": (
                        "Tài khoản đã có hồ sơ khuôn mặt. "
                        "Vui lòng liên hệ quản trị viên nếu cần đăng ký lại."
                    ),
                },
                status=409,
            )

        # Import tại chỗ để không tải mô hình AI khi Django khởi động.
        import numpy as np
        from deepface import DeepFace
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                source_image.verify()

            with Image.open(BytesIO(image_bytes)) as source_image:
                if source_image.format not in ("JPEG", "PNG"):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Định dạng ảnh không hợp lệ.",
                        },
                        status=400,
                    )

                if (
                    source_image.width < 160
                    or source_image.height < 160
                    or source_image.width > 3000
                    or source_image.height > 3000
                ):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": (
                                "Kích thước ảnh không phù hợp. "
                                "Vui lòng chụp lại."
                            ),
                        },
                        status=400,
                    )

                image_array = np.asarray(
                    source_image.convert("RGB")
                )

        except (UnidentifiedImageError, OSError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Tệp gửi lên không phải ảnh hợp lệ.",
                },
                status=400,
            )

        # Phát hiện khuôn mặt và tạo vector đặc trưng.
        representations = DeepFace.represent(
            img_path=image_array,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=True,
        )

        if len(representations) != 1:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Ảnh phải có đúng một khuôn mặt. "
                        "Vui lòng chụp lại trong điều kiện đủ sáng."
                    ),
                },
                status=400,
            )

        embedding = representations[0].get("embedding")

        if not embedding or len(embedding) != 512:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không thể tạo vector khuôn mặt hợp lệ.",
                },
                status=422,
            )

        user_profile = get_object_or_404(
            UserProfile,
            user=request.user,
        )

        FaceProfile.objects.create(
            user_profile=user_profile,
            embedding=[float(value) for value in embedding],
            model_name="Facenet512",
            detector_backend="opencv",
            is_active=True,
            consented_at=timezone.now(),
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Đăng ký khuôn mặt thành công!",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "message": "Dữ liệu gửi lên không hợp lệ.",
            },
            status=400,
        )

    except Exception:
        # Không trả chi tiết lỗi nội bộ hoặc dữ liệu nhạy cảm
        # về trình duyệt.
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Không thể xử lý khuôn mặt lúc này. "
                    "Vui lòng thử lại."
                ),
            },
            status=500,
        )



# ============================================================
# FACE LOGIN
# ============================================================

# @login_required(login_url="qr_login_page")
# def _face_login_placeholder(request):
#     return redirect("home")

@ratelimit(key="ip", rate="5/m", method="POST", block=False)
@require_POST
def verify_face_login(request):
    """
    Đăng nhập bằng cách so sánh khuôn mặt với hồ sơ đã đăng ký.
    Không lưu ảnh webcam được gửi lên.
    """

    if getattr(request, "limited", False):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Bạn đã gửi quá nhiều yêu cầu đăng nhập. "
                    "Vui lòng thử lại sau một phút."
                ),
            },
            status=429,
        )

    try:
        data = json.loads(request.body or "{}")

        if data.get("consent") is not True:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Bạn cần đồng ý sử dụng khuôn mặt để đăng nhập.",
                },
                status=400,
            )

        image_data = data.get("image", "")

        if not isinstance(image_data, str):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Dữ liệu ảnh không hợp lệ.",
                },
                status=400,
            )

        header, separator, encoded_image = image_data.partition(",")

        if (
            not separator
            or header.split(";")[0]
            not in ("data:image/jpeg", "data:image/png")
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Chỉ chấp nhận ảnh JPEG hoặc PNG.",
                },
                status=400,
            )

        if len(encoded_image) > 3 * 1024 * 1024:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ảnh quá lớn. Vui lòng chụp lại.",
                },
                status=413,
            )

        try:
            image_bytes = base64.b64decode(
                encoded_image,
                validate=True,
            )
        except (ValueError, base64.binascii.Error):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không thể đọc dữ liệu ảnh.",
                },
                status=400,
            )

        if len(image_bytes) > 2 * 1024 * 1024:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ảnh vượt quá giới hạn 2 MB.",
                },
                status=413,
            )

        import numpy as np
        from PIL import Image, UnidentifiedImageError
        from deepface import DeepFace

        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                source_image.verify()

            with Image.open(BytesIO(image_bytes)) as source_image:
                if source_image.format not in ("JPEG", "PNG"):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Định dạng ảnh không hợp lệ.",
                        },
                        status=400,
                    )

                if (
                    source_image.width < 160
                    or source_image.height < 160
                    or source_image.width > 3000
                    or source_image.height > 3000
                ):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Kích thước ảnh không phù hợp.",
                        },
                        status=400,
                    )

                image_array = np.asarray(
                    source_image.convert("RGB")
                )

        except (UnidentifiedImageError, OSError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Tệp gửi lên không phải ảnh hợp lệ.",
                },
                status=400,
            )

        # Phát hiện đúng một khuôn mặt trong ảnh đăng nhập.
        representations = DeepFace.represent(
            img_path=image_array,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=True,
        )

        if len(representations) != 1:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Ảnh phải có đúng một khuôn mặt. "
                        "Vui lòng thử lại."
                    ),
                },
                status=400,
            )

        # query_embedding = representations[0].get("embedding")
        #
        # if not query_embedding or len(query_embedding) != 512:
        #     return JsonResponse(
        #         {
        #             "success": False,
        #             "message": "Không thể nhận diện khuôn mặt.",
        #         },
        #         status=422,
        #     )
        #
        # # Chỉ lấy hồ sơ đang bật và tài khoản đang hoạt động.
        # face_profiles = FaceProfile.objects.filter(
        #     is_active=True,
        #     model_name="Facenet512",
        #     user_profile__user__is_active=True,
        # ).select_related(
        #     "user_profile",
        #     "user_profile__user",
        # )
        #
        # candidates = []
        #
        # # Tính cosine distance giữa vector mới và vector đã lưu.
        # query_norm = math.sqrt(
        #     sum(float(value) ** 2 for value in query_embedding)
        # )
        #
        # if query_norm == 0:
        #     return JsonResponse(
        #         {
        #             "success": False,
        #             "message": "Vector khuôn mặt không hợp lệ.",
        #         },
        #         status=422,
        #     )
        #
        # for face_profile in face_profiles:
        #     stored_embedding = face_profile.embedding
        #
        #     if (
        #         not isinstance(stored_embedding, list)
        #         or len(stored_embedding) != 512
        #     ):
        #         continue
        #
        #     stored_norm = math.sqrt(
        #         sum(float(value) ** 2 for value in stored_embedding)
        #     )
        #
        #     if stored_norm == 0:
        #         continue
        #
        #     dot_product = sum(
        #         float(a) * float(b)
        #         for a, b in zip(query_embedding, stored_embedding)
        #     )
        #
        #     cosine_similarity = dot_product / (
        #         query_norm * stored_norm
        #     )
        #
        #     cosine_distance = 1.0 - cosine_similarity
        #
        #     candidates.append(
        #         (cosine_distance, face_profile)
        #     )


        query_embedding = representations[0].get("embedding")

        if not is_valid_face_embedding(query_embedding):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không thể nhận diện khuôn mặt.",
                },
                status=422,
            )

        # Chuẩn hóa embedding đầu vào thành số thực.
        query_embedding = [
            float(value) for value in query_embedding
        ]

        query_norm = math.sqrt(
            sum(value ** 2 for value in query_embedding)
        )

        # Chỉ lấy hồ sơ đang bật và tài khoản đang hoạt động.
        face_profiles = FaceProfile.objects.filter(
            is_active=True,
            model_name="Facenet512",
            user_profile__user__is_active=True,
        ).select_related(
            "user_profile",
            "user_profile__user",
        )

        candidates = []

        for face_profile in face_profiles:
            stored_embedding = face_profile.embedding

            # Bỏ qua hồ sơ có vector bị hỏng hoặc không hợp lệ.
            if not is_valid_face_embedding(stored_embedding):
                logger.warning(
                    "FaceProfile id=%s có embedding không hợp lệ.",
                    face_profile.pk,
                )
                continue

            try:
                stored_embedding = [
                    float(value) for value in stored_embedding
                ]

                stored_norm = math.sqrt(
                    sum(value ** 2 for value in stored_embedding)
                )

                dot_product = sum(
                    a * b
                    for a, b in zip(
                        query_embedding,
                        stored_embedding,
                    )
                )

                cosine_similarity = dot_product / (
                    query_norm * stored_norm
                )

                # Hạn chế sai số số thực khi tính cosine.
                cosine_similarity = max(
                    -1.0,
                    min(1.0, cosine_similarity),
                )

                cosine_distance = 1.0 - cosine_similarity

                if not math.isfinite(cosine_distance):
                    continue

                candidates.append(
                    (cosine_distance, face_profile)
                )

            except (TypeError, ValueError, OverflowError, ZeroDivisionError):
                logger.warning(
                    "Không thể so sánh embedding FaceProfile id=%s.",
                    face_profile.pk,
                )
                continue


        if not candidates:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Không tìm thấy hồ sơ khuôn mặt đã đăng ký."
                    ),
                },
                status=401,
            )

        candidates.sort(key=lambda item: item[0])

        best_distance, best_profile = candidates[0]

        # Ngưỡng ban đầu để thử nghiệm, cần hiệu chỉnh bằng dữ liệu thực tế.
        threshold = 0.30

        # Nếu hai tài khoản có kết quả quá gần nhau thì từ chối.
        if len(candidates) > 1:
            second_distance = candidates[1][0]

            if second_distance - best_distance < 0.05:
                return JsonResponse(
                    {
                        "success": False,
                        "message": (
                            "Khuôn mặt chưa đủ rõ để xác định tài khoản. "
                            "Vui lòng thử lại."
                        ),
                    },
                    status=401,
                )

        if best_distance > threshold:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Không nhận diện được khuôn mặt đã đăng ký."
                    ),
                },
                status=401,
            )

        user = best_profile.user_profile.user

        if not user.is_active:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Tài khoản đã bị vô hiệu hóa.",
                },
                status=403,
            )

        # Không đăng nhập nếu tài khoản đã được xác thực trên phiên khác
        # trong cùng request; request đăng nhập thông thường là anonymous.
        login(request, user)

        return JsonResponse(
            {
                "success": True,
                "message": "Đăng nhập bằng khuôn mặt thành công!",
                "redirect_url": "/",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "message": "Dữ liệu gửi lên không hợp lệ.",
            },
            status=400,
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Không thể xử lý khuôn mặt lúc này. "
                    "Vui lòng thử lại."
                ),
            },
            status=500,
        )


def is_valid_face_embedding(embedding):
    """
    Kiểm tra embedding có đúng 512 giá trị số hữu hạn
    và có độ lớn khác 0 hay không.
    """
    if not isinstance(embedding, (list, tuple)):
        return False

    if len(embedding) != 512:
        return False

    try:
        for value in embedding:
            # Không chấp nhận bool dù Python xem bool là kiểu số.
            if isinstance(value, bool):
                return False

            number = float(value)

            if not math.isfinite(number):
                return False

        norm = math.sqrt(
            sum(float(value) ** 2 for value in embedding)
        )

        return math.isfinite(norm) and norm > 0

    except (TypeError, ValueError, OverflowError):
        return False


# ============================================================
# COURSE LIST
# ============================================================

@login_required(login_url="qr_login_page")
def course_list_view(request):

    profile = get_object_or_404(
        UserProfile,
        user=request.user,
    )

    # ========================================================
    # STUDENT
    # ========================================================

    if profile.role == "student":

        offerings = (
            CourseOffering.objects
            .filter(
                enrollments__student=profile,
                enrollments__status="active",
            )
            .select_related(
                "course",
                "term",
            )
            .distinct()
        )

        courses = (
            Course.objects
            .filter(
                offerings__in=offerings
            )
            .distinct()
        )

    # ========================================================
    # LECTURER
    # ========================================================

    elif profile.role == "lecturer":

        offerings = (
            CourseOffering.objects
            .filter(
                teaching_assignments__lecturer=profile,
            )
            .select_related(
                "course",
                "term",
            )
            .distinct()
        )

        courses = (
            Course.objects
            .filter(
                offerings__in=offerings
            )
            .distinct()
        )

    # ========================================================
    # ADMIN
    # ========================================================

    elif profile.role == "admin" or request.user.is_staff:

        offerings = (
            CourseOffering.objects
            .select_related(
                "course",
                "term",
            )
            .all()
        )

        courses = (
            Course.objects
            .filter(
                is_active=True,
                offerings__in=offerings,
            )
            .distinct()
        )

    else:

        offerings = CourseOffering.objects.none()
        courses = Course.objects.none()

    # ========================================================
    # EXAMS CỦA TỪNG COURSE
    # ========================================================

    for course in courses:

        if profile.role == "admin" or request.user.is_staff:

            course.visible_exams = (
                Exam.objects
                .filter(
                    course=course,
                    is_active=True,
                )
                .select_related("offering")
                .order_by("start_time")
            )

        else:

            course.visible_exams = (
                Exam.objects
                .filter(
                    course=course,
                    is_active=True,
                    offering__in=offerings,
                )
                .select_related("offering")
                .order_by("start_time")
            )

    return render(
        request,
        "courses.html",
        {
            "title": "Khóa học của bạn",
            "courses": courses,
            "offerings": offerings,
        },
    )




def build_student_snapshot_from_paper(exam, paper):
    """
    Tạo snapshot theo đúng cấu trúc hiện tại của exam_engine,
    nhưng sử dụng question_data và paper_code của ExamPaper.
    """

    if paper.exam_id != exam.pk:
        raise ValueError("Phiên bản đề không thuộc bài thi này.")

    if not paper.is_active:
        raise ValueError("Phiên bản đề đã ngừng sử dụng.")

    # Tạo bản sao Exam để không thay đổi dữ liệu Exam gốc.
    exam_for_snapshot = copy.copy(exam)

    exam_for_snapshot.question_data = copy.deepcopy(
        paper.question_data
    )

    exam_for_snapshot.paper_codes = [
        paper.paper_code
    ]

    snapshot = build_student_snapshot(
        exam_for_snapshot
    )

    # Đảm bảo mã đề chính xác theo ExamPaper.
    snapshot["paper_code"] = paper.paper_code

    return snapshot


# ============================================================
# TAKE EXAM
# ============================================================

@login_required(login_url="qr_login_page")
def take_exam_view(request, exam_id):

    profile = get_object_or_404(
        UserProfile,
        user=request.user,
    )

    # ========================================================
    # 1. CHỈ SINH VIÊN ĐƯỢC THI
    # ========================================================

    if profile.role != "student":

        messages.error(
            request,
            "Chỉ sinh viên mới được tham gia bài thi.",
        )

        return redirect("course_list")

    # ========================================================
    # 2. LẤY EXAM
    # ========================================================

    exam = get_object_or_404(
        Exam.objects.select_related(
            "course",
            "offering",
        ),
        pk=exam_id,
        is_active=True,
    )

    # ========================================================
    # 3. EXAM PHẢI CÓ OFFERING
    # ========================================================

    if not exam.offering_id:

        messages.error(
            request,
            "Bài thi chưa được gán cho lớp học phần.",
        )

        return redirect("course_list")

    # ========================================================
    # 4. KIỂM TRA ENROLLMENT
    # ========================================================

    enrollment = (
        Enrollment.objects
        .filter(
            course_offering=exam.offering,
            student=profile,
            status="active",
        )
        .first()
    )

    if not enrollment:

        messages.error(
            request,
            "Bạn không thuộc lớp học phần của bài thi này.",
        )

        return redirect("course_list")

    # ========================================================
    # 4.1. KIỂM TRA ĐIỂM DANH ĐỐI VỚI BÀI THI TẠI LỚP
    # ========================================================

    if exam.exam_type == Exam.EXAM_TYPE_CLASSROOM:

        is_attended = ExamAttendance.objects.filter(
            exam=exam,
            student=profile,
        ).exists()

        if not is_attended:

            messages.error(
                request,
                (
                    "Bạn chưa được điểm danh khuôn mặt. "
                    "Vui lòng liên hệ giảng viên để được "
                    "điểm danh trước khi vào bài thi tại lớp."
                ),
            )

            return redirect("course_list")


    # ========================================================
    # 5. KIỂM TRA THỜI GIAN
    # ========================================================

    now = timezone.now()

    if exam.start_time and now < exam.start_time:

        messages.warning(
            request,
            "Bài thi chưa bắt đầu.",
        )

        return redirect("course_list")

    if exam.end_time and now > exam.end_time:

        messages.warning(
            request,
            "Bài thi đã kết thúc.",
        )

        return redirect("course_list")

    # ========================================================
    # 6. LẤY STUDENT EXAM HIỆN TẠI
    # ========================================================

    assigned_computer = (
        ExamComputer.objects
        .filter(
            exam_session__exam=exam,
            exam_session__offering=exam.offering,
            student=profile,
            status="assigned",
        )
        .order_by("exam_session__start_time", "computer_number")
        .first()
    )

    student_exam = (
        StudentExam.objects
        .filter(
            student=request.user,
            exam=exam,
        )
        .order_by("-started_at")
        .first()
    )

    # ========================================================
    # 7. ĐÃ NỘP → XEM KẾT QUẢ
    # ========================================================

    if student_exam and student_exam.is_submitted:

        return redirect(
            "exam_result",
            student_exam_id=student_exam.id,
        )

    # ========================================================
    # 8. CHƯA CÓ ATTEMPT → TẠO SNAPSHOT
    # ========================================================

    if student_exam is None:

        try:

            # ------------------------------------------------
            # 8.1. Kiểm tra bài thi có sử dụng phiên bản đề không
            # ------------------------------------------------

            has_exam_papers = exam.papers.exists()

            selected_paper = None
            assignment = None

            if has_exam_papers:

                # Sinh viên bắt buộc phải có phân công đề.
                assignment = (
                    ExamAssignment.objects
                    .select_related("paper")
                    .filter(
                        exam=exam,
                        student=profile,
                    )
                    .first()
                )

                if assignment is None:
                    messages.error(
                        request,
                        "Bạn chưa được phân công phiên bản đề thi. "
                        "Vui lòng liên hệ giảng viên.",
                    )

                    return redirect("course_list")

                selected_paper = assignment.paper

                if selected_paper.exam_id != exam.pk:
                    messages.error(
                        request,
                        "Phiên bản đề được phân công không hợp lệ.",
                    )

                    return redirect("course_list")

                if not selected_paper.is_active:
                    messages.error(
                        request,
                        "Phiên bản đề được phân công đã ngừng sử dụng.",
                    )

                    return redirect("course_list")

                # Tạo snapshot từ ExamPaper.
                paper = build_student_snapshot_from_paper(
                    exam,
                    selected_paper,
                )

            else:

                # Bài thi cũ: giữ nguyên cơ chế tạo đề.
                paper = build_student_snapshot(exam)

                paper_codes = exam.paper_codes or []

                if assigned_computer and paper_codes:
                    paper["paper_code"] = paper_codes[
                        (assigned_computer.computer_number - 1)
                        % len(paper_codes)
                        ]

            # ------------------------------------------------
            # 8.2. Lưu StudentExam
            # ------------------------------------------------

            with transaction.atomic():

                student_exam = StudentExam.objects.create(
                    student=request.user,
                    exam=exam,
                    exam_computer=assigned_computer,

                    # Phiên bản đề được phân công.
                    paper=selected_paper,
                    assignment=assignment,

                    exam_code=paper["paper_code"],
                    question_snapshot=paper,
                )


        except Exception:

            logger.exception(

                "Không thể tạo StudentExam cho user_id=%s, exam_id=%s",

                request.user.pk,

                exam.pk,

            )

            messages.error(

                request,

                "Không thể tạo đề thi lúc này. "

                "Vui lòng thử lại hoặc liên hệ giảng viên.",

            )

            return redirect("course_list")
    # ========================================================
    # 9. ĐẢM BẢO SNAPSHOT TỒN TẠI
    #
    # Không ghi đè snapshot đã tồn tại.
    # Nếu attempt thuộc phiên bản đề thì lấy đúng phiên bản đó.
    # ========================================================

    if not student_exam.question_snapshot:

        try:

            if student_exam.paper_id:

                # Attempt đã gắn phiên bản đề.
                if student_exam.paper.exam_id != exam.pk:
                    raise ValueError(
                        "Phiên bản đề không thuộc bài thi này."
                    )

                paper = build_student_snapshot_from_paper(
                    exam,
                    student_exam.paper,
                )

            else:

                # Nếu bài thi đã sử dụng ExamPaper thì không được
                # tự động lấy đề gốc Exam.question_data để thay thế.
                if exam.papers.exists():
                    logger.error(
                        "StudentExam id=%s thiếu liên kết ExamPaper "
                        "trong khi Exam id=%s đã có phiên bản đề.",
                        student_exam.pk,
                        exam.pk,
                    )

                    raise ValueError(
                        "Bài thi thiếu thông tin phiên bản đề. "
                        "Vui lòng liên hệ giảng viên."
                    )

                # Chỉ bài thi cũ chưa sử dụng ExamPaper mới dùng
                # cơ chế tạo snapshot cũ.
                paper = build_student_snapshot(exam)




        except Exception:

            logger.exception(

                "Không thể khôi phục snapshot StudentExam id=%s",

                student_exam.pk,

            )

            messages.error(

                request,

                "Không thể khôi phục dữ liệu đề thi. "

                "Vui lòng liên hệ giảng viên.",

            )

            return redirect("course_list")
    # ========================================================
    # 10. LẤY QUESTIONS TỪ SNAPSHOT
    #
    # Không lấy lại Exam.question_data để hiển thị.
    # ========================================================

    questions = get_student_exam_questions(
        student_exam
    )

    # ========================================================
    # 11. TẠO PUBLIC QUESTIONS
    #
    # Không gửi đáp án đúng xuống browser.
    # ========================================================

    public_questions = []

    for question in questions:

        # Deep copy để việc xóa dữ liệu public
        # không làm thay đổi question_snapshot trong DB.
        public_question = json.loads(
            json.dumps(
                question,
                ensure_ascii=False,
            )
        )

        # ----------------------------------------------------
        # Xóa đáp án server-side
        # ----------------------------------------------------

        public_question.pop(
            "_correct_answers",
            None,
        )

        public_question.pop(
            "_correct_order",
            None,
        )

        public_question.pop(
            "correct_answer",
            None,
        )

        public_question.pop(
            "correct_option",
            None,
        )

        public_question.pop(
            "_correct_choice_index",
            None,
        )

        # ----------------------------------------------------
        # DRAG / SORT
        # Không gửi correct_order xuống browser.
        # ----------------------------------------------------

        for item in public_question.get(
            "items",
            [],
        ):

            item.pop(
                "correct_order",
                None,
            )

        # ----------------------------------------------------
        # MCQ
        # Không gửi flag đáp án đúng xuống browser.
        # ----------------------------------------------------

        for choice in public_question.get(
            "choices",
            [],
        ):

            choice.pop(
                "is_correct",
                None,
            )

            choice.pop(
                "correct",
                None,
            )

            choice.pop(
                "label",
                None,
            )

        public_questions.append(
            public_question
        )

    # ========================================================
    # 12. TÍNH THỜI GIAN CÒN LẠI
    # ========================================================

    remaining_seconds = max(
        0,
        int(
            (
                student_exam.started_at
                + timedelta(
                    minutes=exam.duration_minutes
                )
                - timezone.now()
            ).total_seconds()
        ),
    )

    # ========================================================
    # 13. RENDER
    # ========================================================

    return render(
        request,
        "exam/take_exam.html",
        {
            "exam": exam,
            "student_exam": student_exam,
            "questions": public_questions,
            "total_questions": len(public_questions),
            "remaining_seconds": remaining_seconds,
        },
    )

# ============================================================
# SNAPSHOT HELPERS
# ============================================================

def _get_snapshot_questions(student_exam):

    snapshot = student_exam.question_snapshot or {}

    if isinstance(snapshot, dict):

        questions = snapshot.get(
            "questions",
            [],
        )

    elif isinstance(snapshot, list):

        questions = snapshot

    else:

        questions = []

    return questions


def _find_snapshot_question(
    student_exam,
    question_index,
):

    questions = _get_snapshot_questions(
        student_exam
    )

    for question in questions:

        if str(question.get("index")) == str(
            question_index
        ):
            return question

    return None


def _get_answer_value(
    answer_data,
    *keys,
):

    for key in keys:

        value = answer_data.get(key)

        if value is not None:
            return value

    return None


def _parse_order_value(value):

    if value is None:
        return []

    if isinstance(value, list):

        raw_items = value

    else:

        value = str(value).strip()

        if not value:
            return []

        try:

            if value.startswith("["):

                raw_items = json.loads(
                    value
                )

            else:

                raw_items = [
                    item.strip()
                    for item in value.split(",")
                    if item.strip()
                ]

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):

            return []

    result = []

    for item in raw_items:

        try:

            result.append(
                int(item)
            )

        except (
            TypeError,
            ValueError,
        ):

            result.append(
                str(item)
            )

    return result


def _resolve_snapshot_item(
    items,
    value,
):

    for item in items:

        if str(item.get("id")) == str(value):
            return item

        if str(item.get("index")) == str(value):
            return item

        if str(item.get("text", "")) == str(value):
            return item

    return None


# ============================================================
# RUN CODE
# ============================================================

@csrf_exempt
@login_required(login_url="qr_login_page")
def run_code(request):

    if request.method != "POST":

        return JsonResponse(
            {
                "success": False,
                "message": "POST only",
            }
        )

    try:

        body = json.loads(
            request.body
        )

        question_index = body.get(
            "question_id"
        )

        code = body.get(
            "code",
            "",
        )

        student_exam_id = body.get(
            "student_exam_id"
        )

        if question_index is None:

            return JsonResponse(
                {
                    "success": False,
                    "message": "Thiếu mã câu hỏi.",
                },
                status=400,
            )

        # student_exam = get_object_or_404(
        #     StudentExam,
        #     id=student_exam_id,
        #     student=request.user,
        #     is_submitted=False,
        # )
        student_exam = get_object_or_404(
            StudentExam,
            id=student_exam_id,
            student=request.user,
        )

        if student_exam.is_submitted:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_submitted",
                    "message": "Bài thi đã được nộp, không thể chạy code.",
                },
                status=409,
            )
        if student_exam.is_terminated:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_terminated",
                    "message": "Bài thi đã kết thúc.",
                },
                status=409,
            )

        if student_exam.is_locked:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_locked",
                    "message": (
                        "Bài thi đang tạm dừng "
                        "và chờ giảng viên xử lý."
                    ),
                },
                status=423,
            )

        question = _find_snapshot_question(
            student_exam,
            question_index,
        )

        if question is None:

            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Không tìm thấy câu hỏi "
                        "trong đề thi."
                    ),
                },
                status=404,
            )

        question_type = str(
            question.get(
                "type",
                "",
            )
        ).upper()

        if question_type != "CODE":

            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Câu hỏi này không phải "
                        "câu lập trình."
                    ),
                },
                status=400,
            )

        testcases = question.get(
            "test_cases",
            [],
        )

        if not testcases:

            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Câu lập trình "
                        "chưa có test case."
                    ),
                },
                status=400,
            )

        total_score = 0.0
        max_score = 0.0

        testcase_result = []

        compile_error = None
        runtime_error = None

        # =====================================================
        # CHẠY TEST CASE
        # =====================================================

        for testcase in testcases:

            testcase_score = float(
                testcase.get(
                    "score",
                    0,
                )
                or 0
            )

            max_score += testcase_score

            input_data = testcase.get(
                "input_data",
                testcase.get(
                    "input",
                    "",
                ),
            )

            expected_output = testcase.get(
                "expected_output",
                testcase.get(
                    "output",
                    "",
                ),
            )

            result = run_code_by_language(
                question.get("language", "cpp"),
                code,
                input_data,
            )

            if result.get("status") == "Compile Error":

                compile_error = result.get(
                    "compile_error",
                    result.get(
                        "stderr",
                        "",
                    ),
                )

                testcase_result.append(
                    {
                        "input": input_data,
                        "expected": expected_output,
                        "actual": "",
                        "passed": False,
                        "score": testcase_score,
                    }
                )

                break

            if result.get("status") == "Runtime Error":

                runtime_error = result.get(
                    "stderr",
                    "",
                )

                testcase_result.append(
                    {
                        "input": input_data,
                        "expected": expected_output,
                        "actual": result.get(
                            "stdout",
                            "",
                        ),
                        "passed": False,
                        "score": testcase_score,
                    }
                )

                break

            actual = str(
                result.get(
                    "stdout",
                    "",
                )
            ).strip()

            expected = str(
                expected_output
            ).strip()

            passed = (
                actual == expected
            )

            if passed:
                total_score += testcase_score

            testcase_result.append(
                {
                    "input": input_data,
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                    "score": testcase_score,
                }
            )

        # =====================================================
        # GIỚI HẠN ĐIỂM THEO ĐIỂM CÂU
        # =====================================================

        question_score = float(
            question.get(
                "score",
                0,
            )
            or 0
        )

        if question_score > 0:

            total_score = min(
                total_score,
                question_score,
            )

        # =====================================================
        # CODE CÓ PASS TOÀN BỘ TEST CASE KHÔNG?
        # =====================================================

        all_passed = (
            bool(testcases)
            and compile_error is None
            and runtime_error is None
            and all(
                item.get("passed")
                for item in testcase_result
            )
        )

        # =====================================================
        # LƯU STUDENT ANSWER
        # =====================================================

        StudentAnswer.objects.update_or_create(
            student_exam=student_exam,
            question_index=int(
                question_index
            ),
            defaults={
                # "question": None,
                "question_type": "CODE",
                "answer_text": code,
                "answer_payload": {
                    "code": code,
                },
                "score": total_score,
                "is_correct": all_passed,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "compile_error": compile_error,
                "runtime_error": runtime_error,
                "score": total_score,
                "max_score": max_score,
                "testcases": testcase_result,
            }
        )



    except json.JSONDecodeError:

        return JsonResponse(

            {

                "success": False,

                "message": "Dữ liệu JSON không hợp lệ.",

            },

            status=400,

        )


    except Http404:

        return JsonResponse(

            {

                "success": False,

                "message": (

                    "Không tìm thấy lượt thi "

                    "hoặc bạn không có quyền truy cập."

                ),

            },

            status=404,

        )


    except Exception as e:

        return JsonResponse(

            {

                "success": False,

                "message": str(e),

            },

            status=500,

        )


# ============================================================
# COMPILER TEST
# ============================================================

def compiler_test(request):

    return render(
        request,
        "compiler_test.html",
    )


# ============================================================
# GRADE STUDENT EXAM
# ============================================================

def _grade_student_exam(
    student_exam,
    answer_data,
    terminated=False,
    termination_reason="",
):

    total_score = 0.0

    questions = _get_snapshot_questions(
        student_exam
    )

    for question in questions:

        question_index = question.get(
            "index"
        )

        question_type = str(
            question.get(
                "type",
                "",
            )
        ).upper()

        question_score = float(
            question.get(
                "score",
                0,
            )
            or 0
        )

        answer_content = "Chưa trả lời"
        answer_payload = {}

        earned_score = 0.0
        is_correct = False

        # =====================================================
        # MCQ
        # =====================================================

        if question_type == "MCQ":

            submitted = _get_answer_value(
                answer_data,
                f"question_{question_index}",
                f"q_{question_index}",
                f"choice_{question_index}",
            )

            choices = question.get(
                "choices",
                [],
            )

            selected_choice = None

            if submitted is not None:

                submitted = str(
                    submitted
                )

                for choice in choices:

                    choice_id = choice.get(
                        "id"
                    )

                    choice_index = choice.get(
                        "index"
                    )

                    choice_label = choice.get(
                        "label"
                    )

                    choice_text = (
                            choice.get("text")
                            or choice.get("content")
                            or ""
                    )

                    if (
                            choice_id is not None
                            and str(choice_id) == submitted
                    ):
                        selected_choice = choice
                        break

                    if (
                            choice_index is not None
                            and str(choice_index) == submitted
                    ):
                        selected_choice = choice
                        break

                    if (
                            choice_label is not None
                            and str(choice_label) == submitted
                    ):
                        selected_choice = choice
                        break

                    if (
                            str(choice_text) == submitted
                    ):
                        selected_choice = choice
                        break

            if selected_choice:

                answer_content = (
                        selected_choice.get(
                            "content"
                        )
                        or selected_choice.get(
                    "text",
                    "",
                )
                )

                answer_payload = {
                    "choice_index": selected_choice.get(
                        "index"
                    ),
                    "choice_label": selected_choice.get(
                        "label"
                    ),
                }

                # -------------------------------------------------
                # Xác định đáp án đúng từ JSON snapshot
                # -------------------------------------------------

                correct_answer = question.get(
                    "correct_answer"
                )

                is_correct = False

                if correct_answer is not None:
                    correct_answer = str(
                        correct_answer
                    ).strip()

                    selected_label = str(
                        selected_choice.get(
                            "label",
                            ""
                        )
                    ).strip()

                    selected_index = str(
                        selected_choice.get(
                            "index",
                            ""
                        )
                    ).strip()

                    selected_text = str(
                        selected_choice.get(
                            "text"
                        )
                        or selected_choice.get(
                            "content",
                            ""
                        )
                    ).strip()

                    is_correct = (
                            correct_answer == selected_label
                            or correct_answer == selected_index
                            or correct_answer == selected_text
                    )

                # -------------------------------------------------
                # Hỗ trợ snapshot dạng choice.correct_answer
                # -------------------------------------------------

                if not is_correct:

                    choice_correct_value = (
                        selected_choice.get(
                            "correct_answer"
                        )
                    )

                    if choice_correct_value is True:
                        is_correct = True

                if is_correct:
                    earned_score = question_score
        # =====================================================
        # DRAG
        # =====================================================

        elif question_type == "DRAG":

            submitted = _get_answer_value(
                answer_data,
                f"sorted_ids_{question_index}",
                f"answer_{question_index}",
                f"drag_{question_index}",
            )

            user_order = _parse_order_value(
                submitted
            )

            items = question.get(
                "items",
                [],
            )

            if user_order:

                answer_payload = {
                    "items": user_order,
                }

                submitted_texts = []

                for value in user_order:

                    found = _resolve_snapshot_item(
                        items,
                        value,
                    )

                    if found:

                        submitted_texts.append(
                            str(
                                found.get(
                                    "text"
                                )
                                or found.get(
                                    "code",
                                    "",
                                )
                            )
                        )

                answer_content = (
                    "\n".join(
                        submitted_texts
                    )
                    or "Chưa trả lời"
                )

                correct_answers = question.get(
                    "_correct_answers",
                    [],
                )

                if not correct_answers:

                    correct_answers = [
                        str(
                            item.get(
                                "text"
                            )
                            or item.get(
                                "code",
                                "",
                            )
                        )
                        for item in items
                    ]

                if (
                    submitted_texts
                    == correct_answers
                ):

                    is_correct = True
                    earned_score = question_score

        # =====================================================
        # SORT
        # =====================================================

        elif question_type == "SORT":

            submitted = _get_answer_value(
                answer_data,
                f"sorted_ids_{question_index}",
                f"answer_{question_index}",
                f"sort_{question_index}",
            )

            user_order = _parse_order_value(
                submitted
            )

            items = question.get(
                "items",
                [],
            )

            if user_order:

                answer_payload = {
                    "items": user_order,
                }

                submitted_texts = []

                for value in user_order:

                    found = _resolve_snapshot_item(
                        items,
                        value,
                    )

                    if found:

                        submitted_texts.append(
                            str(
                                found.get(
                                    "text"
                                )
                                or found.get(
                                    "code",
                                    "",
                                )
                            )
                        )

                answer_content = (
                    "\n".join(
                        submitted_texts
                    )
                    or "Chưa trả lời"
                )

                correct_order = question.get(
                    "_correct_order",
                    [],
                )

                if not correct_order:

                    correct_order = [
                        str(
                            item.get(
                                "text"
                            )
                            or item.get(
                                "code",
                                "",
                            )
                        )
                        for item in items
                    ]

                if (
                    submitted_texts
                    == correct_order
                ):

                    is_correct = True
                    earned_score = question_score

        # =====================================================
        # CODE
        # =====================================================

        elif question_type == "CODE":

            answer_content = (
                _get_answer_value(
                    answer_data,
                    f"code_answer_{question_index}",
                    f"code_{question_index}",
                    f"editor_{question_index}",
                )
                or ""
            )

            answer_payload = {
                "code": answer_content,
            }

            test_cases = question.get(
                "test_cases",
                [],
            )

            max_testcase_score = sum(
                float(
                    testcase.get(
                        "score",
                        0,
                    )
                    or 0
                )
                for testcase in test_cases
            )

            passed_testcases = 0

            for testcase in test_cases:

                if not answer_content:
                    break

                input_data = testcase.get(
                    "input_data",
                    testcase.get(
                        "input",
                        "",
                    ),
                )

                expected_output = str(
                    testcase.get(
                        "expected_output",
                        testcase.get(
                            "output",
                            "",
                        ),
                    )
                ).strip()

                result = run_code_by_language(
                    question.get("language", "cpp"),
                    answer_content,
                    input_data,
                )

                if result.get(
                    "status"
                ) != "Success":

                    continue

                actual = str(
                    result.get(
                        "stdout",
                        "",
                    )
                ).strip()

                if actual == expected_output:

                    earned_score += float(
                        testcase.get(
                            "score",
                            0,
                        )
                        or 0
                    )

                    passed_testcases += 1

            if (
                max_testcase_score > 0
                and passed_testcases == len(test_cases)
            ):

                is_correct = True

            earned_score = min(
                earned_score,
                question_score,
            )

        # =====================================================
        # UNKNOWN TYPE
        # =====================================================

        else:

            continue

        # =====================================================
        # LƯU STUDENT ANSWER
        # =====================================================

        StudentAnswer.objects.update_or_create(
            student_exam=student_exam,
            question_index=question_index,
            defaults={

                "question_type": question_type,
                "answer_text": answer_content,
                "answer_payload": answer_payload,
                "is_correct": is_correct,
                "score": earned_score,
            },
        )

        total_score += earned_score

    # ========================================================
    # HOÀN TẤT BÀI THI
    # ========================================================

    student_exam.score = total_score
    student_exam.finished_at = timezone.now()
    student_exam.is_submitted = True

    update_fields = [
        "score",
        "finished_at",
        "is_submitted",
    ]

    if terminated:

        student_exam.is_terminated = True
        student_exam.termination_reason = (
            termination_reason
        )

        update_fields.extend([
            "is_terminated",
            "termination_reason",
        ])

    student_exam.save(
        update_fields=update_fields
    )

    return total_score


# ============================================================
# AUTOSAVE
# ============================================================

def _save_exam_draft(
    student_exam,
    answer_data,
):

    saved_count = 0

    questions = _get_snapshot_questions(
        student_exam
    )

    for question in questions:

        question_index = question.get(
            "index"
        )

        question_type = str(
            question.get(
                "type",
                "",
            )
        ).upper()

        answer_text = None
        payload = {}

        # =====================================================
        # MCQ
        # =====================================================

        if question_type == "MCQ":

            choice_value = _get_answer_value(
                answer_data,
                f"question_{question_index}",
                f"q_{question_index}",
                f"choice_{question_index}",
            )

            if choice_value is not None:

                answer_text = str(
                    choice_value
                )

                payload = {
                    "choice_index": choice_value,
                }

        # =====================================================
        # DRAG / SORT
        # =====================================================

        elif question_type in (
            "DRAG",
            "SORT",
        ):

            submitted_order = _get_answer_value(
                answer_data,
                f"sorted_ids_{question_index}",
                f"answer_{question_index}",
                f"{question_type.lower()}_{question_index}",
            )

            if submitted_order:

                item_order = _parse_order_value(
                    submitted_order
                )

                if item_order:

                    answer_text = json.dumps(
                        item_order,
                        ensure_ascii=False,
                    )

                    payload = {
                        "items": item_order,
                    }

        # =====================================================
        # CODE
        # =====================================================

        elif question_type == "CODE":

            code_key = (
                f"code_answer_{question_index}"
            )

            if code_key in answer_data:

                answer_text = answer_data.get(
                    code_key,
                    "",
                )

                payload = {
                    "code": answer_text,
                }

        # =====================================================
        # SAVE
        # =====================================================

        if answer_text is not None:

            StudentAnswer.objects.update_or_create(
                student_exam=student_exam,
                question_index=question_index,
                defaults={

                    "question_type": question_type,
                    "answer_text": answer_text,
                    "answer_payload": payload,
                },
            )

            saved_count += 1

    return saved_count


# ============================================================
# CONVERT DRAFT → SUBMISSION DATA
# ============================================================

def _submission_data_from_drafts(
    student_exam,
):

    answer_data = QueryDict(
        "",
        mutable=True,
    )

    for answer in student_exam.answers.all():

        question_index = answer.question_index

        question_type = (
            answer.question_type or ""
        ).upper()

        payload = (
            answer.answer_payload or {}
        )

        if question_index is None:
            continue

        # =====================================================
        # MCQ
        # =====================================================

        if question_type == "MCQ":

            choice_id = payload.get("choice_index", payload.get("choice_id"))

            if choice_id is not None:

                answer_data[
                    f"question_{question_index}"
                ] = str(
                    choice_id
                )

        # =====================================================
        # DRAG / SORT
        # =====================================================

        elif question_type in (
            "DRAG",
            "SORT",
        ):

            items = payload.get(
                "items"
            )

            if items is not None:

                answer_data[
                    f"sorted_ids_{question_index}"
                ] = json.dumps(
                    items,
                    ensure_ascii=False,
                )

        # =====================================================
        # CODE
        # =====================================================

        elif question_type == "CODE":

            code = payload.get(
                "code",
                answer.answer_text or "",
            )

            answer_data[
                f"code_answer_{question_index}"
            ] = code

    return answer_data


# ============================================================
# AUTOSAVE VIEW
# ============================================================

# @login_required
# @require_POST
# def autosave_exam(
#     request,
#     student_exam_id,
# ):
#
#     student_exam = get_object_or_404(
#         StudentExam,
#         id=student_exam_id,
#         student=request.user,
#         is_submitted=False,
#     )
#
#     # if student_exam.is_terminated:
#     #
#     #     return JsonResponse(
#     #         {
#     #             "success": False,
#     #             "message": "Bài thi đã bị dừng.",
#     #         },
#     #         status=409,
#     #     )
#
#     if student_exam.is_terminated:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "message": "Bài thi đã bị kết thúc.",
#             },
#             status=409,
#         )
#
#     if student_exam.is_locked:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "code": "exam_locked",
#                 "message": (
#                     "Bài thi đang tạm dừng "
#                     "và chờ giảng viên xử lý."
#                 ),
#             },
#             status=423,
#         )
#
#     saved_count = _save_exam_draft(
#         student_exam,
#         request.POST,
#     )
#
#     return JsonResponse(
#         {
#             "success": True,
#             "saved_count": saved_count,
#         }
#     )



@login_required
@require_POST
def autosave_exam(
    request,
    student_exam_id,
):
    student_exam = get_object_or_404(
        StudentExam,
        id=student_exam_id,
        student=request.user,
    )

    # 1. Bài thi đã bị kết thúc do vi phạm
    if student_exam.is_terminated:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_terminated",
                "message": "Bài thi đã bị kết thúc.",
            },
            status=409,
        )

    # 2. Bài thi đã nộp: không cho phép sửa đáp án
    if student_exam.is_submitted:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_submitted",
                "message": (
                    "Bài thi đã được nộp, "
                    "không thể lưu thêm đáp án."
                ),
            },
            status=409,
        )

    # 3. Bài thi đang bị khóa: không cho phép lưu
    if student_exam.is_locked:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_locked",
                "message": (
                    "Bài thi đang tạm dừng "
                    "và chờ giảng viên xử lý."
                ),
            },
            status=423,
        )

    # 4. Chỉ lưu khi bài thi vẫn hợp lệ
    saved_count = _save_exam_draft(
        student_exam,
        request.POST,
    )

    return JsonResponse(
        {
            "success": True,
            "saved_count": saved_count,
        }
    )


# ============================================================
# PROCTORING FRAME
# ============================================================

@login_required
@require_POST
def proctor_exam_frame(
    request,
    student_exam_id,
):

    student_exam = get_object_or_404(
        StudentExam,
        id=student_exam_id,
        student=request.user,
        is_submitted=False,
    )

    if student_exam.is_terminated:

        return JsonResponse(
            {
                "success": False,
                "terminated": True,
            },
            status=409,
        )

    frame = request.FILES.get(
        "frame"
    )

    if student_exam.is_locked:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_locked",
                "locked": True,
                "warning_count": student_exam.warning_count,
                "message": (
                    "Bài thi đang chờ "
                    "giảng viên xử lý."
                ),
            },
            status=423,
        )

    if not frame:

        return JsonResponse(
            {
                "success": False,
                "message": "Thiếu frame camera.",
            },
            status=400,
        )

    if frame.size > 2 * 1024 * 1024:

        return JsonResponse(
            {
                "success": False,
                "message": "Frame vượt quá 2 MB.",
            },
            status=413,
        )

    try:

        gesture, confidence = classify_frame(
            frame
        )

    except FileNotFoundError as error:

        return JsonResponse(
            {
                "success": False,
                "code": "model_missing",
                "message": str(error),
            },
            status=503,
        )

    except ModuleNotFoundError as error:

        return JsonResponse(
            {
                "success": False,
                "code": "dependency_missing",
                "message": str(error),
            },
            status=503,
        )

    except Exception:

        return JsonResponse(
            {
                "success": False,
                "code": "inference_error",
                "message": (
                    "Không thể phân tích frame."
                ),
            },
            status=422,
        )

    now = timezone.now()

    # ========================================================
    # NORMAL
    # ========================================================

    if gesture == "normal":

        student_exam.active_gesture = ""
        student_exam.gesture_started_at = None
        student_exam.gesture_warned = False

        student_exam.save(
            update_fields=[
                "active_gesture",
                "gesture_started_at",
                "gesture_warned",
            ]
        )

        return JsonResponse(
            {
                "success": True,
                "gesture": "normal",
                "warning_count": student_exam.warning_count,
                "warning_created": False,
            }
        )

    # ========================================================
    # UNCLASSIFIED
    # ========================================================

    if (
        gesture not in {
            "looking_left",
            "looking_right",
            "looking_down",
        }
        or confidence
        < settings.PROCTORING_CONFIDENCE
    ):

        return JsonResponse(
            {
                "success": True,
                "gesture": "unclassified",
                "warning_count": student_exam.warning_count,
                "warning_created": False,
            }
        )

    # ========================================================
    # GESTURE MỚI
    # ========================================================

    if (
        student_exam.active_gesture != gesture
        or not student_exam.gesture_started_at
    ):

        student_exam.active_gesture = gesture
        student_exam.gesture_started_at = now
        student_exam.gesture_warned = False

        student_exam.save(
            update_fields=[
                "active_gesture",
                "gesture_started_at",
                "gesture_warned",
            ]
        )

        return JsonResponse(
            {
                "success": True,
                "gesture": gesture,
                "warning_count": student_exam.warning_count,
                "warning_created": False,
            }
        )

    # ========================================================
    # TÍNH THỜI GIAN
    # ========================================================

    duration = int(
        (
            now
            - student_exam.gesture_started_at
        ).total_seconds()
    )

    if (
        duration < 30
        or student_exam.gesture_warned
    ):

        return JsonResponse(
            {
                "success": True,
                "gesture": gesture,
                "duration_seconds": duration,
                "warning_count": student_exam.warning_count,
                "warning_created": False,
            }
        )

    # ========================================================
    # TẠO PROCTOR EVENT
    # ========================================================

    frame.seek(0)

    event = ProctorEvent.objects.create(
        student_exam=student_exam,
        exam_computer=student_exam.exam_computer,
        event_type=gesture,
        confidence=confidence,
        duration_seconds=duration,
    )

    event.evidence_image.save(
        f"attempt-{student_exam.pk}-{uuid4().hex}.jpg",
        ContentFile(
            frame.read()
        ),
        save=True,
    )

    student_exam.warning_count += 1
    student_exam.gesture_warned = True

    student_exam.save(
        update_fields=[
            "warning_count",
            "gesture_warned",
        ]
    )

    # ========================================================
    # QUÁ 2 CẢNH BÁO → TERMINATE
    # ========================================================

    terminated = (
        student_exam.warning_count > 2
    )

    if terminated:

        _grade_student_exam(
            student_exam,
            _submission_data_from_drafts(
                student_exam
            ),
            terminated=True,
            termination_reason=(
                "Dừng bài sau 3 lần "
                "cảnh báo giám sát."
            ),
        )

    return JsonResponse(
        {
            "success": True,
            "gesture": gesture,
            "warning_created": True,
            "warning_count": student_exam.warning_count,
            "terminated": terminated,
            "redirect_url": (
                reverse(
                    "exam_result",
                    args=(student_exam.pk,),
                )
                if terminated
                else ""
            ),
        }
    )


# ============================================================
# CAMERA COMPUTER PRESENCE
# ============================================================

@csrf_exempt
@require_POST
def report_computer_presence(request):

    ingest_token = settings.CV_INGEST_TOKEN

    if not ingest_token:

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Chưa cấu hình "
                    "CV_INGEST_TOKEN."
                ),
            },
            status=503,
        )

    if not hmac.compare_digest(
        request.headers.get(
            "X-CV-Token",
            "",
        ),
        ingest_token,
    ):

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Token camera không hợp lệ."
                ),
            },
            status=403,
        )

    try:

        payload = json.loads(
            request.body
        )

        computer_id = int(
            payload["computer_id"]
        )

        person_present = payload[
            "person_present"
        ]

        if not isinstance(
            person_present,
            bool,
        ):

            raise ValueError

    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Dữ liệu camera không hợp lệ."
                ),
            },
            status=400,
        )

    computer = get_object_or_404(
        ExamComputer,
        pk=computer_id,
    )

    now = timezone.now()

    computer.camera_last_seen_at = now

    update_fields = [
        "camera_last_seen_at"
    ]

    if person_present:

        computer.presence_last_seen_at = now

        update_fields.append(
            "presence_last_seen_at"
        )

    computer.save(
        update_fields=update_fields
    )

    return JsonResponse(
        {
            "success": True,
            "person_present": person_present,
        }
    )


# ============================================================
# SUBMIT EXAM
# ============================================================

@login_required
def submit_exam(
    request,
    student_exam_id,
):

    student_exam = get_object_or_404(
        StudentExam,
        id=student_exam_id,
        student=request.user,
    )

    if student_exam.is_submitted:

        return redirect(
            "exam_result",
            student_exam_id=student_exam.pk,
        )
    if student_exam.is_terminated:
        return redirect(
            "exam_result",
            student_exam_id=student_exam.pk,
        )
    if student_exam.is_locked:
        return redirect(
            "take_exam",
            exam_id=student_exam.exam_id,
        )

    if request.method != "POST":

        return redirect(
            "take_exam",
            exam_id=student_exam.exam_id,
        )

    _grade_student_exam(
        student_exam,
        request.POST,
    )

    return redirect(
        "exam_result",
        student_exam_id=student_exam.pk,
    )


# ============================================================
# TEACHER CHECK
# ============================================================

def is_teacher(user):

    return user.is_authenticated and (
        user.is_staff
        or (
            hasattr(
                user,
                "userprofile",
            )
            and user.userprofile.role in (
                "admin",
                "lecturer",
            )
        )
    )

def _paper_attempts(paper):
    """
    Tìm mọi lượt thi có liên kết đến phiên bản đề,
    kể cả liên kết trực tiếp qua paper hoặc gián tiếp qua assignment.
    """

    return StudentExam.objects.filter(
        Q(paper_id=paper.pk)
        | Q(assignment__paper_id=paper.pk)
    ).distinct()


def _validate_paper_question_data(question_data):
    """
    Chỉ chấp nhận đúng 4 loại câu hỏi của hệ thống.
    """

    if not isinstance(question_data, list):
        raise ValidationError(
            "Dữ liệu câu hỏi phải là một danh sách."
        )

    if not question_data:
        raise ValidationError(
            "Phiên bản đề phải có ít nhất một câu hỏi."
        )

    allowed_types = {
        "MCQ",
        "DRAG",
        "SORT",
        "CODE",
    }

    for index, question in enumerate(
        question_data,
        start=1,
    ):

        if not isinstance(question, dict):
            raise ValidationError(
                f"Câu {index}: dữ liệu câu hỏi không hợp lệ."
            )

        question_type = str(
            question.get("type", "")
        ).strip().upper()

        if question_type not in allowed_types:
            raise ValidationError(
                f"Câu {index}: chỉ hỗ trợ MCQ, DRAG, SORT và CODE."
            )

        question["type"] = question_type

    return question_data

# ============================================================
# TEACHER EXAM PAPER MANAGEMENT
# ============================================================
@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_exam_papers(request, exam_id):
    """
    Hiển thị danh sách phiên bản đề và quyền thao tác.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    papers = (
        ExamPaper.objects
        .filter(exam=exam)
        .select_related("copied_from")
        .order_by("paper_number")
    )

    paper_rows = []

    for paper in papers:

        assignment_count = paper.assignments.count()

        attempt_count = _paper_attempts(
            paper
        ).count()

        paper_rows.append({
            "paper": paper,
            "assignment_count": assignment_count,
            "attempt_count": attempt_count,

            # Chỉ được sửa/xóa nếu chưa có lượt thi.
            "can_modify": attempt_count == 0,
        })

    return render(
        request,
        "exam/teacher_exam_papers.html",
        {
            "exam": exam,
            "paper_rows": paper_rows,
        },
    )
@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_create_exam_paper(request, exam_id):
    """
    Tạo một phiên bản đề độc lập cho bài thi.
    Giảng viên nhập câu hỏi bằng giao diện biểu mẫu.
    JSON được tạo tự động ở phía trình duyệt.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    last_number = (
        ExamPaper.objects
        .filter(exam=exam)
        .order_by("-paper_number")
        .values_list("paper_number", flat=True)
        .first()
    )

    next_number = (last_number or 0) + 1

    # Giá trị hiển thị lại nếu biểu mẫu gặp lỗi.
    paper_number_input = str(next_number)
    paper_code_input = ""
    title_input = ""

    question_data_text = json.dumps(
        exam.question_data or [],
        ensure_ascii=False,
        indent=2,
    )

    if request.method == "POST":

        paper_number_input = request.POST.get(
            "paper_number",
            "",
        ).strip()

        paper_code_input = request.POST.get(
            "paper_code",
            "",
        ).strip()

        title_input = request.POST.get(
            "title",
            "",
        ).strip()

        question_data_text = request.POST.get(
            "question_data",
            "",
        )

        try:
            paper_number = int(paper_number_input)

            question_data = json.loads(
                question_data_text
            )

            if not isinstance(question_data, list):
                raise ValidationError(
                    "Danh sách câu hỏi không hợp lệ."
                )

            if not question_data:
                raise ValidationError(
                    "Phiên bản đề phải có ít nhất một câu hỏi."
                )

            # Hệ thống chỉ hỗ trợ đúng 4 loại câu hỏi.
            allowed_question_types = {
                "MCQ",
                "DRAG",
                "SORT",
                "CODE",
            }

            for index, question in enumerate(
                question_data,
                start=1,
            ):

                if not isinstance(question, dict):
                    raise ValidationError(
                        f"Câu {index}: dữ liệu câu hỏi không hợp lệ."
                    )

                question_type = str(
                    question.get("type", "")
                ).strip().upper()

                if question_type not in allowed_question_types:
                    raise ValidationError(
                        f"Câu {index}: loại câu hỏi không được hỗ trợ. "
                        "Chỉ chấp nhận MCQ, DRAG, SORT và CODE."
                    )

                # Chuẩn hóa kiểu câu hỏi trước khi lưu.
                question["type"] = question_type

            create_exam_paper(
                exam,
                paper_number=paper_number,
                paper_code=paper_code_input,
                title=title_input,
                question_data=question_data,
            )

            messages.success(
                request,
                "Tạo phiên bản đề thành công.",
            )

            return redirect(
                "teacher_exam_papers",
                exam_id=exam.pk,
            )

        except json.JSONDecodeError:
            messages.error(
                request,
                "Dữ liệu câu hỏi không hợp lệ. "
                "Vui lòng kiểm tra lại biểu mẫu.",
            )

        except ValueError:
            messages.error(
                request,
                "Số thứ tự phiên bản phải là số nguyên.",
            )

        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(exc.messages),
            )

    return render(
        request,
        "exam/teacher_exam_paper_form.html",
        {
            "exam": exam,
            "form_title": "Tạo phiên bản đề mới",
            "submit_label": "Tạo phiên bản đề",
            "paper_number": paper_number_input,
            "paper_code": paper_code_input,
            "title": title_input,
            "question_data_text": question_data_text,
            "show_question_data": True,
        },
    )


@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_edit_exam_paper(
    request,
    exam_id,
    paper_id,
):
    """
    Chỉnh sửa thông tin và nội dung phiên bản đề.

    Không cho phép sửa khi đã có lượt thi.
    Có thể chỉnh sửa khi đã phân công nhưng sinh viên chưa bắt đầu.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    paper = get_object_or_404(
        ExamPaper,
        pk=paper_id,
        exam=exam,
    )

    if _paper_attempts(paper).exists():

        messages.error(
            request,
            (
                "Phiên bản đề đã có lượt thi nên không thể "
                "chỉnh sửa nội dung để bảo toàn lịch sử."
            ),
        )

        return redirect(
            "teacher_exam_papers",
            exam_id=exam.pk,
        )

    question_data_text = json.dumps(
        paper.question_data or [],
        ensure_ascii=False,
        indent=2,
    )

    paper_number_input = paper.paper_number
    paper_code_input = paper.paper_code
    title_input = paper.title

    if request.method == "POST":

        paper_number_input = request.POST.get(
            "paper_number",
            "",
        ).strip()

        paper_code_input = request.POST.get(
            "paper_code",
            "",
        ).strip()

        title_input = request.POST.get(
            "title",
            "",
        ).strip()

        question_data_text = request.POST.get(
            "question_data",
            "",
        )

        try:
            paper_number = int(paper_number_input)

            question_data = json.loads(
                question_data_text
            )

            question_data = _validate_paper_question_data(
                question_data
            )

            with transaction.atomic():

                locked_paper = (
                    ExamPaper.objects
                    .select_for_update()
                    .get(
                        pk=paper_id,
                        exam=exam,
                    )
                )

                # Kiểm tra lại trong transaction để tránh
                # trường hợp sinh viên bắt đầu thi đồng thời.
                if _paper_attempts(locked_paper).exists():

                    raise ValidationError(
                        "Phiên bản đề vừa phát sinh lượt thi. "
                        "Không thể tiếp tục chỉnh sửa."
                    )

                locked_paper.paper_number = paper_number
                locked_paper.paper_code = paper_code_input
                locked_paper.title = title_input
                locked_paper.question_data = question_data

                locked_paper.full_clean()

                locked_paper.save()

            messages.success(
                request,
                "Cập nhật phiên bản đề thành công.",
            )

            return redirect(
                "teacher_exam_papers",
                exam_id=exam.pk,
            )

        except json.JSONDecodeError:
            messages.error(
                request,
                "Dữ liệu câu hỏi không hợp lệ.",
            )

        except ValueError:
            messages.error(
                request,
                "Số thứ tự phiên bản phải là số nguyên.",
            )

        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(exc.messages),
            )

    return render(
        request,
        "exam/teacher_exam_paper_form.html",
        {
            "exam": exam,
            "form_title": "Chỉnh sửa phiên bản đề",
            "submit_label": "Lưu thay đổi",
            "paper_number": paper_number_input,
            "paper_code": paper_code_input,
            "title": title_input,
            "question_data_text": question_data_text,
            "show_question_data": True,
            "editing_paper": paper,
        },
    )





# ============================================================
# COPY EXAM PAPER
# ============================================================
@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_copy_exam_paper(
    request,
    exam_id,
    paper_id,
):
    """
    Sao chép phiên bản đề và cho phép chỉnh sửa bản sao
    ngay trong giao diện tạo đề.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    source_paper = get_object_or_404(
        ExamPaper,
        pk=paper_id,
        exam=exam,
    )

    last_number = (
        ExamPaper.objects
        .filter(exam=exam)
        .order_by("-paper_number")
        .values_list("paper_number", flat=True)
        .first()
    )

    next_number = (last_number or 0) + 1

    title_input = source_paper.title

    # Nạp toàn bộ câu hỏi từ phiên bản gốc vào trình biên tập.
    question_data_text = json.dumps(
        source_paper.question_data or [],
        ensure_ascii=False,
        indent=2,
    )

    paper_number_input = str(next_number)
    paper_code_input = ""

    if request.method == "POST":

        paper_number_input = request.POST.get(
            "paper_number",
            "",
        ).strip()

        paper_code_input = request.POST.get(
            "paper_code",
            "",
        ).strip()

        title_input = request.POST.get(
            "title",
            "",
        ).strip()

        question_data_text = request.POST.get(
            "question_data",
            "",
        )

        try:
            paper_number = int(
                paper_number_input
            )

            question_data = json.loads(
                question_data_text
            )

            question_data = _validate_paper_question_data(
                question_data
            )

            copy_exam_paper(
                source_paper,
                paper_number=paper_number,
                paper_code=paper_code_input,
                title=title_input,
                question_data=question_data,
            )

            messages.success(
                request,
                (
                    f"Đã sao chép {source_paper.paper_code} "
                    "thành phiên bản mới. "
                    "Nội dung đã được lưu độc lập."
                ),
            )

            return redirect(
                "teacher_exam_papers",
                exam_id=exam.pk,
            )

        except json.JSONDecodeError:
            messages.error(
                request,
                "Dữ liệu câu hỏi không hợp lệ.",
            )

        except ValueError:
            messages.error(
                request,
                "Số thứ tự phiên bản phải là số nguyên.",
            )

        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(exc.messages),
            )

    return render(
        request,
        "exam/teacher_exam_paper_form.html",
        {
            "exam": exam,
            "source_paper": source_paper,
            "form_title": "Sao chép và chỉnh sửa phiên bản đề",
            "submit_label": "Tạo phiên bản đề từ bản sao",
            "paper_number": paper_number_input,
            "paper_code": paper_code_input,
            "title": title_input,
            "question_data_text": question_data_text,

            # Bật trình biên tập câu hỏi cho bản sao.
            "show_question_data": True,
        },
    )



@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
@require_POST
def teacher_delete_exam_paper(
    request,
    exam_id,
    paper_id,
):
    """
    Xóa phiên bản đề.

    - Không xóa nếu đã có lượt thi.
    - Nếu mới phân công nhưng chưa thi:
      hủy các phân công đó rồi mới xóa phiên bản.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    try:
        with transaction.atomic():

            paper = get_object_or_404(
                ExamPaper.objects.select_for_update(),
                pk=paper_id,
                exam=exam,
            )

            if _paper_attempts(paper).exists():

                raise ValidationError(
                    "Không thể xóa phiên bản đề đã có lượt thi. "
                    "Dữ liệu lịch sử phải được bảo toàn."
                )

            assignment_count = ExamAssignment.objects.filter(
                paper=paper,
            ).count()

            # Chỉ xóa các phân công chưa phát sinh lượt thi.
            ExamAssignment.objects.filter(
                paper=paper,
            ).delete()

            paper_code = paper.paper_code

            paper.delete()

        if assignment_count:
            messages.success(
                request,
                (
                    f"Đã xóa phiên bản {paper_code} "
                    f"và hủy {assignment_count} phân công "
                    "chưa bắt đầu."
                ),
            )
        else:
            messages.success(
                request,
                f"Đã xóa phiên bản đề {paper_code}.",
            )

    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(exc.messages),
        )

    return redirect(
        "teacher_exam_papers",
        exam_id=exam.pk,
    )


# ============================================================
# TEACHER EXAM ASSIGNMENT MANAGEMENT
# ============================================================

@login_required
@user_passes_test(is_teacher, login_url="home")
def teacher_exam_assignments(request, exam_id):
    """
    Quản lý phân công phiên bản đề cho sinh viên.

    Hỗ trợ:
    - Phân công thủ công.
    - Phân công ngẫu nhiên cân bằng.
    - Theo dõi danh sách sinh viên đã được phân công.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    if request.method == "POST":

        action = request.POST.get("action", "").strip()

        assigned_by = getattr(
            request.user,
            "userprofile",
            None,
        )

        try:

            # ------------------------------------------------
            # 1. PHÂN CÔNG THỦ CÔNG
            # ------------------------------------------------

            if action == "manual":

                student_id = request.POST.get(
                    "student_id",
                    "",
                ).strip()

                paper_id = request.POST.get(
                    "paper_id",
                    "",
                ).strip()

                if not exam.offering_id:
                    raise ValidationError(
                        "Bài thi chưa được gắn với lớp học phần."
                    )

                enrollment = get_object_or_404(
                    Enrollment.objects.select_related(
                        "student",
                    ),
                    course_offering_id=exam.offering_id,
                    student_id=student_id,
                    status="active",
                )

                paper = get_object_or_404(
                    ExamPaper,
                    pk=paper_id,
                    exam=exam,
                    is_active=True,
                )

                assign_paper_manual(
                    exam,
                    paper,
                    enrollment.student,
                    assigned_by=assigned_by,
                )

                messages.success(
                    request,
                    (
                        "Phân công mã đề "
                        f"{paper.paper_code} thành công."
                    ),
                )

            # ------------------------------------------------
            # 2. PHÂN CÔNG NGẪU NHIÊN
            # ------------------------------------------------

            elif action == "random":

                selected_paper_ids = list(
                    dict.fromkeys(
                        request.POST.getlist("paper_ids")
                    )
                )

                if not selected_paper_ids:
                    raise ValidationError(
                        "Vui lòng chọn ít nhất một phiên bản đề."
                    )

                papers = list(
                    ExamPaper.objects.filter(
                        exam=exam,
                        is_active=True,
                        pk__in=selected_paper_ids,
                    ).order_by("paper_number")
                )

                if len(papers) != len(selected_paper_ids):
                    raise ValidationError(
                        "Có phiên bản đề không hợp lệ hoặc đã ngừng sử dụng."
                    )

                assignments = assign_papers_random(
                    exam,
                    papers,
                    assigned_by=assigned_by,
                )

                messages.success(
                    request,
                    (
                        "Đã phân công ngẫu nhiên thành công "
                        f"{len(assignments)} sinh viên."
                    ),
                )

            else:
                raise ValidationError(
                    "Thao tác phân công không hợp lệ."
                )

            return redirect(
                "teacher_exam_assignments",
                exam_id=exam.pk,
            )

        except ValidationError as exc:

            messages.error(
                request,
                "; ".join(exc.messages),
            )

    # --------------------------------------------------------
    # 3. LẤY DANH SÁCH PHIÊN BẢN ĐỀ
    # --------------------------------------------------------

    papers = (
        ExamPaper.objects
        .filter(
            exam=exam,
            is_active=True,
        )
        .order_by("paper_number")
    )

    # --------------------------------------------------------
    # 4. LẤY DANH SÁCH SINH VIÊN ĐANG GHI DANH
    # --------------------------------------------------------

    enrollments = Enrollment.objects.none()

    if exam.offering_id:

        enrollments = (
            Enrollment.objects
            .filter(
                course_offering_id=exam.offering_id,
                status="active",
                student__role="student",
            )
            .select_related(
                "student",
                "student__user",
            )
            .order_by(
                "student__user__last_name",
                "student__user__first_name",
                "student__user__username",
            )
        )

    # --------------------------------------------------------
    # 5. LẤY DANH SÁCH PHÂN CÔNG ĐÃ TỒN TẠI
    # --------------------------------------------------------

    assignments = (
        ExamAssignment.objects
        .filter(exam=exam)
        .select_related(
            "student",
            "student__user",
            "paper",
            "assigned_by",
            "assigned_by__user",
        )
        .order_by(
            "paper__paper_number",
            "student__user__last_name",
        )
    )

    assignment_map = {
        assignment.student_id: assignment
        for assignment in assignments
    }

    student_rows = []

    for enrollment in enrollments:

        student = enrollment.student

        student_rows.append({
            "student": student,
            "assignment": assignment_map.get(student.pk),
        })

    return render(
        request,
        "exam/teacher_exam_assignments.html",
        {
            "exam": exam,
            "papers": papers,
            "student_rows": student_rows,
            "assignments": assignments,
            "assignment_count": assignments.count(),
            "student_count": enrollments.count(),
            "unassigned_count": sum(
                1
                for row in student_rows
                if row["assignment"] is None
            ),
        },
    )


def _assignment_has_attempt(exam, assignment):
    """
    Kiểm tra sinh viên đã có lượt thi thuộc bài thi này chưa.

    Kiểm tra cả quan hệ assignment và quan hệ student trực tiếp
    để bảo vệ cả các lượt thi tương thích dữ liệu cũ.
    """

    return StudentExam.objects.filter(
        Q(assignment_id=assignment.pk)
        | Q(
            exam_id=exam.pk,
            student_id=assignment.student.user_id,
        )
    ).exists()



@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_edit_exam_assignment(
    request,
    exam_id,
    assignment_id,
):
    """
    Chuyển sinh viên sang phiên bản đề khác.

    Không thay đổi sinh viên và phương thức phân công.
    Không cho phép sửa nếu sinh viên đã có lượt thi.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    assignment = get_object_or_404(
        ExamAssignment.objects.select_related(
            "student",
            "student__user",
            "paper",
        ),
        pk=assignment_id,
        exam=exam,
    )

    if _assignment_has_attempt(exam, assignment):

        messages.error(
            request,
            "Sinh viên đã có lượt thi. Không thể thay đổi phân công.",
        )

        return redirect(
            "teacher_exam_assignments",
            exam_id=exam.pk,
        )

    papers = ExamPaper.objects.filter(
        exam=exam,
        is_active=True,
    ).order_by("paper_number")

    selected_paper_id = assignment.paper_id

    if request.method == "POST":

        selected_paper_id = request.POST.get(
            "paper_id",
            "",
        ).strip()

        try:
            with transaction.atomic():

                locked_assignment = (
                    ExamAssignment.objects
                    .select_for_update()
                    .select_related(
                        "student",
                        "student__user",
                    )
                    .get(
                        pk=assignment_id,
                        exam=exam,
                    )
                )

                # Kiểm tra lại ngay trước khi cập nhật.
                if _assignment_has_attempt(
                    exam,
                    locked_assignment,
                ):
                    raise ValidationError(
                        "Sinh viên vừa phát sinh lượt thi. "
                        "Không thể thay đổi phân công."
                    )

                selected_paper = get_object_or_404(
                    ExamPaper,
                    pk=selected_paper_id,
                    exam=exam,
                    is_active=True,
                )

                locked_assignment.paper = selected_paper

                locked_assignment.full_clean()

                locked_assignment.save(
                    update_fields=["paper"]
                )

            messages.success(
                request,
                (
                    "Đã cập nhật phiên bản đề cho sinh viên "
                    f"{assignment.student.student_id}."
                ),
            )

            return redirect(
                "teacher_exam_assignments",
                exam_id=exam.pk,
            )

        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(exc.messages),
            )

        except ValueError:
            messages.error(
                request,
                "Phiên bản đề được chọn không hợp lệ.",
            )

    return render(
        request,
        "exam/teacher_exam_assignment_form.html",
        {
            "exam": exam,
            "assignment": assignment,
            "papers": papers,
            "selected_paper_id": selected_paper_id,
        },
    )


@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
@require_POST
def teacher_delete_exam_assignment(
    request,
    exam_id,
    assignment_id,
):
    """
    Hủy phân công đề của một sinh viên.

    Không cho xóa nếu sinh viên đã có lượt thi.
    """

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    try:
        with transaction.atomic():

            assignment = get_object_or_404(
                ExamAssignment.objects
                .select_for_update()
                .select_related(
                    "student",
                    "student__user",
                    "paper",
                ),
                pk=assignment_id,
                exam=exam,
            )

            if _assignment_has_attempt(
                exam,
                assignment,
            ):
                raise ValidationError(
                    "Sinh viên đã có lượt thi. "
                    "Không thể xóa phân công để bảo toàn lịch sử."
                )

            student_code = (
                assignment.student.student_id
                or assignment.student.user.username
            )

            paper_code = assignment.paper.paper_code

            assignment.delete()

        messages.success(
            request,
            (
                f"Đã hủy phân công mã đề {paper_code} "
                f"của sinh viên {student_code}."
            ),
        )

    except ValidationError as exc:
        messages.error(
            request,
            "; ".join(exc.messages),
        )

    return redirect(
        "teacher_exam_assignments",
        exam_id=exam.pk,
    )


def _teacher_can_manage_student_exam(user, student_exam):
    """
    Kiểm tra user có quyền xử lý StudentExam hay không.

    - staff/superuser/admin: được phép.
    - lecturer: chỉ được xử lý bài thi thuộc CourseOffering
      mà giảng viên đang phụ trách.
    """

    if not is_teacher(user):
        return False

    if user.is_superuser or user.is_staff:
        return True

    profile = getattr(user, "userprofile", None)

    if not profile:
        return False

    if profile.role == "admin":
        return True

    if profile.role != "lecturer":
        return False

    offering = student_exam.exam.offering

    if not offering:
        return False

    return offering.teaching_assignments.filter(
        lecturer=profile
    ).exists()


@login_required
@user_passes_test(is_teacher, login_url="home")
@require_POST
def teacher_allow_student_exam(request, student_exam_id):
    """
    Giảng viên cho phép sinh viên tiếp tục bài thi
    sau khi bài thi bị khóa do đạt ngưỡng cảnh báo.
    """

    student_exam = get_object_or_404(
        StudentExam.objects.select_related(
            "exam",
            "exam__offering",
            "exam__offering__course",
            "student",
        ),
        pk=student_exam_id,
    )

    if not _teacher_can_manage_student_exam(
        request.user,
        student_exam,
    ):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Bạn không có quyền xử lý "
                    "bài thi này."
                ),
            },
            status=403,
        )

    if student_exam.is_submitted:
        return JsonResponse(
            {
                "success": False,
                "message": "Bài thi đã được nộp.",
            },
            status=409,
        )

    if student_exam.is_terminated:
        return JsonResponse(
            {
                "success": False,
                "message": "Bài thi đã kết thúc.",
            },
            status=409,
        )

    if not student_exam.is_locked:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Bài thi hiện không ở trạng thái "
                    "chờ giảng viên xử lý."
                ),
            },
            status=409,
        )

    student_exam.is_locked = False

    # warning_count đại diện cho chu kỳ cảnh báo hiện tại.
    # Lịch sử vi phạm vẫn nằm trong ProctorEvent.
    student_exam.warning_count = 0

    student_exam.active_gesture = ""
    student_exam.gesture_started_at = None
    student_exam.gesture_warned = False

    student_exam.lock_reason = ""
    student_exam.locked_at = None
    student_exam.locked_by = request.user

    student_exam.unlock_count += 1

    student_exam.save(
        update_fields=[
            "is_locked",
            "warning_count",
            "active_gesture",
            "gesture_started_at",
            "gesture_warned",
            "lock_reason",
            "locked_at",
            "locked_by",
            "unlock_count",
        ]
    )

    # return JsonResponse(
    #     {
    #         "success": True,
    #         "message": (
    #             "Đã cho phép sinh viên tiếp tục "
    #             "bài thi."
    #         ),
    #         "student_exam_id": student_exam.pk,
    #         "is_locked": False,
    #         "warning_count": student_exam.warning_count,
    #         "unlock_count": student_exam.unlock_count,
    #     }
    # )
    return redirect("teacher_monitor")



@login_required
@user_passes_test(is_teacher, login_url="home")
@require_POST
def teacher_terminate_student_exam(
    request,
    student_exam_id,
):
    """
    Giảng viên chủ động kết thúc bài thi
    của sinh viên đang bị khóa.
    """

    student_exam = get_object_or_404(
        StudentExam.objects.select_related(
            "exam",
            "exam__offering",
            "exam__offering__course",
            "student",
        ),
        pk=student_exam_id,
    )

    if not _teacher_can_manage_student_exam(
        request.user,
        student_exam,
    ):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Bạn không có quyền xử lý "
                    "bài thi này."
                ),
            },
            status=403,
        )

    if student_exam.is_submitted:
        return JsonResponse(
            {
                "success": False,
                "message": "Bài thi đã được nộp.",
            },
            status=409,
        )

    if student_exam.is_terminated:
        return JsonResponse(
            {
                "success": False,
                "message": "Bài thi đã kết thúc.",
            },
            status=409,
        )

    if not student_exam.is_locked:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Bài thi chưa bị khóa. "
                    "Không thể thực hiện thao tác này."
                ),
            },
            status=409,
        )

    termination_reason = (
        request.POST.get("reason")
        or "Giảng viên kết thúc bài thi sau khi xử lý vi phạm."
    )

    _grade_student_exam(
        student_exam,
        _submission_data_from_drafts(
            student_exam
        ),
        terminated=True,
        termination_reason=termination_reason,
    )

    # return JsonResponse(
    #     {
    #         "success": True,
    #         "message": (
    #             "Đã kết thúc và chấm bài thi "
    #             "của sinh viên."
    #         ),
    #         "student_exam_id": student_exam.pk,
    #         "is_locked": False,
    #         "is_submitted": True,
    #         "is_terminated": True,
    #         "redirect_url": reverse(
    #             "exam_result",
    #             args=(student_exam.pk,),
    #         ),
    #     }
    # )
    return redirect("teacher_monitor")


@login_required
@require_GET
def student_exam_status(request, student_exam_id):
    """
    API để sinh viên kiểm tra realtime trạng thái bài thi.

    Chỉ sinh viên sở hữu StudentExam mới được xem trạng thái.
    """

    try:
        student_exam = StudentExam.objects.select_related(
            "student",
            "exam",
        ).get(
            pk=student_exam_id,
            student=request.user,
        )
    except StudentExam.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Không tìm thấy bài thi."
            },
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "is_locked": student_exam.is_locked,
            "warning_count": student_exam.warning_count,
            "is_submitted": student_exam.is_submitted,
            "is_terminated": student_exam.is_terminated,
        }
    )


# ============================================================
# TEACHER EXAM PDF
# ============================================================

@login_required
@user_passes_test(is_teacher,login_url="home",)
def teacher_exam_pdf(
    request,
    exam_id,
):

    from html import escape
    from pathlib import Path

    from django.utils.text import slugify

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import (
        A4,
        landscape,
    )
    from reportlab.lib.styles import (
        ParagraphStyle,
        getSampleStyleSheet,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    roster = _teacher_exam_roster(
        exam
    )

    buffer = BytesIO()

    font_candidates = (
        Path(settings.BASE_DIR)
        / "static"
        / "fonts"
        / "DejaVuSans.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path(
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        ),
    )

    font_path = next(
        (
            path
            for path in font_candidates
            if path.exists()
        ),
        None,
    )

    font_name = "Helvetica"

    if font_path:

        font_name = "ExamReportUnicode"

        pdfmetrics.registerFont(
            TTFont(
                font_name,
                str(font_path),
            )
        )

    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=28,
        leftMargin=28,
        topMargin=28,
        bottomMargin=28,
        title=f"Kết quả {exam.title}",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ExamReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        alignment=TA_CENTER,
    )

    cell_style = ParagraphStyle(
        "ExamReportCell",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8,
        leading=10,
    )

    story = [
        Paragraph(
            "BẢNG KẾT QUẢ THI",
            title_style,
        ),
        Spacer(1, 8),
        Paragraph(
            f"Bài thi: {escape(exam.title)}",
            cell_style,
        ),
        Paragraph(
            f"Môn học: {escape(str(exam.course))}",
            cell_style,
        ),
        Paragraph(
            "Lớp học phần: "
            + escape(
                exam.offering.group_code
                if exam.offering_id
                else "Chưa gắn lớp"
            ),
            cell_style,
        ),
        Paragraph(
            f"Sĩ số ghi danh: {len(roster)}",
            cell_style,
        ),
        Spacer(1, 10),
    ]

    table_rows = [[
        "STT",
        "Mã SV",
        "Họ và tên",
        "Máy",
        "Camera",
        "Lớp hành chính",
        "Khoa",
        "Điểm",
        "Trạng thái",
        "Thời gian nộp",
    ]]

    for index, row in enumerate(
        roster,
        start=1,
    ):

        profile = row["profile"]
        attempt = row["attempt"]

        submitted_at = (
            timezone.localtime(
                attempt.finished_at
            ).strftime(
                "%d/%m/%Y %H:%M"
            )
            if attempt
            and attempt.finished_at
            else "-"
        )

        table_rows.append([
            str(index),

            Paragraph(
                escape(
                    profile.student_id
                    or "-"
                ),
                cell_style,
            ),

            Paragraph(
                escape(
                    profile.user.get_full_name()
                    or profile.user.username
                ),
                cell_style,
            ),

            row["computer_label"],

            Paragraph(
                escape(
                    row["camera_status"]
                ),
                cell_style,
            ),

            Paragraph(
                escape(
                    profile.class_name
                    or "-"
                ),
                cell_style,
            ),

            Paragraph(
                escape(
                    profile.get_faculty_display()
                    or "-"
                ),
                cell_style,
            ),

            (
                f"{attempt.score:g}"
                if attempt
                and attempt.is_submitted
                else "-"
            ),

            Paragraph(
                escape(
                    row["status"]
                ),
                cell_style,
            ),

            submitted_at,
        ])

    table = Table(
        table_rows,
        repeatRows=1,
        colWidths=[
            24,
            55,
            125,
            36,
            73,
            78,
            80,
            38,
            72,
            90,
        ],
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor(
                    "#174A72"
                ),
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                font_name,
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, 0),
                8,
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                colors.HexColor(
                    "#9AA8B2"
                ),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    colors.HexColor(
                        "#EEF3F6"
                    ),
                ],
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    story.append(table)

    document.build(story)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        'attachment; filename="ket-qua-'
        f'{slugify(exam.title) or exam.pk}.pdf"'
    )

    return response


# ============================================================
# EXAM RESULT
# ============================================================

@login_required
def exam_result_view(
    request,
    student_exam_id,
):

    student_exam = get_object_or_404(
        StudentExam,
        id=student_exam_id,
        student=request.user,
        is_submitted=True,
    )

    detail_results = (
        student_exam.answers
        .all()
        .order_by("question_index")
    )

    _prepare_answer_review(
        detail_results
    )

    snapshot = (
        student_exam.question_snapshot
        or {}
    )

    if isinstance(
        snapshot,
        dict,
    ):

        questions = snapshot.get(
            "questions",
            [],
        )

    elif isinstance(
        snapshot,
        list,
    ):

        questions = snapshot

    else:

        questions = []

    max_score = sum(
        float(
            question.get(
                "score",
                0,
            )
            or 0
        )
        for question in questions
    )

    return render(
        request,
        "exam_result.html",
        {
            "student_exam": student_exam,
            "detail_results": detail_results,
            "max_score": max_score,
        },
    )


# ============================================================
# PREPARE ANSWER REVIEW
# ============================================================

def _prepare_answer_review(
    detail_results,
):

    for answer in detail_results:

        answer.correct_answer = ""

        question_index = (
            answer.question_index
        )

        if question_index is None:
            continue

        student_exam = (
            answer.student_exam
        )

        question = _find_snapshot_question(
            student_exam,
            question_index,
        )

        if question is None:
            continue

        question_type = str(
            question.get(
                "type",
                "",
            )
        ).upper()

        # =====================================================
        # MCQ
        # =====================================================

        if question_type == "MCQ":

            correct_choices = []
            correct_choice_index = question.get("_correct_choice_index")

            for choice in question.get(
                "choices",
                [],
            ):

                if (
                    correct_choice_index is not None
                    and str(choice.get("index")) == str(correct_choice_index)
                ) or choice.get("is_correct") or choice.get("correct"):

                    correct_choices.append(
                        choice.get(
                            "content"
                        )
                        or choice.get(
                            "text",
                            "",
                        )
                    )

            answer.correct_answer = (
                "\n".join(
                    correct_choices
                )
            )

        # =====================================================
        # DRAG
        # =====================================================

        elif question_type == "DRAG":

            correct_answers = question.get(
                "_correct_answers",
                [],
            )

            answer.correct_answer = (
                "\n".join(
                    str(item)
                    for item in correct_answers
                )
            )

        # =====================================================
        # SORT
        # =====================================================

        elif question_type == "SORT":

            correct_order = question.get(
                "_correct_order",
                [],
            )

            answer.correct_answer = (
                "\n".join(
                    str(item)
                    for item in correct_order
                )
            )

        # =====================================================
        # CODE
        # =====================================================

        elif question_type == "CODE":

            lines = []

            for testcase in question.get(
                "test_cases",
                [],
            ):

                input_data = testcase.get(
                    "input_data",
                    testcase.get(
                        "input",
                        "",
                    ),
                )

                expected_output = testcase.get(
                    "expected_output",
                    testcase.get(
                        "output",
                        "",
                    ),
                )

                score = float(
                    testcase.get(
                        "score",
                        0,
                    )
                    or 0
                )

                lines.append(
                    f"Input: "
                    f"{input_data or '(trống)'} | "
                    f"Kết quả mong đợi: "
                    f"{expected_output} | "
                    f"Điểm: {score:g}"
                )

            answer.correct_answer = (
                "\n".join(lines)
            )


# ============================================================
# EXAM LIST
# ============================================================

@login_required(login_url="qr_login_page")
def exam_list_view(request):

    profile = request.user.userprofile

    exams = (
        Exam.objects
        .select_related(
            "course",
            "offering",
            "offering__term",
        )
        .filter(
            is_active=True
        )
    )

    # ========================================================
    # STUDENT
    # ========================================================

    if profile.role == "student":

        enrolled_offerings = (
            Enrollment.objects
            .filter(
                student=profile,
                status="active",
            )
            .values_list(
                "course_offering_id",
                flat=True,
            )
        )

        exams = (
            exams
            .filter(
                Q(offering__isnull=True)
                | Q(
                    offering_id__in=
                    enrolled_offerings
                )
            )
            .distinct()
        )

    # ========================================================
    # LECTURER
    # ========================================================

    elif profile.role == "lecturer":

        assigned_offerings = (
            TeachingAssignment.objects
            .filter(
                lecturer=profile,
            )
            .values_list(
                "course_offering_id",
                flat=True,
            )
        )

        exams = (
            exams
            .filter(
                Q(offering__isnull=True)
                | Q(
                    offering_id__in=
                    assigned_offerings
                )
            )
            .distinct()
        )

    # ========================================================
    # ADMIN
    # ========================================================
    # Admin xem tất cả.

    return render(
        request,
        "exam/exam_list.html",
        {
            "exams": exams,
        },
    )


# ============================================================
# STUDENT RESULT LIST
# ============================================================

@login_required(login_url="qr_login_page")
def exam_result_list_view(request):

    results = (
        StudentExam.objects
        .filter(
            student=request.user,
            is_submitted=True,
        )
        .select_related(
            "exam"
        )
        .order_by(
            "-finished_at"
        )
    )

    return render(
        request,
        "exam/exam_result_list.html",
        {
            "results": results,
        },
    )


# ============================================================
# TEACHER RESULTS
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_results_view(request):

    profile = request.user.userprofile

    offerings = (
        CourseOffering.objects
        .select_related(
            "course",
            "term",
        )
    )

    if profile.role == "lecturer":

        offerings = offerings.filter(
            teaching_assignments__lecturer=profile
        )

    offerings = (
        offerings
        .distinct()
        .order_by(
            "term__academic_year",
            "course__code",
            "group_code",
        )
    )

    for offering in offerings:

        offering.report_exams = (
            Exam.objects
            .filter(
                offering=offering,
            )
            .order_by(
                "-start_time"
            )
        )

    return render(
        request,
        "teacher_results.html",
        {
            "offerings": offerings,
        },
    )


# ============================================================
# ACCESSIBLE TEACHER EXAM
# ============================================================

def _get_accessible_teacher_exam(request, exam_id):
    """
    Lấy bài thi mà tài khoản giảng viên/admin có quyền quản lý.

    - Superuser: được phép.
    - Admin: được phép.
    - Lecturer: chỉ được quản lý lớp học phần được phân công.
    - Staff không có hồ sơ: được phép theo quyền staff.
    - Các vai trò khác: không được phép.
    """

    exam = get_object_or_404(
        Exam.objects.select_related(
            "course",
            "offering",
        ),
        pk=exam_id,
    )

    # 1. Superuser được phép quản lý tất cả bài thi.
    if request.user.is_superuser:
        return exam

    # 2. Lấy hồ sơ người dùng.
    profile = getattr(
        request.user,
        "userprofile",
        None,
    )

    # 3. Staff không có hồ sơ được phép quản lý.
    if profile is None:
        if request.user.is_staff:
            return exam

        raise Http404(
            "Không tìm thấy hồ sơ người dùng."
        )

    # 4. Admin được phép quản lý tất cả bài thi.
    if profile.role == "admin":
        return exam

    # 5. Giảng viên phải được phân công lớp học phần.
    # Không bỏ qua bước này dù tài khoản có is_staff=True.
    if profile.role == "lecturer":

        if not exam.offering_id:
            raise Http404(
                "Bài thi chưa được gán lớp học phần."
            )

        is_assigned = TeachingAssignment.objects.filter(
            course_offering_id=exam.offering_id,
            lecturer=profile,
        ).exists()

        if not is_assigned:
            raise Http404(
                "Bạn không được phân công giảng dạy lớp học phần này."
            )

        return exam

    # 6. Các vai trò còn lại không được quản lý bài thi.
    raise Http404(
        "Bạn không có quyền quản lý bài thi này."
    )

# ============================================================
# REOPEN EXAM COMPUTER
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
@require_POST
def reopen_exam_computer(
    request,
    computer_id,
):

    computer = get_object_or_404(
        ExamComputer.objects.select_related(
            "exam_session__exam",
            "exam_session__offering",
        ),
        pk=computer_id,
    )

    profile = request.user.userprofile

    if (
        profile.role == "lecturer"
        and not TeachingAssignment.objects.filter(
            course_offering=computer.exam_session.offering,
            lecturer=profile,
        ).exists()
    ):

        raise Http404(
            "Bạn không được phân công "
            "lớp học phần này."
        )

    if (
        computer.status != "absent"
        or not computer.student_id
    ):

        messages.error(
            request,
            "Chỉ có thể mở lại máy đang được ghi nhận vắng.",
        )

        return redirect(
            "teacher_exam_report",
            exam_id=computer.exam_session.exam_id,
        )

    computer.status = "assigned"
    computer.absence_reviewed_at = timezone.now()
    computer.absence_reviewed_by = request.user
    computer.note = (
        "Đã được giảng viên xác nhận "
        "có mặt và mở lại."
    )

    computer.save(
        update_fields=[
            "status",
            "absence_reviewed_at",
            "absence_reviewed_by",
            "note",
        ]
    )

    messages.success(
        request,
        (
            f"Đã mở lại máy "
            f"PC{computer.computer_number:02d}."
        ),
    )

    return redirect(
        "teacher_exam_report",
        exam_id=computer.exam_session.exam_id,
    )


# ============================================================
# REVIEW PROCTOR EVENT
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
@require_POST
def review_proctor_event(
    request,
    event_id,
):

    event = get_object_or_404(
        ProctorEvent.objects.select_related(
            "student_exam__exam"
        ),
        pk=event_id,
    )

    _get_accessible_teacher_exam(
        request,
        event.student_exam.exam_id,
    )

    event.reviewed_at = timezone.now()
    event.reviewed_by = request.user
    event.review_note = request.POST.get(
        "review_note",
        "",
    )[:2000]

    event.save(
        update_fields=[
            "reviewed_at",
            "reviewed_by",
            "review_note",
        ]
    )

    messages.success(
        request,
        "Đã lưu kết quả xem xét sự kiện.",
    )

    return redirect(
        "teacher_exam_report",
        exam_id=event.student_exam.exam_id,
    )


# ============================================================
# TEACHER VIEW STUDENT DETAIL
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_view_student_detail(
    request,
    student_exam_id,
):

    student_exam = get_object_or_404(
        StudentExam.objects.select_related(
            "exam",
            "student",
        ),
        id=student_exam_id,
        is_submitted=True,
    )

    _get_accessible_teacher_exam(
        request,
        student_exam.exam_id,
    )

    detail_results = (
        student_exam.answers
        .all()
        .order_by(
            "question_index"
        )
    )

    _prepare_answer_review(
        detail_results
    )

    snapshot = (
        student_exam.question_snapshot
        or {}
    )

    if isinstance(
        snapshot,
        dict,
    ):

        questions = snapshot.get(
            "questions",
            [],
        )

    elif isinstance(
        snapshot,
        list,
    ):

        questions = snapshot

    else:

        questions = []

    max_score = sum(
        float(
            question.get(
                "score",
                0,
            )
            or 0
        )
        for question in questions
    )

    return render(
        request,
        "exam_result.html",
        {
            "student_exam": student_exam,
            "detail_results": detail_results,
            "max_score": max_score,
            "teacher_view": True,
        },
    )


# ============================================================
# TEACHER ROSTER
# ============================================================

def _teacher_exam_roster(exam):

    if not exam.offering_id:
        return []

    enrollments = list(
        Enrollment.objects
        .filter(
            course_offering=exam.offering,
            status="active",
        )
        .select_related(
            "student",
            "student__user",
        )
        .order_by(
            "student__student_id",
            "student__user__last_name",
            "student__user__first_name",
        )
    )

    user_ids = [
        enrollment.student.user_id
        for enrollment in enrollments
    ]

    attempts = (
        StudentExam.objects
        .filter(
            exam=exam,
            student_id__in=user_ids,
        )
        .select_related(
            "student"
        )
        .order_by(
            "student_id",
            "-started_at",
        )
    )

    latest_attempts = {}

    for attempt in attempts:

        latest_attempts.setdefault(
            attempt.student_id,
            attempt,
        )

    computers_by_student = {}

    for computer in (
        ExamComputer.objects
        .filter(
            exam_session__exam=exam,
            student__isnull=False,
        )
        .order_by(
            "exam_session__start_time",
            "computer_number",
        )
    ):

        computers_by_student.setdefault(
            computer.student_id,
            computer,
        )

    rows = []

    camera_online_since = (
        timezone.now()
        - timedelta(
            seconds=120
        )
    )

    for enrollment in enrollments:

        student = enrollment.student

        attempt = latest_attempts.get(
            student.user_id
        )

        computer = computers_by_student.get(
            student.pk
        )

        if (
            attempt
            and attempt.is_submitted
        ):

            status = "Đã nộp"

        elif (
            computer
            and computer.status == "absent"
        ):

            status = "Vắng"

        elif attempt:

            status = "Đang thi"

        else:

            status = "Chưa có lượt thi"

        rows.append(
            {
                "profile": student,
                "attempt": attempt,
                "status": status,
                "computer": computer,

                "computer_label": (
                    f"PC{computer.computer_number:02d}"
                    if computer
                    else "-"
                ),

                "camera_status": (
                    "Đang kết nối"
                    if (
                        computer
                        and computer.camera_last_seen_at
                        and computer.camera_last_seen_at
                        >= camera_online_since
                    )
                    else (
                        "Mất kết nối"
                        if (
                            computer
                            and computer.camera_last_seen_at
                        )
                        else "Chưa cấu hình"
                    )
                ),

                "score_label": (
                    attempt.score
                    if (
                        attempt
                        and attempt.is_submitted
                    )
                    else "-"
                ),

                "can_reopen": (
                    status == "Vắng"
                    and computer is not None
                ),
            }
        )

    return rows


# ============================================================
# TEACHER EXAM SUBMISSIONS
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def teacher_exam_submissions(
    request,
    exam_id,
):

    profile = request.user.userprofile

    exam = get_object_or_404(
        Exam.objects.select_related(
            "course",
            "offering",
        ),
        id=exam_id,
    )

    # ========================================================
    # LECTURER ACCESS
    # ========================================================

    if profile.role == "lecturer":

        if not exam.offering_id:

            messages.error(
                request,
                (
                    "Bài thi này chưa được "
                    "gắn với lớp học phần."
                ),
            )

            return redirect(
                "course_list"
            )

        assigned = (
            TeachingAssignment.objects
            .filter(
                course_offering=exam.offering,
                lecturer=profile,
            )
            .exists()
        )

        if not assigned:

            messages.error(
                request,
                (
                    "Bạn không được phân công "
                    "giảng dạy lớp học phần này."
                ),
            )

            return redirect(
                "course_list"
            )

    submissions = (
        StudentExam.objects
        .filter(
            exam=exam,
            is_submitted=True,
        )
        .select_related(
            "student",
        )
        .order_by(
            "-finished_at"
        )
    )

    return render(
        request,
        "teacher_exam_submissions.html",
        {
            "exam": exam,
            "submissions": submissions,
        },
    )


# ============================================================
# LECTURER EXAM REPORT
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
def lecturer_exam_report(
    request,
    exam_id,
):

    exam = _get_accessible_teacher_exam(
        request,
        exam_id,
    )

    roster = _teacher_exam_roster(
        exam
    )

    proctor_events = (
        ProctorEvent.objects
        .filter(
            student_exam__exam=exam,
        )
        .select_related(
            "student_exam__student",
            "exam_computer",
            "reviewed_by",
        )
    )

    context = {
        "exam": exam,
        "roster": roster,
        "proctor_events": proctor_events,
        "total_students": len(roster),

        "submitted_count": sum(
            row["attempt"] is not None
            and row["attempt"].is_submitted
            for row in roster
        ),
    }

    return render(
        request,
        "lecturer_report.html",
        context,
    )


# @login_required
# @require_POST
# def report_proctor_violation(request, student_exam_id):
#     """
#     Ghi nhận 1 vi phạm giám sát từ trình duyệt.
#
#     Browser chỉ gửi tín hiệu đã được giữ đủ lâu.
#     Server là nơi quyết định warning_count và trạng thái LOCKED.
#     """
#
#     student_exam = get_object_or_404(
#         StudentExam,
#         pk=student_exam_id,
#         student=request.user,
#         is_submitted=False,
#     )
#
#     if student_exam.is_terminated:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "code": "exam_terminated",
#                 "message": "Bài thi đã bị dừng.",
#             },
#             status=409,
#         )
#
#     if student_exam.is_locked:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "code": "exam_locked",
#                 "locked": True,
#                 "warning_count": student_exam.warning_count,
#                 "message": "Bài thi đang được tạm khóa.",
#             },
#             status=423,
#         )
#
#     try:
#         payload = json.loads(request.body or "{}")
#         gesture = str(
#             payload.get("gesture", "")
#         ).strip()
#
#         duration_seconds = int(
#             payload.get("duration_seconds", 0)
#         )
#
#     except (
#         json.JSONDecodeError,
#         TypeError,
#         ValueError,
#     ):
#         return JsonResponse(
#             {
#                 "success": False,
#                 "message": "Dữ liệu cảnh báo không hợp lệ.",
#             },
#             status=400,
#         )
#
#     allowed_gestures = {
#         "looking_left",
#         "looking_right",
#         "looking_down",
#         "tab_switch",
#     }
#
#     if gesture not in allowed_gestures:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "message": "Loại vi phạm không được hỗ trợ.",
#             },
#             status=400,
#         )
#
#     if duration_seconds < 2:
#         return JsonResponse(
#             {
#                 "success": False,
#                 "message": (
#                     "Thời gian vi phạm chưa đủ "
#                     "để ghi nhận cảnh báo."
#                 ),
#             },
#             status=400,
#         )
#
#     now = timezone.now()
#
#     with transaction.atomic():
#
#         locked_exam = (
#             StudentExam.objects
#             .select_for_update()
#             .get(pk=student_exam.pk)
#         )
#
#         if locked_exam.is_submitted:
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "code": "exam_submitted",
#                     "message": "Bài thi đã được nộp.",
#                 },
#                 status=409,
#             )
#
#         if locked_exam.is_terminated:
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "code": "exam_terminated",
#                     "message": "Bài thi đã bị dừng.",
#                 },
#                 status=409,
#             )
#
#         if locked_exam.is_locked:
#             return JsonResponse(
#                 {
#                     "success": False,
#                     "code": "exam_locked",
#                     "locked": True,
#                     "warning_count": (
#                         locked_exam.warning_count
#                     ),
#                     "message": (
#                         "Bài thi đang được tạm khóa."
#                     ),
#                 },
#                 status=423,
#             )
#
#         # Mỗi request hợp lệ = 1 cảnh báo.
#         locked_exam.warning_count += 1
#         locked_exam.last_violation_at = now
#         locked_exam.active_gesture = gesture
#         locked_exam.gesture_warned = True
#
#         should_lock = (
#             locked_exam.warning_count >= 3
#         )
#
#         update_fields = [
#             "warning_count",
#             "last_violation_at",
#             "active_gesture",
#             "gesture_warned",
#         ]
#
#         if should_lock:
#
#             locked_exam.is_locked = True
#
#             locked_exam.lock_reason = (
#                 "Tự động khóa sau 3 lần "
#                 "cảnh báo giám sát AI."
#             )
#
#             locked_exam.locked_at = now
#             locked_exam.locked_by = None
#
#             update_fields.extend(
#                 [
#                     "is_locked",
#                     "lock_reason",
#                     "locked_at",
#                     "locked_by",
#                 ]
#             )
#
#         locked_exam.save(
#             update_fields=update_fields
#         )
#
#         # Bước 8 chỉ lưu metadata.
#         # Ảnh bằng chứng để Bước 10.
#         ProctorEvent.objects.create(
#             student_exam=locked_exam,
#             exam_computer=locked_exam.exam_computer,
#             event_type=gesture,
#             duration_seconds=duration_seconds,
#         )
#
#     if should_lock:
#
#         message = (
#             "Đã đạt 3 lần cảnh báo. "
#             "Bài thi đã được tạm khóa "
#             "để giảng viên kiểm tra."
#         )
#
#     else:
#
#         message = (
#             "Hệ thống đã ghi nhận "
#             "cảnh báo giám sát."
#         )
#
#     return JsonResponse(
#         {
#             "success": True,
#             "warning_created": True,
#             "warning_count": (
#                 locked_exam.warning_count
#             ),
#             "locked": should_lock,
#             "message": message,
#         }
#     )


@login_required
@require_POST
def report_proctor_violation(request, student_exam_id):
    """
    Ghi nhận một vi phạm giám sát.

    Step 10:
    - nhận dữ liệu multipart/form-data từ browser
    - nhận tối đa 1 ảnh webcam làm evidence
    - lưu ProctorEvent + evidence_image
    - server vẫn là nơi quyết định warning_count và LOCKED
    """

    student_exam = get_object_or_404(
        StudentExam,
        pk=student_exam_id,
        student=request.user,
        is_submitted=False,
    )

    if student_exam.is_terminated:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_terminated",
                "message": "Bài thi đã bị dừng.",
            },
            status=409,
        )

    if student_exam.is_locked:
        return JsonResponse(
            {
                "success": False,
                "code": "exam_locked",
                "locked": True,
                "warning_count": student_exam.warning_count,
                "message": "Bài thi đang được tạm khóa.",
            },
            status=423,
        )

    # --------------------------------------------------------
    # Nhận dữ liệu từ multipart/form-data hoặc JSON cũ
    # --------------------------------------------------------

    evidence_image = request.FILES.get("evidence")

    if request.content_type.startswith("multipart/form-data"):
        gesture = str(
            request.POST.get("gesture", "")
        ).strip()

        try:
            duration_seconds = int(
                request.POST.get("duration_seconds", 0)
            )
        except (TypeError, ValueError):
            duration_seconds = 0

    else:
        try:
            payload = json.loads(
                request.body or "{}"
            )
            gesture = str(
                payload.get("gesture", "")
            ).strip()
            duration_seconds = int(
                payload.get("duration_seconds", 0)
            )
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Dữ liệu cảnh báo không hợp lệ.",
                },
                status=400,
            )

    # --------------------------------------------------------
    # Kiểm tra loại vi phạm
    # --------------------------------------------------------

    allowed_gestures = {
        "looking_left",
        "looking_right",
        "looking_down",
        "tab_switch",
    }

    if gesture not in allowed_gestures:
        return JsonResponse(
            {
                "success": False,
                "message": "Loại vi phạm không được hỗ trợ.",
            },
            status=400,
        )

    # Head pose phải tồn tại >= 2 giây.
    # Tab switch chỉ cần >= 1 giây.
    minimum_duration = (
        1
        if gesture == "tab_switch"
        else 2
    )

    if duration_seconds < minimum_duration:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Thời gian vi phạm chưa đủ "
                    "để ghi nhận cảnh báo."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # Kiểm tra evidence image nếu browser gửi
    # --------------------------------------------------------

    if evidence_image:
        max_evidence_size = 2 * 1024 * 1024

        if evidence_image.size > max_evidence_size:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Ảnh bằng chứng vượt quá 2 MB.",
                },
                status=400,
            )

        allowed_content_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if evidence_image.content_type not in allowed_content_types:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Định dạng ảnh bằng chứng không hợp lệ.",
                },
                status=400,
            )

        try:
            image = Image.open(evidence_image)
            image.verify()
            evidence_image.seek(0)
        except Exception:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không thể xác thực ảnh bằng chứng.",
                },
                status=400,
            )

    now = timezone.now()

    with transaction.atomic():
        locked_exam = (
            StudentExam.objects
            .select_for_update()
            .get(pk=student_exam.pk)
        )

        if locked_exam.is_submitted:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_submitted",
                    "message": "Bài thi đã được nộp.",
                },
                status=409,
            )

        if locked_exam.is_terminated:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_terminated",
                    "message": "Bài thi đã bị dừng.",
                },
                status=409,
            )

        if locked_exam.is_locked:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_locked",
                    "locked": True,
                    "warning_count": locked_exam.warning_count,
                    "message": "Bài thi đang được tạm khóa.",
                },
                status=423,
            )

        locked_exam.warning_count += 1
        locked_exam.last_violation_at = now
        locked_exam.active_gesture = gesture
        locked_exam.gesture_warned = True

        should_lock = locked_exam.warning_count >= 3

        update_fields = [
            "warning_count",
            "last_violation_at",
            "active_gesture",
            "gesture_warned",
        ]

        if should_lock:
            locked_exam.is_locked = True
            locked_exam.lock_reason = (
                "Tự động khóa sau 3 lần cảnh báo giám sát AI."
            )
            locked_exam.locked_at = now
            locked_exam.locked_by = None

            update_fields.extend([
                "is_locked",
                "lock_reason",
                "locked_at",
                "locked_by",
            ])

        locked_exam.save(update_fields=update_fields)

        # ----------------------------------------------------
        # STEP 10: lưu event + ảnh bằng chứng
        # ----------------------------------------------------

        event = ProctorEvent(
            student_exam=locked_exam,
            exam_computer=locked_exam.exam_computer,
            event_type=gesture,
            duration_seconds=duration_seconds,
        )

        if evidence_image:
            event.evidence_image = evidence_image

        event.save()

    if should_lock:
        message = (
            "Đã đạt 3 lần cảnh báo. "
            "Bài thi đã được tạm khóa để giảng viên kiểm tra."
        )
    else:
        message = "Hệ thống đã ghi nhận cảnh báo giám sát."

    return JsonResponse(
        {
            "success": True,
            "warning_created": True,
            "warning_count": locked_exam.warning_count,
            "locked": should_lock,
            "event_id": event.id,
            "evidence_saved": bool(event.evidence_image),
            "message": message,
        }
    )


@login_required
@require_POST
def start_screen_sharing(request, student_exam_id):
    """
    Ghi nhận sinh viên bắt đầu chia sẻ màn hình.
    Chỉ cho phép bắt đầu khi bài thi chưa nộp,
    chưa kết thúc và chưa bị khóa.
    """
    with transaction.atomic():
        student_exam = get_object_or_404(
            StudentExam.objects.select_for_update(),
            pk=student_exam_id,
            student=request.user,
        )

        if student_exam.is_submitted:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_submitted",
                    "message": "Bài thi đã được nộp.",
                },
                status=409,
            )

        if student_exam.is_terminated:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_terminated",
                    "message": "Bài thi đã kết thúc.",
                },
                status=409,
            )

        if student_exam.is_locked:
            return JsonResponse(
                {
                    "success": False,
                    "code": "exam_locked",
                    "message": "Bài thi đang bị tạm khóa.",
                },
                status=423,
            )

        # Không tạo sự kiện trùng nếu trạng thái đã là đang chia sẻ.
        if student_exam.is_screen_sharing:
            return JsonResponse(
                {
                    "success": True,
                    "is_screen_sharing": True,
                    "message": "Màn hình đang được ghi nhận là chia sẻ.",
                }
            )

        now = timezone.now()

        student_exam.is_screen_sharing = True
        student_exam.screen_share_started_at = now
        student_exam.screen_share_stopped_at = None

        student_exam.save(
            update_fields=[
                "is_screen_sharing",
                "screen_share_started_at",
                "screen_share_stopped_at",
            ]
        )

        event = ProctorEvent.objects.create(
            student_exam=student_exam,
            exam_computer=student_exam.exam_computer,
            event_type="screen_share_started",
            duration_seconds=0,
        )

    return JsonResponse(
        {
            "success": True,
            "is_screen_sharing": True,
            "event_id": event.id,
            "message": "Đã ghi nhận bắt đầu chia sẻ màn hình.",
        }
    )


@login_required
@require_POST
def stop_screen_sharing(request, student_exam_id):
    """
    Ghi nhận sinh viên dừng chia sẻ màn hình.
    Chỉ tạo sự kiện khi trạng thái chuyển từ đang chia sẻ
    sang đã dừng, tránh ghi nhận trùng.
    """
    with transaction.atomic():
        student_exam = get_object_or_404(
            StudentExam.objects.select_for_update(),
            pk=student_exam_id,
            student=request.user,
        )

        # Nếu đã dừng thì trả về trạng thái hiện tại.
        if not student_exam.is_screen_sharing:
            return JsonResponse(
                {
                    "success": True,
                    "is_screen_sharing": False,
                    "message": "Màn hình hiện không được ghi nhận là đang chia sẻ.",
                }
            )

        now = timezone.now()

        student_exam.is_screen_sharing = False
        student_exam.screen_share_stopped_at = now

        student_exam.save(
            update_fields=[
                "is_screen_sharing",
                "screen_share_stopped_at",
            ]
        )

        event = ProctorEvent.objects.create(
            student_exam=student_exam,
            exam_computer=student_exam.exam_computer,
            event_type="screen_share_stopped",
            duration_seconds=0,
        )

    return JsonResponse(
        {
            "success": True,
            "is_screen_sharing": False,
            "event_id": event.id,
            "message": "Đã ghi nhận dừng chia sẻ màn hình.",
        }
    )


def _teacher_monitor_queryset(user):
    """
    Lấy các StudentExam mà người đang đăng nhập
    được phép giám sát.
    """

    queryset = (
        StudentExam.objects
        .select_related(
            "student",
            "exam",
            "exam__course",
            "exam__offering",
            "exam_computer",
        )
        .filter(
            is_submitted=False
        )
        .order_by(
            "-is_locked",
            "-warning_count",
            "-started_at",
        )
    )

    # Admin / Staff / Superuser
    if user.is_staff or user.is_superuser:
        return queryset

    # Lecturer
    try:
        profile = user.userprofile
    except UserProfile.DoesNotExist:
        return StudentExam.objects.none()

    if profile.role != "lecturer":
        return StudentExam.objects.none()

    return queryset.filter(
        exam__offering__teaching_assignments__lecturer=profile
    ).distinct()
@login_required
def teacher_monitor_view(request):

    if not (
        request.user.is_staff
        or request.user.is_superuser
    ):
        try:
            profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return HttpResponseForbidden(
                "Bạn không có quyền truy cập Teacher Monitor."
            )

        if profile.role != "lecturer":
            return HttpResponseForbidden(
                "Bạn không có quyền truy cập Teacher Monitor."
            )

    student_exams = list(
        _teacher_monitor_queryset(request.user)
    )

    exam_ids = [
        student_exam.id
        for student_exam in student_exams
    ]

    events_by_exam = defaultdict(list)

    if exam_ids:

        events = (
            ProctorEvent.objects
            .filter(
                student_exam_id__in=exam_ids
            )
            .order_by("-created_at")
        )

        for event in events:
            events_by_exam[
                event.student_exam_id
            ].append(event)

    monitor_rows = []

    for student_exam in student_exams:

        events = events_by_exam.get(
            student_exam.id,
            []
        )

        latest_event = (
            events[0]
            if events
            else None
        )

        student_name = (
            student_exam.student
            .get_full_name()
            .strip()
        )

        if not student_name:
            student_name = (
                student_exam.student.username
            )

        computer = student_exam.exam_computer

        monitor_rows.append(
            {
                "student_exam": student_exam,

                "student_name": student_name,

                "username": (
                    student_exam.student.username
                ),

                "computer_number": (
                    computer.computer_number
                    if computer
                    else None
                ),

                "computer_status": (
                    computer.get_status_display()
                    if computer
                    else "Chưa gán máy"
                ),

                "latest_event": latest_event,

                "events": events[:10],
            }
        )

    return render(
        request,
        "exam/teacher_monitor.html",
        {
            "monitor_rows": monitor_rows,
            "monitor_count": len(monitor_rows),
        },
    )

@login_required
def teacher_monitor_data(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
    ):
        try:
            profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không có quyền.",
                },
                status=403,
            )

        if profile.role != "lecturer":
            return JsonResponse(
                {
                    "success": False,
                    "message": "Không có quyền.",
                },
                status=403,
            )

    student_exams = list(
        _teacher_monitor_queryset(request.user)
    )

    exam_ids = [
        student_exam.id
        for student_exam in student_exams
    ]

    events_by_exam = defaultdict(list)

    if exam_ids:
        events = (
            ProctorEvent.objects
            .filter(
                student_exam_id__in=exam_ids
            )
            .order_by("-created_at")
        )

        for event in events:
            # Chỉ giữ tối đa 10 sự kiện gần nhất cho mỗi lượt thi.
            if len(events_by_exam[event.student_exam_id]) < 10:
                events_by_exam[event.student_exam_id].append(event)

    rows = []

    for student_exam in student_exams:
        computer = student_exam.exam_computer
        latest_events = events_by_exam.get(
            student_exam.id,
            [],
        )
        latest_event = (
            latest_events[0]
            if latest_events
            else None
        )

        student_name = (
            student_exam.student
            .get_full_name()
            .strip()
        )

        if not student_name:
            student_name = (
                student_exam.student.username
            )

        offering = student_exam.exam.offering

        rows.append(
            {
                "student_exam_id": student_exam.id,
                "student_name": student_name,
                "username": student_exam.student.username,
                "exam_title": student_exam.exam.title,
                "group_code": (
                    offering.group_code
                    if offering
                    else ""
                ),
                "classroom": (
                    offering.classroom
                    if offering
                    else ""
                ),
                "computer_number": (
                    computer.computer_number
                    if computer
                    else None
                ),
                "computer_status": (
                    computer.get_status_display()
                    if computer
                    else "Chưa gán máy"
                ),
                "warning_count": student_exam.warning_count,
                "is_screen_sharing": student_exam.is_screen_sharing,
                "screen_share_started_at": (
                    student_exam.screen_share_started_at.isoformat()
                    if student_exam.screen_share_started_at
                    else None
                ),
                "screen_share_stopped_at": (
                    student_exam.screen_share_stopped_at.isoformat()
                    if student_exam.screen_share_stopped_at
                    else None
                ),
                "is_locked": student_exam.is_locked,
                "is_submitted": student_exam.is_submitted,
                "is_terminated": student_exam.is_terminated,
                "lock_reason": student_exam.lock_reason,
                "active_gesture": student_exam.active_gesture,
                "last_violation_at": (
                    student_exam.last_violation_at.isoformat()
                    if student_exam.last_violation_at
                    else None
                ),
                "latest_event": (
                    {
                        "id": latest_event.id,
                        "event_type": latest_event.event_type,
                        "event_type_display": (
                            latest_event.get_event_type_display()
                        ),
                        "duration_seconds": (
                            latest_event.duration_seconds
                        ),
                        "created_at": (
                            latest_event.created_at.isoformat()
                        ),
                        "evidence_url": (
                            latest_event.evidence_image.url
                            if latest_event.evidence_image
                            else ""
                        ),
                    }
                    if latest_event
                    else None
                ),
                "events": [
                    {
                        "id": event.id,
                        "event_type": event.event_type,
                        "event_type_display": (
                            event.get_event_type_display()
                        ),
                        "duration_seconds": (
                            event.duration_seconds
                        ),
                        "created_at": (
                            event.created_at.isoformat()
                        ),
                        "evidence_url": (
                            event.evidence_image.url
                            if event.evidence_image
                            else ""
                        ),
                    }
                    for event in latest_events
                ],
            }
        )

    return JsonResponse(
        {
            "success": True,
            "count": len(rows),
            "rows": rows,
        }
    )


# ============================================================
# ĐIỂM DANH KHUÔN MẶT - TRANG CHỌN BÀI THI
# ============================================================

@login_required(login_url="qr_login_page")
def face_attendance_view(request):
    profile = get_object_or_404(
        UserProfile,
        user=request.user,
    )

    # Chỉ giảng viên và quản trị viên được truy cập.
    if profile.role not in ("lecturer", "admin"):
        messages.error(
            request,
            "Bạn không có quyền truy cập chức năng điểm danh.",
        )
        return redirect("course_list")

    # Lấy các lớp học phần mà giảng viên được phân công.
    if profile.role == "lecturer":
        offerings = CourseOffering.objects.filter(
            teaching_assignments__lecturer=profile,
        ).distinct()
    else:
        # Quản trị viên có thể xem các lớp học phần.
        offerings = CourseOffering.objects.all()

    # Chỉ hiển thị bài thi tại lớp, đang được cho phép thi
    # và có lớp học phần hợp lệ.
    exams = (
        Exam.objects
        .filter(
            offering__in=offerings,
            exam_type=Exam.EXAM_TYPE_CLASSROOM,
            is_active=True,
        )
        .select_related(
            "course",
            "offering",
            "offering__term",
        )
        .order_by("start_time")
    )

    return render(
        request,
        "exam/face_attendance.html",
        {
            "title": "Điểm danh khuôn mặt",
            "exams": exams,
        },
    )




@csrf_protect
@login_required(login_url="qr_login_page")
@require_POST
def verify_face_attendance(request, exam_id):
    """
    Xác minh khuôn mặt sinh viên và ghi nhận điểm danh
    cho một bài thi tại lớp.
    """
    import base64
    import binascii
    import io
    import json
    import math

    import numpy as np
    from PIL import Image, UnidentifiedImageError
    from django.db import transaction
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404
    from django.views.decorators.http import require_POST
    from deepface import DeepFace

    profile = get_object_or_404(UserProfile, user=request.user)

    if profile.role not in ("lecturer", "admin"):
        return JsonResponse(
            {"success": False, "message": "Bạn không có quyền điểm danh."},
            status=403,
        )

    exam = get_object_or_404(
        Exam.objects.select_related("offering", "course"),
        pk=exam_id,
    )

    if (
        exam.exam_type != Exam.EXAM_TYPE_CLASSROOM
        or exam.offering_id is None
    ):
        return JsonResponse(
            {"success": False, "message": "Bài thi không thuộc hình thức thi tại lớp."},
            status=400,
        )

    if profile.role == "lecturer":
        if not TeachingAssignment.objects.filter(
            course_offering_id=exam.offering_id,
            lecturer=profile,
        ).exists():
            return JsonResponse(
                {"success": False, "message": "Bạn không được phân công dạy lớp này."},
                status=403,
            )

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"success": False, "message": "Dữ liệu gửi lên không hợp lệ."},
            status=400,
        )

    if data.get("consent") is not True:
        return JsonResponse(
            {"success": False, "message": "Cần xác nhận đồng ý xử lý ảnh khuôn mặt."},
            status=400,
        )

    image_data = data.get("image", "")

    if not isinstance(image_data, str):
        return JsonResponse(
            {"success": False, "message": "Ảnh khuôn mặt không hợp lệ."},
            status=400,
        )

    if image_data.startswith("data:image/jpeg;base64,"):
        encoded = image_data.split(",", 1)[1]
    elif image_data.startswith("data:image/png;base64,"):
        encoded = image_data.split(",", 1)[1]
    else:
        return JsonResponse(
            {"success": False, "message": "Ảnh phải ở định dạng JPEG hoặc PNG."},
            status=400,
        )

    if len(encoded) > 4 * 1024 * 1024:
        return JsonResponse(
            {"success": False, "message": "Ảnh quá lớn."},
            status=413,
        )

    try:
        raw_image = base64.b64decode(encoded, validate=True)

        if len(raw_image) > 3 * 1024 * 1024:
            raise ValueError("Image too large")

        with Image.open(io.BytesIO(raw_image)) as img:
            if img.format not in ("JPEG", "PNG"):
                raise ValueError("Unsupported image format")

            img.verify()

        with Image.open(io.BytesIO(raw_image)) as img:
            img = img.convert("RGB")

            if (
                img.width < 160
                or img.height < 160
                or img.width > 3000
                or img.height > 3000
            ):
                raise ValueError("Invalid dimensions")

            image_array = np.asarray(img)

    except (
        ValueError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
    ):
        return JsonResponse(
            {"success": False, "message": "Không thể đọc ảnh. Vui lòng quét lại."},
            status=400,
        )

    try:
        representations = DeepFace.represent(
            img_path=image_array,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=True,
        )
    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": "Không nhận diện được khuôn mặt. Hãy đặt khuôn mặt ngay trước camera và thử lại.",
            },
            status=422,
        )

    if len(representations) != 1:
        return JsonResponse(
            {"success": False, "message": "Ảnh phải có đúng một khuôn mặt."},
            status=422,
        )

    query_embedding = representations[0].get("embedding")

    if not is_valid_face_embedding(query_embedding):
        return JsonResponse(
            {"success": False, "message": "Không tạo được dữ liệu khuôn mặt hợp lệ."},
            status=422,
        )

    query_vector = np.asarray(query_embedding, dtype=np.float64)
    query_norm = np.linalg.norm(query_vector)

    # Chỉ xét sinh viên đang hoạt động trong lớp học phần của bài thi.
    enrollments = Enrollment.objects.filter(
        course_offering_id=exam.offering_id,
        status="active",
        student__role="student",
        student__user__is_active=True,
        student__face_profile__is_active=True,
        student__face_profile__model_name="Facenet512",
    ).select_related(
        "student",
        "student__user",
        "student__face_profile",
    )

    candidates = []

    for enrollment in enrollments:
        student = enrollment.student
        face_profile = student.face_profile
        stored_embedding = face_profile.embedding

        if not is_valid_face_embedding(stored_embedding):
            continue

        stored_vector = np.asarray(stored_embedding, dtype=np.float64)
        stored_norm = np.linalg.norm(stored_vector)

        if not math.isfinite(stored_norm) or stored_norm <= 0:
            continue

        similarity = float(
            np.dot(query_vector, stored_vector)
            / (query_norm * stored_norm)
        )

        if not math.isfinite(similarity):
            continue

        similarity = max(-1.0, min(1.0, similarity))
        distance = 1.0 - similarity
        candidates.append((distance, student))

    if not candidates:
        return JsonResponse(
            {
                "success": False,
                "message": "Không tìm thấy sinh viên có hồ sơ khuôn mặt hợp lệ trong lớp này.",
            },
            status=404,
        )

    candidates.sort(key=lambda item: item[0])
    best_distance, best_student = candidates[0]

    # Ngưỡng ban đầu cần được kiểm thử với dữ liệu khuôn mặt thực tế.
    if best_distance > 0.30:
        return JsonResponse(
            {"success": False, "message": "Không khớp với hồ sơ khuôn mặt của sinh viên trong lớp."},
            status=404,
        )

    # Từ chối nếu hai hồ sơ đứng đầu quá gần nhau về điểm khớp.
    if (
        len(candidates) > 1
        and candidates[1][0] - best_distance < 0.05
    ):
        return JsonResponse(
            {
                "success": False,
                "message": "Kết quả nhận diện chưa đủ chắc chắn. Vui lòng quét lại.",
            },
            status=409,
        )

    from django.db import IntegrityError

    try:
        with transaction.atomic():
            attendance, created = ExamAttendance.objects.get_or_create(
                exam=exam,
                student=best_student,
                defaults={"method": ExamAttendance.METHOD_FACE},
            )
    except IntegrityError:
        attendance = ExamAttendance.objects.get(
            exam=exam,
            student=best_student,
        )
        created = False

    user = best_student.user
    display_name = user.get_full_name().strip() or user.username

    return JsonResponse(
        {
            "success": True,
            "created": created,
            "message": (
                "Điểm danh thành công."
                if created
                else "Sinh viên này đã được điểm danh trước đó."
            ),
            "student": display_name,
            "attendance_time": attendance.checked_in_at.isoformat(),
        }
    )





@login_required(login_url="qr_login_page")
def face_attendance_exam_view(request, exam_id):
    profile = get_object_or_404(UserProfile, user=request.user)

    if profile.role not in ("lecturer", "admin"):
        messages.error(
            request,
            "Bạn không có quyền truy cập chức năng điểm danh.",
        )
        return redirect("course_list")

    exam = get_object_or_404(
        Exam.objects.select_related("course", "offering"),
        pk=exam_id,
        exam_type=Exam.EXAM_TYPE_CLASSROOM,
        is_active=True,
    )

    if exam.offering_id is None:
        messages.error(request, "Bài thi chưa được gắn với lớp học phần.")
        return redirect("face_attendance")

    if profile.role == "lecturer":
        is_assigned = TeachingAssignment.objects.filter(
            course_offering_id=exam.offering_id,
            lecturer=profile,
        ).exists()

        if not is_assigned:
            messages.error(
                request,
                "Bạn không được phân công dạy lớp có bài thi này.",
            )
            return redirect("face_attendance")

    return render(
        request,
        "exam/face_attendance_scan.html",
        {
            "title": "Điểm danh khuôn mặt",
            "exam": exam,
        },
    )