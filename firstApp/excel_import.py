from datetime import datetime

from django.contrib.auth.models import User
from django.db import transaction
from django.utils.dateparse import parse_date

from openpyxl import load_workbook

from .models import (
    UserProfile,
    Enrollment,
    TeachingAssignment,
)


# ============================================================
# CHUẨN HÓA HEADER EXCEL
# ============================================================

def normalize_header(value):
    """
    Chuẩn hóa tên cột Excel.

    Ví dụ:
        "MSSV"        -> "mssv"
        "Họ Tên"      -> "hoten"
        "HoTen"       -> "hoten"
        " Số Điện Thoại " -> "sodienthoai"
    """

    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
    )


# ============================================================
# CHUYỂN NGÀY SINH
# ============================================================

def parse_excel_date(value):
    """
    Chuyển ngày Excel về datetime.date.
    """

    if value is None or value == "":
        return None

    # Excel trả về datetime
    if isinstance(value, datetime):
        return value.date()

    # Excel có thể trả về date
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value

    value = str(value).strip()

    date_formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return parse_date(value)


# ============================================================
# TẠO USERNAME
# ============================================================

def create_username(user_id):
    """
    Username chính là MSSV hoặc mã giảng viên.
    """

    return str(user_id).strip()


# ============================================================
# KIỂM TRA FILE EXCEL
# ============================================================

def validate_excel_file(file):
    """
    Hệ thống chỉ chấp nhận file .xlsx.
    """

    if not file:
        raise ValueError("Chưa chọn file Excel.")

    file_name = getattr(file, "name", "")

    if not file_name.lower().endswith(".xlsx"):
        raise ValueError(
            "Chỉ chấp nhận file Excel có định dạng .xlsx."
        )


# ============================================================
# ĐỌC WORKSHEET
# ============================================================

def load_excel_rows(file):
    """
    Đọc worksheet đầu tiên của file Excel.
    """

    validate_excel_file(file)

    try:
        workbook = load_workbook(
            file,
            data_only=True
        )
    except Exception as exc:
        raise ValueError(
            f"Không thể đọc file Excel: {exc}"
        )

    worksheet = workbook.active

    rows = list(
        worksheet.iter_rows(
            values_only=True
        )
    )

    if not rows:
        raise ValueError(
            "File Excel không có dữ liệu."
        )

    return rows


# ============================================================
# TẠO HEADER MAP
# ============================================================

def build_header_map(rows):
    """
    Tạo dictionary:

        {
            "mssv": 0,
            "hoten": 1,
            "email": 2,
            ...
        }
    """

    headers = [
        normalize_header(value)
        for value in rows[0]
    ]

    header_map = {
        header: index
        for index, header in enumerate(headers)
        if header
    }

    return header_map


# ============================================================
# KIỂM TRA HEADER BẮT BUỘC
# ============================================================

def validate_required_columns(
    header_map,
    required_columns
):
    missing_columns = [
        column
        for column in required_columns
        if column not in header_map
    ]

    if missing_columns:
        raise ValueError(
            "Excel thiếu các cột: "
            + ", ".join(missing_columns)
        )


# ============================================================
# IMPORT SINH VIÊN
# ============================================================

