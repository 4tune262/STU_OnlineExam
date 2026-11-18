

from django.contrib import admin
from django.contrib import messages
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html

from .models import (
    AcademicTerm,
    Course,
    CourseOffering,
    Enrollment,
    Exam,
    ExamSession,
    ExamComputer,
    ProctorEvent,
    StudentAnswer,
    StudentExam,
    TeachingAssignment,
    UserProfile,
)

from .excel_import import (
    import_students_from_excel,
    import_lecturers_from_excel,
)


admin.site.site_header = "Quản trị hệ thống thi trực tuyến STU"
admin.site.site_title = "STU Online Examination"
admin.site.index_title = "Quản lý hệ thống"


# @admin.register(UserProfile)
# class UserProfileAdmin(admin.ModelAdmin):
#     change_list_template = "admin/firstApp/userprofile/change_list.html"
#     list_display = (
#         "user",
#         "role",
#         "student_id",
#         "lecturer_id",
#         "faculty",
#         "display_qr",
#     )
#
#     search_fields = (
#         "user__username",
#         "user__first_name",
#         "student_id",
#         "lecturer_id",
#         "qr_token",
#     )
#
#     list_filter = (
#         "role",
#         "faculty",
#         "study_year",
#     )
#
#     readonly_fields = (
#         "qr_token",
#         "display_qr_large",
#     )
#
#     # ========================================================
#     # URL CUSTOM CHO IMPORT EXCEL
#     # ========================================================
#
#     def get_urls(self):
#
#         urls = super().get_urls()
#
#         custom_urls = [
#             path(
#                 "import-excel/",
#                 self.admin_site.admin_view(
#                     self.import_excel_view
#                 ),
#                 name="firstApp_userprofile_import_excel",
#             ),
#         ]
#
#         return custom_urls + urls
#
#     # ========================================================
#     # VIEW IMPORT EXCEL
#     # ========================================================
#
#     def import_excel_view(self, request):
#
#         if request.method == "POST":
#
#             import_type = request.POST.get(
#                 "import_type"
#             )
#
#             excel_file = request.FILES.get(
#                 "excel_file"
#             )
#
#             # ------------------------------------------------
#             # Kiểm tra file
#             # ------------------------------------------------
#
#             if not excel_file:
#
#                 self.message_user(
#                     request,
#                     "Vui lòng chọn file Excel.",
#                     level=messages.ERROR,
#                 )
#
#                 return TemplateResponse(
#                     request,
#                     "admin/firstApp/userprofile/import_excel.html",
#                 )
#
#             # ------------------------------------------------
#             # Kiểm tra định dạng
#             # ------------------------------------------------
#
#             if not excel_file.name.lower().endswith(".xlsx"):
#
#                 self.message_user(
#                     request,
#                     "Chỉ hỗ trợ file Excel có định dạng .xlsx.",
#                     level=messages.ERROR,
#                 )
#
#                 return TemplateResponse(
#                     request,
#                     "admin/firstApp/userprofile/import_excel.html",
#                 )
#
#             # ------------------------------------------------
#             # Import sinh viên
#             # ------------------------------------------------
#
#             if import_type == "students":
#
#                 try:
#
#                     result = import_students_from_excel(
#                         excel_file
#                     )
#
#                     self.message_user(
#                         request,
#                         (
#                             f"Import sinh viên hoàn tất. "
#                             f"Tạo mới: {result['created']}; "
#                             f"Cập nhật: {result['updated']}; "
#                             f"Lỗi: {len(result['errors'])}."
#                         ),
#                         level=(
#                             messages.ERROR
#                             if result["errors"]
#                             else messages.SUCCESS
#                         ),
#                     )
#
#                     # Hiển thị chi tiết lỗi
#                     for error in result["errors"]:
#
#                         self.message_user(
#                             request,
#                             error,
#                             level=messages.ERROR,
#                         )
#
#                 except Exception as exc:
#
#                     self.message_user(
#                         request,
#                         f"Import sinh viên thất bại: {exc}",
#                         level=messages.ERROR,
#                     )
#
#             # ------------------------------------------------
#             # Import giảng viên
#             # ------------------------------------------------
#
#             elif import_type == "lecturers":
#
#                 try:
#
#                     result = import_lecturers_from_excel(
#                         excel_file
#                     )
#
#                     self.message_user(
#                         request,
#                         (
#                             f"Import giảng viên hoàn tất. "
#                             f"Tạo mới: {result['created']}; "
#                             f"Cập nhật: {result['updated']}; "
#                             f"Lỗi: {len(result['errors'])}."
#                         ),
#                         level=(
#                             messages.ERROR
#                             if result["errors"]
#                             else messages.SUCCESS
#                         ),
#                     )
#
#                     # Hiển thị chi tiết lỗi
#                     for error in result["errors"]:
#
#                         self.message_user(
#                             request,
#                             error,
#                             level=messages.ERROR,
#                         )
#
#                 except Exception as exc:
#
#                     self.message_user(
#                         request,
#                         f"Import giảng viên thất bại: {exc}",
#                         level=messages.ERROR,
#                     )
#
#             else:
#
#                 self.message_user(
#                     request,
#                     "Loại import không hợp lệ.",
#                     level=messages.ERROR,
#                 )
#
#         # ----------------------------------------------------
#         # Hiển thị trang
#         # ----------------------------------------------------
#
#         context = {
#             **self.admin_site.each_context(request),
#             "title": "Import dữ liệu từ Excel",
#         }
#
#         return TemplateResponse(
#             request,
#             "admin/firstApp/userprofile/import_excel.html",
#             context,
#         )
#
#     # ========================================================
#     # QR CODE
#     # ========================================================
#
#     def display_qr(self, obj):
#
#         if obj.qr_code:
#
#             return format_html(
#                 '<img src="{}" width="50" height="50" />',
#                 obj.qr_code.url,
#             )
#
#         return "No QR"
#
#     display_qr.short_description = "Mã QR"
#
#     # ========================================================
#     # QR CODE LỚN
#     # ========================================================
#
#     def display_qr_large(self, obj):
#
#         if obj.qr_code:
#
#             return format_html(
#                 '<img src="{}" width="200" height="200" />',
#                 obj.qr_code.url,
#             )
#
#         return "No QR"
#
#     display_qr_large.short_description = "Ảnh QR lớn"

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    change_list_template = (
        "admin/firstApp/userprofile/change_list.html"
    )

    list_display = (
        "user",
        "role",
        "student_id",
        "lecturer_id",
        "faculty",
        "display_qr",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "student_id",
        "lecturer_id",
        "qr_token",
    )

    list_filter = (
        "role",
        "faculty",
        "study_year",
    )

    readonly_fields = (
        "qr_token",
        "display_qr_large",
    )

    # ========================================================
    # URL CUSTOM CHO IMPORT EXCEL
    # ========================================================

    def get_urls(self):

        urls = super().get_urls()

        custom_urls = [
            path(
                "import-excel/",
                self.admin_site.admin_view(
                    self.import_excel_view
                ),
                name="firstApp_userprofile_import_excel",
            ),
        ]

        return custom_urls + urls

    # ========================================================
    # VIEW IMPORT EXCEL
    # ========================================================

    def import_excel_view(self, request):

        # ====================================================
        # POST
        # ====================================================

        if request.method == "POST":

            import_type = request.POST.get(
                "import_type"
            )

            offering_id = request.POST.get(
                "course_offering"
            )

            excel_file = request.FILES.get(
                "excel_file"
            )

            # =================================================
            # 1. KIỂM TRA LỚP HỌC PHẦN
            # =================================================

            if not offering_id:

                self.message_user(
                    request,
                    "Vui lòng chọn lớp học phần.",
                    level=messages.ERROR,
                )

                return self._render_import_page(
                    request
                )

            # =================================================
            # 2. LẤY LỚP HỌC PHẦN
            # =================================================

            try:

                course_offering = (
                    CourseOffering.objects
                    .select_related(
                        "course",
                        "term",
                    )
                    .get(
                        pk=offering_id
                    )
                )

            except CourseOffering.DoesNotExist:

                self.message_user(
                    request,
                    "Lớp học phần không tồn tại.",
                    level=messages.ERROR,
                )

                return self._render_import_page(
                    request
                )

            # =================================================
            # 3. KIỂM TRA FILE
            # =================================================

            if not excel_file:

                self.message_user(
                    request,
                    "Vui lòng chọn file Excel.",
                    level=messages.ERROR,
                )

                return self._render_import_page(
                    request
                )

            if not excel_file.name.lower().endswith(
                ".xlsx"
            ):

                self.message_user(
                    request,
                    "Chỉ chấp nhận file Excel có định dạng .xlsx.",
                    level=messages.ERROR,
                )

                return self._render_import_page(
                    request
                )

            # =================================================
            # 4. IMPORT SINH VIÊN
            # =================================================

            if import_type == "students":

                try:

                    result = (
                        import_students_from_excel(
                            excel_file,
                            course_offering,
                        )
                    )

                    self.message_user(
                        request,
                        (
                            f"Import sinh viên hoàn tất cho "
                            f"{course_offering.course.code} - "
                            f"{course_offering.group_code}. "
                            f"Tạo mới: {result['created']}; "
                            f"Cập nhật: {result['updated']}; "
                            f"Ghi danh mới: {result['enrolled']}; "
                            f"Đã có trong lớp: "
                            f"{result['already_enrolled']}; "
                            f"Lỗi: {len(result['errors'])}."
                        ),
                        level=(
                            messages.ERROR
                            if result["errors"]
                            else messages.SUCCESS
                        ),
                    )

                    # -----------------------------------------
                    # CHI TIẾT LỖI
                    # -----------------------------------------

                    for error in result["errors"]:

                        self.message_user(
                            request,
                            error,
                            level=messages.ERROR,
                        )

                except Exception as exc:

                    self.message_user(
                        request,
                        (
                            "Import sinh viên thất bại: "
                            f"{exc}"
                        ),
                        level=messages.ERROR,
                    )

            # =================================================
            # 5. IMPORT GIẢNG VIÊN
            # =================================================

            elif import_type == "lecturers":

                try:

                    result = (
                        import_lecturers_from_excel(
                            excel_file,
                            course_offering,
                        )
                    )

                    self.message_user(
                        request,
                        (
                            f"Import giảng viên hoàn tất cho "
                            f"{course_offering.course.code} - "
                            f"{course_offering.group_code}. "
                            f"Tạo mới: {result['created']}; "
                            f"Cập nhật: {result['updated']}; "
                            f"Phân công mới: "
                            f"{result['assigned']}; "
                            f"Đã phân công: "
                            f"{result['already_assigned']}; "
                            f"Lỗi: {len(result['errors'])}."
                        ),
                        level=(
                            messages.ERROR
                            if result["errors"]
                            else messages.SUCCESS
                        ),
                    )

                    # -----------------------------------------
                    # CHI TIẾT LỖI
                    # -----------------------------------------

                    for error in result["errors"]:

                        self.message_user(
                            request,
                            error,
                            level=messages.ERROR,
                        )

                except Exception as exc:

                    self.message_user(
                        request,
                        (
                            "Import giảng viên thất bại: "
                            f"{exc}"
                        ),
                        level=messages.ERROR,
                    )

            # =================================================
            # 6. IMPORT TYPE KHÔNG HỢP LỆ
            # =================================================

            else:

                self.message_user(
                    request,
                    "Loại import không hợp lệ.",
                    level=messages.ERROR,
                )

        # ====================================================
        # GET
        # ====================================================

        return self._render_import_page(
            request
        )

    # ========================================================
    # RENDER IMPORT PAGE
    # ========================================================

    def _render_import_page(self, request):

        offerings = (
            CourseOffering.objects
            .select_related(
                "course",
                "term",
            )
            .order_by(
                "course__code",
                "group_code",
                "session_number",
            )
        )

        context = {
            **self.admin_site.each_context(request),

            "title": "Import dữ liệu từ Excel",

            "offerings": offerings,
        }

        return TemplateResponse(
            request,
            "admin/firstApp/userprofile/import_excel.html",
            context,
        )

    # ========================================================
    # QR CODE
    # ========================================================

    def display_qr(self, obj):

        if obj.qr_code:

            return format_html(
                '<img src="{}" width="50" height="50" />',
                obj.qr_code.url,
            )

        return "No QR"

    display_qr.short_description = "Mã QR"

    # ========================================================
    # QR CODE LỚN
    # ========================================================

    def display_qr_large(self, obj):

        if obj.qr_code:

            return format_html(
                '<img src="{}" width="200" height="200" />',
                obj.qr_code.url,
            )

        return "No QR"

    display_qr_large.short_description = "Ảnh QR lớn"

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "faculty", "credit", "is_active")
    list_filter = ("faculty", "is_active")
    search_fields = ("code", "name")


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = (
        "academic_year",
        "semester_number",
        "start_date",
        "end_date",
        "is_active",
    )

    list_filter = (
        "academic_year",
        "semester_number",
        "is_active",
    )

    search_fields = (
        "academic_year",
    )

    ordering = (
        "-academic_year",
        "semester_number",
    )

