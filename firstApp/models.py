from io import BytesIO

import qrcode
from django.core.files import File
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import uuid
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
        max_length=20,
        blank=True
    )

    lecturer_id = models.CharField(
        max_length=20,
        blank=True
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


class CourseOffering(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="offerings",
    )
    term = models.ForeignKey(
        AcademicTerm,
        on_delete=models.PROTECT,
        related_name="course_offerings",
    )
    group_code = models.CharField(max_length=40, help_text="Mã nhóm/ca, ví dụ: NMLT-N1")
    session_number = models.PositiveSmallIntegerField(help_text="Ca học/thi")
    classroom = models.CharField(max_length=100, blank=True)
    lecturers = models.ManyToManyField(
        UserProfile,
        related_name="teaching_offerings",
        limit_choices_to={"role__in": ("lecturer", "admin")},
        blank=True,
    )
    students = models.ManyToManyField(
        UserProfile,
        related_name="course_offerings",
        limit_choices_to={"role": "student"},
        blank=True,
    )

    class Meta:
        ordering = ("term", "course__code", "group_code")
        constraints = [
            models.UniqueConstraint(
                fields=("term", "course", "group_code"),
                name="unique_course_group_per_term",
            )
        ]

    def __str__(self):
        return (
            f"{self.course.code} - {self.term} - "
            f"{self.group_code} (Ca {self.session_number})"
        )


# class Exam(models.Model):
#         course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
#         title = models.CharField(max_length=200)  # Tên bài thi (VD: Giữa kỳ môn Java)
#         duration_minutes = models.IntegerField(default=45)  # Thời gian làm bài (phút)
#         is_active = models.BooleanField(default=True)  # Trạng thái mở thi hay không
#
#         def __str__(self):
#             return f"{self.title} - {self.course.name}"

# ===========================================
# EXAM CONFIG
# ===========================================

class Exam(models.Model):

    course = models.ForeignKey(

        Course,

        on_delete=models.CASCADE,

        related_name="exams"

    )
    offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.SET_NULL,
        related_name="exams",
        null=True,
        blank=True,
        help_text="Nhóm môn học/ca được phép dự thi; để trống cho bài thi cũ.",
    )

    title = models.CharField(
        max_length=200
    )
    # BỔ SUNG TRƯỜNG MÃ ĐỀ
    code = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Mã đề"
    )
    duration_minutes = models.IntegerField(
        default=60
    )

    easy_mcq = models.IntegerField(default=3)

    medium_mcq = models.IntegerField(default=0)

    hard_mcq = models.IntegerField(default=0)

    easy_drag = models.IntegerField(default=0)

    medium_drag = models.IntegerField(default=3)

    hard_drag = models.IntegerField(default=0)

    easy_sort = models.IntegerField(default=0)

    medium_sort = models.IntegerField(default=2)

    hard_sort = models.IntegerField(default=0)

    easy_code = models.IntegerField(default=0)

    medium_code = models.IntegerField(default=0)

    hard_code = models.IntegerField(default=2)

    start_time = models.DateTimeField()

    end_time = models.DateTimeField()

    is_active = models.BooleanField(
        default=True
    )

    def clean(self):
        super().clean()
        if self.offering_id and self.course_id and self.offering.course_id != self.course_id:
            raise ValidationError(
                {"offering": "Nhóm môn học phải thuộc cùng môn với kỳ thi."}
            )

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"CPP_{random.randint(1000, 9999)}"
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.title} (Mã đề: {self.code})"
# ===========================================
# QUESTION BANK
# ===========================================
import random
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
    exam_code = models.CharField(max_length=50, blank=True, null=True)  # Lưu mã đề cố định
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

    def save(self, *args, **kwargs):
        if not self.exam_code and self.exam:
            self.exam_code = self.exam.code
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

    question = models.ForeignKey(

        QuestionBank,

        on_delete=models.CASCADE

    )

    answer_text = models.TextField(

        blank=True

    )

    score = models.FloatField(

        default=0

    )

    is_correct = models.BooleanField(

        default=False

    )

    def __str__(self):

        return self.question.title