@transaction.atomic
def import_students_from_excel(
    file,
    course_offering
):
    """
    Import danh sách sinh viên cho MỘT lớp học phần.

    Excel bắt buộc:

        MSSV
        HoTen
        Email
        Khoa
        Nganh
        Lop
        NamHoc
        NgaySinh
        SoDienThoai
        DiaChi

    Sau khi import:

        Excel
          ↓
        User
          username = MSSV
          password = MSSV
          ↓
        UserProfile
          role = student
          ↓
        Enrollment
          ↓
        CourseOffering
    """

    if course_offering is None:
        raise ValueError(
            "Chưa chọn lớp học phần."
        )

    rows = load_excel_rows(file)

    header_map = build_header_map(rows)

    required_columns = [
        "mssv",
        "hoten",
        "email",
        "khoa",
        "nganh",
        "lop",
        "namhoc",
        "ngaysinh",
        "sodienthoai",
        "diachi",
    ]

    validate_required_columns(
        header_map,
        required_columns
    )

    created_count = 0
    updated_count = 0
    enrolled_count = 0
    already_enrolled_count = 0
    errors = []

    # ========================================================
    # XỬ LÝ TỪNG DÒNG
    # ========================================================

    for row_number, row in enumerate(
        rows[1:],
        start=2
    ):

        try:

            def get_value(column):
                index = header_map[column]

                if index >= len(row):
                    return ""

                value = row[index]

                if value is None:
                    return ""

                return str(value).strip()

            # ------------------------------------------------
            # LẤY DỮ LIỆU
            # ------------------------------------------------

            student_id = get_value("mssv")
            full_name = get_value("hoten")
            email = get_value("email")
            faculty = get_value("khoa")
            major = get_value("nganh")
            class_name = get_value("lop")
            study_year = get_value("namhoc")
            birthday = get_value("ngaysinh")
            phone = get_value("sodienthoai")
            address = get_value("diachi")

            # ------------------------------------------------
            # KIỂM TRA
            # ------------------------------------------------

            if not student_id:
                raise ValueError(
                    "Thiếu MSSV."
                )

            if not full_name:
                raise ValueError(
                    "Thiếu họ tên."
                )

            # ------------------------------------------------
            # NGÀY SINH
            # ------------------------------------------------

            birthday_value = parse_excel_date(
                birthday
            )

            # =================================================
            # USER
            # =================================================

            username = create_username(
                student_id
            )

            user, user_created = (
                User.objects.get_or_create(
                    username=username
                )
            )

            user.first_name = full_name
            user.email = email

            # =================================================
            # PASSWORD BAN ĐẦU = MSSV
            # =================================================

            if user_created:
                user.set_password(
                    student_id
                )

            user.save()

            # =================================================
            # USER PROFILE
            # =================================================

            profile, profile_created = (
                UserProfile.objects.get_or_create(
                    user=user
                )
            )
            if not profile_created and profile.role not in (
                    "student",
                    "admin",
            ):
                raise ValueError(
                    f"Tài khoản {username} đã tồn tại "
                    f"với vai trò {profile.role}, "
                    f"không thể import thành sinh viên."
                )

            profile.role = "student"
            profile.student_id = student_id

            # Nếu tài khoản trước đây là giảng viên
            # thì xóa mã giảng viên.
            profile.lecturer_id = None

            profile.faculty = faculty
            profile.major = major
            profile.class_name = class_name
            profile.study_year = study_year
            profile.birthday = birthday_value
            profile.phone = phone
            profile.address = address

            profile.save()

            # =================================================
            # ENROLLMENT
            # =================================================

            enrollment, enrollment_created = (
                Enrollment.objects.get_or_create(
                    course_offering=course_offering,
                    student=profile,
                    defaults={
                        "status": "active"
                    }
                )
            )

            if enrollment_created:
                enrolled_count += 1
            else:
                already_enrolled_count += 1

                # Nếu đã tồn tại nhưng bị inactive
                # thì kích hoạt lại.
                if enrollment.status != "active":
                    enrollment.status = "active"
                    enrollment.save(
                        update_fields=["status"]
                    )

            # =================================================
            # THỐNG KÊ USER PROFILE
            # =================================================

            if profile_created:
                created_count += 1
            else:
                updated_count += 1

        except Exception as exc:

            errors.append(
                f"Dòng {row_number}: {str(exc)}"
            )

    return {
        "created": created_count,
        "updated": updated_count,
        "enrolled": enrolled_count,
        "already_enrolled": already_enrolled_count,
        "errors": errors,
    }


# ============================================================
# IMPORT GIẢNG VIÊN
# ============================================================
# ============================================================
# IMPORT GIẢNG VIÊN
# ============================================================