# @admin.register(CourseOffering)
# class CourseOfferingAdmin(admin.ModelAdmin):
#     list_display = ("group_code", "course", "term", "session_number", "classroom")
#     list_filter = ("term", "course", "session_number")
#     search_fields = ("group_code", "course__code", "course__name", "classroom")
#     filter_horizontal = ("lecturers", "students")
#
#     def formfield_for_manytomany(self, db_field, request, **kwargs):
#         field = super().formfield_for_manytomany(db_field, request, **kwargs)
#         if db_field.name == "lecturers":
#             field.queryset = UserProfile.objects.filter(role__in=("lecturer", "admin"))
#         elif db_field.name == "students":
#             field.queryset = UserProfile.objects.filter(role="student")
#         return field


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "course",
        "offering",
        "duration_minutes",
        "number_of_papers",
        "start_time",
        "end_time",
        "is_active",
    )

    list_filter = (
        "course",
        "offering__term",
        "is_active",
    )

    search_fields = (
        "title",
        "course__code",
        "course__name",
        "offering__group_code",
    )

    autocomplete_fields = (
        "course",
        "offering",
    )

    change_form_template = (
        "admin/firstApp/exam/exam_builder.html"
    )

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()

        custom_urls = [
            # Tạo bài thi mới
            path(
                "builder/",
                self.admin_site.admin_view(
                    self.builder_view
                ),
                name="firstApp_exam_builder_create",
            ),

            # Chỉnh sửa bài thi
            path(
                "<path:object_id>/builder/",
                self.admin_site.admin_view(
                    self.builder_view
                ),
                name="firstApp_exam_builder",
            ),
        ]

        return custom_urls + urls

    def add_view(self, request, form_url="", extra_context=None):
        """
        Khi Admin bấm + Add ở Exams,
        chuyển thẳng sang Exam Builder.
        """

        from django.shortcuts import redirect

        return redirect(
            "admin:firstApp_exam_builder_create"
        )

    def change_view(
            self,
            request,
            object_id,
            form_url="",
            extra_context=None,
    ):
        """
        Khi Admin mở một bài thi đã tồn tại,
        chuyển thẳng sang Exam Builder.

        Ví dụ:
            /admin/firstApp/exam/7/change/

        sẽ chuyển thành:
            /admin/firstApp/exam/7/builder/
        """

        from django.shortcuts import redirect

        return redirect(
            "admin:firstApp_exam_builder",
            object_id=object_id,
        )

    def builder_view(self, request, object_id=None):
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from django.db import transaction
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime
        import json
        import random
        import re

        exam = None

        # =====================================================
        # LOAD EXAM KHI CHỈNH SỬA
        # =====================================================

        if object_id:

            exam = self.get_object(
                request,
                object_id,
            )

            if exam is None:

                messages.error(
                    request,
                    "Không tìm thấy bài thi."
                )

                return redirect(
                    "admin:firstApp_exam_changelist"
                )

        # =====================================================
        # POST → LƯU BÀI THI
        # =====================================================

        if request.method == "POST":

            try:

                # -------------------------------------------------
                # 1. LẤY THÔNG TIN CƠ BẢN
                # -------------------------------------------------

                title = request.POST.get(
                    "title",
                    ""
                ).strip()

                course_id = request.POST.get(
                    "course"
                )

                offering_id = request.POST.get(
                    "offering"
                )

                duration_minutes = request.POST.get(
                    "duration_minutes",
                    "60"
                )

                start_time = request.POST.get(
                    "start_time"
                )

                end_time = request.POST.get(
                    "end_time"
                )

                number_of_papers = request.POST.get(
                    "number_of_papers",
                    "1"
                )
                exam_type = request.POST.get(
                    "exam_type",
                    Exam.EXAM_TYPE_AT_HOME,
                ).strip()

                if exam_type not in dict(Exam.EXAM_TYPE_CHOICES):
                    raise ValueError("Hình thức thi không hợp lệ.")

                question_data_raw = request.POST.get(
                    "question_data",
                    "[]"
                )

                # -------------------------------------------------
                # 2. VALIDATE
                # -------------------------------------------------

                if not title:

                    raise ValueError(
                        "Vui lòng nhập tên bài thi."
                    )

                if not course_id:

                    raise ValueError(
                        "Vui lòng chọn môn học."
                    )

                try:

                    duration_minutes = int(
                        duration_minutes
                    )

                except ValueError:

                    raise ValueError(
                        "Thời gian làm bài không hợp lệ."
                    )

                if duration_minutes <= 0:

                    raise ValueError(
                        "Thời gian làm bài phải lớn hơn 0."
                    )

                try:

                    number_of_papers = int(
                        number_of_papers
                    )

                except ValueError:

                    raise ValueError(
                        "Số mã đề không hợp lệ."
                    )

                if number_of_papers <= 0:

                    raise ValueError(
                        "Số mã đề phải lớn hơn 0."
                    )

                parsed_start_time = parse_datetime(start_time or "")
                parsed_end_time = parse_datetime(end_time or "")
                if not parsed_start_time or not parsed_end_time:
                    raise ValueError("Vui lòng nhập thời gian bắt đầu và kết thúc hợp lệ.")
                if timezone.is_naive(parsed_start_time):
                    parsed_start_time = timezone.make_aware(
                        parsed_start_time,
                        timezone.get_current_timezone(),
                    )
                if timezone.is_naive(parsed_end_time):
                    parsed_end_time = timezone.make_aware(
                        parsed_end_time,
                        timezone.get_current_timezone(),
                    )
                if parsed_end_time <= parsed_start_time:
                    raise ValueError("Thời gian kết thúc phải sau thời gian bắt đầu.")

                # -------------------------------------------------
                # 3. PARSE QUESTION DATA
                # -------------------------------------------------

                try:

                    question_data = json.loads(
                        question_data_raw
                    )

                except json.JSONDecodeError:

                    raise ValueError(
                        "Dữ liệu câu hỏi không hợp lệ."
                    )

                if not isinstance(
                    question_data,
                    list
                ):

                    raise ValueError(
                        "Danh sách câu hỏi không hợp lệ."
                    )

                if len(question_data) == 0:

                    raise ValueError(
                        "Bài thi phải có ít nhất 1 câu hỏi."
                    )

                # -------------------------------------------------
                # 4. KIỂM TRA TỪNG CÂU
                # -------------------------------------------------

                for index, question in enumerate(
                    question_data,
                    start=1
                ):

                    question_type = question.get(
                        "type"
                    )

                    content = question.get(
                        "content",
                        ""
                    ).strip()

                    if not question_type:

                        raise ValueError(
                            f"Câu {index}: chưa chọn loại câu hỏi."
                        )

                    if not content:

                        raise ValueError(
                            f"Câu {index}: chưa nhập nội dung."
                        )

                    # -----------------------------
                    # MCQ
                    # -----------------------------

                    if question_type == "MCQ":

                        choices = question.get(
                            "choices",
                            []
                        )

                        if len(choices) != 4:

                            raise ValueError(
                                f"Câu {index}: MCQ phải có đúng 4 đáp án."
                            )

                        correct_answer = question.get(
                            "correct_answer"
                        )

                        if correct_answer not in [
                            "A",
                            "B",
                            "C",
                            "D",
                        ]:

                            raise ValueError(
                                f"Câu {index}: chưa chọn đáp án đúng."
                            )

                        for choice in choices:

                            if not choice.get(
                                "text",
                                ""
                            ).strip():

                                raise ValueError(
                                    f"Câu {index}: không được để trống đáp án."
                                )

                    # -----------------------------
                    # DRAG
                    # -----------------------------

                    elif question_type == "DRAG":

                        items = question.get(
                            "items",
                            []
                        )

                        if len(items) < 1:

                            raise ValueError(
                                f"Câu {index}: DRAG phải có ít nhất 1 item."
                            )

                        code_template = question.get("code_template", "").strip()
                        blank_numbers = re.findall(r"\[\[(\d+)\]\]", code_template)
                        expected_blanks = [str(number) for number in range(1, len(items) + 1)]
                        if sorted(blank_numbers, key=int) != expected_blanks:
                            raise ValueError(
                                f"Câu {index}: DRAG cần đúng một placeholder [[1]] đến "
                                f"[[{len(items)}]] trong mẫu code."
                            )

                        for item in items:

                            if not item.get(
                                "text",
                                ""
                            ).strip():

                                raise ValueError(
                                    f"Câu {index}: item DRAG không được để trống."
                                )

                    # -----------------------------
                    # SORT
                    # -----------------------------

                    elif question_type == "SORT":

                        items = question.get(
                            "items",
                            []
                        )

                        if len(items) < 1:

                            raise ValueError(
                                f"Câu {index}: SORT phải có ít nhất 1 item."
                            )

                        for item in items:

                            if not item.get(
                                "text",
                                ""
                            ).strip():

                                raise ValueError(
                                    f"Câu {index}: item SORT không được để trống."
                                )

                    # -----------------------------
                    # CODE
                    # -----------------------------

                    elif question_type == "CODE":

                        test_cases = question.get(
                            "test_cases",
                            []
                        )

                        if len(test_cases) < 1:

                            raise ValueError(
                                f"Câu {index}: CODE phải có ít nhất 1 Test Case."
                            )

                    else:

                        raise ValueError(
                            f"Câu {index}: loại câu hỏi không hợp lệ."
                        )

                # -------------------------------------------------
                # 5. IMPORT COURSE / OFFERING
                # -------------------------------------------------

                course = Course.objects.get(
                    pk=course_id
                )

                offering = None

                if offering_id:

                    offering = CourseOffering.objects.get(
                        pk=offering_id
                    )

                    if (
                        offering.course_id
                        != course.id
                    ):

                        raise ValueError(
                            "Lớp học phần không thuộc môn học đã chọn."
                        )

                # -------------------------------------------------
                # 6. TẠO / CẬP NHẬT EXAM
                # -------------------------------------------------

                with transaction.atomic():

                    if exam is not None and StudentExam.objects.filter(exam=exam).exists():
                        raise ValueError(
                            "Không thể chỉnh sửa bài thi sau khi sinh viên đã bắt đầu làm bài."
                        )

                    if exam is None:

                        exam = Exam()

                    exam.title = title

                    exam.course = course

                    exam.offering = offering

                    exam.exam_type = exam_type

                    exam.duration_minutes = (
                        duration_minutes
                    )

                    exam.start_time = parsed_start_time

                    exam.end_time = parsed_end_time

                    exam.number_of_papers = (
                        number_of_papers
                    )

                    exam.question_data = (
                        question_data
                    )

                    exam.is_active = True

                    # -------------------------------------------------
                    # 7. TẠO MÃ ĐỀ
                    # -------------------------------------------------

                    existing_codes = set()

                    if exam.paper_codes:

                        existing_codes = set(
                            exam.paper_codes
                        )

                    paper_codes = []

                    while len(paper_codes) < number_of_papers:

                        code = str(
                            random.randint(
                                1000,
                                9999
                            )
                        )

                        if code not in existing_codes:

                            paper_codes.append(
                                code
                            )

                            existing_codes.add(
                                code
                            )

                    exam.paper_codes = paper_codes

                    exam.save()


                # -------------------------------------------------
                # 8. THÔNG BÁO
                # -------------------------------------------------

                messages.success(
                    request,
                    (
                        f'Đã lưu bài thi "{exam.title}" '
                        f'với {len(question_data)} câu hỏi '
                        f'và {number_of_papers} mã đề.'
                    )
                )

                return redirect(
                    "admin:firstApp_exam_changelist"
                )

            except Course.DoesNotExist:

                messages.error(
                    request,
                    "Môn học không tồn tại."
                )

            except CourseOffering.DoesNotExist:

                messages.error(
                    request,
                    "Lớp học phần không tồn tại."
                )

            except ValueError as error:

                messages.error(
                    request,
                    str(error)
                )

            except Exception as error:

                messages.error(
                    request,
                    (
                        "Không thể lưu bài thi: "
                        f"{error}"
                    )
                )

        # =====================================================
        # CONTEXT CHO BUILDER
        # =====================================================

        context = dict(
            self.admin_site.each_context(request),

            title=(
                "Chỉnh sửa bài thi"
                if exam
                else "Tạo bài thi"
            ),

            exam=exam,

            courses=Course.objects.all()
                .order_by("code"),

            offerings=CourseOffering.objects.select_related(
                "course",
                "term",
            ).order_by(
                "course__code",
                "group_code",
                "session_number",
            ),
        )

        return render(
            request,
            "admin/firstApp/exam/exam_builder.html",
            context,
        )


