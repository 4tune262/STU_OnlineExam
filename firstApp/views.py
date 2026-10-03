import json
import random
import re
import hmac

from uuid import uuid4
from io import BytesIO
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import Http404, HttpResponse, JsonResponse, QueryDict
from django.contrib.auth import login
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    UserProfile,
    Course,
    CourseOffering,
    Exam,
    ExamComputer,
    ProctorEvent,
    StudentExam,
    StudentAnswer,
    TeachingAssignment,
    Enrollment,
)

from .exam_engine import (
    build_student_snapshot,
    get_student_exam_questions,
)

from .vision import (
    classify_frame,
    proctoring_available,
)

from compiler.run import run_cpp


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

        elif profile and exam.offering_id:

            exam.dashboard_action_url = reverse(
                "teacher_exam_report",
                args=(exam.pk,),
            )

            exam.dashboard_action_label = "Xem kết quả lớp"
            exam.dashboard_action_icon = "bi bi-clipboard-data"
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

            data = json.loads(request.body)

            qr_token = data.get("qr_token")

            profile = (
                UserProfile.objects
                .filter(
                    qr_token=qr_token
                )
                .select_related("user")
                .first()
            )

            if profile and profile.user.is_active:

                login(
                    request,
                    profile.user,
                )

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

        except Exception as e:

            return JsonResponse({
                "status": "error",
                "message": str(e),
            })

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

    return render(
        request,
        "profile.html",
        {
            "title": "Hồ sơ cá nhân",
            "profile": user_profile,
        },
    )


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

            paper = build_student_snapshot(exam)
            paper_codes = exam.paper_codes or []
            if assigned_computer and paper_codes:
                paper["paper_code"] = paper_codes[
                    (assigned_computer.computer_number - 1) % len(paper_codes)
                ]

            with transaction.atomic():

                student_exam = StudentExam.objects.create(
                    student=request.user,
                    exam=exam,
                    exam_computer=assigned_computer,
                    exam_code=paper["paper_code"],
                    question_snapshot=paper,
                )

        except Exception as e:

            messages.error(
                request,
                f"Không thể tạo đề thi: {e}",
            )

            return redirect("course_list")

    # ========================================================
    # 9. ĐẢM BẢO SNAPSHOT TỒN TẠI
    #
    # Chỉ dùng cho attempt cũ bị thiếu snapshot.
    # Nếu snapshot đã tồn tại thì tuyệt đối không tạo lại.
    # ========================================================

    if not student_exam.question_snapshot:

        try:

            paper = build_student_snapshot(exam)

            student_exam.question_snapshot = paper
            student_exam.exam_code = paper["paper_code"]

            student_exam.save(
                update_fields=[
                    "question_snapshot",
                    "exam_code",
                ],
            )

        except Exception as e:

            messages.error(
                request,
                f"Không thể tạo snapshot đề thi: {e}",
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

        student_exam = get_object_or_404(
            StudentExam,
            id=student_exam_id,
            student=request.user,
            is_submitted=False,
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

            result = run_cpp(
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
                "question": None,
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

                result = run_cpp(
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
        is_submitted=False,
    )

    if student_exam.is_terminated:

        return JsonResponse(
            {
                "success": False,
                "message": "Bài thi đã bị dừng.",
            },
            status=409,
        )

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


# ============================================================
# TEACHER EXAM PDF
# ============================================================

@login_required
@user_passes_test(
    is_teacher,
    login_url="home",
)
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

def _get_accessible_teacher_exam(
    request,
    exam_id,
):

    exam = get_object_or_404(
        Exam.objects.select_related(
            "course",
            "offering",
        ),
        id=exam_id,
    )

    profile = request.user.userprofile

    if profile.role == "lecturer":

        if (
            not exam.offering_id
            or not TeachingAssignment.objects.filter(
                course_offering=exam.offering,
                lecturer=profile,
            ).exists()
        ):

            raise Http404(
                "Bạn không được phân công "
                "giảng dạy lớp học phần này."
            )

    return exam


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