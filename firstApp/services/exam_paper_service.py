
"""
Service xử lý nghiệp vụ phiên bản đề thi và phân công mã đề.

Các nguyên tắc:
- Một Exam có nhiều ExamPaper.
- Một sinh viên chỉ có một ExamAssignment cho mỗi Exam.
- Không ghi đè phân công đã tồn tại.
- Không phân công cho sinh viên không thuộc lớp học phần.
- Không phân công phiên bản đề đã ngừng hoạt động.
- Các thao tác ghi dữ liệu phải nằm trong transaction.
"""

import copy
import random

from django.core.exceptions import ValidationError
from django.db import transaction

from firstApp.models import (
    Exam,
    ExamPaper,
    ExamAssignment,
    StudentExam,
    UserProfile,
    Enrollment,
)


# ==========================================================
# PRIVATE HELPERS
# ==========================================================

def _validate_model_instance(instance, model, field_name):
    """Kiểm tra đối tượng đầu vào đúng Model."""

    if not isinstance(instance, model):
        raise ValidationError({
            field_name: f"Dữ liệu phải là đối tượng {model.__name__}."
        })


def _get_locked_exam(exam):
    """
    Lấy Exam có khóa bản ghi trong transaction.

    Giúp hạn chế hai thao tác đồng thời cùng sửa
    dữ liệu của một bài thi.
    """

    _validate_model_instance(exam, Exam, "exam")

    return Exam.objects.select_for_update().get(pk=exam.pk)


def _get_locked_student(student):
    """Lấy UserProfile sinh viên có khóa bản ghi."""

    _validate_model_instance(student, UserProfile, "student")

    locked_student = (
        UserProfile.objects
        .select_for_update()
        .get(pk=student.pk)
    )

    if locked_student.role != "student":
        raise ValidationError({
            "student": "Chỉ được phân công đề cho sinh viên."
        })

    return locked_student


def _get_locked_paper(paper):
    """Lấy ExamPaper có khóa bản ghi."""

    _validate_model_instance(paper, ExamPaper, "paper")

    return (
        ExamPaper.objects
        .select_for_update()
        .select_related("exam")
        .get(pk=paper.pk)
    )


def _validate_paper_for_exam(exam, paper):
    """Kiểm tra phiên bản đề có hợp lệ với bài thi."""

    if paper.exam_id != exam.pk:
        raise ValidationError({
            "paper": "Phiên bản đề không thuộc bài thi này."
        })

    if not paper.is_active:
        raise ValidationError({
            "paper": "Phiên bản đề này đã ngừng sử dụng."
        })


def _validate_student_enrollment(exam, student):
    """
    Kiểm tra sinh viên đã ghi danh hợp lệ vào
    đúng lớp học phần của bài thi.
    """

    if not exam.offering_id:
        raise ValidationError({
            "exam": "Bài thi chưa được gắn với lớp học phần."
        })

    is_enrolled = Enrollment.objects.filter(
        course_offering_id=exam.offering_id,
        student_id=student.pk,
        status="active",
    ).exists()

    if not is_enrolled:
        raise ValidationError({
            "student": (
                "Sinh viên chưa được ghi danh hợp lệ "
                "vào lớp học phần của bài thi."
            )
        })


def _ensure_student_has_no_attempt(exam, student):
    """
    Không phân công lại nếu sinh viên đã có lượt thi.

    StudentExam.student liên kết trực tiếp với User,
    còn ExamAssignment.student liên kết với UserProfile.
    """

    has_attempt = StudentExam.objects.filter(
        exam_id=exam.pk,
        student_id=student.user_id,
    ).exists()

    if has_attempt:
        raise ValidationError({
            "student": (
                "Sinh viên đã có lượt thi. "
                "Không thể thay đổi phân công đề."
            )
        })


def _create_assignment(
    exam,
    paper,
    student,
    assigned_by=None,
    assignment_method="manual",
):
    """
    Tạo một phân công mới.

    Hàm này chỉ được gọi bên trong transaction.atomic().
    """

    # Không ghi đè phân công cũ.
    already_assigned = ExamAssignment.objects.filter(
        exam=exam,
        student=student,
    ).exists()

    if already_assigned:
        raise ValidationError({
            "student": "Sinh viên đã được phân công đề thi này."
        })

    _validate_paper_for_exam(exam, paper)
    _validate_student_enrollment(exam, student)
    _ensure_student_has_no_attempt(exam, student)

    assignment = ExamAssignment(
        exam=exam,
        paper=paper,
        student=student,
        assigned_by=assigned_by,
        assignment_method=assignment_method,
    )

    # Chạy clean(), validate_unique() và kiểm tra constraints.
    assignment.full_clean()

    assignment.save()

    return assignment


# ==========================================================
# 1. CREATE EXAM PAPER
# ==========================================================

@transaction.atomic
def create_exam_paper(
    exam,
    *,
    paper_number,
    paper_code,
    question_data,
    title="",
):
    """
    Tạo một phiên bản đề độc lập.

    Không sao chép từ phiên bản khác.
    """

    exam = _get_locked_exam(exam)

    paper = ExamPaper(
        exam=exam,
        paper_number=paper_number,
        paper_code=paper_code,
        title=title,
        question_data=copy.deepcopy(question_data),
        copied_from=None,
        is_active=True,
    )

    paper.full_clean()
    paper.save()

    return paper