@admin.register(ExamComputer)
class ExamComputerAdmin(admin.ModelAdmin):

    list_display = (
        "exam_session",
        "computer_number_display",
        "student",
        "status",
        "assigned_at",
        "camera_last_seen_at",
        "presence_last_seen_at",
    )

    list_filter = (
        "status",
        "exam_session",
    )

    search_fields = (
        "student__user__username",
        "student__student_id",
        "student__user__first_name",
        "student__user__last_name",
        "exam_session__exam__title",
        "exam_session__offering__group_code",
    )

    autocomplete_fields = (
        "exam_session",
        "student",
    )

    ordering = (
        "exam_session",
        "computer_number",
    )

    actions = [
        "auto_assign_students",
        "mark_absent",
    ]

    @admin.action(description="Tự động xếp sinh viên vào máy")
    def auto_assign_students(self, request, queryset):

        from django.utils import timezone

        total_assigned = 0

        for computer in queryset:

            # Lấy các sinh viên thuộc lớp học phần của ca thi
            enrollments = Enrollment.objects.filter(
                course_offering=computer.exam_session.offering,
                status="active",
            ).select_related(
                "student",
                "student__user",
            ).order_by(
                "student__student_id",
            )

            students = [
                enrollment.student
                for enrollment in enrollments
            ]

            # Kiểm tra số thứ tự máy
            index = computer.computer_number - 1

            if 0 <= index < len(students):

                computer.student = students[index]

                computer.status = "assigned"

                computer.assigned_at = timezone.now()

                computer.save(
                    update_fields=[
                        "student",
                        "status",
                        "assigned_at",
                    ]
                )

                total_assigned += 1

            else:

                # Không có sinh viên cho máy này
                computer.student = None

                computer.status = "available"

                computer.assigned_at = None

                computer.save(
                    update_fields=[
                        "student",
                        "status",
                        "assigned_at",
                    ]
                )

        self.message_user(
            request,
            f"Đã tự động xếp {total_assigned} sinh viên vào máy.",
        )
    @admin.action(description="Đánh dấu vắng và cho 0 điểm")
    def mark_absent(self, request, queryset):
        from django.utils import timezone

        absent_count = 0
        skipped_count = 0

        for computer in queryset.select_related(
            "student__user",
            "exam_session__exam",
        ):
            # Chỉ xử lý máy đã được gán sinh viên
            if not computer.student:
                skipped_count += 1
                continue

            # Nếu máy đã vắng rồi thì bỏ qua
            if computer.status == "absent":
                skipped_count += 1
                continue

            # Nếu máy đã khóa thì không tự chuyển thành vắng
            if computer.status == "locked":
                skipped_count += 1
                continue

            student_user = computer.student.user
            exam = computer.exam_session.exam
            now = timezone.now()

            # ------------------------------------------------
            # Đánh dấu máy là VẮNG
            # ------------------------------------------------
            computer.status = "absent"
            computer.note = "Sinh viên vắng thi - tự động 0 điểm."
            computer.save(
                update_fields=[
                    "status",
                    "note",
                ]
            )

            # ------------------------------------------------
            # Tạo / cập nhật StudentExam
            # ------------------------------------------------
            student_exam = StudentExam.objects.filter(
                student=student_user,
                exam=exam,
            ).order_by("-started_at").first()

            if student_exam is None:
                student_exam = StudentExam.objects.create(
                    student=student_user,
                    exam=exam,
                    exam_code=(exam.paper_codes or ["ABSENT"])[0],
                    score=0,
                    is_submitted=True,
                    finished_at=now,
                )
            else:
                # Nếu sinh viên chưa nộp bài,
                # chuyển sang trạng thái vắng và 0 điểm.
                if not student_exam.is_submitted:
                    student_exam.score = 0
                    student_exam.is_submitted = True
                    student_exam.finished_at = now
                    student_exam.exam_code = (exam.paper_codes or ["ABSENT"])[0]
                    student_exam.save(
                        update_fields=[
                            "score",
                            "is_submitted",
                            "finished_at",
                            "exam_code",
                        ]
                    )

            absent_count += 1

        message = (
            f"Đã đánh dấu {absent_count} sinh viên vắng "
            f"và ghi nhận 0 điểm."
        )

        if skipped_count:
            message += (
                f" Bỏ qua {skipped_count} máy "
                f"không phù hợp."
            )

        self.message_user(
            request,
            message,
        )
    def computer_number_display(self, obj):
        return f"PC{obj.computer_number:02d}"

    computer_number_display.short_description = "Máy"


