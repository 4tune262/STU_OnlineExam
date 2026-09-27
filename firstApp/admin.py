from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AcademicTerm,
    Choice,
    Course,
    CourseOffering,
    DragItem,
    Exam,
    QuestionBank,
    SortItem,
    StudentAnswer,
    StudentExam,
    TestCase,
    UserProfile,
)


admin.site.site_header = "Quản trị hệ thống thi trực tuyến STU"
admin.site.site_title = "STU Online Examination"
admin.site.index_title = "Quản lý hệ thống"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "student_id",
        "faculty",
        "display_qr", # Hiển thị hình ảnh QR thu nhỏ trong bảng
    )
    search_fields = ("user__username", "student_id", "qr_token")
    list_filter = ("role", "faculty", "study_year")
    readonly_fields = ("qr_token", "display_qr_large")

    def display_qr(self, obj):
        if obj.qr_code:
            return format_html('<img src="{}" width="50" height="50" />', obj.qr_code.url)
        return "No QR"
    display_qr.short_description = "Mã QR"

    def display_qr_large(self, obj):
        if obj.qr_code:
            return format_html('<img src="{}" width="200" height="200" />', obj.qr_code.url)
        return "No QR"
    display_qr_large.short_description = "Ảnh QR lớn"


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "faculty", "credit", "is_active")
    list_filter = ("faculty", "is_active")
    search_fields = ("code", "name")


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ("academic_year", "semester_number", "start_date", "end_date", "is_active")
    list_filter = ("academic_year", "semester_number", "is_active")
    ordering = ("-academic_year", "semester_number")


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = ("group_code", "course", "term", "session_number", "classroom")
    list_filter = ("term", "course", "session_number")
    search_fields = ("group_code", "course__code", "course__name", "classroom")
    filter_horizontal = ("lecturers", "students")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "lecturers":
            field.queryset = UserProfile.objects.filter(role__in=("lecturer", "admin"))
        elif db_field.name == "students":
            field.queryset = UserProfile.objects.filter(role="student")
        return field


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "offering", "start_time", "end_time", "is_active")
    list_filter = ("course", "offering__term", "is_active")
    search_fields = ("title", "course__code", "offering__group_code")
    autocomplete_fields = ("course", "offering")


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "exam", "question_type", "difficulty", "score")
    list_filter = ("question_type", "difficulty", "course", "exam")
    search_fields = ("title", "chapter")


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("question", "content", "is_correct")
    list_filter = ("is_correct",)


@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ("question", "input_data", "expected_output", "score")


@admin.register(StudentExam)
class StudentExamAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "score", "is_submitted", "started_at")
    list_filter = ("is_submitted", "exam")


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ("student_exam", "question", "score", "is_correct")
    list_filter = ("is_correct",)


# Đăng ký các phần còn lại nếu cần
admin.site.register(DragItem)
admin.site.register(SortItem)