@transaction.atomic
def copy_exam_paper(
    source_paper,
    *,
    paper_number,
    paper_code,
    title=None,
    question_data=None,
):
    """
    Sao chép một phiên bản đề thành phiên bản độc lập.

    Nếu question_data được truyền vào:
        Dùng dữ liệu đã chỉnh sửa từ giao diện.

    Nếu question_data không được truyền vào:
        Sao chép nguyên dữ liệu từ phiên bản nguồn.
    """

    source_paper = _get_locked_paper(source_paper)

    exam = _get_locked_exam(source_paper.exam)

    source_question_data = (
        source_paper.question_data
        if question_data is None
        else question_data
    )

    new_paper = ExamPaper(
        exam=exam,
        paper_number=paper_number,
        paper_code=paper_code,
        title=(
            source_paper.title
            if title is None
            else title
        ),
        question_data=copy.deepcopy(
            source_question_data
        ),
        copied_from=source_paper,
        is_active=True,
    )

    new_paper.full_clean()
    new_paper.save()

    return new_paper
@transaction.atomic
def assign_paper_manual(
    exam,
    paper,
    student,
    assigned_by=None,
):
    """
    Giảng viên phân công một phiên bản đề cho một sinh viên.

    Không cho phép ghi đè phân công đã có.
    """

    exam = _get_locked_exam(exam)
    paper = _get_locked_paper(paper)
    student = _get_locked_student(student)

    return _create_assignment(
        exam=exam,
        paper=paper,
        student=student,
        assigned_by=assigned_by,
        assignment_method="manual",
    )


# ==========================================================
# 4. RANDOM ASSIGNMENT
# ==========================================================

@transaction.atomic
def assign_papers_random(
    exam,
    papers,
    assigned_by=None,
    student_ids=None,
):
    """
    Phân công ngẫu nhiên các phiên bản đề cho sinh viên.

    papers:
        Danh sách đối tượng ExamPaper thuộc cùng một Exam.

    student_ids:
        Danh sách ID UserProfile của sinh viên cần phân công.
        Nếu None, lấy toàn bộ sinh viên đang ghi danh
        hợp lệ vào lớp học phần của Exam.

    Nguyên tắc phân phối:
        - Ngẫu nhiên thứ tự sinh viên.
        - Ngẫu nhiên thứ tự phiên bản đề.
        - Phân phối luân phiên để số lượng giữa các mã đề
          chênh lệch tối đa 1 sinh viên.
        - Không ghi đè phân công đã tồn tại.

    Trả về:
        Danh sách ExamAssignment vừa được tạo.
    """

    exam = _get_locked_exam(exam)

    # ------------------------------------------------------
    # A. Kiểm tra danh sách phiên bản đề
    # ------------------------------------------------------

    if not papers:
        raise ValidationError({
            "papers": "Phải có ít nhất một phiên bản đề."
        })

    paper_ids = set()

    locked_papers = []

    for paper in papers:

        locked_paper = _get_locked_paper(paper)

        _validate_paper_for_exam(exam, locked_paper)

        if locked_paper.pk in paper_ids:
            raise ValidationError({
                "papers": "Danh sách có phiên bản đề bị trùng."
            })

        paper_ids.add(locked_paper.pk)

        locked_papers.append(locked_paper)

    # ------------------------------------------------------
    # B. Lấy sinh viên đã ghi danh hợp lệ
    # ------------------------------------------------------

    if not exam.offering_id:
        raise ValidationError({
            "exam": "Bài thi chưa được gắn với lớp học phần."
        })

    enrollment_queryset = Enrollment.objects.filter(
        course_offering_id=exam.offering_id,
        status="active",
    )

    if student_ids is not None:

        requested_ids = set(student_ids)

        enrolled_ids = set(
            enrollment_queryset.filter(
                student_id__in=requested_ids,
            ).values_list(
                "student_id",
                flat=True,
            )
        )

        invalid_ids = requested_ids - enrolled_ids

        if invalid_ids:
            raise ValidationError({
                "student_ids": (
                    "Có sinh viên không thuộc lớp học phần "
                    f"hoặc không còn ghi danh hợp lệ: "
                    f"{sorted(invalid_ids)}"
                )
            })

        eligible_ids = enrolled_ids

    else:

        eligible_ids = set(
            enrollment_queryset.values_list(
                "student_id",
                flat=True,
            )
        )

    students = list(
        UserProfile.objects
        .select_for_update()
        .filter(
            pk__in=eligible_ids,
            role="student",
        )
        .order_by("pk")
    )

    if not students:
        raise ValidationError({
            "students": "Không có sinh viên hợp lệ để phân công."
        })

    # ------------------------------------------------------
    # C. Loại sinh viên đã có phân công
    # ------------------------------------------------------

    existing_assignment_ids = set(
        ExamAssignment.objects.filter(
            exam=exam,
            student_id__in=eligible_ids,
        ).values_list(
            "student_id",
            flat=True,
        )
    )

    students = [
        student
        for student in students
        if student.pk not in existing_assignment_ids
    ]

    if not students:
        return []

    # ------------------------------------------------------
    # D. Không phân công nếu đã có lượt thi
    # ------------------------------------------------------

    user_ids = [
        student.user_id
        for student in students
    ]

    students_with_attempts = set(
        StudentExam.objects.filter(
            exam=exam,
            student_id__in=user_ids,
        ).values_list(
            "student_id",
            flat=True,
        )
    )

    if students_with_attempts:
        raise ValidationError({
            "students": (
                "Có sinh viên đã có lượt thi. "
                "Không thể phân công đề cho các sinh viên này."
            )
        })

    # ------------------------------------------------------
    # E. Phân phối ngẫu nhiên cân bằng
    # ------------------------------------------------------

    random.shuffle(students)
    random.shuffle(locked_papers)

    assignments = []

    for index, student in enumerate(students):

        paper = locked_papers[
            index % len(locked_papers)
        ]

        assignment = _create_assignment(
            exam=exam,
            paper=paper,
            student=student,
            assigned_by=assigned_by,
            assignment_method="random",
        )

        assignments.append(assignment)

    return assignments