# @admin.register(StudentExam)
# class StudentExamAdmin(admin.ModelAdmin):
#     list_display = (
#         "student_exam",
#         "question_index",
#         "question_type",
#         "answer_text",
#         "score",
#         "is_correct",
#     )
#     list_filter = ("is_submitted", "exam")
@admin.register(StudentExam)
class StudentExamAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "exam",
        "exam_code",
        "exam_computer",
       
        "score",
        "started_at",
        "finished_at",
    )
    list_filter = (

        "exam",
    )

@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ("student_exam", "question_index", "score", "is_correct")
    list_filter = ("is_correct",)


@admin.register(ProctorEvent)
class ProctorEventAdmin(admin.ModelAdmin):
    list_display = (
        "student_exam",
        "exam_computer",
        "event_type",
        "confidence",
        "duration_seconds",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("event_type", "reviewed_at", "created_at")
    readonly_fields = (
        "student_exam",
        "exam_computer",
        "event_type",
        "confidence",
        "duration_seconds",
        "evidence_image",
        "created_at",
    )


# @admin.register(Semester)
# class SemesterAdmin(admin.ModelAdmin):
#     list_display = (
#         "name",
#         "academic_year",
#         "start_date",
#         "end_date",
#         "is_active",
#     )
#
#     list_filter = (
#         "is_active",
#         "academic_year",
#     )
#
#     search_fields = (
#         "name",
#         "academic_year",
#     )
#
#     ordering = (
#         "-start_date",
#     )


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = (
        "group_code",
        "course",
        "term",
        "session_number",
        "classroom",
    )

    list_filter = (
        "term",
        "course",
        "session_number",
    )

    search_fields = (
        "group_code",
        "course__code",
        "course__name",
        "classroom",
    )

    autocomplete_fields = (
        "course",
        "term",
    )

    ordering = (
        "term",
        "course__code",
        "group_code",
    )

@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "course_offering",
        "lecturer",
        "role",
        "assigned_at",
    )

    list_filter = (
        "role",
        "course_offering__term",
    )

    search_fields = (
        "lecturer__user__username",
        "lecturer__user__first_name",
        "lecturer__user__last_name",
        "lecturer__lecturer_id",
        "course_offering__group_code",
        "course_offering__course__code",
    )

    autocomplete_fields = (
        "course_offering",
        "lecturer",
    )

    ordering = (
        "-assigned_at",
    )

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "course_offering",
        "student",
        "status",
        "enrolled_at",
    )

    list_filter = (
        "status",
        "course_offering__term",
    )

    search_fields = (
        "student__user__username",
        "student__student_id",
        "student__user__first_name",
        "student__user__last_name",
        "course_offering__group_code",
        "course_offering__course__code",
    )

    autocomplete_fields = (
        "course_offering",
        "student",
    )

    ordering = (
        "-enrolled_at",
    )

