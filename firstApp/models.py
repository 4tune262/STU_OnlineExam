from io import BytesIO
import random
import uuid

import qrcode
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models
# Create your models here.
# =====================================
# USER PROFILE
# =====================================

class UserProfile(models.Model):

    ROLE_CHOICES = (

        ("student", "Sinh viên"),

        ("lecturer", "Giảng viên"),

        ("admin", "Quản trị viên"),

    )

    FACULTY_CHOICES = (

        ("CNTT", "Công nghệ Thông tin"),

        ("QTKD", "Quản trị Kinh doanh"),

        ("TKDH", "Thiết kế Đồ họa"),

        ("CK", "Cơ khí"),

        ("DTVT", "Điện tử Viễn thông"),

        ("XD", "Xây dựng"),

        ("CNTP", "Công nghệ Thực phẩm"),

        ("KT", "Kế toán"),

        ("TCNH", "Tài chính Ngân hàng"),

        ("NNA", "Ngôn ngữ Anh"),

    )

    YEAR_CHOICES = (

        (1, "Năm 1"),

        (2, "Năm 2"),

        (3, "Năm 3"),

        (4, "Năm 4"),

    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    avatar = models.ImageField(
        upload_to="avatar/",
        default="avatar/default.png"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="student"
    )

    student_id = models.CharField(
        max_length=50,
        # unique=True,
        blank=True,
        null=True,
        verbose_name="Mã sinh viên",
    )

    lecturer_id = models.CharField(
        max_length=50,
        # unique=True,
        blank=True,
        null=True,
        verbose_name="Mã giảng viên",
    )

    faculty = models.CharField(
        max_length=20,
        choices=FACULTY_CHOICES,
        blank=True
    )

    major = models.CharField(
        max_length=100,
        blank=True
    )

    class_name = models.CharField(
        max_length=50,
        blank=True
    )

    study_year = models.IntegerField(
        choices=YEAR_CHOICES,
        default=1
    )

    birthday = models.DateField(
        null=True,
        blank=True
    )

    phone = models.CharField(
        max_length=15,
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    qr_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True
    )
    # Thêm trường lưu ảnh QR code
    qr_code = models.ImageField(upload_to="qr_codes/", blank=True, null=True)
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    @property
    def avatar_display_url(self):
        if self.avatar and self.avatar.name and self.avatar.name != "avatar/default.png":
            return self.avatar.url
        return f"{settings.STATIC_URL}images/default-avatar.png"

    def save(self, *args, **kwargs):
        # Tự động tạo ảnh QR chứa chuỗi token khi lưu profile
        qr_image = qrcode.make(str(self.qr_token))
        buffer = BytesIO()
        qr_image.save(buffer, format="PNG")
        file_name = f"qr_{self.qr_token}.png"
        self.qr_code.save(file_name, File(buffer), save=False)
        super().save(*args, **kwargs)
    def __str__(self):

        return f"{self.user.username} ({self.role})"



# class Course(models.Model):
#         name = models.CharField(max_length=100)  # Tên môn học (VD: Lập trình Java)
#         code = models.CharField(max_length=20, unique=True)  # Mã môn học
#         description = models.TextField(blank=True)
#         faculty = models.CharField(max_length=20, choices=UserProfile.FACULTY_CHOICES)
#
#         def __str__(self):
#             return f"{self.name} ({self.code})"
# ===========================================
# COURSE
# ===========================================

class Course(models.Model):

    FACULTY_CHOICES = UserProfile.FACULTY_CHOICES

    code = models.CharField(
        max_length=20,
        unique=True
    )

    name = models.CharField(
        max_length=200
    )

    faculty = models.CharField(
        max_length=20,
        choices=FACULTY_CHOICES
    )

    description = models.TextField(
        blank=True
    )

    credit = models.IntegerField(
        default=3
    )

    semester = models.IntegerField(
        default=1
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):

        return f"{self.code} - {self.name}"


class AcademicTerm(models.Model):
    academic_year = models.CharField(max_length=9, help_text="Ví dụ: 2026-2027")
    semester_number = models.PositiveSmallIntegerField(
        choices=((1, "Học kỳ 1"), (2, "Học kỳ 2"), (3, "Học kỳ hè"))
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-academic_year", "semester_number")
        constraints = [
            models.UniqueConstraint(
                fields=("academic_year", "semester_number"),
                name="unique_academic_year_semester",
            )
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Ngày kết thúc phải sau ngày bắt đầu."})

    def __str__(self):
        return f"{self.academic_year} - Học kỳ {self.semester_number}"

# ===========================================
# COURSE OFFERING
# ===========================================

class CourseOffering(models.Model):
    """
    Một môn học được mở trong một học kỳ cụ thể.

    Ví dụ:
    Môn: Lập trình C++
    Năm học: 2026-2027
    Học kỳ: 1
    Nhóm: NMLT-N1
    Ca: 2
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        related_name="offerings",
        verbose_name="Môn học",
    )

    term = models.ForeignKey(
        AcademicTerm,
        on_delete=models.PROTECT,
        related_name="course_offerings",
        verbose_name="Học kỳ",
    )

    group_code = models.CharField(
        max_length=40,
        verbose_name="Mã nhóm",
        help_text="Ví dụ: NMLT-N1",
    )

    session_number = models.PositiveSmallIntegerField(
        verbose_name="Ca học/thi",
    )

    classroom = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Phòng học",
    )

    class Meta:
        ordering = (
            "term",
            "course__code",
            "group_code",
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "term",
                    "course",
                    "group_code",
                ),
                name="unique_course_group_per_term",
            )
        ]

        verbose_name = "Lớp học phần"
        verbose_name_plural = "Các lớp học phần"

    def __str__(self):
        return (
            f"{self.course.code} - "
            f"{self.term} - "
            f"{self.group_code} "
            f"(Ca {self.session_number})"
        )
# ===========================================
# TEACHING ASSIGNMENT
# ===========================================

class TeachingAssignment(models.Model):
    """
    Phân công giảng viên cho một lớp học phần.

    Một lớp học phần có thể có nhiều giảng viên.
    Một giảng viên có thể dạy nhiều lớp học phần.
    """

    ROLE_CHOICES = (
        ("main", "Giảng viên chính"),
        ("assistant", "Giảng viên phụ trách"),
    )

    course_offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="teaching_assignments",
        verbose_name="Lớp học phần",
    )

    lecturer = models.ForeignKey(
        UserProfile,
        on_delete=models.PROTECT,
        related_name="teaching_assignments",
        limit_choices_to={
            "role__in": ("lecturer", "admin")
        },
        verbose_name="Giảng viên",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="main",
        verbose_name="Vai trò",
    )

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày phân công",
    )

    note = models.TextField(
        blank=True,
        default="",
        verbose_name="Ghi chú",
    )

    class Meta:
        ordering = ("-assigned_at",)

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "course_offering",
                    "lecturer",
                ),
                name="unique_lecturer_course_offering",
            )
        ]

        verbose_name = "Phân công giảng viên"
        verbose_name_plural = "Phân công giảng viên"

    def __str__(self):
        return (
            f"{self.lecturer} - "
            f"{self.course_offering}"
        )
# ===========================================
# ENROLLMENT
# ===========================================

class Enrollment(models.Model):
    """
    Sinh viên được ghi danh vào một lớp học phần.

    Sinh viên của cùng một lớp học phần có thể
    đến từ nhiều lớp hành chính khác nhau.
    """

    STATUS_CHOICES = (
        ("active", "Đang học"),
        ("completed", "Đã hoàn thành"),
        ("dropped", "Đã thôi học"),
    )

    course_offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="Lớp học phần",
    )

    student = models.ForeignKey(
        UserProfile,
        on_delete=models.PROTECT,
        related_name="course_enrollments",
        limit_choices_to={
            "role": "student"
        },
        verbose_name="Sinh viên",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Trạng thái",
    )

    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày ghi danh",
    )

    note = models.TextField(
        blank=True,
        default="",
        verbose_name="Ghi chú",
    )

    class Meta:
        ordering = ("student",)

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "course_offering",
                    "student",
                ),
                name="unique_student_course_offering",
            )
        ]

        verbose_name = "Đăng ký môn học"
        verbose_name_plural = "Danh sách sinh viên môn học"

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.course_offering}"
        )

# ==========================================
# EXAM - BÀI THI
# ==========================================

class Exam(models.Model):

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="exams",
        verbose_name="Môn học",
    )

    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.SET_NULL,
        related_name="exams",
        null=True,
        blank=True,
        verbose_name="Lớp / Nhóm",
        help_text="Nhóm môn học được phép dự thi.",
    )

    title = models.CharField(
        max_length=200,
        verbose_name="Tên bài thi",
    )

    duration_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Thời gian làm bài (phút)",
    )

    start_time = models.DateTimeField(
        verbose_name="Thời gian bắt đầu",
    )

    end_time = models.DateTimeField(
        verbose_name="Thời gian kết thúc",
    )

    number_of_papers = models.PositiveIntegerField(
        default=1,
        verbose_name="Số mã đề",
        help_text="Ví dụ: 5 sẽ tạo 5 mã đề.",
    )

    question_data = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Dữ liệu câu hỏi",
    )

    paper_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Danh sách mã đề",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Cho phép thi",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày tạo",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Cập nhật lần cuối",
    )

    def clean(self):
        super().clean()

        if self.offering_id and self.course_id:
            if self.offering.course_id != self.course_id:
                raise ValidationError({
                    "offering": (
                        "Lớp / nhóm phải thuộc cùng môn học "
                        "với bài thi."
                    )
                })

        if self.end_time and self.start_time:
            if self.end_time <= self.start_time:
                raise ValidationError({
                    "end_time": (
                        "Thời gian kết thúc phải sau "
                        "thời gian bắt đầu."
                    )
                })

        if self.number_of_papers < 1:
            raise ValidationError({
                "number_of_papers": (
                    "Số mã đề phải lớn hơn hoặc bằng 1."
                )
            })

    def __str__(self):
        return self.title




# ==========================================
# EXAM RESULT - KẾT QUẢ SINH VIÊN
# ==========================================

class ExamResult(models.Model):

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_results",
        verbose_name="Sinh viên",
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="Bài thi",
    )

    paper_code = models.CharField(
        max_length=50,
        verbose_name="Mã đề",
    )

    answers = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Câu trả lời",
    )

    score = models.FloatField(
        default=0,
        verbose_name="Điểm",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Bắt đầu thi",
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Nộp bài",
    )

    is_submitted = models.BooleanField(
        default=False,
        verbose_name="Đã nộp",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày tạo",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Cập nhật",
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Kết quả bài thi"
        verbose_name_plural = "Kết quả bài thi"

    def __str__(self):
        return (
            f"{self.student.username} - "
            f"{self.exam.title} - "
            f"Mã đề {self.paper_code}"
        )


class ExamSession(models.Model):

        STATUS_CHOICES = [
            ("scheduled", "Đã lên lịch"),
            ("ongoing", "Đang diễn ra"),
            ("completed", "Đã hoàn thành"),
            ("cancelled", "Đã hủy"),
        ]

        exam = models.ForeignKey(
            Exam,
            on_delete=models.PROTECT,
            related_name="sessions",
            verbose_name="Kỳ thi",
        )

        offering = models.ForeignKey(
            CourseOffering,
            on_delete=models.PROTECT,
            related_name="exam_sessions",
            verbose_name="Lớp học phần",
        )

        room = models.CharField(
            max_length=100,
            verbose_name="Phòng thi",
        )
        machine_count = models.PositiveIntegerField(
            default=26,
            verbose_name="Số máy trong phòng",
            help_text="Tổng số máy tính có trong phòng thi, ví dụ 26.",
        )
        start_time = models.DateTimeField(
            verbose_name="Thời gian bắt đầu",
        )

        end_time = models.DateTimeField(
            verbose_name="Thời gian kết thúc",
        )

        status = models.CharField(
            max_length=20,
            choices=STATUS_CHOICES,
            default="scheduled",
            verbose_name="Trạng thái",
        )

        note = models.TextField(
            blank=True,
            verbose_name="Ghi chú",
        )

        created_at = models.DateTimeField(
            auto_now_add=True,
            verbose_name="Ngày tạo",
        )

        updated_at = models.DateTimeField(
            auto_now=True,
            verbose_name="Cập nhật lần cuối",
        )

        class Meta:
            ordering = [
                "-start_time",
            ]

            verbose_name = "Ca thi"
            verbose_name_plural = "Các ca thi"

        def clean(self):
            super().clean()

            if self.start_time and self.end_time:
                if self.end_time <= self.start_time:
                    raise ValidationError({
                        "end_time": "Thời gian kết thúc phải sau thời gian bắt đầu."
                    })

            if self.exam_id and self.offering_id:
                if (
                        self.exam.offering_id
                        and self.exam.offering_id != self.offering_id
                ):
                    raise ValidationError({
                        "offering": (
                            "Lớp học phần của ca thi phải phù hợp "
                            "với lớp học phần của kỳ thi."
                        )
                    })

                if (
                        self.exam.course_id
                        and self.offering.course_id != self.exam.course_id
                ):
                    raise ValidationError({
                        "offering": (
                            "Lớp học phần phải thuộc cùng môn học "
                            "với kỳ thi."
                        )
                    })

        def __str__(self):
            return (
                f"{self.exam.title} - "
                f"{self.offering.group_code} - "
                f"{self.room}"
            )
class ExamComputer(models.Model):

    STATUS_CHOICES = [
        ("available", "Đang trống"),
        ("assigned", "Đã gán sinh viên"),
        ("absent", "Vắng"),
        ("locked", "Đã khóa"),
    ]

    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="computers",
        verbose_name="Ca thi",
    )

    computer_number = models.PositiveIntegerField(
        verbose_name="Số máy",
        help_text="Ví dụ: 1, 2, 3,... 26",
    )

    student = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_computers",
        verbose_name="Sinh viên",
        limit_choices_to={"role": "student"},
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="available",
        verbose_name="Trạng thái",
    )

    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời gian gán",
    )

    camera_last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Heartbeat camera cuối",
    )

    presence_last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Phát hiện sinh viên cuối",
    )

    absence_reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời gian mở lại máy",
    )

    absence_reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reopened_exam_computers",
        verbose_name="Người xác nhận mở lại",
    )

    note = models.TextField(
        blank=True,
        verbose_name="Ghi chú",
    )

    class Meta:
        ordering = [
            "exam_session",
            "computer_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "exam_session",
                    "computer_number",
                ],
                name="unique_computer_per_exam_session",
            )
        ]

        verbose_name = "Máy thi"
        verbose_name_plural = "Các máy thi"

    def __str__(self):
        student_name = (
            self.student.user.get_full_name()
            if self.student
            else "Chưa gán"
        )

        return (
            f"PC{self.computer_number:02d} - "
            f"{student_name}"
        )
# ===========================================
# QUESTION BANK
# ===========================================
class QuestionBank(models.Model):

    QUESTION_TYPES = (

        ("MCQ", "Multiple Choice"),

        ("DRAG", "Drag Code"),

        ("SORT", "Sort Code"),

        ("CODE", "Coding"),

    )

    LEVELS = (

        ("Easy", "Easy"),

        ("Medium", "Medium"),

        ("Hard", "Hard"),

    )

    course = models.ForeignKey(

        Course,

        on_delete=models.CASCADE,

        related_name="question_bank"

    )

    chapter = models.CharField(
        max_length=100
    )

    title = models.TextField()

    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES
    )

    difficulty = models.CharField(
        max_length=20,
        choices=LEVELS
    )

    score = models.FloatField(
        default=1
    )

    starter_code = models.TextField(
        blank=True
    )

    function_name = models.CharField(
        max_length=100,
        blank=True
    )

    language = models.CharField(
        max_length=20,
        default="cpp"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    # NEW
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="question_pool",
        null=True,
        blank=True
    )
    # Bổ sung trường này vào model QuestionBank để render mã nguồn điền khuyết
    code_template = models.TextField(
        blank=True,
        null=True,
        help_text="VD: int sum(int a) { <span class='blank-slot' data-index='1'></span> return a; }"
    )

    code_snippet = models.TextField(
        blank=True,
        null=True,
        help_text="Dành cho đoạn code minh họa của câu MCQ hoặc chung"
    )
    def __str__(self):

        return self.title

# ==========================================
# MCQ CHOICE
# ==========================================

class Choice(models.Model):

    question = models.ForeignKey(
        QuestionBank,
        on_delete=models.CASCADE,
        related_name="choices"
    )

    content = models.CharField(
        max_length=500
    )

    is_correct = models.BooleanField(
        default=False
    )

    def __str__(self):

        return self.content

# ==========================================
# DRAG CODE ITEM
# ==========================================

class DragItem(models.Model):

    question = models.ForeignKey(

        QuestionBank,

        on_delete=models.CASCADE,

        related_name="drag_items"

    )

    code = models.TextField()

    correct_order = models.IntegerField()

    def __str__(self):

        return self.code

# ==========================================
# SORT ITEM
# ==========================================

class SortItem(models.Model):

    question = models.ForeignKey(

        QuestionBank,

        on_delete=models.CASCADE,

        related_name="sort_items"

    )

    code = models.TextField()

    correct_order = models.IntegerField()

    def __str__(self):

        return self.code
# ==========================================
# TEST CASE
# ==========================================

class TestCase(models.Model):

    question = models.ForeignKey(

        QuestionBank,

        on_delete=models.CASCADE,

        related_name="test_cases"

    )

    input_data = models.TextField()

    expected_output = models.TextField()

    score = models.FloatField(default=1)

    def __str__(self):

        return self.expected_output

# ==========================================
# STUDENT EXAM
# ==========================================

class StudentExam(models.Model):

    student = models.ForeignKey(

        User,

        on_delete=models.CASCADE

    )

    exam = models.ForeignKey(

        Exam,

        on_delete=models.CASCADE

    )

    exam_computer = models.ForeignKey(
        ExamComputer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_exams",
        verbose_name="Máy thi được phân công",
    )

    exam_code = models.CharField(max_length=50, blank=True, null=True)  # Lưu mã đề cố định
    question_snapshot = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Snapshot đề thi"
    )
    question_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Danh sách câu hỏi của lượt thi",
    )
    started_at = models.DateTimeField(

        auto_now_add=True

    )

    finished_at = models.DateTimeField(

        null=True,

        blank=True

    )

    score = models.FloatField(

        default=0

    )

    is_submitted = models.BooleanField(

        default=False

    )

    is_terminated = models.BooleanField(default=False, verbose_name="Bị dừng do vi phạm")

    termination_reason = models.CharField(max_length=200, blank=True, default="")

    warning_count = models.PositiveSmallIntegerField(default=0, verbose_name="Số lần cảnh báo")

    active_gesture = models.CharField(max_length=30, blank=True, default="")

    gesture_started_at = models.DateTimeField(null=True, blank=True)

    gesture_warned = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.exam_code and self.exam:
            paper_codes = self.exam.paper_codes or []
            if paper_codes and self.exam_computer_id:
                computer_number = self.exam_computer.computer_number
                self.exam_code = paper_codes[(computer_number - 1) % len(paper_codes)]
            else:
                self.exam_code = random.choice(paper_codes) if paper_codes else f"DE{self.exam_id:04d}"
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.student.username} - {self.exam.title} ({self.exam_code})"

# ==========================================
# STUDENT ANSWER
# ==========================================

class StudentAnswer(models.Model):

    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    # ------------------------------------------------------
    # BACKWARD COMPATIBILITY
    # ------------------------------------------------------
    # Giữ lại QuestionBank tạm thời để không phá dữ liệu cũ.
    # Sau khi workflow mới chạy ổn định sẽ xóa field này.
    # question = models.ForeignKey(
    #     QuestionBank,
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    # )

    # ------------------------------------------------------
    # KIẾN TRÚC MỚI
    # ------------------------------------------------------
    # Index của câu hỏi trong StudentExam.question_snapshot.
    question_index = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="STT câu hỏi",
    )

    # MCQ / DRAG / SORT / CODE
    question_type = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Loại câu hỏi",
    )

    # ------------------------------------------------------
    # CÂU TRẢ LỜI
    # ------------------------------------------------------

    answer_text = models.TextField(
        blank=True
    )

    answer_payload = models.JSONField(
        default=dict,
        blank=True
    )

    # ------------------------------------------------------
    # KẾT QUẢ CHẤM
    # ------------------------------------------------------

    score = models.FloatField(
        default=0
    )

    is_correct = models.BooleanField(
        default=False
    )

    def __str__(self):
        return (
            f"{self.student_exam} - "
            f"Câu {self.question_index or '?'}"
        )

class ProctorEvent(models.Model):
    EVENT_TYPES = (
        ("looking_left", "Quay mặt sang trái"),
        ("looking_right", "Quay mặt sang phải"),
        ("looking_down", "Cúi mặt"),
    )

    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="proctor_events",
    )
    exam_computer = models.ForeignKey(
        ExamComputer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proctor_events",
    )
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    confidence = models.FloatField(null=True, blank=True)
    duration_seconds = models.PositiveSmallIntegerField(default=0)
    evidence_image = models.ImageField(upload_to="proctor_evidence/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_proctor_events",
    )
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.student_exam}"