@transaction.atomic
def import_lecturers_from_excel(
    file,
    course_offering
):
    """
    Import danh sách giảng viên cho MỘT lớp học phần.

    Excel bắt buộc:

        MaGV
        HoTen
        Email
        Khoa
        Nganh
        SoDienThoai
        DiaChi

    Sau khi import:

        Excel
          ↓
        User
          username = MaGV
          password = MaGV
          ↓
        UserProfile
          role = lecturer
          ↓
        TeachingAssignment
          ↓
        CourseOffering
    """

    if course_offering is None:
        raise ValueError(
            "Chưa chọn lớp học phần."
        )

    # ========================================================
    # ĐỌC FILE EXCEL
    # ========================================================

    rows = load_excel_rows(file)

    header_map = build_header_map(rows)

    required_columns = [
        "magv",
        "hoten",
        "email",
        "khoa",
        "nganh",
        "sodienthoai",
        "diachi",
    ]

    validate_required_columns(
        header_map,
        required_columns
    )

    # ========================================================
    # THỐNG KÊ
    # ========================================================

    created_count = 0
    updated_count = 0
    assigned_count = 0
    already_assigned_count = 0
    errors = []

    # ========================================================
    # XỬ LÝ TỪNG DÒNG EXCEL
    # ========================================================

    for row_number, row in enumerate(
        rows[1:],
        start=2
    ):

        try:

            # ==================================================
            # HÀM LẤY GIÁ TRỊ TỪ EXCEL
            # ==================================================

            def get_value(column):
                index = header_map[column]

                if index >= len(row):
                    return ""

                value = row[index]

                if value is None:
                    return ""

                return str(value).strip()

            # ==================================================
            # LẤY DỮ LIỆU
            # ==================================================

            lecturer_id = get_value("magv")
            full_name = get_value("hoten")
            email = get_value("email")
            faculty = get_value("khoa")
            major = get_value("nganh")
            phone = get_value("sodienthoai")
            address = get_value("diachi")

            # ==================================================
            # KIỂM TRA DỮ LIỆU BẮT BUỘC
            # ==================================================

            if not lecturer_id:
                raise ValueError(
                    "Thiếu mã giảng viên."
                )

            if not full_name:
                raise ValueError(
                    "Thiếu họ tên."
                )

            # ==================================================
            # TẠO USERNAME
            # ==================================================

            username = create_username(
                lecturer_id
            )

            # ==================================================
            # USER
            # ==================================================

            user, user_created = (
                User.objects.get_or_create(
                    username=username
                )
            )

            # --------------------------------------------------
            # Cập nhật thông tin User
            # --------------------------------------------------

            user.first_name = full_name
            user.email = email

            # --------------------------------------------------
            # Tài khoản mới:
            # password ban đầu = mã giảng viên
            # --------------------------------------------------

            if user_created:
                user.set_password(
                    lecturer_id
                )

            user.save()

            # ==================================================
            # USER PROFILE
            # ==================================================

            profile, profile_created = (
                UserProfile.objects.get_or_create(
                    user=user
                )
            )

            # ==================================================
            # KIỂM TRA ROLE
            # ==================================================

            """
            Trường hợp 1:
                User mới vừa được tạo.

            Có thể signal của project đã tự động tạo
            UserProfile với role = student.

            Đây KHÔNG phải sinh viên thật sự.

            Vì vậy cho phép chuyển profile đó thành lecturer.

            --------------------------------------------------

            Trường hợp 2:
                User đã tồn tại trước đó.

            Nếu profile đang là student thì KHÔNG cho phép
            importer tự động biến sinh viên thành giảng viên.

            Chỉ cho phép:

                lecturer
                admin
            """

            if not user_created and profile.role not in (
                "lecturer",
                "admin",
            ):
                raise ValueError(
                    f"Tài khoản {username} đã tồn tại "
                    f"với vai trò {profile.role}, "
                    f"không thể import thành giảng viên."
                )

            # ==================================================
            # CẤU HÌNH PROFILE GIẢNG VIÊN
            # ==================================================

            profile.role = "lecturer"

            profile.lecturer_id = lecturer_id

            # Không giữ MSSV
            profile.student_id = None

            profile.faculty = faculty
            profile.major = major
            profile.phone = phone
            profile.address = address

            profile.save()

            # ==================================================
            # PHÂN CÔNG GIẢNG VIÊN VÀO LỚP HỌC PHẦN
            # ==================================================

            assignment, assignment_created = (
                TeachingAssignment.objects.get_or_create(
                    course_offering=course_offering,
                    lecturer=profile,
                )
            )

            if assignment_created:
                assigned_count += 1
            else:
                already_assigned_count += 1

            # ==================================================
            # THỐNG KÊ USER PROFILE
            # ==================================================

            if profile_created:
                created_count += 1
            else:
                updated_count += 1

        # ======================================================
        # LỖI TỪNG DÒNG
        # ======================================================

        except Exception as exc:

            errors.append(
                f"Dòng {row_number}: {str(exc)}"
            )

    # ========================================================
    # KẾT QUẢ
    # ========================================================

    return {
        "created": created_count,
        "updated": updated_count,
        "assigned": assigned_count,
        "already_assigned": already_assigned_count,
        "errors": errors,
    }