@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):

    list_display = (
        "exam",
        "offering",
        "room",
        "machine_count",
        "start_time",
        "end_time",
        "status",
        "room_map_button",
    )

    list_filter = (
        "status",
        "room",
        "offering__term",
    )

    search_fields = (
        "exam__title",
        "exam__code",
        "offering__group_code",
        "offering__course__code",
        "offering__course__name",
        "room",
    )

    autocomplete_fields = (
        "exam",
        "offering",
    )

    ordering = (
        "-start_time",
    )

    actions = [
        "create_exam_computers",
    ]

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "<path:object_id>/room-map/",
                self.admin_site.admin_view(
                    self.room_map_view
                ),
                name="firstApp_examsession_room_map",
            ),
        ]

        return custom_urls + urls
    def room_map_button(self, obj):
        return format_html(
            '<a class="button" href="{}">'
            'Xem phòng thi'
            '</a>',
            f"/admin/firstApp/examsession/{obj.pk}/room-map/",
        )

    room_map_button.short_description = "Sơ đồ phòng"
    def room_map_view(self, request, object_id):

        from django.shortcuts import get_object_or_404

        session = get_object_or_404(
            ExamSession.objects.select_related(
                "exam",
                "offering",
                "offering__course",
                "offering__term",
            ),
            pk=object_id,
        )

        computers = (
            ExamComputer.objects
            .filter(exam_session=session)
            .select_related(
                "student",
                "student__user",
            )
            .order_by("computer_number")
        )

        total_computers = computers.count()

        assigned_count = computers.filter(
            status="assigned"
        ).count()

        available_count = computers.filter(
            status="available"
        ).count()

        absent_count = computers.filter(
            status="absent"
        ).count()

        locked_count = computers.filter(
            status="locked"
        ).count()

        context = {
            **self.admin_site.each_context(request),

            "title": "Sơ đồ phòng thi",

            "session": session,

            "computers": computers,

            "total_computers": total_computers,

            "assigned_count": assigned_count,

            "available_count": available_count,

            "absent_count": absent_count,

            "locked_count": locked_count,
        }

        return TemplateResponse(
            request,
            "admin/firstApp/examsession/room_map.html",
            context,
        )

    @admin.action(description="Tạo máy thi và tự động xếp sinh viên")
    def create_exam_computers(self, request, queryset):
        from django.contrib import messages
        from django.utils import timezone

        for session in queryset:
            enrollments = (
                Enrollment.objects
                .filter(
                    course_offering=session.offering,
                    status="active",
                )
                .select_related("student", "student__user")
                .order_by("student__student_id")
            )

            students = [
                enrollment.student
                for enrollment in enrollments
            ]

            machine_count = session.machine_count

            # Không đủ máy cho số sinh viên
            if len(students) > machine_count:
                self.message_user(
                    request,
                    (
                        f"Ca thi '{session}' có {len(students)} sinh viên "
                        f"nhưng phòng chỉ có {machine_count} máy. "
                        f"Không thể tự động xếp máy."
                    ),
                    level=messages.ERROR,
                )
                continue

            for index in range(machine_count):
                computer_number = index + 1

                # Nếu còn sinh viên thì gán sinh viên
                if index < len(students):
                    student = students[index]
                    status = "assigned"
                else:
                    # Máy còn dư
                    student = None
                    status = "available"

                computer, created = ExamComputer.objects.get_or_create(
                    exam_session=session,
                    computer_number=computer_number,
                )

                computer.student = student
                computer.status = status

                if student:
                    computer.assigned_at = timezone.now()
                else:
                    computer.assigned_at = None

                computer.save()

            self.message_user(
                request,
                (
                    f"Đã tạo/cập nhật {machine_count} máy cho "
                    f"ca thi '{session}'. "
                    f"Đã xếp {len(students)} sinh viên."
                ),
                level=messages.SUCCESS,
            )
    create_exam_computers.short_description = "Tạo danh sách máy và tự động xếp sinh viên"




from django.contrib import admin
from .models import FaceProfile


@admin.register(FaceProfile)
class FaceProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_profile",
        "model_name",
        "is_active",
        "registered_at",
    )

    list_filter = ("is_active", "model_name")

    search_fields = (
        "user_profile__user__username",
        "user_profile__student_id",
        "user_profile__lecturer_id",
    )

    readonly_fields = (
        "registered_at",
        "updated_at",
        "consented_at",
    )
